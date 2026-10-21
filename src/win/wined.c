/* Original per-user Windows compatibility service.
 *
 * One instance per signed-in user, started in the background by the seat at
 * graphical login (or on demand by the ominx-win console client). On first
 * start it creates the user's Wine prefix without any dialogs, installs the
 * runtime's DXVK/vkd3d-proton DLLs, precreates the default Proton prefix and
 * then keeps a persistent wineserver so launching a Windows program is as
 * fast as a native one. The root setup service never runs Windows code;
 * everything here runs only with the owning user's privileges and Wine is
 * not a sandbox. See docs/windows-compatibility.md. */
#define _GNU_SOURCE
#include "../lib/pe.h"
#include "../lib/winproto.h"
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <poll.h>
#include <signal.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <unistd.h>

#define PATHBUF 4096
enum state { ST_RUNTIME_MISSING, ST_PENDING, ST_SETTING_UP, ST_READY, ST_FAILED };

static struct {
    int present, dxvk, vkd3d;
    char root[PATHBUF], wine[PATHBUF], wineserver[PATHBUF], version[65];
} runtime;
static char home_dir[PATHBUF], prefix[PATHBUF], proton_base[PATHBUF];
static char log_path[PATHBUF], socket_path[PATHBUF];
static enum state state = ST_PENDING;
static int step_percent;
static char step_name[64] = "waiting";
static char failure[96] = "";
static pid_t worker = -1, wineserver_pid = -1;
static int worker_pipe = -1, worker_proton;
static char worker_prefix[PATHBUF], worker_appid[40];
static char proton_setup[16] = "idle";
static struct { pid_t pid; char what[128]; } running[OMINX_WIN_MAX_RUNNING];
static int last_exit = -1, stopping;

