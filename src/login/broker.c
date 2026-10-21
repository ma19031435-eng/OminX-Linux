/* Original bounded authentication broker. Verifies passwords only for the
   packaged account records and hands a single pending session to the seat.
   It never executes programs, opens files for callers, or forwards commands. */
#define _GNU_SOURCE
#include "login.h"
#include <crypt.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/un.h>
#include <stdarg.h>
#include <time.h>
#include <unistd.h>

static volatile sig_atomic_t stopping;
static unsigned pending_uid;
static long pending_when;
static char pending_power; /* 0 none, 1 poweroff, 2 reboot */
struct attempt {
    char name[OMINX_LOGIN_MAX_NAME];
    int count;
    long when;
};
static struct attempt attempts[OMINX_LOGIN_MAX_ACCOUNTS];
static const char *accounts_path = OMINX_LOGIN_ACCOUNTS;
static uid_t root_uid;
/* A handed-out session expires quickly so a stale approval cannot be reused. */
#ifdef OMINX_LOGIN_TEST
#define OMINX_LOGIN_SESSION_WINDOW 2
#else
#define OMINX_LOGIN_SESSION_WINDOW 60
#endif

static void stop(int signal) { (void)signal; stopping = 1; }
/* No SA_RESTART: accept4/waitpid must return EINTR so shutdown is prompt. */
static void handle_stop(void) {
    struct sigaction action = {.sa_handler = stop, .sa_flags = 0};
    sigemptyset(&action.sa_mask);
    sigaction(SIGTERM, &action, NULL);
    sigaction(SIGINT, &action, NULL);
}
static long monotonic(void) {
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC, &now)) return 0;
    return now.tv_sec;
}
static void reply(int fd, const char *text) { (void)send(fd, text, strlen(text), MSG_NOSIGNAL); }
static void log_event(const char *format, ...) {
    va_list list;
    va_start(list, format);
    vprintf(format, list);
    va_end(list);
    fputc('\n', stdout);
    fflush(stdout);
}
#ifndef OMINX_LOGIN_TEST
static int source_boot(void) {
    char path[128];
    ssize_t length = readlink("/proc/1/exe", path, sizeof path - 1);
    if (length < 0) return 0;
    path[length] = 0;
    return !strcmp(path, "/init");
}
#endif

/* The account file is root-only and re-read for every request, so a recovery
   password change applies immediately without restarting the service. */
static int load_accounts(struct ominx_account *accounts, int *count) {
    int fd = open(accounts_path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0) return -1;
    struct stat st;
    if (fstat(fd, &st) || !S_ISREG(st.st_mode) || st.st_nlink != 1 ||
        (st.st_mode & 0177) || st.st_size > 4096) {
        close(fd);
        return -1;
    }
#ifndef OMINX_LOGIN_TEST
    if (st.st_uid != 0) { close(fd); return -1; }
#endif
    char buffer[4096];
    ssize_t length = read(fd, buffer, sizeof buffer - 1);
    close(fd);
    if (length <= 0) return -1;
    buffer[length] = 0;
    *count = 0;
    for (char *line = strtok(buffer, "\n"); line; line = strtok(NULL, "\n")) {
        if (!*line || line[0] == '#') continue;
        if (*count >= OMINX_LOGIN_MAX_ACCOUNTS) return -1;
        if (ominx_parse_account_line(line, &accounts[*count])) return -1;
        (*count)++;
    }
    return *count ? 0 : -1;
}

/* Always runs a full crypt pass, including for unknown names, so response time
   does not disclose whether an account exists. */
static int verify(const struct ominx_account *account, const char *password) {
    const char *setting = account ? account->hash : OMINX_LOGIN_DUMMY_HASH;
    if (!strcmp(setting, "!")) return 0;
    char *computed = crypt(password, setting);
    if (!computed) return 0;
    size_t length = strlen(computed);
    if (length != strlen(setting)) return 0;
    unsigned char difference = 0;
    for (size_t i = 0; i < length; i++) difference |= (unsigned char)(computed[i] ^ setting[i]);
    return difference == 0;
}

