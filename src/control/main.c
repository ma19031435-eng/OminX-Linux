/* Original bounded local power broker. No shell execution, path operands or mounts. */
#define _GNU_SOURCE
#include "../lib/control.h"
#include "../lib/session.h"
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/reboot.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/un.h>
#include <unistd.h>

static void reply(int fd, const char *message) {
    (void)send(fd, message, strlen(message), MSG_NOSIGNAL);
}
static int operation(const char *packet, ssize_t size) {
    if (size == 7 && !memcmp(packet, "status\n", 7)) return 0;
    if (size == 9 && !memcmp(packet, "poweroff\n", 9)) return RB_POWER_OFF;
    if (size == 7 && !memcmp(packet, "reboot\n", 7)) return RB_AUTOBOOT;
    return -1;
}
int main(int argc, char **argv) {
    const char *path = OMINX_CONTROL_SOCKET;
    uid_t owner = 0, allowed = OMINX_UID;
#ifdef OMINX_CONTROL_TEST
    /* Compiled only into the host test executable. Never packaged. */
    if (argc != 2) return 2;
    path = argv[1]; owner = getuid(); allowed = getuid();
#else
    (void)argv;
    if (argc != 1 || getuid() != 0 || geteuid() != 0) {
        fputs("ominx-control requires root service context\n", stderr); return 2;
    }
    if (mkdir("/run/ominx", 0755) && errno != EEXIST) { perror("service directory"); return 1; }
    struct stat directory;
    if (lstat("/run/ominx", &directory) || !S_ISDIR(directory.st_mode) ||
        directory.st_uid != 0 || (directory.st_mode & 0022)) {
        fputs("Unsafe service directory\n", stderr); return 1;
    }
#endif
    struct sockaddr_un address = {.sun_family = AF_UNIX};
    if (strlen(path) >= sizeof address.sun_path) return 2;
    strcpy(address.sun_path, path);
    struct stat existing;
    if (!lstat(path, &existing)) {
        if (!S_ISSOCK(existing.st_mode) || existing.st_uid != owner) {
            fputs("Refusing to replace non-owned socket\n", stderr); return 1;
        }
        /* A second live server must not replace the first. */
        int probe = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0);
        if (probe < 0) return 1;
        int connected = connect(probe, (struct sockaddr *)&address, sizeof address);
        int saved = errno;
        close(probe);
        if (!connected || saved != ECONNREFUSED) return 1;
        if (unlink(path)) return 1;
    } else if (errno != ENOENT) return 1;
    umask(077);
    int server = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0);
    if (server < 0 || bind(server, (struct sockaddr *)&address, sizeof address)) { perror("control bind"); return 1; }
#ifndef OMINX_CONTROL_TEST
    if (chown(path, 0, OMINX_GID)) { perror("control ownership"); return 1; }
#endif
    if (chmod(path, 0660) || listen(server, 8)) { perror("control listen"); return 1; }
    signal(SIGPIPE, SIG_IGN);
    for (;;) {
        int client = accept4(server, NULL, NULL, SOCK_CLOEXEC);
        if (client < 0) { if (errno == EINTR) continue; perror("control accept"); return 1; }
        struct timeval timeout = {0, 200000};
        struct ucred peer;
        socklen_t size = sizeof peer;
        if (setsockopt(client, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof timeout) ||
            setsockopt(client, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof timeout) ||
            getsockopt(client, SOL_SOCKET, SO_PEERCRED, &peer, &size) ||
            (peer.uid != owner && peer.uid != allowed)) {
            reply(client, "ERR denied\n"); close(client); continue;
        }
        char packet[32];
        ssize_t count = recv(client, packet, sizeof packet, MSG_TRUNC);
        int action = operation(packet, count);
        if (action == -1) reply(client, "ERR invalid-request\n");
        else if (!action) reply(client, "OK service=ominx-control protocol=1\n");
        else {
#ifdef OMINX_CONTROL_TEST
            reply(client, "OK test-only-no-power-action\n");
#else
            sync();
            if (umount("/mnt/data") && errno != EINVAL && errno != ENOENT) {
                reply(client, "ERR data-busy-or-unmount-failed\n");
            } else {
                reply(client, action == RB_POWER_OFF ? "OK poweroff-requested\n" : "OK reboot-requested\n");
                if (reboot(action)) perror("power action failed");
            }
#endif
        }
        close(client);
    }
}
