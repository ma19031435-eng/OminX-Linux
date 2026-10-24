/* OminX game profiles: strict parsing, launch gate and EAC Linux v2 host checks.
 * Pure C on purpose: the same code runs in the console, the per-user daemon and
 * host tests. It reads only profile files and kernel/firmware state. */
#define _GNU_SOURCE
#include "gamedb.h"

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static void set_error(char *error, size_t size, const char *message) {
    if (error && size) snprintf(error, size, "%s", message);
}

static int copy_field(char *out, size_t size, const char *value) {
    size_t length = strlen(value);
    if (!length || length >= size) return -1;
    memcpy(out, value, length + 1);
    return 0;
}

static int valid_id(const char *id) {
    size_t length = strlen(id);
    if (!length || length > OMINX_GAME_ID_MAX) return 0;
    for (size_t i = 0; i < length; i++) {
        char c = id[i];
        if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '-')) return 0;
    }
    return 1;
}

static int valid_appid(const char *appid) {
    size_t length = strlen(appid);
    if (!length || length > 32) return 0;
    for (size_t i = 0; i < length; i++) {
        char c = appid[i];
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') ||
              c == '-' || c == '_')) return 0;
    }
    return 1;
}

/* Relative path below a fixed directory: no leading slash, no empty, "." or
   ".." components, no control characters. */
static int valid_relative(const char *path, size_t limit) {
    size_t length = strlen(path);
    if (!length || length >= limit || path[0] == '/') return 0;
    const char *part = path;
    for (;;) {
        const char *slash = strchr(part, '/');
        size_t size = slash ? (size_t)(slash - part) : strlen(part);
        if (!size) return 0;
        if ((size == 1 && part[0] == '.') || (size == 2 && part[0] == '.' && part[1] == '.')) return 0;
        if (!slash) break;
        part = slash + 1;
    }
    for (size_t i = 0; i < length; i++) {
        unsigned char c = (unsigned char)path[i];
        if (c < 0x20 || c == 0x7f) return 0;
    }
    return 1;
}

static int valid_text(const char *text, size_t limit) {
    size_t length = strlen(text);
    if (!length || length >= limit) return 0;
    for (size_t i = 0; i < length; i++) {
        unsigned char c = (unsigned char)text[i];
        if (c < 0x20 || c == 0x7f) return 0;
    }
    return 1;
}

static void trim(char *text) {
    size_t length = strlen(text);
    while (length && (text[length - 1] == ' ' || text[length - 1] == '\t' || text[length - 1] == '\r'))
        text[--length] = 0;
    char *start = text;
    while (*start == ' ' || *start == '\t') start++;
    if (start != text) memmove(text, start, strlen(start) + 1);
}

static int parse_runner(const char *value) {
    if (!strcmp(value, "proton")) return OMINX_GAME_RUNNER_PROTON;
    if (!strcmp(value, "wine")) return OMINX_GAME_RUNNER_WINE;
    return OMINX_GAME_RUNNER_NONE;
}

static int parse_anticheat(const char *value) {
    if (!strcmp(value, "none")) return OMINX_AC_NONE;
    if (!strcmp(value, "eac")) return OMINX_AC_EAC;
    if (!strcmp(value, "battleye")) return OMINX_AC_BATTLEYE;
    if (!strcmp(value, "vanguard")) return OMINX_AC_VANGUARD;
    if (!strcmp(value, "other")) return OMINX_AC_OTHER;
    return -1;
}

static int parse_status(const char *value) {
    if (!strcmp(value, "none")) return OMINX_AC_STATUS_NONE;
    if (!strcmp(value, "vendor-opt-in")) return OMINX_AC_VENDOR_OPT_IN;
    if (!strcmp(value, "pending")) return OMINX_AC_PENDING;
    if (!strcmp(value, "denied")) return OMINX_AC_DENIED;
    return -1;
}

static int parse_requires(const char *value) {
    if (!strcmp(value, "none")) return OMINX_GAME_REQ_NONE;
    if (!strcmp(value, "eac-v2")) return OMINX_GAME_REQ_EAC_V2;
    return -1;
}

