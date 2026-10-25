#define _GNU_SOURCE
#include "gamesched.h"

#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

/* Joins @abs (an absolute path inside the target) under @sysroot. "/" is the
   real root, so the sysroot's trailing slash is dropped before joining. */
static int under_sysroot(char *out, size_t size, const char *sysroot, const char *abs) {
    size_t ls = strlen(sysroot), la = strlen(abs);
    size_t trim = (ls && sysroot[ls - 1] == '/') ? ls - 1 : ls;
    if (trim + la + 1 > size) return -1;
    memcpy(out, sysroot, trim);
    memcpy(out + trim, abs, la + 1);
    return 0;
}

/* Appends "/name" to @dir. @name is a single path component. */
static int child_path(char *out, size_t size, const char *dir, const char *name) {
    size_t ld = strlen(dir), ln = strlen(name);
    if (ld + 1 + ln + 1 > size) return -1;
    memcpy(out, dir, ld);
    out[ld] = '/';
    memcpy(out + ld + 1, name, ln + 1);
    return 0;
}

/* Writes @text into an existing kernel knob. Returns 0 or a positive errno. */
static int write_knob(const char *path, const char *text) {
    int fd = open(path, O_WRONLY | O_CLOEXEC);
    if (fd < 0) return errno;
    size_t n = strlen(text);
    ssize_t w = write(fd, text, n);
    int err = 0;
    if (w < 0) err = errno;
    else if ((size_t)w != n) err = EIO;
    close(fd);
    return err;
}

static const char *errno_word(int err) {
    switch (err) {
    case ENOENT: return "knob missing";
    case EACCES:
    case EPERM: return "permission denied";
    case EBUSY: return "busy";
    case EINVAL: return "rejected by kernel";
    case EOPNOTSUPP: return "unsupported";
    default: return "failed";
    }
}

/* Appends @a and @b to @report, truncating silently at the buffer end. */
static void say(char *report, size_t size, const char *a, const char *b) {
    if (!size) return;
    size_t used = strlen(report);
    if (used >= size - 1) return;
    size_t room = size - 1 - used;
    size_t la = strlen(a);
    if (la > room) la = room;
    memcpy(report + used, a, la);
    used += la;
    room = size - 1 - used;
    size_t lb = strlen(b);
    if (lb > room) lb = room;
    memcpy(report + used, b, lb);
    report[used + lb] = '\0';
}

/* Records one knob result: "<name>: applied" or "<name>: skipped (<why>)". */
static void note_knob(char *report, size_t size, const char *name, int err) {
    say(report, size, name, err ? ": skipped (" : ": applied");
    if (err) {
        say(report, size, errno_word(err), ")");
    }
    say(report, size, "; ", "");
}

static int delegated(const char *sysroot, const char *root) {
    char real[OMINX_SCHED_PATH_MAX];
    struct stat st;
    if (under_sysroot(real, sizeof real, sysroot, root)) return 0;
    if (stat(real, &st) || !S_ISDIR(st.st_mode)) return 0;
    return access(real, W_OK) == 0;
}

void ominx_sched_plan_game(const struct ominx_game *game, const char *sysroot, const char *root,
                           struct ominx_sched_plan *plan) {
    char reason[128] = "";
    memset(plan, 0, sizeof *plan);
    snprintf(plan->root, sizeof plan->root, "%s", root);
    if (!game) {
        snprintf(plan->why, sizeof plan->why, "%s", "no profile");
        return;
    }
    if (ominx_game_gate(game, sysroot, reason, sizeof reason)) {
        snprintf(plan->why, sizeof plan->why, "launch refused (%s)", reason);
        return;
    }
    /* Only publisher-enabled titles are boosted. Titles with no anti-cheat are
       left at the default priorities until a reviewed rule covers them. */
    if (game->status != OMINX_AC_VENDOR_OPT_IN) {
        snprintf(plan->why, sizeof plan->why, "%s", "not a publisher-enabled title");
        return;
    }
    /* One group per title: "<root>/game-<appid>". The app id is numeric or a
       short token from the reviewed profile, so it cannot escape the root. */
    char name[sizeof game->appid + 8];
    snprintf(name, sizeof name, "game-%s", game->appid);
    if (strchr(game->appid, '/') || child_path(plan->group, sizeof plan->group, root, name)) {
        snprintf(plan->why, sizeof plan->why, "%s", "bad app id for a group name");
        return;
    }
    plan->boost = 1;
}

