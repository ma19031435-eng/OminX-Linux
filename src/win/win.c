/* Original OminX Windows application client.
 * Used by the console (`win run setup.exe`), the desktop-wide .exe/.msi
 * file association and binfmt. Prefers the per-user background service and
 * starts it on demand for console sessions. Repository license applies. */
#define _GNU_SOURCE
#include "../lib/files.h"
#include "../lib/gamedb.h"
#include "../lib/gamesched.h"
#include "../lib/pe.h"
#include "../lib/winproto.h"
#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/un.h>
#include <unistd.h>

static char socket_path[PATH_MAX];

static int find_socket(void) {
    const char *env = getenv(OMINX_WINED_SOCKET_ENV);
    if (env && *env) {
        if (strlen(env) >= sizeof socket_path) return -1;
        strcpy(socket_path, env);
        return 0;
    }
    const char *dir = getenv("XDG_RUNTIME_DIR");
    if (!dir || !*dir) { errno = ENOENT; return -1; }
    int length = snprintf(socket_path, sizeof socket_path, "%s/%s", dir, OMINX_WINED_SOCKET_NAME);
    if (length < 0 || (size_t)length >= sizeof socket_path) return -1;
    return 0;
}
/* Console sessions have no supervisor for user services yet: detach the
   same daemon the seat would start, recording its output under XDG. */