/* Parses profile text. Returns 0 or -1 with a stable reason in @error. */
static int parse_profile(const char *text, struct ominx_game *game, char *error, size_t error_size) {
    unsigned seen = 0;
    enum { F_ID = 1, F_NAME = 2, F_APPID = 4, F_RUNNER = 8, F_DIR = 16, F_EXE = 32,
           F_ANTICHEAT = 64, F_STATUS = 128 };
    char buffer[OMINX_GAME_PROFILE_MAX];
    if (strlen(text) >= sizeof buffer) { set_error(error, error_size, "profile-too-large"); return -1; }
    memcpy(buffer, text, strlen(text) + 1);
    memset(game, 0, sizeof *game);
    game->runner = OMINX_GAME_RUNNER_NONE;
    game->anticheat = -1;
    game->status = -1;
    game->requires = OMINX_GAME_REQ_NONE;

    char *save = NULL;
    for (char *line = strtok_r(buffer, "\n", &save); line; line = strtok_r(NULL, "\n", &save)) {
        trim(line);
        if (!*line || line[0] == '#') continue;
        char *equals = strchr(line, '=');
        if (!equals) { set_error(error, error_size, "malformed-line"); return -1; }
        *equals = 0;
        char *key = line, *value = equals + 1;
        trim(key);
        trim(value);
        if (!*value && strcmp(key, "notes")) { set_error(error, error_size, "empty-value"); return -1; }
        if (!strcmp(key, "id")) {
            if (!valid_id(value) || copy_field(game->id, sizeof game->id, value)) {
                set_error(error, error_size, "bad-id"); return -1;
            }
            seen |= F_ID;
        } else if (!strcmp(key, "name")) {
            if (!valid_text(value, sizeof game->name) || copy_field(game->name, sizeof game->name, value)) {
                set_error(error, error_size, "bad-name"); return -1;
            }
            seen |= F_NAME;
        } else if (!strcmp(key, "appid")) {
            if (!valid_appid(value) || copy_field(game->appid, sizeof game->appid, value)) {
                set_error(error, error_size, "bad-appid"); return -1;
            }
            seen |= F_APPID;
        } else if (!strcmp(key, "runner")) {
            game->runner = parse_runner(value);
            if (game->runner == OMINX_GAME_RUNNER_NONE) { set_error(error, error_size, "bad-runner"); return -1; }
            seen |= F_RUNNER;
        } else if (!strcmp(key, "dir")) {
            if (!valid_relative(value, sizeof game->dir) || copy_field(game->dir, sizeof game->dir, value)) {
                set_error(error, error_size, "bad-dir"); return -1;
            }
            seen |= F_DIR;
        } else if (!strcmp(key, "exe")) {
            if (!valid_relative(value, sizeof game->exe) || copy_field(game->exe, sizeof game->exe, value)) {
                set_error(error, error_size, "bad-exe"); return -1;
            }
            seen |= F_EXE;
        } else if (!strcmp(key, "anticheat")) {
            game->anticheat = parse_anticheat(value);
            if (game->anticheat < 0) { set_error(error, error_size, "bad-anticheat"); return -1; }
            seen |= F_ANTICHEAT;
        } else if (!strcmp(key, "anticheat_status")) {
            game->status = parse_status(value);
            if (game->status < 0) { set_error(error, error_size, "bad-anticheat-status"); return -1; }
            seen |= F_STATUS;
        } else if (!strcmp(key, "requires")) {
            game->requires = parse_requires(value);
            if (game->requires < 0) { set_error(error, error_size, "bad-requires"); return -1; }
        } else if (!strcmp(key, "notes")) {
            if (*value && (!valid_text(value, sizeof game->notes) ||
                           copy_field(game->notes, sizeof game->notes, value))) {
                set_error(error, error_size, "bad-notes"); return -1;
            }
        } else {
            set_error(error, error_size, "unknown-key");
            return -1;
        }
    }
    if (seen != (F_ID | F_NAME | F_APPID | F_RUNNER | F_DIR | F_EXE | F_ANTICHEAT | F_STATUS)) {
        set_error(error, error_size, "missing-required-key");
        return -1;
    }
    /* Consistency: the profile must not overstate what the publisher said. */
    if ((game->anticheat == OMINX_AC_NONE) != (game->status == OMINX_AC_STATUS_NONE)) {
        set_error(error, error_size, "anticheat-status-mismatch");
        return -1;
    }
    if (game->anticheat == OMINX_AC_VANGUARD && game->status != OMINX_AC_DENIED) {
        set_error(error, error_size, "vanguard-must-be-denied");
        return -1;
    }
    if (game->requires == OMINX_GAME_REQ_EAC_V2 && game->anticheat != OMINX_AC_EAC) {
        set_error(error, error_size, "eac-v2-requires-eac");
        return -1;
    }
    return 0;
}