static int join(char *out, size_t capacity, const char *a, const char *b) {
    size_t a_length = strlen(a), b_length = strlen(b);
    int slash = a_length && a[a_length - 1] != '/';
    if (a_length + (size_t)slash + b_length + 1 > capacity) {
        errno = ENAMETOOLONG;
        return -1;
    }
    memcpy(out, a, a_length);
    if (slash) out[a_length++] = '/';
    memcpy(out + a_length, b, b_length + 1);
    return 0;
}
static int mkdir_p(const char *path) {
    char copy[PATHBUF];
    if (strlen(path) >= sizeof copy) { errno = ENAMETOOLONG; return -1; }
    strcpy(copy, path);
    for (char *p = copy + 1; *p; p++) {
        if (*p == '/') {
            *p = 0;
            if (mkdir(copy, 0700) && errno != EEXIST) return -1;
            *p = '/';
        }
    }
    if (mkdir(copy, 0700) && errno != EEXIST) return -1;
    return 0;
}
static int copy_replace(const char *source, const char *destination) {
    int in = open(source, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (in < 0) return -1;
    char temporary[PATHBUF];
    size_t destination_length = strlen(destination);
    if (destination_length + 11 > sizeof temporary) {
        close(in); errno = ENAMETOOLONG; return -1;
    }
    memcpy(temporary, destination, destination_length);
    memcpy(temporary + destination_length, ".ominx-new", 11);
    int out = open(temporary, O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0644);
    if (out < 0) { int saved = errno; close(in); errno = saved; return -1; }
    char buffer[65536];
    int result = -1;
    for (;;) {
        ssize_t count = read(in, buffer, sizeof buffer);
        if (count < 0) { if (errno == EINTR) continue; break; }
        if (!count) { result = 0; break; }
        ssize_t done = 0;
        while (done < count) {
            ssize_t written = write(out, buffer + done, (size_t)(count - done));
            if (written < 0) { if (errno == EINTR) continue; break; }
            done += written;
        }
        if (done != count) break;
    }
    int saved = errno;
    if (!result && (fsync(out) || rename(temporary, destination))) result = -1, saved = errno;
    close(out); close(in);
    if (result) unlink(temporary);
    errno = saved;
    return result;
}
static void record(const char *format, ...) {
    va_list args;
    va_start(args, format);
    vfprintf(stderr, format, args);
    va_end(args);
    fputc('\n', stderr);
    fflush(stderr);
}

/* Runtime discovery: a fixed prefix on the target. The host-test build may
   point at a stub runtime instead; it is never packaged. */
static void detect_runtime(void) {
    const char *root = OMINX_WINE_RUNTIME;
#ifdef OMINX_WINED_TEST
    const char *override = getenv("OMINX_WINE_RUNTIME_DIR");
    if (override && *override) root = override;
#endif
    snprintf(runtime.root, sizeof runtime.root, "%s", root);
    join(runtime.wine, sizeof runtime.wine, root, "bin/wine");
    join(runtime.wineserver, sizeof runtime.wineserver, root, "bin/wineserver");
    char version_file[PATHBUF], directory[PATHBUF];
    runtime.present = !access(runtime.wine, X_OK);
#ifndef OMINX_WINED_TEST
    join(directory, sizeof directory, root, OMINX_WINE_LOADER);
    if (access(directory, X_OK)) runtime.present = 0;
#endif
    join(version_file, sizeof version_file, root, "VERSION");
    FILE *file = fopen(version_file, "r");
    if (file) {
        if (!fgets(runtime.version, sizeof runtime.version, file))
            runtime.version[0] = 0;
        runtime.version[strcspn(runtime.version, "\r\n")] = 0;
        fclose(file);
    }
    if (!runtime.version[0]) snprintf(runtime.version, sizeof runtime.version, "%s", "unknown");
    join(directory, sizeof directory, root, "share/dxvk/x64/d3d11.dll");
    runtime.dxvk = runtime.present && !access(directory, R_OK);
    join(directory, sizeof directory, root, "share/vkd3d-proton/x64/d3d12.dll");
    runtime.vkd3d = runtime.present && !access(directory, R_OK);
    if (access(runtime.wineserver, X_OK)) /* wine binary provides the builtin. */
        snprintf(runtime.wineserver, sizeof runtime.wineserver, "%s", runtime.wine);
}
static int marker_ready(const char *target_prefix) {
    char marker[PATHBUF];
    if (join(marker, sizeof marker, target_prefix, OMINX_WINE_MARKER)) return 0;
    FILE *file = fopen(marker, "r");
    if (!file) return 0;
    char line[128] = "";
    int ok = fgets(line, sizeof line, file) != NULL;
    fclose(file);
    line[strcspn(line, "\r\n")] = 0;
    return ok && !strcmp(line, runtime.version);
}
static void wine_env(const char *target_prefix, int quiet) {
    setenv("WINEPREFIX", target_prefix, 1);
    setenv("WINEARCH", "win64", 1);
    /* Blank overrides disable Wine Mono/Gecko: first setup must never block
       on a download dialog. .NET/HTML components are an explicit later opt-in. */
    setenv("WINEDLLOVERRIDES", "mscoree,mshtml=", 1);
    setenv("WINEDEBUG", quiet ? "-all" : "fixme-all", 1);
    setenv("WINEESYNC", "1", 1);
    setenv("WINEFSYNC", "1", 1);
    setenv("WINE_LARGE_ADDRESS_AWARE", "1", 1);
    struct rlimit limit;
    if (!getrlimit(RLIMIT_NOFILE, &limit)) {
        /* esync spends one eventfd per synchronization object. */
        rlim_t wanted = 1048576;
        limit.rlim_cur = limit.rlim_max < wanted ? limit.rlim_max : wanted;
        if (setrlimit(RLIMIT_NOFILE, &limit)) { /* wine still runs with the inherited limit */ }
    }
}
/* Runs one runtime command to completion in this (worker) process context. */
static int run_wait(char *const argv[], const char *target_prefix) {
    pid_t pid = fork();
    if (pid == 0) {
        int log = open(log_path, O_WRONLY | O_CREAT | O_APPEND, 0600);
        if (log >= 0) { dup2(log, 1); dup2(log, 2); if (log > 2) close(log); }
        wine_env(target_prefix, 1);
        execv(argv[0], argv);
        _exit(127);
    }
    if (pid < 0) return -1;
    int status;
    while (waitpid(pid, &status, 0) < 0) if (errno != EINTR) return -1;
    return WIFEXITED(status) ? WEXITSTATUS(status) : 128;
}
static void progress(int pipe_fd, int percent, const char *step) {
    dprintf(pipe_fd, "%d %s\n", percent, step);
}
static int install_dll_set(const char *runtime_dir, const char *system_dir,
                           const char *const names[]) {
    int installed = 0;
    for (int i = 0; names[i]; i++) {
        char source[PATHBUF], destination[PATHBUF];
        if (join(source, sizeof source, runtime_dir, names[i]) || access(source, R_OK)) continue;
        if (mkdir_p(system_dir) || join(destination, sizeof destination, system_dir, names[i]) ||
            copy_replace(source, destination)) return -1;
        installed = 1;
    }
    return installed;
}
static int reg_native(const char *target_prefix, const char *name) {
    char value[160];
    snprintf(value, sizeof value, "native");
    char *argv[] = {runtime.wine, "reg", "add",
                    "HKCU\\Software\\Wine\\DllOverrides", "/v", (char *)name,
                    "/d", value, "/f", NULL};
    return run_wait(argv, target_prefix);
}
/* Worker process: performs a complete silent prefix setup. Progress is
   reported as text lines so the parent stays responsive to STATUS. */
static void setup_worker(int pipe_fd, const char *target_prefix, int proton) {
    char path[PATHBUF], other[PATHBUF];
    progress(pipe_fd, 5, "directories");
    if (mkdir_p(target_prefix)) _exit(10);
    if (!proton) {
        /* ~/.wine compatibility link for traditional Wine tooling. */
        join(path, sizeof path, home_dir, ".wine");
        struct stat st;
        if (lstat(path, &st) && errno == ENOENT && symlink(target_prefix, path) && errno != EEXIST)
            record("ominx-wined: ~/.wine link failed (%s)", strerror(errno));
    }
    progress(pipe_fd, 20, "wineboot");
    char *boot[] = {runtime.wine, "wineboot", "--init", NULL};
    if (run_wait(boot, target_prefix)) _exit(11);
    progress(pipe_fd, 55, "prefix-sync");
    const int builtin = !strcmp(runtime.wineserver, runtime.wine);
    char *wait_server[] = {runtime.wineserver, "-w", NULL};
    char *wait_builtin[] = {runtime.wine, "wineserver", "-w", NULL};
    if (run_wait(builtin ? wait_builtin : wait_server, target_prefix)) _exit(12);
    static const char *const dxvk64[] = {"d3d8.dll", "d3d9.dll", "d3d10core.dll",
                                         "d3d11.dll", "dxgi.dll", NULL};
    static const char *const vkd3d[] = {"d3d12.dll", "d3d12core.dll", NULL};
    static const char *const overrides[] = {"d3d9", "d3d10core", "d3d11", "dxgi",
                                            "d3d12", "d3d12core", NULL};
    if (runtime.dxvk || runtime.vkd3d) {
        progress(pipe_fd, 70, "graphics-dlls");
        struct { const char *share; const char *const *names; } sets[4] = {
            {"share/dxvk/x64", dxvk64}, {"share/dxvk/x32", dxvk64},
            {"share/vkd3d-proton/x64", vkd3d}, {"share/vkd3d-proton/x86", vkd3d}};
        static const char *const targets[4] = {
            "drive_c/windows/system32", "drive_c/windows/syswow64",
            "drive_c/windows/system32", "drive_c/windows/syswow64"};
        for (int i = 0; i < 4; i++) {
            join(path, sizeof path, runtime.root, sets[i].share);
            join(other, sizeof other, target_prefix, targets[i]);
            if (install_dll_set(path, other, sets[i].names) < 0) _exit(13);
        }
        for (int i = 0; overrides[i]; i++) (void)reg_native(target_prefix, overrides[i]);
    }
    progress(pipe_fd, 90, "finalize");
    join(path, sizeof path, target_prefix, OMINX_WINE_MARKER);
    FILE *marker = fopen(path, "w");
    if (!marker) _exit(14);
    fprintf(marker, "%s\nominx-setup=%s\nproton=%d\n", runtime.version,
            OMINX_WIN_SETUP_VERSION, proton);
    if (fclose(marker)) _exit(14);
    progress(pipe_fd, 100, "ready");
    _exit(0);
}
static int start_setup(const char *target_prefix, int proton, const char *appid) {
    if (!runtime.present || worker > 0) return -1;
    int fds[2];
    if (pipe(fds)) return -1;
    pid_t pid = fork();
    if (pid == 0) {
        close(fds[0]);
        setup_worker(fds[1], target_prefix, proton);
    }
    close(fds[1]);
    if (pid < 0) { close(fds[0]); return -1; }
    worker = pid;
    worker_pipe = fds[0];
    worker_proton = proton;
    snprintf(worker_prefix, sizeof worker_prefix, "%s", target_prefix);
    snprintf(worker_appid, sizeof worker_appid, "%s", appid ? appid : "");
    int flags = fcntl(worker_pipe, F_GETFL);
    if (flags >= 0 && fcntl(worker_pipe, F_SETFL, flags | O_NONBLOCK)) { /* progress read would block */ }
    if (proton) snprintf(proton_setup, sizeof proton_setup, "%s", "running");
    else { state = ST_SETTING_UP; step_percent = 0; snprintf(step_name, sizeof step_name, "%s", "starting"); }
    return 0;
}
static void start_wineserver(void) {
    if (!runtime.present || wineserver_pid > 0) return;
    pid_t pid = fork();
    if (pid == 0) {
        int log = open(log_path, O_WRONLY | O_CREAT | O_APPEND, 0600);
        int null = open("/dev/null", O_RDONLY);
        if (null >= 0) dup2(null, 0);
        if (log >= 0) { dup2(log, 1); dup2(log, 2); }
        wine_env(prefix, 1);
        /* Foreground + persistent: supervised here, survives across launches. */
        char *argv[] = {runtime.wineserver, "-f", "-p", NULL};
        char *builtin[] = {runtime.wine, "wineserver", "-f", "-p", NULL};
        execv(argv[0], !strcmp(runtime.wineserver, runtime.wine) ? builtin : argv);
        _exit(127);
    }
    if (pid > 0) wineserver_pid = pid;
}
static const char *state_name(void) {
    switch (state) {
        case ST_RUNTIME_MISSING: return "runtime-missing";
        case ST_SETTING_UP: return "setting-up";
        case ST_READY: return "ready";
        case ST_FAILED: return "failed";
        default: return "pending";
    }
}
static void append(char *reply, size_t capacity, size_t *used, const char *format, ...) {
    if (*used >= capacity) return;
    va_list args;
    va_start(args, format);
    int written = vsnprintf(reply + *used, capacity - *used, format, args);
    va_end(args);
    if (written > 0) *used += (size_t)written < capacity - *used ? (size_t)written : capacity - *used - 1;
}
static int running_count(void) {
    int count = 0;
    for (int i = 0; i < OMINX_WIN_MAX_RUNNING; i++) if (running[i].pid > 0) count++;
    return count;
}
static void status_reply(char *reply, size_t capacity) {
    size_t used = 0;
    char default_pfx[PATHBUF];
    join(default_pfx, sizeof default_pfx, proton_base, "default/pfx");
    append(reply, capacity, &used,
           "OK\nservice=ominx-wined\nprotocol=1\nstate=%s\nstep=%s\npercent=%d\n"
           "runtime=%s\nversion=%s\ndxvk=%d\nvkd3d-proton=%d\nprefix=%s\n"
           "wineserver=%s\nrunning=%d\nlast-exit=%d\nproton-default=%s\n"
           "proton-setup=%s\n",
           state_name(), step_name, step_percent, runtime.present ? "present" : "missing",
           runtime.version, runtime.dxvk, runtime.vkd3d, prefix,
           wineserver_pid > 0 ? "running" : "stopped", running_count(), last_exit,
           marker_ready(default_pfx) ? "ready" : "absent", proton_setup);
    if (failure[0]) append(reply, capacity, &used, "error=%s\n", failure);
    append(reply, capacity, &used, "pids=");
    int first = 1;
    for (int i = 0; i < OMINX_WIN_MAX_RUNNING; i++)
        if (running[i].pid > 0) {
            append(reply, capacity, &used, "%s%ld", first ? "" : ",", (long)running[i].pid);
            first = 0;
        }
    append(reply, capacity, &used, "\n");
}
static void scan_apps(const char *directory, int depth, char *reply, size_t capacity,
                      size_t *used, int *found) {
    if (depth < 0 || *found >= OMINX_WIN_MAX_APPS) return;
    DIR *dir = opendir(directory);
    if (!dir) return;
    struct dirent *entry;
    while ((entry = readdir(dir)) && *found < OMINX_WIN_MAX_APPS) {
        if (entry->d_name[0] == '.') continue;
        char path[PATHBUF];
        if (join(path, sizeof path, directory, entry->d_name)) continue;
        struct stat st;
        if (lstat(path, &st)) continue;
        if (S_ISDIR(st.st_mode)) {
            if (!strcmp(entry->d_name, "Common Files")) continue;
            scan_apps(path, depth - 1, reply, capacity, used, found);
        } else if (S_ISREG(st.st_mode) && ominx_pe_suffix(entry->d_name) == 1) {
            int clean = 1;
            for (const char *p = entry->d_name; *p; p++)
                if (*p == '\t' || *p == '\n') clean = 0;
            if (clean) {
                append(reply, capacity, used, "APP\t%s\t%s\n", entry->d_name, path);
                (*found)++;
            }
        }
    }
    closedir(dir);
}
static int valid_field(const char *field, int path) {
    size_t length = strlen(field);
    if (!length || length > (path ? (size_t)PATHBUF - 1 : (size_t)OMINX_WIN_MAX_ARG)) return 0;
    if (path && field[0] != '/') return 0;
    for (size_t i = 0; i < length; i++)
        if ((unsigned char)field[i] < 0x20 || field[i] == 0x7f) return 0;
    return 1;
}
static int valid_appid(const char *field) {
    size_t length = strlen(field);
    if (!length || length > 32) return 0;
    for (size_t i = 0; i < length; i++) {
        char c = field[i];
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
              (c >= '0' && c <= '9') || c == '-' || c == '_')) return 0;
    }
    return 1;
}
/* Launches under the selected prefix. The file has already been inspected. */
static pid_t launch(const char *target_prefix, const char *file, char *const args[],
                    int count, int msi, int proton, const char *appid) {
    pid_t pid = fork();
    if (pid != 0) return pid;
    char directory[PATHBUF];
    snprintf(directory, sizeof directory, "%s", file);
    char *slash = strrchr(directory, '/');
    if (slash && slash != directory) *slash = 0;
    else snprintf(directory, sizeof directory, "%s", "/");
    if (chdir(directory)) _exit(126); /* Installers expect their own folder. */
    int log = open(log_path, O_WRONLY | O_CREAT | O_APPEND, 0600);
    if (log >= 0) { dup2(log, 1); dup2(log, 2); if (log > 2) close(log); }
    wine_env(target_prefix, 0);
    if (proton) {
        char compatdata[PATHBUF], steam[PATHBUF];
        if (join(compatdata, sizeof compatdata, proton_base, appid)) _exit(127);
        setenv("STEAM_COMPAT_DATA_PATH", compatdata, 1);
        join(steam, sizeof steam, home_dir, ".steam/steam");
        setenv("STEAM_COMPAT_CLIENT_INSTALL_PATH", steam, 1);
        setenv("SteamAppId", appid, 1);
        setenv("SteamGameId", appid, 1);
        setenv("PROTON_LOG", "0", 1);
    }
    char *argv[4 + OMINX_WIN_MAX_ARGS + 1];
    int at = 0;
    argv[at++] = runtime.wine;
    if (msi) { argv[at++] = "msiexec"; argv[at++] = "/i"; }
    argv[at++] = (char *)file;
    for (int i = 0; i < count; i++) argv[at++] = args[i];
    argv[at] = NULL;
    execv(argv[0], argv);
    _exit(127);
}
static void track(pid_t pid, const char *file) {
    for (int i = 0; i < OMINX_WIN_MAX_RUNNING; i++)
        if (!running[i].pid) {
            running[i].pid = pid;
            const char *name = strrchr(file, '/');
            snprintf(running[i].what, sizeof running[i].what, "%s", name ? name + 1 : file);
            return;
        }
}
/* Splits one request packet in place on tabs. Returns field count or -1. */
static int split(char *request, ssize_t size, char *fields[], int max) {
    if (size <= 0 || size > OMINX_WIN_MAX_REQUEST || request[size - 1] != '\n') return -1;
    request[size - 1] = 0;
    int count = 0;
    char *at = request;
    for (;;) {
        if (count >= max) return -1;
        fields[count++] = at;
        char *tab = strchr(at, '\t');
        if (!tab) break;
        *tab = 0;
        at = tab + 1;
    }
    for (int i = 0; i < count; i++) if (!fields[i][0]) return -1;
    return count;
}
static void handle(int client, char *request, ssize_t size) {
    char reply[16384];
    char *fields[3 + OMINX_WIN_MAX_ARGS];
    int count = split(request, size, fields, 3 + OMINX_WIN_MAX_ARGS);
    size_t used = 0;
    const char *out = reply;
    if (count < 0) { out = "ERR invalid-request\n"; goto send; }
    if (!strcmp(fields[0], "STATUS") && count == 1) { status_reply(reply, sizeof reply); goto send; }
    if (!strcmp(fields[0], "QUIT") && count == 1) {
        out = "OK bye\n"; stopping = 1; goto send;
    }
    if (!strcmp(fields[0], "SETUP") && count == 1) {
        if (!runtime.present) { out = "ERR runtime-missing\n"; goto send; }
        if (state == ST_READY && marker_ready(prefix)) { out = "OK already-ready\n"; goto send; }
        if (worker > 0) { out = "OK already-running\n"; goto send; }
        if (start_setup(prefix, 0, "")) { out = "ERR setup-failed-to-start\n"; goto send; }
        out = "OK setup-started\n"; goto send;
    }
    if (!strcmp(fields[0], "APPS") && count == 1) {
        append(reply, sizeof reply, &used, "OK\n");
        int found = 0;
        char root[PATHBUF];
        join(root, sizeof root, prefix, "drive_c/Program Files");
        scan_apps(root, 3, reply, sizeof reply, &used, &found);
        join(root, sizeof root, prefix, "drive_c/Program Files (x86)");
        scan_apps(root, 3, reply, sizeof reply, &used, &found);
        append(reply, sizeof reply, &used, "END count=%d\n", found);
        goto send;
    }
    if (!strcmp(fields[0], "PROBE") && count == 2 && valid_field(fields[1], 1)) {
        struct ominx_pe_info info;
        int result = ominx_pe_inspect_path(fields[1], &info);
        if (result == -2) { out = "ERR unreadable\n"; goto send; }
        append(reply, sizeof reply, &used,
               "OK\nkind=%s\narch=%s\nbits=%d\nsubsystem=%s\ndotnet=%d\nsections=%u\nsize=%llu\n",
               ominx_pe_kind_name(info.kind), ominx_pe_arch_name(info.arch),
               info.bits, info.subsystem == 2 ? "gui" : info.subsystem == 3 ? "console" : "other",
               info.dotnet, info.sections, info.file_size);
        if (result) append(reply, sizeof reply, &used, "error=%s\n", info.error);
        goto send;
    }
    if (!strcmp(fields[0], "STOP") && count == 1) {
        if (wineserver_pid > 0) kill(wineserver_pid, SIGTERM);
        out = "OK stopping\n"; goto send;
    }
    if (!strcmp(fields[0], "PROTONSETUP") && count == 2 && valid_appid(fields[1])) {
        if (!runtime.present) { out = "ERR runtime-missing\n"; goto send; }
        char pfx[PATHBUF], appdir[PATHBUF];
        if (join(appdir, sizeof appdir, proton_base, fields[1]) ||
            join(pfx, sizeof pfx, appdir, "pfx")) {
            out = "ERR path-too-long\n"; goto send;
        }
        if (marker_ready(pfx)) { out = "OK already-ready\n"; goto send; }
        if (worker > 0) { out = "OK already-running\n"; goto send; }
        if (start_setup(pfx, 1, fields[1])) { out = "ERR setup-failed-to-start\n"; goto send; }
        out = "OK setup-started\n"; goto send;
    }
    if (!strcmp(fields[0], "RUN") || !strcmp(fields[0], "MSI") || !strcmp(fields[0], "PROTON")) {
        int proton = !strcmp(fields[0], "PROTON");
        int msi = !strcmp(fields[0], "MSI");
        int file_at = proton ? 2 : 1;
        if (count <= file_at || count - file_at - 1 > OMINX_WIN_MAX_ARGS) {
            out = "ERR invalid-request\n"; goto send;
        }
        if (!runtime.present) { out = "ERR runtime-missing\n"; goto send; }
        if (proton && !valid_appid(fields[1])) { out = "ERR bad-app-id\n"; goto send; }
        if (!valid_field(fields[file_at], 1)) { out = "ERR bad-path\n"; goto send; }
        for (int i = file_at + 1; i < count; i++)
            if (!valid_field(fields[i], 0)) { out = "ERR bad-argument\n"; goto send; }
        char pfx[PATHBUF];
        if (proton) {
            char appdir[PATHBUF];
            if (join(appdir, sizeof appdir, proton_base, fields[1]) ||
                join(pfx, sizeof pfx, appdir, "pfx")) { out = "ERR path-too-long\n"; goto send; }
            if (!marker_ready(pfx)) {
                if (worker < 0) (void)start_setup(pfx, 1, fields[1]);
                out = "ERR prefix-not-ready\n"; goto send;
            }
        } else {
            if (state != ST_READY) {
                if (worker < 0 && state != ST_FAILED) (void)start_setup(prefix, 0, "");
                out = "ERR prefix-not-ready\n"; goto send;
            }
            snprintf(pfx, sizeof pfx, "%s", prefix);
        }
        struct ominx_pe_info info;
        int result = ominx_pe_inspect_path(fields[file_at], &info);
        if (result == -2) { out = "ERR unreadable\n"; goto send; }
        if (result) {
            append(reply, sizeof reply, &used, "ERR invalid-file-%s\n", info.error); goto send;
        }
        if (msi && info.kind != OMINX_PE_MSI) { out = "ERR not-an-msi\n"; goto send; }
        if (!msi && info.kind == OMINX_PE_MSI) { out = "ERR use-msi-for-installers\n"; goto send; }
        if (!msi && info.kind == OMINX_PE_DLL) { out = "ERR dlls-are-not-programs\n"; goto send; }
        if (!msi && info.kind != OMINX_PE_EXE) { out = "ERR not-a-windows-program\n"; goto send; }
        if (!msi && info.arch != OMINX_PE_ARCH_I386 && info.arch != OMINX_PE_ARCH_AMD64) {
            out = "ERR unsupported-architecture\n"; goto send;
        }
        if (running_count() >= OMINX_WIN_MAX_RUNNING) { out = "ERR too-many-programs\n"; goto send; }
        pid_t pid = launch(pfx, fields[file_at], fields + file_at + 1,
                           count - file_at - 1, msi, proton, proton ? fields[1] : "");
        if (pid < 0) { out = "ERR launch-failed\n"; goto send; }
        track(pid, fields[file_at]);
        append(reply, sizeof reply, &used, "OK pid=%ld dotnet=%d\n", (long)pid, info.dotnet);
        goto send;
    }
    out = "ERR invalid-request\n";
send:;
    size_t length = strlen(out);
    struct timeval timeout = {2, 0};
    setsockopt(client, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof timeout);
    (void)send(client, out, length, MSG_NOSIGNAL);
}
static void reap(void) {
    for (;;) {
        int status;
        pid_t ended = waitpid(-1, &status, WNOHANG);
        if (ended <= 0) break;
        if (ended == worker) {
            worker = -1;
            int code = WIFEXITED(status) ? WEXITSTATUS(status) : 128;
            if (worker_proton) {
                snprintf(proton_setup, sizeof proton_setup, "%s", code ? "failed" : "idle");
                record("ominx-wined: proton prefix %s setup %s (code %d)",
                       worker_appid, code ? "failed" : "ready", code);
            } else if (code) {
                state = ST_FAILED;
                snprintf(failure, sizeof failure, "setup-step-%d", code);
                snprintf(step_name, sizeof step_name, "%s", "failed");
                record("ominx-wined: setup failed at step code %d, see %s", code, log_path);
            } else {
                state = ST_READY;
                step_percent = 100;
                snprintf(step_name, sizeof step_name, "%s", "ready");
                failure[0] = 0;
                record("OMINX_WINE_READY prefix=%s", prefix);
                start_wineserver();
                /* Precreate the default Proton prefix in the background so
                   the first game or non-Steam title does not wait for it. */
                char pfx[PATHBUF];
                join(pfx, sizeof pfx, proton_base, "default/pfx");
                if (!marker_ready(pfx)) (void)start_setup(pfx, 1, "default");
            }
        } else if (ended == wineserver_pid) {
            wineserver_pid = -1;
        } else {
            for (int i = 0; i < OMINX_WIN_MAX_RUNNING; i++)
                if (running[i].pid == ended) {
                    running[i].pid = 0;
                    last_exit = WIFEXITED(status) ? WEXITSTATUS(status) : 128;
                    record("ominx-wined: %s exited %d", running[i].what, last_exit);
                }
        }
    }
}
static void read_progress(void) {
    if (worker_pipe < 0) return;
    char buffer[512];
    ssize_t count = read(worker_pipe, buffer, sizeof buffer - 1);
    if (count <= 0) {
        if (count == 0) { close(worker_pipe); worker_pipe = -1; }
        return;
    }
    buffer[count] = 0;
    char *line = strtok(buffer, "\n");
    while (line) {
        int percent;
        char step[64];
        if (sscanf(line, "%d %63s", &percent, step) == 2 && !worker_proton) {
            step_percent = percent;
            snprintf(step_name, sizeof step_name, "%s", step);
        }
        line = strtok(NULL, "\n");
    }
}
static void stop(int signal) { (void)signal; stopping = 1; }