static void autostart_daemon(void) {
    pid_t pid = fork();
    if (pid != 0) return;
    if (setsid() < 0) _exit(1);
    const char *dir = getenv("XDG_RUNTIME_DIR");
    char log[PATH_MAX] = "/dev/null";
    if (dir) snprintf(log, sizeof log, "%s/ominx-wined.log", dir);
    int fd = open(log, O_WRONLY | O_CREAT | O_APPEND, 0600);
    int null = open("/dev/null", O_RDONLY);
    if (null >= 0) dup2(null, 0);
    if (fd >= 0) { dup2(fd, 1); dup2(fd, 2); }
    /* Sibling of this client first (build/host in tests, /bin on target). */
    char program[PATH_MAX];
    ssize_t length = readlink("/proc/self/exe", program, sizeof program - 16);
    if (length > 0) {
        program[length] = 0;
        char *slash = strrchr(program, '/');
        if (slash) strcpy(slash + 1, "ominx-wined");
        execl(program, "ominx-wined", (char *)NULL);
    }
    execl("/bin/ominx-wined", "ominx-wined", (char *)NULL);
    _exit(127);
}
static int request_once(const char *request, char *reply, size_t capacity) {
    int fd = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0);
    if (fd < 0) return -1;
    struct sockaddr_un address = {.sun_family = AF_UNIX};
    if (strlen(socket_path) >= sizeof address.sun_path) { close(fd); errno = ENAMETOOLONG; return -1; }
    strcpy(address.sun_path, socket_path);
    struct timeval timeout = {10, 0};
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof timeout);
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof timeout);
    if (connect(fd, (struct sockaddr *)&address, sizeof address)) {
        int saved = errno; close(fd); errno = saved; return -1;
    }
    size_t length = strlen(request);
    if (send(fd, request, length, MSG_NOSIGNAL) != (ssize_t)length) {
        int saved = errno; close(fd); errno = saved; return -1;
    }
    ssize_t count = recv(fd, reply, capacity - 1, 0);
    int saved = errno;
    close(fd);
    errno = saved;
    if (count <= 0) return -1;
    reply[count] = 0;
    return 0;
}
static int request_daemon(const char *request, char *reply, size_t capacity, int autostart) {
    if (!request_once(request, reply, capacity)) return 0;
    if (!autostart || (errno != ENOENT && errno != ECONNREFUSED)) return -1;
    autostart_daemon();
    for (int i = 0; i < 50; i++) {
        usleep(100000);
        if (!request_once(request, reply, capacity)) return 0;
    }
    errno = ECONNREFUSED;
    return -1;
}
static const char *field(const char *reply, const char *name, char *buffer, size_t capacity) {
    size_t name_length = strlen(name);
    const char *at = reply;
    while (at && *at) {
        const char *end = strchr(at, '\n');
        size_t line = end ? (size_t)(end - at) : strlen(at);
        if (line > name_length && !strncmp(at, name, name_length) && at[name_length] == '=') {
            size_t value = line - name_length - 1;
            if (value >= capacity) value = capacity - 1;
            memcpy(buffer, at + name_length + 1, value);
            buffer[value] = 0;
            return buffer;
        }
        at = end ? end + 1 : NULL;
    }
    buffer[0] = 0;
    return buffer;
}
/* Blocks (with progress) until the background first-boot setup finishes. */
static int wait_ready(int proton) {
    char reply[16384], value[128];
    int printed = -1;
    for (int seconds = 0; seconds < 600; seconds++) {
        if (request_daemon("STATUS\n", reply, sizeof reply, 1)) return -1;
        if (proton) {
            field(reply, "proton-setup", value, sizeof value);
            if (!strcmp(value, "idle")) {
                field(reply, "proton-default", value, sizeof value);
                /* idle only means the worker finished; a per-title setup is
                   accepted by the launch retry below. */
                return 0;
            }
            if (!strcmp(value, "failed")) { fputs("Proton prefix setup failed. See ominx-win status.\n", stderr); return 1; }
        } else {
            field(reply, "state", value, sizeof value);
            if (!strcmp(value, "ready")) { if (printed >= 0) putchar('\n'); return 0; }
            if (!strcmp(value, "runtime-missing")) {
                fputs("The Wine runtime is not installed in this OminX image yet.\n"
                      "This development image has the Windows services, kernel support and\n"
                      "packaging, but still needs the source-built Wine/Proton runtime\n"
                      "artifact (see docs/windows-compatibility.md).\n", stderr);
                return 1;
            }
            if (!strcmp(value, "failed")) {
                field(reply, "error", value, sizeof value);
                fprintf(stderr, "Windows setup failed (%s). Try: win setup\n", value);
                return 1;
            }
            char percent[16], step[64];
            field(reply, "percent", percent, sizeof percent);
            field(reply, "step", step, sizeof step);
            int shown = atoi(percent);
            if (shown != printed) {
                printf("\rPreparing your Windows environment... %d%% (%s)   ", shown, step);
                fflush(stdout);
                printed = shown;
            }
        }
        sleep(1);
    }
    fputs("Timed out waiting for Windows setup.\n", stderr);
    return 1;
}
static int absolute(const char *path, char *out, size_t capacity) {
    char resolved[PATH_MAX];
    if (!realpath(path, resolved)) return -1;
    if (strlen(resolved) >= capacity) { errno = ENAMETOOLONG; return -1; }
    strcpy(out, resolved);
    return 0;
}
static int clean_arg(const char *arg) {
    if (!*arg || strlen(arg) > OMINX_WIN_MAX_ARG) return 0;
    for (const unsigned char *p = (const unsigned char *)arg; *p; p++)
        if (*p < 0x20 || *p == '\t') return 0;
    return 1;
}
static int build_request(char *out, size_t capacity, const char *verb, const char *appid,
                         const char *file, char **args, int count) {
    size_t used = 0;
    int written;
    if (appid) written = snprintf(out, capacity, "%s\t%s\t%s", verb, appid, file);
    else written = snprintf(out, capacity, "%s\t%s", verb, file);
    if (written < 0 || (size_t)written >= capacity) return -1;
    used = (size_t)written;
    for (int i = 0; i < count; i++) {
        if (!clean_arg(args[i])) { errno = EINVAL; return -1; }
        written = snprintf(out + used, capacity - used, "\t%s", args[i]);
        if (written < 0 || (size_t)written >= capacity - used) return -1;
        used += (size_t)written;
    }
    if (used + 2 > capacity) return -1;
    out[used] = '\n';
    out[used + 1] = 0;
    return 0;
}
static int launch_waiting(const char *verb, const char *appid, const char *file,
                          char **args, int count, int wait) {
    char path[PATH_MAX], request[OMINX_WIN_MAX_REQUEST], reply[16384];
    if (absolute(file, path, sizeof path)) { perror(file); return 1; }
    struct ominx_pe_info info;
    int inspected = ominx_pe_inspect_path(path, &info);
    if (inspected == -2) { perror(path); return 1; }
    if (inspected) {
        fprintf(stderr, "Not a valid Windows file (%s): %s\n", info.error, path);
        return 1;
    }
    if (!strcmp(verb, "MSI") && info.kind != OMINX_PE_MSI) {
        fputs("That file is not a Windows Installer (.msi) package.\n", stderr);
        return 1;
    }
    if (strcmp(verb, "MSI") && info.kind == OMINX_PE_MSI) verb = "MSI";
    if (build_request(request, sizeof request, verb, appid, path, args, count)) {
        fputs("Invalid or over-long argument.\n", stderr);
        return 2;
    }
    if (request_daemon(request, reply, sizeof reply, 1)) {
        perror("Windows service");
        return 1;
    }
    if (!strncmp(reply, "ERR prefix-not-ready", 20)) {
        int ready = wait_ready(!strcmp(verb, "PROTON"));
        if (ready) return ready;
        if (request_daemon(request, reply, sizeof reply, 0)) { perror("Windows service"); return 1; }
    }
    if (!strncmp(reply, "ERR runtime-missing", 19)) return wait_ready(0);
    if (!strncmp(reply, "ERR ", 4)) { fprintf(stderr, "Windows service refused: %s", reply + 4); return 1; }
    fputs(reply, stdout);
    if (!wait) return 0;
    /* Wait for this launch: poll its pid in STATUS until it disappears. */
    char launched[32] = "";
    const char *pid_at = strstr(reply, "pid=");
    if (!pid_at) return 0;
    snprintf(launched, sizeof launched, "%ld", strtol(pid_at + 4, NULL, 10));
    for (;;) {
        sleep(1);
        if (request_daemon("STATUS\n", reply, sizeof reply, 0)) return 1;
        char pids[256], exited[32];
        field(reply, "pids", pids, sizeof pids);
        int present = 0;
        for (char *token = strtok(pids, ","); token; token = strtok(NULL, ","))
            if (!strcmp(token, launched)) present = 1;
        if (!present) {
            field(reply, "last-exit", exited, sizeof exited);
            printf("Program exited (%s).\n", exited);
            return atoi(exited);
        }
    }
}
static void print_probe(const char *file, int json) {
    char path[PATH_MAX];
    if (absolute(file, path, sizeof path)) { perror(file); exit(1); }
    struct ominx_pe_info info;
    int result = ominx_pe_inspect_path(path, &info);
    if (result == -2) { perror(path); exit(1); }
    const char *subsystem = info.subsystem == 2 ? "gui" : info.subsystem == 3 ? "console" : "other";
    if (json)
        printf("{\"kind\":\"%s\",\"arch\":\"%s\",\"bits\":%d,\"subsystem\":\"%s\",\"dotnet\":%s,"
               "\"sections\":%u,\"size\":%llu}\n",
               ominx_pe_kind_name(info.kind), ominx_pe_arch_name(info.arch), info.bits,
               subsystem, info.dotnet ? "true" : "false", info.sections, info.file_size);
    else
        printf("%s: kind=%s arch=%s bits=%d subsystem=%s dotnet=%d sections=%u size=%llu%s%s\n",
               path, ominx_pe_kind_name(info.kind), ominx_pe_arch_name(info.arch), info.bits,
               subsystem, info.dotnet, info.sections, info.file_size,
               result ? " error=" : "", result ? info.error : "");
    exit(result ? 1 : 0);
}
static void doctor(void) {
    char reply[16384], value[128];
    FILE *file = fopen("/proc/sys/vm/max_map_count", "r");
    long maps = 0;
    if (file) { if (fscanf(file, "%ld", &maps) != 1) maps = 0; fclose(file); }
    printf("vm.max_map_count=%ld (%s, Proton wants >= %d)\n", maps,
           maps >= OMINX_WINE_MIN_MAP_COUNT ? "ok" : "LOW", OMINX_WINE_MIN_MAP_COUNT);
    printf("binfmt=%s\n", !access("/proc/sys/fs/binfmt_misc/" OMINX_WINE_BINFMT_NAME, F_OK)
                               ? "registered (./program.exe works)"
                               : "not-registered (use win run)");
    printf("ntsync=%s\n", !access("/dev/ntsync", F_OK) ? "present" : "absent (fsync fallback)");
    if (request_daemon("STATUS\n", reply, sizeof reply, 0))
        puts("service=not-running (starts at login or first win command)");
    else {
        static const char *const names[] = {"runtime", "version", "state", "dxvk",
                                            "vkd3d-proton", "wineserver", "proton-default"};
        for (size_t i = 0; i < sizeof names / sizeof names[0]; i++)
            printf("%s=%s\n", names[i], field(reply, names[i], value, sizeof value));
    }
}
static void usage(void) {
    puts("OminX Windows App Support\n"
         "  win status                  Background service and setup state\n"
         "  win setup                   Create/repair your Windows environment\n"
         "  win probe [--json] FILE     Identify an .exe/.msi/.dll without running it\n"
         "  win run [--wait] FILE [args]  Run a Windows program\n"
         "  win install FILE            Install from an .exe installer or .msi package\n"
         "  win msi FILE [options]      Run Windows Installer on an .msi package\n"
         "  win proton [--appid ID] [--wait] FILE [args]\n"
         "                              Run in a per-game Proton-style prefix\n"
         "  win apps                    Programs installed in your Windows environment\n"
         "  win stop | win quit         Stop Windows programs / the background service\n"
         "  win game list               Game profiles and their anti-cheat status\n"
         "  win game info|check ID      Details and launch policy for one title\n"
         "  win game launch ID          Start a launchable title in the background service\n"
         "  win doctor                  Check kernel and runtime prerequisites\n"
         "Only run programs you trust: Wine is not a sandbox.");
}
/* ---- Game framework (win game ...) ---------------------------------------- */
static const char *games_path(void) {
#ifdef OMINX_WIN_TEST
    const char *test = getenv("OMINX_GAMES_DIR");
    if (test && *test) return test;
#endif
    return OMINX_GAME_DIR_DEFAULT;
}