int ominx_game_load(const char *games_dir, const char *id, struct ominx_game *game,
                    char *error, size_t error_size) {
    if (!valid_id(id)) { set_error(error, error_size, "bad-id"); return -1; }
    char path[512];
    int length = snprintf(path, sizeof path, "%s/%s.game", games_dir, id);
    if (length < 0 || (size_t)length >= sizeof path) { set_error(error, error_size, "path-too-long"); return -1; }
    int fd = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) { set_error(error, error_size, errno == ENOENT ? "unknown-game" : "unreadable"); return -1; }
    struct stat info;
    if (fstat(fd, &info) || !S_ISREG(info.st_mode) || info.st_size <= 0 || info.st_size >= OMINX_GAME_PROFILE_MAX) {
        close(fd);
        set_error(error, error_size, "bad-profile-file");
        return -1;
    }
    char text[OMINX_GAME_PROFILE_MAX];
    size_t used = 0;
    while (used < (size_t)info.st_size) {
        ssize_t got = read(fd, text + used, (size_t)info.st_size - used);
        if (got < 0 && errno == EINTR) continue;
        if (got <= 0) break;
        used += (size_t)got;
    }
    close(fd);
    if (used != (size_t)info.st_size) { set_error(error, error_size, "unreadable"); return -1; }
    text[used] = 0;
    if (parse_profile(text, game, error, error_size)) return -1;
    if (strcmp(game->id, id)) { set_error(error, error_size, "id-does-not-match-file"); return -1; }
    return 0;
}

static int compare_names(const void *a, const void *b) {
    return strcmp(*(char *const *)a, *(char *const *)b);
}

int ominx_game_for_each(const char *games_dir,
                        void (*visit)(const char *id, const struct ominx_game *game,
                                      const char *error, void *context),
                        void *context) {
    DIR *dir = opendir(games_dir);
    if (!dir) return -1;
    char *names[256];
    int count = 0;
    struct dirent *entry;
    while ((entry = readdir(dir)) != NULL && count < 256) {
        size_t length = strlen(entry->d_name);
        if (length <= 5 || strcmp(entry->d_name + length - 5, ".game")) continue;
        names[count] = strdup(entry->d_name);
        if (!names[count]) break;
        count++;
    }
    closedir(dir);
    qsort(names, (size_t)count, sizeof names[0], compare_names);
    int last = 0;
    for (int i = 0; i < count; i++) {
        char id[OMINX_GAME_ID_MAX + 1];
        size_t stem = strlen(names[i]) - 5;
        if (stem > OMINX_GAME_ID_MAX) stem = OMINX_GAME_ID_MAX;
        memcpy(id, names[i], stem);
        id[stem] = 0;
        struct ominx_game game;
        char error[64] = "";
        int result = ominx_game_load(games_dir, id, &game, error, sizeof error);
        if (visit) {
            if (result) visit(id, NULL, error, context);
            else visit(id, &game, "", context);
        }
        free(names[i]);
        last = result ? -1 : 0;
    }
    return last;
}

/* Reads a small kernel/firmware file. Returns the byte count or -1. */
static ssize_t read_small(const char *root, const char *relative, char *buffer, size_t size) {
    char path[512];
    if (snprintf(path, sizeof path, "%s/%s", root, relative) >= (int)sizeof path) return -1;
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) return -1;
    ssize_t got = read(fd, buffer, size - 1);
    close(fd);
    if (got < 0) return -1;
    buffer[got] = 0;
    return got;
}

static int path_exists(const char *root, const char *relative) {
    char path[512];
    if (snprintf(path, sizeof path, "%s/%s", root, relative) >= (int)sizeof path) return 0;
    struct stat info;
    return stat(path, &info) == 0;
}

static int starts_with(const char *text, const char *prefix) {
    return !strncmp(text, prefix, strlen(prefix));
}

static int contains_token(const char *list, const char *token) {
    size_t length = strlen(token);
    for (const char *at = list; (at = strstr(at, token)) != NULL; at += length) {
        int before = at == list || at[-1] == ',' || at[-1] == ' ' || at[-1] == '[';
        char after = at[length];
        int boundary = after == 0 || after == ',' || after == ' ' || after == ']' || after == '\n';
        if (before && boundary) return 1;
    }
    return 0;
}

static int secure_boot_enabled(const char *root) {
    char path[512];
    if (snprintf(path, sizeof path, "%s/sys/firmware/efi/efivars", root) >= (int)sizeof path) return 0;
    DIR *dir = opendir(path);
    if (!dir) return 0;
    int enabled = 0;
    struct dirent *entry;
    while ((entry = readdir(dir)) != NULL) {
        if (!starts_with(entry->d_name, "SecureBoot-")) continue;
        /* efivars: 4-byte attribute header, then the value (1 = enabled). */
        unsigned char value[8];
        char path2[700];
        if (snprintf(path2, sizeof path2, "%s/%s", path, entry->d_name) >= (int)sizeof path2) continue;
        int fd = open(path2, O_RDONLY | O_CLOEXEC);
        if (fd < 0) continue;
        ssize_t got = read(fd, value, sizeof value);
        close(fd);
        if (got == 5 && value[4] == 1) enabled = 1;
    }
    closedir(dir);
    return enabled;
}

