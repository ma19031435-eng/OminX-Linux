/* Original root Windows-compatibility setup service.
 *
 * Runs at every boot under PID 1 supervision and finishes the machine-wide
 * half of first-install/first-boot setup before anyone logs in: verifies
 * the source-built Wine/Proton runtime, registers the MZ binfmt handler,
 * raises vm.max_map_count for Proton, prepares state directories and then
 * answers STATUS for the installer, desktop and diagnostics. It never
 * loads or executes Windows code: prefixes are created by the per-user
 * ominx-wined with that user's privileges only. */
#define _GNU_SOURCE
#include "../lib/session.h"
#include "../lib/gamesched.h"
#include "../lib/winproto.h"
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/un.h>
#include <unistd.h>

static char runtime_state[24] = "missing";
static char runtime_version[65] = "unknown";
static int flags_bits; /* 1 binfmt, 2 sysctl, 4 marker */
static char state_dir[4096] = OMINX_WINE_STATE_DIR;
static char marker_path[4096] = OMINX_WINE_SYSTEM_MARKER;
static char report_path[4096] = OMINX_WINE_RUNTIME_REPORT;

static void record(const char *text) { puts(text); fflush(stdout); }

static int write_text(const char *path, const char *text, mode_t mode) {
    int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC | O_NOFOLLOW | O_CLOEXEC, mode);
    if (fd < 0) return -1;
    size_t length = strlen(text), done = 0;
    while (done < length) {
        ssize_t written = write(fd, text + done, length - done);
        if (written < 0) { if (errno == EINTR) continue; break; }
        done += (size_t)written;
    }
    int result = done == length && !fsync(fd) ? 0 : -1;
    int saved = errno;
    close(fd);
    errno = saved;
    return result;
}
static void detect_runtime(void) {
    const char *root = OMINX_WINE_RUNTIME;
#ifdef OMINX_WINSETUP_TEST
    const char *override = getenv("OMINX_WINE_RUNTIME_DIR");
    if (override && *override) root = override;
#endif
    char path[4096];
    snprintf(path, sizeof path, "%s/bin/wine", root);
    int present = !access(path, X_OK);
#ifndef OMINX_WINSETUP_TEST
    snprintf(path, sizeof path, "%s/%s", root, OMINX_WINE_LOADER);
    if (access(path, X_OK)) present = 0;
#endif
    snprintf(path, sizeof path, "%s/VERSION", root);
    FILE *file = fopen(path, "r");
    if (file) {
        if (!fgets(runtime_version, sizeof runtime_version, file)) runtime_version[0] = 0;
        runtime_version[strcspn(runtime_version, "\r\n")] = 0;
        fclose(file);
    }
    if (!runtime_version[0]) strcpy(runtime_version, "unknown");
    snprintf(runtime_state, sizeof runtime_state, "%s", present ? "present" : "missing");
}
#ifndef OMINX_WINSETUP_TEST
static int raise_map_count(void) {
    const char *path = "/proc/sys/vm/max_map_count";
    FILE *file = fopen(path, "r");
    long current = 0;
    if (!file) return -1;
    int ok = fscanf(file, "%ld", &current) == 1;
    fclose(file);
    if (!ok) return -1;
    if (current >= OMINX_WINE_MIN_MAP_COUNT) return 0;
    char wanted[32];
    snprintf(wanted, sizeof wanted, "%d\n", OMINX_WINE_MIN_MAP_COUNT);
    int fd = open(path, O_WRONLY | O_CLOEXEC);
    if (fd < 0) return -1;
    int result = write(fd, wanted, strlen(wanted)) == (ssize_t)strlen(wanted) ? 0 : -1;
    close(fd);
    return result;
}
static int register_binfmt(void) {
    if (access("/proc/sys/fs/binfmt_misc/register", W_OK)) {
        if (mount("binfmt_misc", "/proc/sys/fs/binfmt_misc", "binfmt_misc",
                  MS_NOSUID | MS_NODEV | MS_NOEXEC, NULL))
            return -1;
    }
    if (!access("/proc/sys/fs/binfmt_misc/" OMINX_WINE_BINFMT_NAME, F_OK)) return 0;
    int fd = open("/proc/sys/fs/binfmt_misc/register", O_WRONLY | O_CLOEXEC);
    if (fd < 0) return -1;
    const char *line = OMINX_WINE_BINFMT_LINE;
    int result = write(fd, line, strlen(line)) == (ssize_t)strlen(line) ? 0 : -1;
    close(fd);
    return result;
}
#endif
static void system_setup(void) {
    flags_bits = 0;
    detect_runtime();
    /* Wine/Proton only get their machine-wide hooks when a real runtime is
       installed, so a services-only image never intercepts MZ files. */
    if (!strcmp(runtime_state, "present")) {
#ifdef OMINX_WINSETUP_TEST
        flags_bits |= 1 | 2; /* Host tests must not touch /proc. */
#else
        if (!register_binfmt()) flags_bits |= 1;
        if (!raise_map_count()) flags_bits |= 2;
#endif
    }
    if (mkdir(state_dir, 0755) && errno != EEXIST) {
        record("winsetup: state directory unavailable");
    } else {
        char text[256];
        snprintf(text, sizeof text, "runtime=%s\nversion=%s\nsetup=%s\n",
                 runtime_state, runtime_version, OMINX_WIN_SETUP_VERSION);
        if (!write_text(marker_path, text, 0644)) flags_bits |= 4;
        char report[320];
        snprintf(report, sizeof report,
                 "runtime=%s\nversion=%s\nbinfmt=%d\nmax-map-count=%d\n",
                 runtime_state, runtime_version, !!(flags_bits & 1), !!(flags_bits & 2));
        (void)write_text(report_path, report, 0644);
    }
    /* Game scheduling is independent of the runtime: the delegated cgroup is
       prepared on every boot so a later game launch can boost itself. */
#ifndef OMINX_WINSETUP_TEST
    {
        char sched[256];
        int ready = ominx_sched_prepare("/", OMINX_SCHED_ROOT_DEFAULT, sched, sizeof sched);
        char line[400];
        snprintf(line, sizeof line, "OMINX_WINSETUP_SCHED %s %s", ready ? "unavailable" : "ready", sched);
        record(line);
    }
#endif
    char message[256];
    snprintf(message, sizeof message,
             "OMINX_WINSETUP_DONE runtime=%s version=%s binfmt=%d sysctl=%d marker=%d",
             runtime_state, runtime_version, !!(flags_bits & 1),
             !!(flags_bits & 2), !!(flags_bits & 4));
    record(message);
}
static void status(int client) {
    char reply[512];
    snprintf(reply, sizeof reply,
             "OK\nservice=ominx-winsetup\nprotocol=1\nstate=%s\nruntime=%s\nversion=%s\n"
             "binfmt=%d\nmax-map-count=%d\nmarker=%d\n",
             strcmp(runtime_state, "present") ? "runtime-missing" : "ready",
             runtime_state, runtime_version, !!(flags_bits & 1),
             !!(flags_bits & 2), !!(flags_bits & 4));
    (void)send(client, reply, strlen(reply), MSG_NOSIGNAL);
}