static const char *sysroot_path(void) {
#ifdef OMINX_WIN_TEST
    const char *test = getenv("OMINX_SYSROOT");
    if (test && *test) return test;
#endif
    return "/";
}

static void explain_refusal(const char *reason) {
    if (!strcmp(reason, "anticheat-denied"))
        puts("  The publisher blocks Linux for this title (anti-cheat denied).\n"
             "  OminX does not offer workarounds for anti-cheat.");
    else if (!strcmp(reason, "anticheat-pending-publisher-support"))
        puts("  The publisher has not enabled Linux support for this title yet.");
    else if (!strncmp(reason, "eac-v2-requirements-unmet:", 26))
        printf("  This host is missing EAC Linux v2 requirements: %s\n", reason + 26);
    else
        printf("  Refused: %s\n", reason);
}

/* JSON output (schema 1). Strings are escaped; no other encoding is needed. */
static void json_string(const char *text) {
    putchar('"');
    for (const unsigned char *p = (const unsigned char *)text; *p; p++) {
        switch (*p) {
        case '"': fputs("\\\"", stdout); break;
        case '\\': fputs("\\\\", stdout); break;
        case '\n': fputs("\\n", stdout); break;
        case '\t': fputs("\\t", stdout); break;
        default:
            if (*p < 0x20) printf("\\u%04x", *p);
            else putchar(*p);
        }
    }
    putchar('"');
}

