/* Original single-seat display manager. Starts the themed greeter as an
   unprivileged service account, asks the authentication broker for the one
   pending verified session, runs that fixed session program as the user, and
   returns to the greeter on logout. No shells, paths or arguments from
   callers are ever executed. */
#define _GNU_SOURCE
#include "login.h"
#include "../lib/control.h"
#include "../lib/session.h"
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <linux/kd.h>
#include <signal.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/ioctl.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <sys/vt.h>
#include <sys/wait.h>
#include <unistd.h>

static volatile sig_atomic_t stopping;
static pid_t child_pid = -1;
static void stop(int signal) {
    (void)signal;
    stopping = 1;
    if (child_pid > 0) kill(child_pid, SIGTERM);
}
/* No SA_RESTART: waitpid and read must return EINTR for prompt shutdown. */
static void handle_stop(void) {
    struct sigaction action = {.sa_handler = stop, .sa_flags = 0};
    sigemptyset(&action.sa_mask);
    sigaction(SIGTERM, &action, NULL);
    sigaction(SIGINT, &action, NULL);
}
static void log_event(const char *format, ...) {
    va_list list;
    va_start(list, format);
    vprintf(format, list);
    va_end(list);
    fputc('\n', stdout);
    fflush(stdout);
}
static int source_boot(void) {
    char path[128];
    ssize_t length = readlink("/proc/1/exe", path, sizeof path - 1);
    if (length < 0) return 0;
    path[length] = 0;
    return !strcmp(path, "/init");
}
static int directory(const char *path, uid_t uid, mode_t mode) {
    if (mkdir(path, mode) && errno != EEXIST) return -1;
    int fd = open(path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0) return -1;
    int result = fchown(fd, uid, uid) || fchmod(fd, mode);
    int saved = errno;
    close(fd);
    errno = saved;
    return result ? -1 : 0;
}
/* The greeter owns the visible VT while it runs; the session takes it over. */
static void console_mode(uid_t owner, int graphics) {
    int fd = open(OMINX_LOGIN_TTY, O_RDWR | O_NOCTTY | O_CLOEXEC);
    if (fd < 0) {
        log_event("seat: console unavailable (%s)", strerror(errno));
        return;
    }
    if (ioctl(fd, VT_ACTIVATE, 1) || ioctl(fd, VT_WAITACTIVE, 1))
        log_event("seat: virtual terminal switch failed (%s)", strerror(errno));
    if (ioctl(fd, KDSETMODE, graphics ? KD_GRAPHICS : KD_TEXT))
        log_event("seat: console mode failed (%s)", strerror(errno));
    if (fchown(fd, owner, owner) || fchmod(fd, 0620))
        log_event("seat: console ownership failed (%s)", strerror(errno));
    close(fd);
}
static int broker(const char *request, char *reply, size_t capacity) {
    struct sockaddr_un address = {.sun_family = AF_UNIX};
    strcpy(address.sun_path, OMINX_LOGIN_SOCKET);
    int fd = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0);
    if (fd < 0) return -1;
    if (connect(fd, (struct sockaddr *)&address, sizeof address)) { close(fd); return -1; }
    struct timeval timeout = {2, 0};
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof timeout);
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof timeout);
    if (send(fd, request, strlen(request), MSG_NOSIGNAL) < 0) { close(fd); return -1; }
    ssize_t size = recv(fd, reply, capacity - 1, 0);
    close(fd);
    if (size <= 0) return -1;
    reply[size] = 0;
    return 0;
}
static pid_t start_child(uid_t uid, gid_t gid, const char *home, const char *runtime,
                         const char *log_path, int dbus, const char *const argv[]) {
    pid_t parent = getpid();
    pid_t pid = fork();
    if (pid != 0) return pid;
    signal(SIGTERM, SIG_DFL);
    signal(SIGINT, SIG_DFL);
    int null = open("/dev/null", O_RDWR);
    int log = open(log_path, O_WRONLY | O_CREAT | O_APPEND, 0644);
    if (null < 0 || log < 0) _exit(1);
    if (dup2(null, 0) < 0 || dup2(log, 1) < 0 || dup2(log, 2) < 0) _exit(1);
    close(null);
    if (log > 2) close(log);
    if (clearenv() || chdir(home)) _exit(1);
    static const gid_t groups[] = {OMINX_VIDEO, OMINX_INPUT, OMINX_RENDER};
    char buffer[64];
    /* The identity comes from the validated home path, never from a guess. */
    const char *name = uid == OMINX_GREETER_UID ? "greeter" : strrchr(home, '/');
    name = name && name[1] ? name + 1 : "ominx";
    if (setenv("HOME", home, 1) ||
        setenv("USER", name, 1) ||
        setenv("LOGNAME", name, 1) ||
        setenv("PATH", "/bin", 1) || setenv("SHELL", "/init", 1) ||
        setenv("LANG", "C.UTF-8", 1) || setenv("TERM", "linux", 1) ||
        setenv("XDG_RUNTIME_DIR", runtime, 1) ||
        setenv("QT_QPA_PLATFORM", "linuxfb:fb=/dev/fb0:vtcurser=hide", 1) ||
        setenv("QT_QPA_FB_TTY", OMINX_LOGIN_TTY, 1) ||
        setenv("QT_QUICK_BACKEND", "software", 1)) _exit(1);
    if (dbus && !setenv("DBUS_SYSTEM_BUS_ADDRESS", "unix:path=/run/dbus/system_bus_socket", 1) &&
        uid != OMINX_GREETER_UID) {
        snprintf(buffer, sizeof buffer, "unix:path=%s/bus", runtime);
        if (setenv("DBUS_SESSION_BUS_ADDRESS", buffer, 1)) _exit(1);
    }
    if (setgroups(uid == OMINX_GREETER_UID ? 2 : 3, groups) ||
        setresgid(gid, gid, gid) || setresuid(uid, uid, uid) ||
        prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) ||
        prctl(PR_SET_PDEATHSIG, SIGKILL) || getppid() != parent) _exit(1);
    execv(argv[0], (char *const *)argv);
    _exit(1);
}
int main(int argc, char **argv) {
    if (argc == 2 && !strcmp(argv[1], "--help")) {
        puts("ominx-seat: fixed greeter/session supervisor for the OminX console");
        return 0;
    }
    if (argc != 1 || getuid() != 0 || geteuid() != 0 || !source_boot()) {
        fputs("ominx-seat requires the root source boot context\n", stderr);
        return 2;
    }
    umask(022);
    if (directory("/run/ominx", 0, 0755) ||
        directory(OMINX_LOGIN_GREETER_DIR, OMINX_GREETER_UID, 0700)) return 1;
    int lock = open(OMINX_LOGIN_SEAT_LOCK, O_CREAT | O_RDWR | O_NOFOLLOW | O_CLOEXEC, 0600);
    struct stat st;
    if (lock < 0 || fstat(lock, &st) || !S_ISREG(st.st_mode) || st.st_uid || st.st_nlink != 1 ||
        flock(lock, LOCK_EX | LOCK_NB)) {
        fputs("seat supervisor already running or unsafe lock\n", stderr);
        return 1;
    }
    if (!freopen(OMINX_LOGIN_SEAT_LOG, "a", stdout)) { perror("seat log"); return 1; }
    setvbuf(stdout, NULL, _IOLBF, 0);
    int dbus = !access("/sbin/ominx-desktop-bus", X_OK);
    handle_stop();
    /* SIGCHLD stays default: a child exiting is normal work, not a shutdown. */
    /* Wait for the authentication broker; never start a greeter without it. */
    char reply[512];
    for (int attempt = 0; attempt < 60; attempt++) {
        if (!broker("STATUS\n", reply, sizeof reply)) break;
        if (stopping) return 0;
        sleep(1);
    }
    log_event("seat: ready greeter-uid=%u session=%s", (unsigned)OMINX_GREETER_UID,
         OMINX_LOGIN_SESSION_PROGRAM);
    static const char *const greeter[] = {OMINX_LOGIN_SESSION_PROGRAM, "--greeter", NULL};
    while (!stopping) {
        console_mode(OMINX_GREETER_UID, 1);
        child_pid = start_child(OMINX_GREETER_UID, OMINX_GREETER_GID, OMINX_LOGIN_GREETER_DIR,
                                OMINX_LOGIN_GREETER_DIR, OMINX_LOGIN_GREETER_LOG, dbus, greeter);
        if (child_pid < 0) {
            log_event("seat: greeter launch failed (%s)", strerror(errno));
            sleep(1);
            continue;
        }
        log_event("seat: greeter started pid=%ld", (long)child_pid);
        int status = 0;
        while (waitpid(child_pid, &status, 0) < 0 && errno == EINTR) {}
        log_event("seat: greeter exited status=%d", status);
        child_pid = -1;
        if (stopping) break;
        unsigned session_uid = 0;
        char session_home[OMINX_LOGIN_MAX_PATH] = "";
        if (!broker("SESSION\n", reply, sizeof reply) && !strncmp(reply, "OK\t", 3)) {
            char *tab = strchr(reply + 3, '\t');
            session_uid = tab ? (unsigned)strtoul(reply + 3, NULL, 10) : 0;
            if (tab && strlen(tab + 1) < sizeof session_home) snprintf(session_home, sizeof session_home, "%s", tab + 1);
            session_home[strcspn(session_home, "\n")] = 0;
            /* Re-validate: the seat never trusts a path it did not check. */
            if (strncmp(session_home, "/home/", 6) || strchr(session_home + 6, '/') ||
                strstr(session_home, "..")) session_uid = 0;
        }
        if (!broker("POWERSTATE\n", reply, sizeof reply) && !strcmp(reply, "OK\toff\n")) {
            log_event("seat: shutdown requested from the login screen");
            console_mode(0, 0);
            char response[128];
            if (ominx_control_request("poweroff", response, sizeof response))
                log_event("seat: power service unavailable (%s)", strerror(errno));
            else
                log_event("seat: power service said %s", response);
            sleep(2);
            continue;
        }
        if (!strcmp(reply, "OK\treboot\n")) {
            log_event("seat: restart requested from the login screen");
            console_mode(0, 0);
            char response[128];
            if (ominx_control_request("reboot", response, sizeof response))
                log_event("seat: power service unavailable (%s)", strerror(errno));
            else
                log_event("seat: power service said %s", response);
            sleep(2);
            continue;
        }
        if (!session_uid || session_uid < 1000) {
            sleep(1); /* Unauthenticated exit: rate-limited greeter restart. */
            continue;
        }
        char runtime[64];
        snprintf(runtime, sizeof runtime, "/run/user/%u", session_uid);
        if (directory(runtime, session_uid, 0700)) {
            log_event("seat: runtime directory failed for uid=%u", session_uid);
            sleep(1);
            continue;
        }
        static const char *const session[] = {OMINX_LOGIN_SESSION_PROGRAM, "--session", NULL};
        console_mode(session_uid, 1);
        child_pid = start_child(session_uid, session_uid, session_home, runtime,
                                OMINX_LOGIN_SESSION_LOG, dbus, session);
        log_event("seat: session started uid=%u pid=%ld", session_uid, (long)child_pid);
        while (child_pid > 0 && waitpid(child_pid, &status, 0) < 0 && errno == EINTR) {}
        log_event("seat: session ended uid=%u status=%d", session_uid, status);
        child_pid = -1;
    }
    if (child_pid > 0) {
        kill(child_pid, SIGTERM);
        sleep(1);
        kill(child_pid, SIGKILL);
        while (waitpid(-1, NULL, 0) > 0 || errno == EINTR) {}
    }
    console_mode(0, 0);
    close(lock);
    return 0;
}