int main(int argc, char **argv) {
#ifdef OMINX_WINED_TEST
    if (argc != 2) { fputs("usage: ominx-wined-test SOCKET\n", stderr); return 2; }
    snprintf(socket_path, sizeof socket_path, "%s", argv[1]);
    const char *runtime_override = getenv("OMINX_WINE_RUNTIME_DIR");
    (void)runtime_override;
#else
    (void)argv;
    if (argc != 1) { fputs("ominx-wined takes no arguments\n", stderr); return 2; }
    if (!geteuid()) { fputs("ominx-wined: never run Windows programs as root\n", stderr); return 2; }
    const char *socket_env = getenv(OMINX_WINED_SOCKET_ENV);
    const char *runtime_dir = getenv("XDG_RUNTIME_DIR");
    if (socket_env && *socket_env) snprintf(socket_path, sizeof socket_path, "%s", socket_env);
    else if (runtime_dir && *runtime_dir)
        join(socket_path, sizeof socket_path, runtime_dir, OMINX_WINED_SOCKET_NAME);
    else { fputs("ominx-wined: no runtime directory\n", stderr); return 2; }
#endif
    const char *home = getenv("HOME");
    if (!home || home[0] != '/') { fputs("ominx-wined: HOME is not set\n", stderr); return 2; }
    snprintf(home_dir, sizeof home_dir, "%s", home);
    const char *preset = getenv("WINEPREFIX");
#ifdef OMINX_WINED_TEST
    const char *test_prefix = getenv("OMINX_WINEPREFIX");
    if (test_prefix && *test_prefix) preset = test_prefix;
#endif
    if (preset && preset[0] == '/') snprintf(prefix, sizeof prefix, "%s", preset);
    else join(prefix, sizeof prefix, home_dir, OMINX_WINE_PREFIX_REL);
#ifdef OMINX_WINED_TEST
    const char *test_proton = getenv("OMINX_PROTON_DIR");
    if (test_proton && *test_proton) snprintf(proton_base, sizeof proton_base, "%s", test_proton);
    else
#endif
    join(proton_base, sizeof proton_base, home_dir, OMINX_PROTON_REL);
    char log_dir[PATHBUF];
    join(log_path, sizeof log_path, home_dir, OMINX_WINE_LOG_REL);
    join(log_dir, sizeof log_dir, home_dir, ".local/share/ominx/wine/logs");
    if (mkdir_p(log_dir) || mkdir_p(proton_base)) { perror("ominx-wined directories"); return 1; }
    detect_runtime();
    if (!runtime.present) state = ST_RUNTIME_MISSING;
    else if (marker_ready(prefix)) state = ST_READY;
    record("OMINX_WINED_START runtime=%s version=%s state=%s prefix=%s",
           runtime.present ? "present" : "missing", runtime.version, state_name(), prefix);

    struct sockaddr_un address = {.sun_family = AF_UNIX};
    if (strlen(socket_path) >= sizeof address.sun_path) return 2;
    strcpy(address.sun_path, socket_path);
    struct stat existing;
    if (!lstat(socket_path, &existing)) {
        if (!S_ISSOCK(existing.st_mode)) { fputs("Refusing to replace non-socket\n", stderr); return 1; }
        int probe_socket = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0);
        if (probe_socket < 0) return 1;
        int connected = connect(probe_socket, (struct sockaddr *)&address, sizeof address);
        int saved = errno;
        close(probe_socket);
        if (!connected || saved != ECONNREFUSED) { fputs("ominx-wined already running\n", stderr); return 1; }
        if (unlink(socket_path)) return 1;
    } else if (errno != ENOENT) return 1;
    umask(077);
    int server = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0);
    if (server < 0 || bind(server, (struct sockaddr *)&address, sizeof address)) {
        perror("ominx-wined bind"); return 1;
    }
    if (chmod(socket_path, 0600) || listen(server, 8)) { perror("ominx-wined listen"); return 1; }
    signal(SIGPIPE, SIG_IGN);
    struct sigaction action = {.sa_handler = stop, .sa_flags = 0};
    sigemptyset(&action.sa_mask);
    sigaction(SIGTERM, &action, NULL);
    sigaction(SIGINT, &action, NULL);
    /* The defining behavior: a fresh prefix sets itself up at first login,
       in the background, before the user opens a single Windows program. */
    if (state == ST_READY) start_wineserver();
    else if (runtime.present) (void)start_setup(prefix, 0, "");
    while (!stopping) {
        reap();
        read_progress();
        struct pollfd listening = {.fd = server, .events = POLLIN};
        int ready = poll(&listening, 1, 200);
        if (ready < 0) { if (errno == EINTR) continue; break; }
        if (!ready || !(listening.revents & POLLIN)) continue;
        int client = accept4(server, NULL, NULL, SOCK_CLOEXEC);
        if (client < 0) continue;
        struct ucred peer;
        socklen_t size = sizeof peer;
        struct timeval timeout = {2, 0};
        setsockopt(client, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof timeout);
        if (getsockopt(client, SOL_SOCKET, SO_PEERCRED, &peer, &size) || peer.uid != geteuid()) {
            close(client);
            continue;
        }
        char request[OMINX_WIN_MAX_REQUEST + 1];
        ssize_t count = recv(client, request, OMINX_WIN_MAX_REQUEST, MSG_TRUNC);
        if (count > 0) { request[count <= OMINX_WIN_MAX_REQUEST ? count : OMINX_WIN_MAX_REQUEST] = 0; handle(client, request, count); }
        close(client);
    }
    if (wineserver_pid > 0) kill(wineserver_pid, SIGTERM);
    for (int i = 0; i < OMINX_WIN_MAX_RUNNING; i++)
        if (running[i].pid > 0) kill(running[i].pid, SIGTERM);
    unlink(socket_path);
    close(server);
    return 0;
}
