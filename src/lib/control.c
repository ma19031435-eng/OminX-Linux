#define _GNU_SOURCE
#include "control.h"
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/time.h>
#include <unistd.h>

int ominx_control_request(const char *command, char *reply, unsigned capacity) {
    if (!capacity || (strcmp(command, "status") && strcmp(command, "poweroff") && strcmp(command, "reboot"))) {
        errno = EINVAL; return -1;
    }
    int fd = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0);
    if (fd < 0) return -1;
    struct timeval timeout = {2, 0};
    struct sockaddr_un address = {.sun_family = AF_UNIX};
    memcpy(address.sun_path, OMINX_CONTROL_SOCKET, sizeof OMINX_CONTROL_SOCKET);
    struct ucred peer;
    socklen_t size = sizeof peer;
    int result = -1;
    if (setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof timeout) ||
        setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof timeout) ||
        connect(fd, (struct sockaddr *)&address, sizeof address) ||
        getsockopt(fd, SOL_SOCKET, SO_PEERCRED, &peer, &size)) goto done;
    if (peer.uid != 0) { errno = EPERM; goto done; }
    char packet[32];
    int length = snprintf(packet, sizeof packet, "%s\n", command);
    if (send(fd, packet, (size_t)length, MSG_NOSIGNAL) != length) goto done;
    ssize_t received = recv(fd, reply, capacity - 1, MSG_TRUNC);
    if (received <= 0 || (unsigned)received >= capacity) { errno = EPROTO; goto done; }
    reply[received] = 0;
    result = 0;
done:;
    int saved = errno;
    close(fd); errno = saved;
    return result;
}
