/* Diagnostic client for the authentication broker. Sends exactly one fixed
   request as the calling identity and prints the reply, so guest tests can
   prove which identities the broker accepts. It cannot authenticate: only the
   packaged greeter account and root may ask. */
#define _GNU_SOURCE
#include "login.h"
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <sys/un.h>
#include <unistd.h>

int main(int argc, char **argv) {
    if (argc == 2 && !strcmp(argv[1], "--help")) {
        puts("ominx-login-probe: send one fixed request to the login broker");
        puts("usage: ominx-login-probe LIST|SESSION|STATUS|POWERSTATE");
        puts("       ominx-login-probe AUTH NAME [--password-file PATH]");
        return 0;
    }
    if (argc != 2 && argc != 3 && argc != 5) return 2;
    const char *command = argv[1];
    char request[OMINX_LOGIN_MAX_REQUEST];
    if (argc == 2) {
        snprintf(request, sizeof request, "%s\n", command);
    } else if (!strcmp(command, "AUTH") && (argc == 3 || (argc == 5 && !strcmp(argv[3], "--password-file")))) {
        /* Never taken from argv: standard input or a caller-owned file. */
        char password[OMINX_LOGIN_MAX_PASSWORD + 2];
        if (argc == 5) {
            if (ominx_read_password_file(argv[4], password, sizeof password)) return 1;
        } else {
            if (!fgets(password, sizeof password, stdin)) return 1;
            password[strcspn(password, "\n")] = 0;
        }
        snprintf(request, sizeof request, "AUTH\t%s\t%s\n", argv[2], password);
        memset(password, 0, sizeof password);
    } else {
        return 2;
    }
    struct sockaddr_un address = {.sun_family = AF_UNIX};
    if (strlen(OMINX_LOGIN_SOCKET) >= sizeof address.sun_path) return 2;
    strcpy(address.sun_path, OMINX_LOGIN_SOCKET);
    int fd = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0);
    if (fd < 0) { perror("socket"); return 1; }
    struct timeval timeout = {10, 0};
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof timeout);
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof timeout);
    if (connect(fd, (struct sockaddr *)&address, sizeof address)) {
        perror("connect");
        return 1;
    }
    if (send(fd, request, strlen(request), MSG_NOSIGNAL) < 0) {
        perror("send");
        return 1;
    }
    char reply[1024];
    ssize_t size = recv(fd, reply, sizeof reply - 1, 0);
    close(fd);
    if (size < 0) { perror("recv"); return 1; }
    reply[size] = 0;
    fputs(reply, stdout);
    return 0;
}
