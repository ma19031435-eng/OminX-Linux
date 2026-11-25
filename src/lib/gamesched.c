#define _GNU_SOURCE
#include "gamesched.h"

#include <dirent.h>
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
    /* O_TRUNC matches `echo value > knob`; kernel attributes ignore it. */
    int fd = open(path, O_WRONLY | O_TRUNC | O_CLOEXEC);
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
    if (err) say(report, size, errno_word(err), ")");
    say(report, size, "; ", "");
}

static int is_dir(const char *sysroot, const char *abs) {
    char real[OMINX_SCHED_PATH_MAX];
    struct stat st;
    if (under_sysroot(real, sizeof real, sysroot, abs)) return 0;
    return stat(real, &st) == 0 && S_ISDIR(st.st_mode);
}

/* True when the user's group exists and the session user can create children in it. */
static int delegated(const char *sysroot, const char *user_root) {
    char real[OMINX_SCHED_PATH_MAX];
    if (!is_dir(sysroot, user_root)) return 0;
    if (under_sysroot(real, sizeof real, sysroot, user_root)) return 0;
    return access(real, W_OK) == 0;
}

int ominx_sched_user_root(const char *root, unsigned uid, char *out, size_t size) {
    char name[24];
    snprintf(name, sizeof name, "user-%u", uid);
    return child_path(out, size, root, name);
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
    if (!root || !*root) {
        snprintf(plan->why, sizeof plan->why, "%s", "no delegated group");
        return;
    }
    if (ominx_game_gate(game, sysroot, reason, sizeof reason)) {
        snprintf(plan->why, sizeof plan->why, "launch refused (%s)", reason);
        return;
    }
    /* The gate has passed, so the title has no anti-cheat, or its publisher enabled
       it. Either way it may be boosted. */
    if (game->anticheat != OMINX_AC_NONE && game->status != OMINX_AC_VENDOR_OPT_IN) {
        snprintf(plan->why, sizeof plan->why, "%s", "publisher has not enabled this title");
        return;
    }
    /* One group per title: "<user root>/game-<appid>". The profile loader validates
       the app id; the slash check guards the group name regardless. */
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
    char real_group[OMINX_SCHED_PATH_MAX];
    char path[OMINX_SCHED_PATH_MAX + 32], text[32];
    int applied = 0;

    if (report_size) report[0] = '\0';
    if (!plan->boost) {
        say(report, report_size, "scheduling: not boosted (", plan->why);
        say(report, report_size, ")", "");
        return 0;
    }
    if (under_sysroot(real_group, sizeof real_group, sysroot, plan->group)) {
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
    char real_group[OMINX_SCHED_PATH_MAX], service[OMINX_SCHED_PATH_MAX], real_service[OMINX_SCHED_PATH_MAX];
    char path[OMINX_SCHED_PATH_MAX + 32], text[32];

    if (!plan->boost) return;
    if (under_sysroot(real_group, sizeof real_group, sysroot, plan->group)) return;
    if (child_path(service, sizeof service, plan->root, "service") ||
        under_sysroot(real_service, sizeof real_service, sysroot, service))
        return;

    snprintf(text, sizeof text, "%d\n", (int)pid);
    if (child_path(path, sizeof path, real_service, "cgroup.procs") == 0)
        (void)write_knob(path, text);
    /* Fails harmlessly while another process is still in the group. */
    rmdir(real_group);

    if (plan->gpu_raised && under_sysroot(path, sizeof path, sysroot, OMINX_SCHED_GPU_KNOB) == 0)
        (void)write_knob(path, "auto\n");
}

enum ominx_sched_state ominx_sched_state_of(const struct ominx_game *game, const char *sysroot,
                                            const char *root, char *detail, size_t detail_size) {
    struct ominx_sched_plan plan;
    if (detail_size) detail[0] = '\0';
    ominx_sched_plan_game(game, sysroot, root, &plan);
    if (!plan.boost) {
        say(detail, detail_size, plan.why, "");
        return OMINX_SCHED_NOT_ELIGIBLE;
    }
    if (!delegated(sysroot, root)) {
        say(detail, detail_size, "user group not delegated", "");
        return OMINX_SCHED_NOT_DELEGATED;
    }
    say(detail, detail_size, "cpu, io and gpu boost ready", "");
    return OMINX_SCHED_READY;
}

const char *ominx_sched_state_name(enum ominx_sched_state state) {
    switch (state) {
    case OMINX_SCHED_READY: return "ready";
    case OMINX_SCHED_NOT_ELIGIBLE: return "not-eligible";
    case OMINX_SCHED_NOT_DELEGATED: return "not-delegated";
    }
    return "unknown";
}

void ominx_sched_status(const struct ominx_game *game, const char *sysroot, const char *root,
                        char *out, size_t out_size) {
    char detail[160];
    if (!out_size) return;
    out[0] = '\0';
    say(out, out_size, "Compatibility: ", game ? ominx_game_status_name(game->status) : "unknown");
    enum ominx_sched_state state = ominx_sched_state_of(game, sysroot, root, detail, sizeof detail);
    if (state == OMINX_SCHED_NOT_ELIGIBLE) {
        say(out, out_size, ", ", detail);
        say(out, out_size, "; scheduling: default priorities", "");
    } else {
        say(out, out_size, ", launch allowed", "");
        if (state == OMINX_SCHED_READY) {
            say(out, out_size, "; scheduling: game boost ready (cpu, io, gpu where supported)", "");
        } else {
            say(out, out_size, "; scheduling: default priorities (group not delegated)", "");
        }
    }
}

/* Each helper appends "<what>: <reason>" to @report on failure and returns -1. */
static int ensure_group(const char *sysroot, const char *abs, const char *what,
                        char *report, size_t report_size) {
    char real[OMINX_SCHED_PATH_MAX];
    if (under_sysroot(real, sizeof real, sysroot, abs)) {
        say(report, report_size, what, ": path too long");
        return -1;
    }
    if (mkdir(real, 0755) && errno != EEXIST) {
        say(report, report_size, what, ": ");
        say(report, report_size, strerror(errno), "");
        return -1;
    }
    return 0;
}

static int enable_controllers(const char *sysroot, const char *abs, const char *what,
                              char *report, size_t report_size) {
    char real[OMINX_SCHED_PATH_MAX], path[OMINX_SCHED_PATH_MAX + 32];
    if (under_sysroot(real, sizeof real, sysroot, abs) ||
        child_path(path, sizeof path, real, "cgroup.subtree_control")) {
        say(report, report_size, what, ": path too long");
        return -1;
    }
    int err = write_knob(path, "+cpu +io\n");
    if (err) {
        say(report, report_size, what, ": cannot enable cpu/io (");
        say(report, report_size, errno_word(err), ")");
        return -1;
    }
    return 0;
}

static int chown_group(const char *sysroot, const char *abs, unsigned uid, const char *what,
                       char *report, size_t report_size) {
    char real[OMINX_SCHED_PATH_MAX], path[OMINX_SCHED_PATH_MAX + 32];
    static const char *const files[] = {"cgroup.procs", "cgroup.subtree_control"};
    if (under_sysroot(real, sizeof real, sysroot, abs)) {
        say(report, report_size, what, ": path too long");
        return -1;
    }
    if (chown(real, (uid_t)uid, (gid_t)-1)) {
        say(report, report_size, what, ": chown failed");
        return -1;
    }
    /* The files the user writes must belong to the user as well. */
    for (size_t i = 0; i < sizeof files / sizeof files[0]; i++) {
        if (child_path(path, sizeof path, real, files[i]) || chown(path, (uid_t)uid, (gid_t)-1)) {
            say(report, report_size, what, ": chown failed for ");
            say(report, report_size, files[i], "");
            return -1;
        }
    }
    return 0;
}

/* io.weight is only honoured by the BFQ elevator. Switch every disk that offers
   BFQ to it. Returns the number of disks switched; never fails the boot. */
static int select_bfq(const char *sysroot, char *report, size_t report_size) {
    char block[OMINX_SCHED_PATH_MAX];
    if (under_sysroot(block, sizeof block, sysroot, "/sys/block")) return 0;
    DIR *dir = opendir(block);
    if (!dir) return 0;
    int switched = 0;
    struct dirent *entry;
    while ((entry = readdir(dir))) {
        if (entry->d_name[0] == '.') continue;
        char scheduler[OMINX_SCHED_PATH_MAX + 64], text[160] = "";
        if (child_path(scheduler, sizeof scheduler, block, entry->d_name) ||
            strlen(scheduler) + 32 > sizeof scheduler)
            continue;
        strcat(scheduler, "/queue/scheduler");
        FILE *f = fopen(scheduler, "r");
        if (!f) continue;
        if (!fgets(text, sizeof text, f)) text[0] = '\0';
        fclose(f);
        if (!strstr(text, "bfq")) continue;
        if (write_knob(scheduler, "bfq\n") == 0) switched++;
    }
    closedir(dir);
    say(report, report_size, switched ? "io: bfq selected" : "io: no disk offers bfq; io.weight inactive", "");
    say(report, report_size, "", "; ");
    return switched;
}

int ominx_sched_prepare(const char *sysroot, const char *root, char *report, size_t report_size) {
    char parent[OMINX_SCHED_PATH_MAX];
    if (report_size) report[0] = '\0';
    size_t lr = strlen(root);
    if (lr == 0 || root[lr - 1] == '/' || lr >= sizeof parent) {
        say(report, report_size, "prepare: bad root", "");
        return -1;
    }
    snprintf(parent, sizeof parent, "%s", root);
    char *slash = strrchr(parent, '/');
    if (!slash || slash == parent) {
        say(report, report_size, "prepare: root must sit below the cgroup mount", "");
        return -1;
    }
    *slash = '\0';
    /* The parent is the cgroup v2 mount. Enabling its controllers lets the ominx
       root delegate cpu and io to its children. */
    if (enable_controllers(sysroot, parent, "prepare: parent", report, report_size)) return -1;
    if (ensure_group(sysroot, root, "prepare: root", report, report_size)) return -1;
    if (enable_controllers(sysroot, root, "prepare: root", report, report_size)) return -1;
    say(report, report_size, "prepare: scheduling root ready; ", "");
    (void)select_bfq(sysroot, report, report_size);
    return 0;
}

int ominx_sched_enter(const char *sysroot, const char *root, unsigned uid, pid_t pid,
                      char *report, size_t report_size) {
    char user[OMINX_SCHED_PATH_MAX], service[OMINX_SCHED_PATH_MAX], real_service[OMINX_SCHED_PATH_MAX];
    char path[OMINX_SCHED_PATH_MAX + 32], text[32];
    if (report_size) report[0] = '\0';

    /* Idempotent, so the seat does not depend on the boot service having run first. */
    if (ominx_sched_prepare(sysroot, root, report, report_size)) return -1;
    if (ominx_sched_user_root(root, uid, user, sizeof user)) {
        say(report, report_size, "enter: user path too long", "");
        return -1;
    }
    if (ensure_group(sysroot, user, "enter: user group", report, report_size)) return -1;
    /* Enable the controllers while the user group has no processes in it. The daemon
       goes into service/, a child, so the group never holds a process of its own. */
    if (enable_controllers(sysroot, user, "enter: user group", report, report_size)) return -1;
    if (child_path(service, sizeof service, user, "service") ||
        under_sysroot(real_service, sizeof real_service, sysroot, service)) {
        say(report, report_size, "enter: service path too long", "");
        return -1;
    }
    if (ensure_group(sysroot, service, "enter: service group", report, report_size)) return -1;
    if (chown_group(sysroot, user, uid, "enter: user group", report, report_size)) return -1;
    if (chown_group(sysroot, service, uid, "enter: service group", report, report_size)) return -1;

    snprintf(text, sizeof text, "%d\n", (int)pid);
    if (child_path(path, sizeof path, real_service, "cgroup.procs")) {
        say(report, report_size, "enter: path too long", "");
        return -1;
    }
    int err = write_knob(path, text);
    if (err) {
        say(report, report_size, "enter: move daemon: ", errno_word(err));
        return -1;
    }
    say(report, report_size, "enter: session group ready", "");
    return 0;
}
