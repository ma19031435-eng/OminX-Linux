/* OminX original early userspace. Repository license applies; see LICENSE. */
#define _GNU_SOURCE
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/reboot.h>
#include <sys/stat.h>
#include <sys/utsname.h>
#include <sys/wait.h>
#include <unistd.h>

static int is_init;
static void error(const char *s) { fprintf(stderr, "%s: %s\n", s, strerror(errno)); }
static void reap(int sig) {
    (void)sig;
    int saved = errno;
    while (waitpid(-1, NULL, WNOHANG) > 0) {}
    errno = saved;
}
static void filesystem(const char *type, const char *path) {
    if (mkdir(path, 0755) && errno != EEXIST) error(path);
    if (mount(type, path, type, MS_NOSUID | MS_NODEV, NULL)) error(path);
}
static void shell(void) {
    char *line = NULL;
    size_t cap = 0;
    puts("OminX console ready. Type help. No disk is mounted automatically.");
    for (;;) {
        char cwd[4096];
        printf("ominx:%s# ", getcwd(cwd, sizeof cwd) ? cwd : "?");
        fflush(stdout);
        if (getline(&line, &cap, stdin) < 0) break;
        char *args[64], *save = NULL;
        int n = 0;
        char *word = strtok_r(line, " \t\r\n", &save);
        while (word && n < 63) {
            args[n++] = word;
            word = strtok_r(NULL, " \t\r\n", &save);
        }
        if (word) { puts("Too many arguments."); continue; }
        args[n] = NULL;
        if (!n) continue;
        const char *cmd = args[0];
        if (!strcmp(cmd, "help")) {
            puts("help | uname | pwd | cd PATH | ls [PATH] | cat FILE\n"
                 "mkdir PATH | write FILE WORDS... | echo WORDS... | sync\n"
                 "exit | reboot | poweroff | /absolute/program [args]\n"
                 "Whitespace separates arguments; no quoting, pipes or expansion.\n"
                 "write replaces a file. Files in this RAM system are NOT persistent.");
        } else if (!strcmp(cmd, "exit")) break;
        else if (!strcmp(cmd, "uname")) {
            struct utsname u;
            if (uname(&u)) error(cmd);
            else printf("%s %s %s\n", u.sysname, u.release, u.machine);
        } else if (!strcmp(cmd, "pwd")) {
            if (getcwd(cwd, sizeof cwd)) puts(cwd); else error(cmd);
        } else if (!strcmp(cmd, "cd") && n == 2) {
            if (chdir(args[1])) error(args[1]);
        } else if (!strcmp(cmd, "mkdir") && n == 2) {
            if (mkdir(args[1], 0755)) error(args[1]);
        } else if (!strcmp(cmd, "ls") && n <= 2) {
            DIR *d = opendir(n == 2 ? args[1] : ".");
            if (!d) error(cmd);
            else {
                struct dirent *e;
                while ((e = readdir(d))) puts(e->d_name);
                closedir(d);
            }
        } else if (!strcmp(cmd, "cat") && n == 2) {
            FILE *f = fopen(args[1], "rb");
            if (!f) error(args[1]);
            else {
                char buf[4096]; size_t count;
                while ((count = fread(buf, 1, sizeof buf, f))) {
                    if (fwrite(buf, 1, count, stdout) != count) { error("stdout"); break; }
                }
                if (ferror(f)) error(args[1]);
                fclose(f);
            }
        } else if (!strcmp(cmd, "echo") || (!strcmp(cmd, "write") && n >= 3)) {
            int writing = !strcmp(cmd, "write");
            FILE *f = writing ? fopen(args[1], "w") : stdout;
            if (!f) { error(args[1]); continue; }
            for (int i = writing ? 2 : 1; i < n; i++)
                fprintf(f, "%s%s", i == (writing ? 2 : 1) ? "" : " ", args[i]);
            fputc('\n', f);
            if (writing && fclose(f)) error(args[1]);
        } else if (!strcmp(cmd, "sync")) sync();
        else if (!strcmp(cmd, "reboot") || !strcmp(cmd, "poweroff")) {
            if (!is_init) { puts("Power controls only run in the OminX boot environment."); continue; }
            sync();
            if (reboot(!strcmp(cmd, "reboot") ? RB_AUTOBOOT : RB_POWER_OFF)) error(cmd);
        } else if (cmd[0] == '/') {
            pid_t pid = fork();
            if (pid == 0) {
                signal(SIGINT, SIG_DFL);
                execv(cmd, args); error(cmd); _exit(127);
            }
            if (pid < 0) error("fork");
            else while (waitpid(pid, NULL, 0) < 0 && errno == EINTR) {}
        } else puts("Unknown command or wrong argument count. Type help.");
    }
    free(line);
}
int main(int argc, char **argv) {
    is_init = getpid() == 1;
    if (!is_init && (argc != 2 || strcmp(argv[1], "--shell"))) {
        fputs("Usage: ominx --shell (or boot as /init)\n", stderr); return 2;
    }
    if (!is_init) { shell(); return 0; }
    umask(022);
    if (mkdir("/dev", 0755) && errno != EEXIST) error("/dev");
    if (mount("devtmpfs", "/dev", "devtmpfs", MS_NOSUID, NULL)) error("devtmpfs");
    int fd = open("/dev/console", O_RDWR);
    if (fd >= 0) {
        for (int i = 0; i < 3; i++) if (dup2(fd, i) < 0) error("dup2");
        if (fd > 2) close(fd);
    }
    filesystem("proc", "/proc"); filesystem("sysfs", "/sys");
    filesystem("tmpfs", "/run"); filesystem("tmpfs", "/tmp");
    if (chmod("/tmp", 01777)) error("/tmp permissions");
    setenv("PATH", "/bin", 1); setenv("HOME", "/root", 1);
    if (chdir("/root")) error("/root");
    signal(SIGINT, SIG_IGN);
    /* PID 1 never exits. A child owns the console; PID 1 reaps orphans. */
    for (;;) {
        pid_t child = fork();
        if (child == 0) { shell(); _exit(0); }
        if (child < 0) { error("console fork"); sleep(1); continue; }
        int status;
        for (;;) {
            pid_t ended = wait(&status);
            if (ended == child) break;
            if (ended < 0 && errno != EINTR) break;
        }
        reap(0);
        sleep(1);
    }
}
