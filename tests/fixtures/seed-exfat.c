/* Test-only PID 1: seed an exclusive disposable exFAT image inside QEMU.
   Never included in the production initramfs or ISO. Repository license applies. */
#define _GNU_SOURCE
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/reboot.h>
#include <unistd.h>

int main(void) {
    if (getpid() != 1) {
        fputs("Fixture initializer may only run as guest PID 1.\n", stderr);
        return 2;
    }
    if (mount("devtmpfs", "/dev", "devtmpfs", 0, NULL)) { perror("devtmpfs"); return 1; }
    int console = open("/dev/console", O_RDWR);
    if (console < 0) { perror("console"); return 1; }
    for (int i = 0; i < 3; i++) if (dup2(console, i) < 0) return 1;
    if (console > 2) close(console);
    if (mount("/dev/vda", "/mnt/data", "exfat", MS_NOSUID | MS_NODEV | MS_NOEXEC, "iocharset=utf8")) {
        perror("fixture mount"); return 1;
    }
    int fd = open("/mnt/data/Windows Notes.txt", O_WRONLY | O_CREAT | O_EXCL, 0600);
    if (fd < 0) { perror("fixture create"); return 1; }
    const char text[] = "OMINX_WINDOWS_FILE_READ\r\n";
    if (write(fd, text, sizeof text - 1) != (ssize_t)(sizeof text - 1) || fsync(fd)) {
        perror("fixture write"); return 1;
    }
    if (close(fd) || umount("/mnt/data")) { perror("fixture close"); return 1; }
    sync();
    puts("OMINX_FIXTURE_READY"); fflush(stdout);
    if (reboot(RB_POWER_OFF)) perror("fixture poweroff");
    return 1;
}
