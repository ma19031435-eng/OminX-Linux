/* Original fixed-service supervisor. Not a general root command execution API. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/prctl.h>
#include <sys/random.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

static volatile sig_atomic_t stopping;
static void stop(int sig) { (void)sig; stopping = 1; }
static int source_boot(void) {
    char path[128];
    ssize_t n = readlink("/proc/1/exe", path, sizeof path - 1);
    if (n < 0) return 0;
    path[n] = 0;
    return !strcmp(path, "/init");
}
static int directory(const char *path, uid_t uid, mode_t mode) {
    if (mkdir(path, mode) && errno != EEXIST) return -1;
    int fd = open(path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0) return -1;
    int result = fchown(fd, uid, uid) || fchmod(fd, mode);
    close(fd);
    return result ? -1 : 0;
}
static int machine_id(void) {
    int fd = open("/etc/machine-id", O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (fd >= 0) {
        char text[34]; struct stat st;
        ssize_t n = read(fd, text, sizeof text);
        int good = !fstat(fd, &st) && S_ISREG(st.st_mode) && st.st_uid == 0 &&
                   !(st.st_mode & 0222) && st.st_nlink == 1 && n == 33 && text[32] == '\n';
        for (int i = 0; good && i < 32; i++)
            good = (text[i] >= '0' && text[i] <= '9') || (text[i] >= 'a' && text[i] <= 'f');
        close(fd); return good ? 0 : -1;
    }
    if (errno != ENOENT) return -1;
    unsigned char random[16]; size_t used = 0;
    while (used < sizeof random) {
        ssize_t n = getrandom(random + used, sizeof random - used, 0);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return -1;
        used += (size_t)n;
    }
    random[6] = (random[6] & 0x0f) | 0x40;
    random[8] = (random[8] & 0x3f) | 0x80;
    char text[34];
    for (int i = 0; i < 16; i++) snprintf(text + i * 2, 3, "%02x", random[i]);
    text[32] = '\n';
    fd = open("/etc/machine-id", O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0444);
    if (fd < 0) return -1;
    int good = write(fd, text, 33) == 33 && fsync(fd) == 0;
    close(fd); return good ? 0 : -1;
}
static pid_t launch(uid_t uid, const char *config) {
    pid_t parent = getpid(), child = fork();
    if (child != 0) return child;
    signal(SIGTERM, SIG_DFL); signal(SIGINT, SIG_DFL);
    if (clearenv() || chdir("/") || setgroups(0, NULL) ||
        setresgid(uid, uid, uid) || setresuid(uid, uid, uid) ||
        prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) ||
        prctl(PR_SET_PDEATHSIG, SIGKILL) || getppid() != parent) _exit(1);
    execl("/sbin/dbus-daemon", "dbus-daemon", "--nofork", "--nopidfile", config, (char *)NULL);
    _exit(1);
}
int main(int argc, char **argv) {
    if (argc == 2 && !strcmp(argv[1], "--help")) {
        puts("ominx-desktop-bus: fixed system/session bus supervisor for source boot"); return 0;
    }
    if (argc != 1 || getuid() != 0 || !source_boot()) {
        fputs("ominx-desktop-bus requires root source boot context\n", stderr); return 2;
    }
    umask(022);
    if (directory("/run/ominx", 0, 0755)) return 1;
    int lock = open("/run/ominx/bus-service.lock", O_CREAT | O_RDWR | O_NOFOLLOW | O_CLOEXEC, 0600);
    struct stat st;
    if (lock < 0 || fstat(lock, &st) || !S_ISREG(st.st_mode) || st.st_uid || st.st_nlink != 1 ||
        flock(lock, LOCK_EX | LOCK_NB)) { fputs("bus supervisor already running or unsafe lock\n", stderr); return 1; }
    char pid_text[32];
    int pid_length = snprintf(pid_text, sizeof pid_text, "%ld\n", (long)getpid());
    if (ftruncate(lock, 0) || pwrite(lock, pid_text, (size_t)pid_length, 0) != pid_length) return 1;
    if (machine_id() || directory("/run/dbus", 81, 0755)) return 1;
    signal(SIGTERM, stop); signal(SIGINT, stop);
    pid_t children[2] = {-1, -1};
    while (!stopping) {
        int status;
        pid_t ended;
        while ((ended = waitpid(-1, &status, WNOHANG)) > 0)
            for (int i = 0; i < 2; i++) if (children[i] == ended) children[i] = -1;
        for (int i = 0; i < 2; i++) if (children[i] < 0) {
            children[i] = launch(i ? 1000 : 81, i ? "--config-file=/etc/dbus-1/ominx-session.conf" : "--config-file=/etc/dbus-1/ominx-system.conf");
            printf("OminX bus service: %s pid=%ld\n", i ? "session" : "system", (long)children[i]);
            fflush(stdout);
        }
        sleep(1); /* Bounded restart rate, including exec/configuration failures. */
    }
    for (int i = 0; i < 2; i++) if (children[i] > 0) kill(children[i], SIGTERM);
    sleep(1);
    for (int i = 0; i < 2; i++) if (children[i] > 0) kill(children[i], SIGKILL);
    while (waitpid(-1, NULL, 0) > 0 || errno == EINTR) {}
    close(lock);
    return 0;
}