int main(int argc, char **argv) {
    const char *socket_path = OMINX_WINSETUP_SOCKET;
#ifdef OMINX_WINSETUP_TEST
    /* Host-only variant: socket and state live in a temporary directory. */
    if (argc != 3) { fputs("usage: ominx-winsetup-test SOCKET STATE_DIR\n", stderr); return 2; }
    socket_path = argv[1];
    if (snprintf(state_dir, sizeof state_dir, "%s", argv[2]) >= (int)sizeof state_dir ||
        snprintf(marker_path, sizeof marker_path, "%s/system-setup-v1", argv[2]) >= (int)sizeof marker_path ||
        snprintf(report_path, sizeof report_path, "%s/wine-runtime.conf", argv[2]) >= (int)sizeof report_path)
        return 2;
#else
    (void)argv;
    if (argc != 1 || getuid() || geteuid()) {
        fputs("ominx-winsetup requires the root service context\n", stderr);
        return 2;
    }
    if (mkdir("/run/ominx", 0755) && errno != EEXIST) { perror("service directory"); return 1; }
    if (mkdir("/var", 0755) && errno != EEXIST) { perror("/var"); return 1; }
    if (mkdir("/var/lib", 0755) && errno != EEXIST) { perror("/var/lib"); return 1; }
    if (mkdir("/var/lib/ominx", 0755) && errno != EEXIST) { perror("/var/lib/ominx"); return 1; }
    struct stat directory;
    if (lstat("/run/ominx", &directory) || !S_ISDIR(directory.st_mode) ||
        directory.st_uid || (directory.st_mode & 0022)) {
        fputs("Unsafe service directory\n", stderr);
        return 1;
    }
#endif
    int log_fd = -1;
#ifndef OMINX_WINSETUP_TEST
    log_fd = open("/run/ominx/winsetup.log", O_WRONLY | O_CREAT | O_APPEND, 0644);
    if (log_fd >= 0) { dup2(log_fd, 1); dup2(log_fd, 2); }
#endif
    (void)log_fd;
    setvbuf(stdout, NULL, _IOLBF, 0);
    system_setup();
    struct sockaddr_un address = {.sun_family = AF_UNIX};
    if (strlen(socket_path) >= sizeof address.sun_path) return 2;
    strcpy(address.sun_path, socket_path);
    struct stat existing;
    if (!lstat(socket_path, &existing)) {
        if (!S_ISSOCK(existing.st_mode)) { fputs("Refusing non-socket path\n", stderr); return 1; }
#ifndef OMINX_WINSETUP_TEST
        if (existing.st_uid) { fputs("Refusing non-owned socket\n", stderr); return 1; }
#endif
        int probe_fd = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0);
        if (probe_fd < 0) return 1;
        int connected = connect(probe_fd, (struct sockaddr *)&address, sizeof address);
        int saved = errno;
        close(probe_fd);
        if (!connected || saved != ECONNREFUSED) { fputs("winsetup already running\n", stderr); return 1; }
        if (unlink(socket_path)) return 1;
    } else if (errno != ENOENT) return 1;
    umask(077);
    int server = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0);
    if (server < 0 || bind(server, (struct sockaddr *)&address, sizeof address)) {
        perror("winsetup bind"); return 1;
    }