int ominx_sched_boost(const char *sysroot, struct ominx_sched_plan *plan, pid_t pid,
                      char *report, size_t report_size) {
    char real_root[OMINX_SCHED_PATH_MAX], real_group[OMINX_SCHED_PATH_MAX];
    char path[OMINX_SCHED_PATH_MAX + 32], text[32];
    int applied = 0;

    if (report_size) report[0] = '\0';
    if (!plan->boost) {
        say(report, report_size, "scheduling: not boosted (", plan->why);
        say(report, report_size, ")", "");
        return 0;
    }
    if (under_sysroot(real_root, sizeof real_root, sysroot, plan->root) ||
        under_sysroot(real_group, sizeof real_group, sysroot, plan->group)) {
        say(report, report_size, "scheduling: not boosted (path too long)", "");
        return 0;
    }
    if (mkdir(real_group, 0755) && errno != EEXIST) {
        say(report, report_size, "scheduling: not boosted (group: ", strerror(errno));
        say(report, report_size, ")", "");
        return 0;
    }

    snprintf(text, sizeof text, "%d\n", OMINX_SCHED_CPU_WEIGHT);
    if (child_path(path, sizeof path, real_group, "cpu.weight") == 0) {
        int err = write_knob(path, text);
        note_knob(report, report_size, "cpu", err);
        applied += err == 0;
    }
    snprintf(text, sizeof text, "%d\n", OMINX_SCHED_IO_WEIGHT);
    if (child_path(path, sizeof path, real_group, "io.weight") == 0) {
        int err = write_knob(path, text);
        note_knob(report, report_size, "io", err);
        applied += err == 0;
    }

    snprintf(text, sizeof text, "%d\n", (int)pid);
    if (child_path(path, sizeof path, real_group, "cgroup.procs") == 0) {
        int err = write_knob(path, text);
        if (err) {
            /* Without the process in the group there is nothing to boost. */
            rmdir(real_group);
            say(report, report_size, "scheduling: not boosted (move: ", errno_word(err));
            say(report, report_size, ")", "");
            return 0;
        }
    }

    /* GPU: amdgpu only. Other drivers and missing knobs are skipped, not failed. */
    if (under_sysroot(path, sizeof path, sysroot, OMINX_SCHED_GPU_KNOB) == 0) {
        int err = write_knob(path, "high\n");
        note_knob(report, report_size, "gpu", err);
        if (!err) {
            plan->gpu_raised = 1;
            applied++;
        }
    }
    return applied;
}

void ominx_sched_release(const char *sysroot, const struct ominx_sched_plan *plan, pid_t pid) {
    char real_root[OMINX_SCHED_PATH_MAX], real_group[OMINX_SCHED_PATH_MAX];
    char path[OMINX_SCHED_PATH_MAX + 32], text[32];

    if (!plan->boost) return;
    if (under_sysroot(real_root, sizeof real_root, sysroot, plan->root) ||
        under_sysroot(real_group, sizeof real_group, sysroot, plan->group))
        return;

    snprintf(text, sizeof text, "%d\n", (int)pid);
    if (child_path(path, sizeof path, real_root, "cgroup.procs") == 0)
        (void)write_knob(path, text);
    /* Fails harmlessly while another process is still in the group. */
    rmdir(real_group);

    if (plan->gpu_raised && under_sysroot(path, sizeof path, sysroot, OMINX_SCHED_GPU_KNOB) == 0)
        (void)write_knob(path, "auto\n");
}