static const char *user_root_path(char *buffer, size_t size) {
    if (ominx_sched_user_root(OMINX_SCHED_ROOT_DEFAULT, (unsigned)geteuid(), buffer, size)) buffer[0] = '\0';
    return buffer;
}

static void print_game_json(const struct ominx_game *game) {
    char reason[256] = "", detail[160] = "", user_root[OMINX_SCHED_PATH_MAX];
    int allowed = ominx_game_gate(game, sysroot_path(), reason, sizeof reason) == 0;
    enum ominx_sched_state state = ominx_sched_state_of(game, sysroot_path(),
                                                        user_root_path(user_root, sizeof user_root),
                                                        detail, sizeof detail);
    fputs("{\"id\":", stdout); json_string(game->id);
    fputs(",\"valid\":true,\"name\":", stdout); json_string(game->name);
    fputs(",\"runner\":", stdout); json_string(ominx_game_runner_name(game->runner));
    fputs(",\"appid\":", stdout); json_string(game->appid);
    fputs(",\"anticheat\":", stdout); json_string(ominx_game_anticheat_name(game->anticheat));
    fputs(",\"publisher_status\":", stdout); json_string(ominx_game_status_name(game->status));
    fputs(",\"requires\":", stdout); json_string(ominx_game_requirement_name(game->requires));
    printf(",\"launchable\":%s", allowed ? "true" : "false");
    fputs(",\"refusal\":", stdout); json_string(allowed ? "" : reason);
    fputs(",\"install_dir\":", stdout);
    char install[OMINX_GAME_PROFILE_MAX];
    snprintf(install, sizeof install, "$HOME/%s", game->dir);
    json_string(install);
    fputs(",\"program\":", stdout); json_string(game->exe);
    fputs(",\"notes\":", stdout); json_string(game->notes);
    fputs(",\"scheduling\":{\"state\":", stdout); json_string(ominx_sched_state_name(state));
    fputs(",\"detail\":", stdout); json_string(detail);
    fputs("}}", stdout);
}