#ifndef OMINX_WINSETUP_TEST
    if (chown(socket_path, 0, OMINX_GID)) { perror("winsetup ownership"); return 1; }
#endif
    if (chmod(socket_path, 0660) || listen(server, 8)) { perror("winsetup listen"); return 1; }
    signal(SIGPIPE, SIG_IGN);
    for (;;) {
        int client = accept4(server, NULL, NULL, SOCK_CLOEXEC);
        if (client < 0) { if (errno == EINTR) continue; return 1; }
        struct timeval timeout = {1, 0};
        setsockopt(client, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof timeout);
        struct ucred peer;
        socklen_t size = sizeof peer;
        uid_t allowed = OMINX_UID;
#ifdef OMINX_WINSETUP_TEST
        allowed = getuid();
#endif
        if (getsockopt(client, SOL_SOCKET, SO_PEERCRED, &peer, &size) ||
            (peer.uid && peer.uid != allowed && peer.uid != getuid())) {
            close(client);
            continue;
        }
        char request[64];
        ssize_t count = recv(client, request, sizeof request, MSG_TRUNC);
        if (count == 7 && !memcmp(request, "STATUS\n", 7)) status(client);
        else if (count == 8 && !memcmp(request, "RECHECK\n", 8)) { system_setup(); status(client); }
        else (void)send(client, "ERR invalid-request\n", 20, MSG_NOSIGNAL);
        close(client);
    }
}
