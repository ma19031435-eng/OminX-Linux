/* OminX original early userspace. Repository license applies; see LICENSE. */
#define _GNU_SOURCE
#include "../lib/parse.h"
#include "../lib/files.h"
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mount.h>
#include <termios.h>
#include <sys/reboot.h>
#include <sys/stat.h>
#include <sys/utsname.h>
#include <sys/wait.h>
#include <unistd.h>

static int is_init;
static void error(const char *s) { fprintf(stderr, "%s: %s\n", s, strerror(errno)); }
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
        char *args[64];
        int n = ominx_parse(line, args, 64);
        if (n == -2) { puts("Too many arguments."); continue; }
        if (n < 0) { puts("Malformed quoting or trailing escape."); continue; }
        if (!n) continue;
        const char *cmd = args[0];
        if (!strcmp(cmd, "help")) {
            puts("help | uname | pwd | cd PATH | ls [PATH] | cat FILE\n"
                 "mkdir PATH | write FILE WORDS... | echo WORDS... | sync\n"
                 "cp SOURCE DEST | mv SOURCE DEST | rm FILE\n"
                 "attach DEVICE [ro [ext4|vfat|exfat|ntfs3]] | detach\n"
                 "files COMMAND [args] | exit | reboot | poweroff | /absolute/program [args]\n"
                 "Single/double quotes and backslash escapes supported; no pipes or expansion.\n"
                 "write replaces a file. Only files on an attached data disk survive reboot.");
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
        } else if (!strcmp(cmd, "cp") && n == 3) {
            if (ominx_copy(args[1], args[2])) error(cmd);
        }
        else if (!strcmp(cmd, "mv") && n == 3) {
            if (ominx_move(args[1], args[2])) error(cmd);
        } else if (!strcmp(cmd, "rm") && n == 2) {
            if (unlink(args[1])) error(args[1]);
        } else if (!strcmp(cmd, "attach") && (n == 2 || ((n == 3 || n == 4) && !strcmp(args[2], "ro")))) {
            if (!is_init) { puts("Disk attachment only runs in the OminX boot environment."); continue; }
            const char *type = n == 4 ? args[3] : "ext4";
            if (strcmp(type, "ext4") && strcmp(type, "vfat") && strcmp(type, "exfat") && strcmp(type, "ntfs3")) {
                puts("Unsupported filesystem type."); continue;
            }
            struct stat st;
            if (stat(args[1], &st)) { error(args[1]); continue; }
            if (!S_ISBLK(st.st_mode)) { puts("Refusing: device is not a block device."); continue; }
            /* Never format or mount user disks automatically. Refuse mount stacking. */
            struct stat parent, current;
            if (stat("/mnt", &parent) || stat("/mnt/data", &current)) { error("/mnt/data"); continue; }
            if (parent.st_dev != current.st_dev) { puts("Data already attached; detach first."); continue; }
            unsigned long flags = MS_NOSUID | MS_NODEV | MS_NOEXEC;
            if (n >= 3) flags |= MS_RDONLY;
            const char *options = !strcmp(type, "ext4") ? (n >= 3 ? "noload" : NULL) :
                                  !strcmp(type, "vfat") ? "utf8=1" : "iocharset=utf8";
            if (mount(args[1], "/mnt/data", type, flags, options)) error("attach");
            else puts("Data attached at /mnt/data.");
        } else if (!strcmp(cmd, "detach") && n == 1) {
            if (!is_init) { puts("Disk attachment only runs in the OminX boot environment."); continue; }
            sync();
            if (umount("/mnt/data")) error("detach"); else puts("Data detached.");
        } else if (!strcmp(cmd, "sync")) sync();
        else if (!strcmp(cmd, "reboot") || !strcmp(cmd, "poweroff")) {
            if (!is_init) { puts("Power controls only run in the OminX boot environment."); continue; }
            if (chdir("/root")) error("/root");
            sync();
            if (umount("/mnt/data") && errno != EINVAL && errno != ENOENT) {
                error("Detach data disk before shutdown"); continue;
            }
            if (reboot(!strcmp(cmd, "reboot") ? RB_AUTOBOOT : RB_POWER_OFF)) error(cmd);
        } else if (cmd[0] == '/' || !strcmp(cmd, "files")) {
            pid_t pid = fork();
            if (pid == 0) {
                signal(SIGINT, SIG_DFL);
                execv(!strcmp(cmd, "files") ? "/bin/ominx-files" : cmd, args); error(cmd); _exit(127);
            }
            if (pid < 0) error("fork");
            else while (waitpid(pid, NULL, 0) < 0 && errno == EINTR) {}
        } else puts("Unknown command or wrong argument count. Type help.");
    }
    free(line);
}
static pid_t start_console(const char *device) {
    pid_t child = fork();
    if (child != 0) return child;
    if (setsid() < 0) { error("setsid"); _exit(1); }
    int fd = open(device, O_RDWR);
    if (fd < 0) { error(device); _exit(1); }
    if (ioctl(fd, TIOCSCTTY, 0)) { error("controlling terminal"); _exit(1); }
    for (int i = 0; i < 3; i++) if (dup2(fd, i) < 0) _exit(1);
    if (fd > 2) close(fd);
    struct termios t;
    if (!tcgetattr(0, &t)) {
        t.c_lflag |= ICANON | ECHO | ISIG;
        t.c_oflag |= OPOST | ONLCR;
        t.c_iflag |= ICRNL;
        cfsetispeed(&t, B115200); cfsetospeed(&t, B115200);
        if (tcsetattr(0, TCSANOW, &t)) error("terminal setup");
    }
    setvbuf(stdout, NULL, _IOLBF, 0);
    shell();
    exit(0);
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
    /* Independent local-keyboard and serial sessions; PID 1 reaps all children. */
    const char *devices[] = {"/dev/tty1", "/dev/ttyS0"};
    pid_t consoles[2];
    for (int i = 0; i < 2; i++) consoles[i] = start_console(devices[i]);
    for (;;) {
        int status;
        pid_t ended = wait(&status);
        if (ended < 0 && errno == EINTR) continue;
        for (int i = 0; i < 2; i++) {
            if (consoles[i] < 0 || consoles[i] == ended) {
                sleep(1); /* Rate-limit failed console devices. */
                consoles[i] = start_console(devices[i]);
            }
        }
        if (ended < 0) sleep(1);
    }
}