static void print_game_row(const char *id, const struct ominx_game *game, const char *error, void *context) {
    (void)context;
    if (!game) { printf("%-14s invalid profile (%s)\n", id, error); return; }
    char reason[256] = "";
    int allowed = ominx_game_gate(game, sysroot_path(), reason, sizeof reason) == 0;
    printf("%-14s %-20s anticheat=%-9s status=%-18s %s\n", game->id, game->name,
           ominx_game_anticheat_name(game->anticheat), ominx_game_status_name(game->status),
           allowed ? "launchable" : "refused");
}

/* Visitor state for `game list --json`: the envelope opens before the first item. */
static int json_games_first = 1;
static void print_game_json_item(const char *id, const struct ominx_game *game, const char *error, void *context) {
    (void)context;
    if (!json_games_first) putchar(',');
    json_games_first = 0;
    if (!game) {
        fputs("{\"id\":", stdout); json_string(id);
        fputs(",\"valid\":false,\"error\":", stdout); json_string(error);
        fputs("}", stdout);
        return;
    }
    print_game_json(game);
}

static int game_command(int argc, char **argv) {
    const char *verb = argv[2];
    if (!strcmp(verb, "list") && argc == 4 && !strcmp(argv[3], "--json")) {
        json_games_first = 1;
        fputs("{\"schema\":1,\"games\":[", stdout);
        int result = ominx_game_for_each(games_path(), print_game_json_item, NULL);
        fputs("]}\n", stdout);
        if (result < 0) { perror(games_path()); return 1; }
        return 0;
    }
    if (!strcmp(verb, "info") && argc == 5 && !strcmp(argv[4], "--json")) {
        struct ominx_game game;
        char error[64];
        if (ominx_game_load(games_path(), argv[3], &game, error, sizeof error)) {
            fputs("{\"schema\":1,\"valid\":false,\"error\":", stdout); json_string(error);
            fputs("}\n", stdout);
            return 1;
        }
        fputs("{\"schema\":1,\"game\":", stdout);
        print_game_json(&game);
        fputs("}\n", stdout);
        return 0;
    }
    if (!strcmp(verb, "list") && argc == 3) {
        int result = ominx_game_for_each(games_path(), print_game_row, NULL);
        if (result < 0) { perror(games_path()); return 1; }
        return 0;
    }
    if ((!strcmp(verb, "info") || !strcmp(verb, "check") || !strcmp(verb, "launch")) && argc == 4) {
        struct ominx_game game;
        char error[64], reason[256] = "";
        if (ominx_game_load(games_path(), argv[3], &game, error, sizeof error)) {
            fprintf(stderr, "Unknown or invalid game '%s': %s\n", argv[3], error);
            return 1;
        }
        int allowed = ominx_game_gate(&game, sysroot_path(), reason, sizeof reason) == 0;
        /* Compatibility and scheduling state, shown before anything else happens. */
        char status[320];
        char user_root[OMINX_SCHED_PATH_MAX];
        if (ominx_sched_user_root(OMINX_SCHED_ROOT_DEFAULT, (unsigned)geteuid(), user_root, sizeof user_root))
            user_root[0] = '\0';
        ominx_sched_status(&game, sysroot_path(), user_root, status, sizeof status);
        if (!strcmp(verb, "info")) {
            printf("id:            %s\nname:          %s\nrunner:        %s\nappid:         %s\n"
                   "install dir:   $HOME/%s\nprogram:       %s\nanti-cheat:    %s\n"
                   "publisher:     %s\nrequires:      %s\nlaunchable:    %s\n",
                   game.id, game.name, ominx_game_runner_name(game.runner), game.appid,
                   game.dir, game.exe, ominx_game_anticheat_name(game.anticheat),
                   ominx_game_status_name(game.status), ominx_game_requirement_name(game.requires),
                   allowed ? "yes" : "no");
            printf("status:        %s\n", status);
            if (game.notes[0]) printf("notes:         %s\n", game.notes);
            if (!allowed) explain_refusal(reason);
            return 0;
        }
        if (!strcmp(verb, "check")) {
            printf("status: %s\n", status);
            if (allowed) { printf("%s: launchable on this host.\n", game.name); return 0; }
            printf("%s: not launchable.\n", game.name);
            explain_refusal(reason);
            return 1;
        }
        /* launch: the daemon repeats the same gate before it starts anything. */
        if (!allowed) {
            printf("%s will not start.\n", game.name);
            explain_refusal(reason);
            return 1;
        }
        printf("status: %s\n", status);
        if (find_socket()) { fputs("No user runtime directory for the Windows service.\n", stderr); return 1; }
        char request[256], reply[16384];
        snprintf(request, sizeof request, "GAMELAUNCH\t%s\n", game.id);
        if (request_daemon(request, reply, sizeof reply, 1)) { perror("Windows service"); return 1; }
        if (!strncmp(reply, "OK ", 3)) {
            printf("Started %s (%s", game.name, reply + 3);
            return 0;
        }
        if (!strncmp(reply, "ERR prefix-not-ready", 20)) {
            puts("Your Windows environment is still being prepared in the background.\n"
                 "Run `ominx-win status` and try again when it reports ready.");
            return 1;
        }
        if (!strncmp(reply, "ERR refused-", 12)) {
            char refusal[256];
            size_t length = strcspn(reply + 12, "\n");
            if (length >= sizeof refusal) length = sizeof refusal - 1;
            memcpy(refusal, reply + 12, length);
            refusal[length] = 0;
            printf("%s will not start.\n", game.name);
            explain_refusal(refusal);
            return 1;
        }
        fprintf(stderr, "Could not start %s: %s", game.name, reply);
        return 1;
    }
    usage();
    return 2;
}