static struct attempt *attempt_slot(const char *name) {
    struct attempt *free_slot = NULL;
    for (int i = 0; i < OMINX_LOGIN_MAX_ACCOUNTS; i++) {
        if (!attempts[i].name[0]) { free_slot = &attempts[i]; continue; }
        if (!strcmp(attempts[i].name, name)) return &attempts[i];
    }
    if (!free_slot) free_slot = &attempts[0]; /* Oldest entry is recycled. */
    snprintf(free_slot->name, sizeof free_slot->name, "%s", name);
    free_slot->count = 0;
    free_slot->when = 0;
    return free_slot;
}

static int password_valid(const char *password) {
    size_t length = strlen(password);
    if (!length || length > OMINX_LOGIN_MAX_PASSWORD) return 0;
    for (size_t i = 0; i < length; i++)
        if ((unsigned char)password[i] < 0x20 || (unsigned char)password[i] == 0x7f) return 0;
    return 1;
}

static void authenticate(int client, const char *name, const char *password) {
    struct ominx_account accounts[OMINX_LOGIN_MAX_ACCOUNTS];
    int count = 0;
    struct attempt *slot = attempt_slot(name);
    long now = monotonic();
    /* Bounded backoff applies to any attempted name, existing or not. */
    if (slot->count >= 3 && now - slot->when < 5 * slot->count) {
        reply(client, "DENY\trate-limited\n");
        log_event("login: denied name=%s reason=rate-limited attempts=%d", name, slot->count);
        return;
    }
    if (load_accounts(accounts, &count)) {
        verify(NULL, password);
        reply(client, "DENY\tunavailable\n");
        log_event("login: denied name=%s reason=accounts-unavailable", name);
        return;
    }
    const struct ominx_account *account = NULL;
    for (int i = 0; i < count; i++)
        if (!strcmp(accounts[i].name, name)) account = &accounts[i];
    if (!password_valid(password)) {
        verify(NULL, password);
        reply(client, "DENY\tcredentials\n");
        log_event("login: denied name=%s reason=malformed-password", name);
        return;
    }
    if (account && account->locked) {
        verify(account, password);
        slot->count++;
        slot->when = now;
        reply(client, "DENY\tlocked\n");
        log_event("login: denied name=%s reason=locked", name);
        return;
    }
    if (!verify(account, password)) {
        slot->count++;
        slot->when = now;
        reply(client, "DENY\tcredentials\n");
        log_event("login: denied name=%s reason=credentials attempts=%d", name, slot->count);
        return;
    }
    slot->count = 0;
    slot->when = 0;
    pending_uid = account->uid;
    pending_when = now;
    char text[32];
    snprintf(text, sizeof text, "OK\t%u\n", account->uid);
    reply(client, text);
    log_event("login: accepted name=%s uid=%u", name, account->uid);
}

