/* Original password tool for recovery. Changes only the stored hash of an
   account that the image already defines; it cannot create or remove accounts,
   change identities, or modify any other field. */
#define _GNU_SOURCE
#include "login.h"
#include <crypt.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/random.h>
#include <sys/stat.h>
#include <unistd.h>

static int source_boot(void) {
    char path[128];
    ssize_t length = readlink("/proc/1/exe", path, sizeof path - 1);
    if (length < 0) return 0;
    path[length] = 0;
    return !strcmp(path, "/init");
}
static const char ALPHABET[] = "./0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";

static int salt(char *out, size_t capacity) {
    unsigned char random[16];
    size_t used = 0;
    while (used < 12) {
        ssize_t count = getrandom(random + used, sizeof random - used, 0);
        if (count < 0 && errno == EINTR) continue;
        if (count <= 0) return -1;
        used += (size_t)count;
    }
    if (capacity < 14) return -1;
    for (int i = 0; i < 12; i++) out[i] = ALPHABET[random[i] % (sizeof ALPHABET - 1)];
    out[12] = 0;
    return 0;
}

int main(int argc, char **argv) {
    if (argc == 2 && !strcmp(argv[1], "--help")) {
        puts("ominx-passwd: change a packaged account password from recovery");
        puts("usage: ominx-passwd --set NAME <password-on-stdin>");
        puts("       ominx-passwd --list");
        return 0;
    }
    if (getuid() != 0 || geteuid() != 0 || !source_boot()) {
        fputs("ominx-passwd requires the root source boot context\n", stderr);
        return 2;
    }
    if (argc == 2 && !strcmp(argv[1], "--list")) {
        int fd = open(OMINX_LOGIN_ACCOUNTS, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
        if (fd < 0) { perror(OMINX_LOGIN_ACCOUNTS); return 1; }
        char buffer[4096];
        ssize_t length = read(fd, buffer, sizeof buffer - 1);
        close(fd);
        if (length <= 0) return 1;
        buffer[length] = 0;
        struct ominx_account account;
        for (char *line = strtok(buffer, "\n"); line; line = strtok(NULL, "\n")) {
            if (ominx_parse_account_line(line, &account)) {
                fputs("Refusing: account file is malformed\n", stderr);
                return 1;
            }
            printf("%s\tuid=%u\t%s\n", account.name, account.uid,
                   account.locked || !strcmp(account.hash, "!") ? "locked" : "password-set");
        }
        return 0;
    }
    if (argc != 3 || strcmp(argv[1], "--set")) {
        fputs("usage: ominx-passwd --set NAME <password-on-stdin>\n", stderr);
        return 2;
    }
    const char *name = argv[2];
    if (!ominx_account_name_valid(name)) {
        fputs("Refusing: invalid account name\n", stderr);
        return 1;
    }
    char password[OMINX_LOGIN_MAX_PASSWORD + 2];
    if (!fgets(password, sizeof password, stdin)) {
        fputs("Refusing: no password on standard input\n", stderr);
        return 1;
    }
    password[strcspn(password, "\n")] = 0;
    size_t length = strlen(password);
    if (!length || length > OMINX_LOGIN_MAX_PASSWORD || strchr(password, ':')) {
        fputs("Refusing: password must be 1-128 bytes without colons\n", stderr);
        return 1;
    }
    int fd = open(OMINX_LOGIN_ACCOUNTS, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0) { perror(OMINX_LOGIN_ACCOUNTS); return 1; }
    struct stat st;
    if (fstat(fd, &st) || !S_ISREG(st.st_mode) || st.st_uid != 0 || st.st_nlink != 1 ||
        (st.st_mode & 0177) || st.st_size > 4096) {
        fputs("Refusing: unsafe account file\n", stderr);
        close(fd);
        return 1;
    }
    char current[4096];
    ssize_t size = read(fd, current, sizeof current - 1);
    close(fd);
    if (size <= 0) { fputs("Refusing: empty account file\n", stderr); return 1; }
    current[size] = 0;
    char setting[64], *hash;
    char generated_salt[16];
    if (salt(generated_salt, sizeof generated_salt)) return 1;
    snprintf(setting, sizeof setting, "$6$%s$", generated_salt);
    hash = crypt(password, setting);
    memset(password, 0, sizeof password);
    if (!hash || strncmp(hash, setting, strlen(setting))) {
        fputs("Refusing: password hashing failed\n", stderr);
        return 1;
    }
    char updated[4096];
    size_t used = 0;
    int replaced = 0;
    struct ominx_account account;
    char copy[4096];
    memcpy(copy, current, (size_t)size + 1);
    for (char *line = strtok(copy, "\n"); line; line = strtok(NULL, "\n")) {
        if (ominx_parse_account_line(line, &account)) {
            fputs("Refusing: account file is malformed\n", stderr);
            return 1;
        }
        int count = !strcmp(account.name, name) ?
            snprintf(updated + used, sizeof updated - used, "%s:%u:%u:%s:%s:0:%s",
                     account.name, account.uid, account.gid, account.home,
                     OMINX_LOGIN_SESSION_SHELL, hash) :
            snprintf(updated + used, sizeof updated - used, "%s", line);
        if (count < 0 || (size_t)count >= sizeof updated - used - 2) {
            fputs("Refusing: account file too large\n", stderr);
            return 1;
        }
        used += (size_t)count;
        updated[used++] = '\n';
        if (!strcmp(account.name, name)) replaced = 1;
    }
    if (!replaced) {
        fputs("Refusing: no such packaged account\n", stderr);
        return 1;
    }
    char temporary[] = "/etc/ominx/.accounts.XXXXXX";
    int out = mkstemp(temporary);
    if (out < 0) { perror("temporary account file"); return 1; }
    int good = write(out, updated, used) == (ssize_t)used && !fchown(out, 0, 0) &&
               !fchmod(out, 0400) && fsync(out) == 0;
    close(out);
    if (!good || rename(temporary, OMINX_LOGIN_ACCOUNTS)) {
        unlink(temporary);
        fputs("Refusing: account update failed\n", stderr);
        return 1;
    }
    printf("OK password-updated name=%s\n", name);
    return 0;
}