int main(int argc, char **argv) {
    const char *name = strrchr(argv[0], '/');
    name = name ? name + 1 : argv[0];
    if (find_socket()) { /* probe/doctor still work without a session */ }
    /* binfmt hands us the program as argv[1] (no O flag: a real path). */
    if (!strcmp(name, "ominx-win-binfmt")) {
        if (argc < 2) return 2;
        if (find_socket()) { fputs("No user session for Windows programs.\n", stderr); return 1; }
        const char *file = argv[1];
        return launch_waiting(ominx_pe_suffix(file) == 2 ? "MSI" : "RUN", NULL, file,
                              argv + 2, argc - 2, 1);
    }
    if (argc >= 2 && !strcmp(argv[1], "probe")) {
        int json = argc == 4 && !strcmp(argv[2], "--json");
        if (argc != 3 && !json) { usage(); return 2; }
        print_probe(argv[argc - 1], json);
    }
    if (argc == 2 && !strcmp(argv[1], "doctor")) { doctor(); return 0; }
    if (argc >= 3 && !strcmp(argv[1], "game")) return game_command(argc, argv);
    if (argc < 2 || !strcmp(argv[1], "help") || !strcmp(argv[1], "--help")) { usage(); return argc < 2 ? 2 : 0; }
    if (find_socket()) { fputs("No user runtime directory for the Windows service.\n", stderr); return 1; }
    char reply[16384];
    if (!strcmp(argv[1], "status") && argc == 2) {
        if (request_daemon("STATUS\n", reply, sizeof reply, 1)) { perror("Windows service"); return 1; }
        fputs(reply, stdout); return 0;
    }
    if (!strcmp(argv[1], "setup") && argc == 2) {
        if (request_daemon("SETUP\n", reply, sizeof reply, 1)) { perror("Windows service"); return 1; }
        if (!strncmp(reply, "ERR runtime-missing", 19)) return wait_ready(0);
        int result = wait_ready(0);
        if (!result) puts("Your Windows environment is ready.");
        return result;
    }
    if (!strcmp(argv[1], "apps") && argc == 2) {
        if (request_daemon("APPS\n", reply, sizeof reply, 1)) { perror("Windows service"); return 1; }
        fputs(reply, stdout); return 0;
    }
    if ((!strcmp(argv[1], "stop") || !strcmp(argv[1], "quit")) && argc == 2) {
        if (request_daemon(!strcmp(argv[1], "stop") ? "STOP\n" : "QUIT\n", reply, sizeof reply, 0)) {
            perror("Windows service"); return 1;
        }
        fputs(reply, stdout); return 0;
    }
    if (!strcmp(argv[1], "run") || !strcmp(argv[1], "install")) {
        int at = 2, wait = !strcmp(argv[1], "install");
        if (at < argc && !strcmp(argv[at], "--wait")) { wait = 1; at++; }
        if (at >= argc || argc - at - 1 > OMINX_WIN_MAX_ARGS) { usage(); return 2; }
        const char *verb = ominx_pe_suffix(argv[at]) == 2 ? "MSI" : "RUN";
        return launch_waiting(verb, NULL, argv[at], argv + at + 1, argc - at - 1, wait);
    }
    if (!strcmp(argv[1], "msi")) {
        if (argc < 3 || argc - 3 > OMINX_WIN_MAX_ARGS) { usage(); return 2; }
        return launch_waiting("MSI", NULL, argv[2], argv + 3, argc - 3, 1);
    }
    if (!strcmp(argv[1], "proton")) {
        int at = 2, wait = 0;
        const char *appid = "default";
        while (at < argc && argv[at][0] == '-') {
            if (!strcmp(argv[at], "--wait")) { wait = 1; at++; }
            else if (!strcmp(argv[at], "--appid") && at + 1 < argc) { appid = argv[at + 1]; at += 2; }
            else { usage(); return 2; }
        }
        if (at >= argc || argc - at - 1 > OMINX_WIN_MAX_ARGS) { usage(); return 2; }
        char path[PATH_MAX], setup[128];
        if (absolute(argv[at], path, sizeof path)) { perror(argv[at]); return 1; }
        int length = snprintf(setup, sizeof setup, "PROTONSETUP\t%s\n", appid);
        if (length < 0 || (size_t)length >= sizeof setup) return 2;
        if (request_daemon(setup, reply, sizeof reply, 1)) { perror("Windows service"); return 1; }
        if (!strncmp(reply, "ERR runtime-missing", 19)) return wait_ready(0);
        int ready = wait_ready(1);
        if (ready) return ready;
        return launch_waiting("PROTON", appid, path, argv + at + 1, argc - at - 1, wait);
    }
    usage();
    return 2;
}