void ominx_sched_status(const struct ominx_game *game, const char *sysroot, const char *root,
                        char *out, size_t out_size) {
    struct ominx_sched_plan plan;
    if (!out_size) return;
    out[0] = '\0';
    ominx_sched_plan_game(game, sysroot, root, &plan);
    say(out, out_size, "Compatibility: ", game ? ominx_game_status_name(game->status) : "unknown");
    if (plan.boost) {
        say(out, out_size, ", launch allowed", "");
    } else {
        say(out, out_size, ", ", plan.why);
    }
    if (!plan.boost) {
        say(out, out_size, "; scheduling: default priorities", "");
    } else if (delegated(sysroot, root)) {
        say(out, out_size, "; scheduling: game boost ready (cpu, io, gpu where supported)", "");
    } else {
        say(out, out_size, "; scheduling: default priorities (group not delegated)", "");
    }
}

int ominx_sched_prepare(const char *sysroot, const char *root, unsigned uid,
                        char *report, size_t report_size) {
    char real_root[OMINX_SCHED_PATH_MAX], parent[OMINX_SCHED_PATH_MAX], path[OMINX_SCHED_PATH_MAX + 32];
    char tmp[OMINX_SCHED_PATH_MAX];
    size_t lr = strlen(root);
    int err;

    if (report_size) report[0] = '\0';
    if (under_sysroot(real_root, sizeof real_root, sysroot, root)) {
        say(report, report_size, "prepare: root path too long", "");
        return -1;
    }
    /* The parent of @root is the cgroup v2 mount, which must enable the controllers. */
    if (lr == 0 || root[lr - 1] == '/') {
        say(report, report_size, "prepare: bad root", "");
        return -1;
    }
    snprintf(tmp, sizeof tmp, "%s", root);
    char *slash = strrchr(tmp, '/');
    if (!slash || slash == tmp) {
        say(report, report_size, "prepare: root must sit below the cgroup mount", "");
        return -1;
    }
    *slash = '\0';
    if (under_sysroot(parent, sizeof parent, sysroot, tmp)) {
        say(report, report_size, "prepare: parent path too long", "");
        return -1;
    }
    if (child_path(path, sizeof path, parent, "cgroup.subtree_control") == 0) {
        err = write_knob(path, "+cpu +io\n");
        if (err) {
            say(report, report_size, "prepare: cannot enable cpu/io on the parent (", errno_word(err));
            say(report, report_size, ")", "");
            return -1;
        }
    }

    if (mkdir(real_root, 0755) && errno != EEXIST) {
        say(report, report_size, "prepare: cannot create group (", strerror(errno));
        say(report, report_size, ")", "");
        return -1;
    }
    if (child_path(path, sizeof path, real_root, "cgroup.subtree_control") == 0) {
        err = write_knob(path, "+cpu +io\n");
        if (err) {
            say(report, report_size, "prepare: cannot delegate cpu/io to children (", errno_word(err));
            say(report, report_size, ")", "");
            return -1;
        }
    }

    /* Hand the group's control files to the session user so the daemon can
       create per-game children. Failure here leaves scheduling disabled. */
    if (child_path(path, sizeof path, real_root, "cgroup.procs") == 0 &&
        chown(path, (uid_t)uid, (gid_t)-1) != 0) {
        say(report, report_size, "prepare: chown of cgroup.procs failed", "");
        return -1;
    }
    if (child_path(path, sizeof path, real_root, "cgroup.subtree_control") == 0 &&
        chown(path, (uid_t)uid, (gid_t)-1) != 0) {
        say(report, report_size, "prepare: chown of subtree_control failed", "");
        return -1;
    }
    if (chown(real_root, (uid_t)uid, (gid_t)-1) != 0) {
        say(report, report_size, "prepare: chown of group failed", "");
        return -1;
    }
    say(report, report_size, "prepare: scheduling group ready", "");
    return 0;
}