static void handle(int client, uid_t peer) {
    char packet[OMINX_LOGIN_MAX_REQUEST];
    struct timeval timeout = {2, 0};
    if (setsockopt(client, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof timeout) ||
        setsockopt(client, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof timeout)) return;
    ssize_t size = recv(client, packet, sizeof packet - 1, 0);
    if (size <= 0) return;
    packet[size] = 0;
    if (packet[size - 1] == '\n') packet[size - 1] = 0;
    char *fields[3];
    size_t index = 0;
    fields[index++] = packet;
    for (ssize_t i = 0; i < size && index < 3; i++)
        if (packet[i] == '\t') { packet[i] = 0; fields[index++] = packet + i + 1; }
    const char *command = fields[0];
    int root = peer == root_uid, greeter = peer == OMINX_GREETER_UID;
    if (!strcmp(command, "STATUS") && root) {
        char text[128];
        snprintf(text, sizeof text, "%s pending=%u\n", OMINX_LOGIN_PROTOCOL, pending_uid);
        reply(client, text);
        return;
    }
    if (!strcmp(command, "LIST") && (root || greeter)) {
        struct ominx_account accounts[OMINX_LOGIN_MAX_ACCOUNTS];
        int count = 0;
        char text[512] = "OK\n";
        size_t used = strlen(text);
        if (!load_accounts(accounts, &count))
            for (int i = 0; i < count && used < sizeof text - 64; i++)
                used += (size_t)snprintf(text + used, sizeof text - used, "%s\t%u\t%d\n",
                                         accounts[i].name, accounts[i].uid, accounts[i].locked);
        else
            snprintf(text, sizeof text, "ERR\taccounts-unavailable\n");
        reply(client, text);
        return;
    }
    if (!strcmp(command, "AUTH") && index == 3 && (root || greeter)) {
        authenticate(client, fields[1], fields[2]);
        return;
    }
    if (!strcmp(command, "POWER") && index == 2 && greeter) {
        if (!strcmp(fields[1], "off")) pending_power = 1;
        else if (!strcmp(fields[1], "reboot")) pending_power = 2;
        else { reply(client, "DENY\tinvalid\n"); return; }
        reply(client, "OK\n");
        log_event("login: power requested=%s", fields[1]);
        return;
    }
    if (!strcmp(command, "SESSION") && root) {
        char text[160];
        if (pending_uid && monotonic() - pending_when <= OMINX_LOGIN_SESSION_WINDOW) {
            struct ominx_account accounts[OMINX_LOGIN_MAX_ACCOUNTS];
            int count = 0;
            const char *home = NULL;
            if (!load_accounts(accounts, &count))
                for (int i = 0; i < count; i++)
                    if (accounts[i].uid == pending_uid) home = accounts[i].home;
            if (home) snprintf(text, sizeof text, "OK\t%u\t%s\n", pending_uid, home);
            else snprintf(text, sizeof text, "NONE\n");
        } else {
            snprintf(text, sizeof text, "NONE\n");
        }
        pending_uid = 0;
        pending_when = 0;
        reply(client, text);
        return;
    }
    if (!strcmp(command, "POWERSTATE") && root) {
        char text[32];
        snprintf(text, sizeof text, pending_power == 1 ? "OK\toff\n" : pending_power == 2 ? "OK\treboot\n" : "NONE\n");
        if (pending_power) pending_power = 0;
        reply(client, text);
        return;
    }
    reply(client, "DENY\tforbidden\n");
    log_event("login: refused command=%s peer=%u", command, (unsigned)peer);
}

#ifndef OMINX_LOGIN_TEST
/* Recovery/admin check: password arrives on stdin, never as an argument. */
static int check_mode(int argc, char **argv) {
    const char *name = argv[2];
    if (getuid() != 0 || geteuid() != 0 || !source_boot()) {
        fputs("ominx-login --check requires the root source boot context\n", stderr);
        return 2;
    }
    char password[OMINX_LOGIN_MAX_PASSWORD + 2];
    if (argc == 5 && !strcmp(argv[3], "--password-file")) {
        if (ominx_read_password_file(argv[4], password, sizeof password)) {
            fputs("Refusing: unreadable password file\n", stderr);
            return 1;
        }
    } else if (argc == 3) {
        if (!fgets(password, sizeof password, stdin)) return 1;
        password[strcspn(password, "\n")] = 0;
    } else {
        fputs("usage: ominx-login --check NAME [--password-file PATH]\n", stderr);
        return 2;
    }
    struct ominx_account accounts[OMINX_LOGIN_MAX_ACCOUNTS];
    int count = 0;
    if (load_accounts(accounts, &count)) { puts("DENY\tunavailable"); return 1; }
    const struct ominx_account *account = NULL;
    for (int i = 0; i < count; i++)
        if (!strcmp(accounts[i].name, name)) account = &accounts[i];
    if (!account) { verify(NULL, password); puts("DENY\tcredentials"); return 1; }
    if (account->locked) { puts("DENY\tlocked"); return 1; }
    if (!verify(account, password)) { puts("DENY\tcredentials"); return 1; }
    printf("OK\t%u\n", account->uid);
    return 0;
}
#endif