static int iommu_present(const char *root) {
    char path[512];
    if (snprintf(path, sizeof path, "%s/sys/class/iommu", root) >= (int)sizeof path) return 0;
    DIR *dir = opendir(path);
    if (!dir) return 0;
    int present = 0;
    struct dirent *entry;
    while ((entry = readdir(dir)) != NULL)
        if (strcmp(entry->d_name, ".") && strcmp(entry->d_name, "..")) present = 1;
    closedir(dir);
    return present;
}

int ominx_host_eac_v2_missing(const char *sysroot, char *missing, size_t missing_size) {
    char text[512];
    char list[256] = "";
    size_t used = 0;
#define MISSING(name)                                                                    \
    do {                                                                                 \
        int n = snprintf(list + used, sizeof list - used, "%s%s", used ? "," : "", name); \
        if (n > 0 && (size_t)n < sizeof list - used) used += (size_t)n;                 \
    } while (0)

    if (read_small(sysroot, "sys/module/module/parameters/sig_enforce", text, sizeof text) < 0 ||
        text[0] != 'Y')
        MISSING("module-signing");
    if (read_small(sysroot, "sys/class/tpm/tpm0/tpm_version_major", text, sizeof text) < 0 ||
        text[0] != '2')
        MISSING("tpm2");
    if (!secure_boot_enabled(sysroot)) MISSING("secure-boot");
    if (!path_exists(sysroot, "sys/kernel/security/tpm0/binary_bios_measurements"))
        MISSING("measured-boot");
    if (!iommu_present(sysroot)) MISSING("iommu");
    if (read_small(sysroot, "sys/kernel/security/lockdown", text, sizeof text) < 0 ||
        !(strstr(text, "[integrity]") || strstr(text, "[confidentiality]")))
        MISSING("kernel-lockdown");
    if (read_small(sysroot, "proc/sys/kernel/kexec_load_disabled", text, sizeof text) < 0 || text[0] != '1')
        MISSING("kexec-disabled");
    if (read_small(sysroot, "sys/kernel/security/lsm", text, sizeof text) < 0 || !contains_token(text, "bpf"))
        MISSING("bpf-lsm");
#undef MISSING
    if (missing_size) snprintf(missing, missing_size, "%s", list);
    return used ? -1 : 0;
}

int ominx_game_gate(const struct ominx_game *game, const char *sysroot,
                    char *reason, size_t reason_size) {
    const char *denied = NULL;
    if (game->anticheat == OMINX_AC_NONE) return 0;
    if (game->status == OMINX_AC_DENIED) denied = "anticheat-denied";
    else if (game->status == OMINX_AC_PENDING) denied = "anticheat-pending-publisher-support";
    else if (game->status != OMINX_AC_VENDOR_OPT_IN) denied = "anticheat-status-unknown";
    if (denied) {
        if (reason_size) snprintf(reason, reason_size, "%s", denied);
        return -1;
    }
    if (game->requires == OMINX_GAME_REQ_EAC_V2) {
        char missing[256];
        if (ominx_host_eac_v2_missing(sysroot, missing, sizeof missing)) {
            if (reason_size) snprintf(reason, reason_size, "eac-v2-requirements-unmet:%s", missing);
            return -1;
        }
    }
    return 0;
}

const char *ominx_game_runner_name(int runner) {
    switch (runner) {
    case OMINX_GAME_RUNNER_PROTON: return "proton";
    case OMINX_GAME_RUNNER_WINE: return "wine";
    default: return "none";
    }
}

const char *ominx_game_anticheat_name(int anticheat) {
    switch (anticheat) {
    case OMINX_AC_EAC: return "eac";
    case OMINX_AC_BATTLEYE: return "battleye";
    case OMINX_AC_VANGUARD: return "vanguard";
    case OMINX_AC_OTHER: return "other";
    default: return "none";
    }
}

const char *ominx_game_status_name(int status) {
    switch (status) {
    case OMINX_AC_VENDOR_OPT_IN: return "vendor-opt-in";
    case OMINX_AC_PENDING: return "pending";
    case OMINX_AC_DENIED: return "denied";
    default: return "none";
    }
}

const char *ominx_game_requirement_name(int requirement) {
    return requirement == OMINX_GAME_REQ_EAC_V2 ? "eac-v2" : "none";
}