int main(int argc, char **argv) {
    const char *path = OMINX_LOGIN_SOCKET;
    uid_t allowed_greeter = OMINX_GREETER_UID;
#ifdef OMINX_LOGIN_TEST
    /* Host-test executable only; never packaged into media. */
    if (argc != 3) return 2;
    path = argv[1];
    accounts_path = argv[2];
    allowed_greeter = getuid();
    root_uid = getuid();
#else
    (void)argv;
    root_uid = 0;
    if (argc == 2 && !strcmp(argv[1], "--help")) {
        puts("ominx-login: fixed authentication broker for the OminX graphical login");
        puts("usage: ominx-login            (service, started by /init)");
        puts("       ominx-login --check NAME [--password-file PATH]");
        return 0;
    }
    if ((argc == 3 || argc == 5) && !strcmp(argv[1], "--check")) return check_mode(argc, argv);
    if (argc != 1 || getuid() != 0 || geteuid() != 0 || !source_boot()) {
        fputs("ominx-login requires the root source boot context\n", stderr);
        return 2;
    }
#endif
    handle_stop();
    signal(SIGPIPE, SIG_IGN);
    struct sockaddr_un address = {.sun_family = AF_UNIX};
    if (strlen(path) >= sizeof address.sun_path) return 2;
    strcpy(address.sun_path, path);
    struct stat existing;
    if (!lstat(path, &existing)) {
        if (!S_ISSOCK(existing.st_mode) || existing.st_uid != 0) {
            fputs("Refusing to replace a foreign login socket\n", stderr);
            return 1;
        }
        int probe = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0);
        if (probe < 0) return 1;
        int connected = connect(probe, (struct sockaddr *)&address, sizeof address);
        int saved = errno;
        close(probe);
        if (!connected || saved != ECONNREFUSED) {
            fputs("Login broker already running\n", stderr);
            return 1;
        }
        if (unlink(path)) return 1;
    } else if (errno != ENOENT) return 1;
    umask(077);
#ifndef OMINX_LOGIN_TEST
    /* Keep service diagnostics off the boot console; never log a password. */
    if (!freopen(OMINX_LOGIN_BROKER_LOG, "a", stdout)) { perror("login log"); return 1; }
    setvbuf(stdout, NULL, _IOLBF, 0);
#endif
    int server = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0);
    if (server < 0 || bind(server, (struct sockaddr *)&address, sizeof address)) {
        perror("login bind");
        return 1;
    }
#ifndef OMINX_LOGIN_TEST
    if (chown(path, 0, OMINX_GREETER_GID)) { perror("login ownership"); return 1; }
#endif
    if (chmod(path, 0660) || listen(server, 4)) { perror("login listen"); return 1; }
    log_event("login: service ready accounts-file=%s", accounts_path);
    while (!stopping) {
        int client = accept4(server, NULL, NULL, SOCK_CLOEXEC);
        if (client < 0) {
            if (errno == EINTR) continue;
            perror("login accept");
            break;
        }
        struct ucred peer;
        socklen_t size = sizeof peer;
        if (getsockopt(client, SOL_SOCKET, SO_PEERCRED, &peer, &size) ||
            (peer.uid != 0 && peer.uid != allowed_greeter)) {
            reply(client, "DENY\tforbidden\n");
            log_event("login: refused peer=%u", (unsigned)(size == sizeof peer ? peer.uid : 0));
            close(client);
            continue;
        }
        handle(client, peer.uid);
        close(client);
    }
    close(server);
    return 0;
}
