/* Shared account-record parsing. The service and its tool cannot disagree. */
#define _GNU_SOURCE
#include "login.h"
#include <ctype.h>
#include <stdio.h>
#include <string.h>

int ominx_account_name_valid(const char *name) {
    if (!name || !*name) return 0;
    if (!islower((unsigned char)name[0]) && name[0] != '_') return 0;
    for (size_t i = 0; name[i]; i++) {
        if (i >= OMINX_LOGIN_MAX_NAME - 1) return 0;
        unsigned char c = (unsigned char)name[i];
        if (!(islower(c) || isdigit(c) || c == '_' || c == '-')) return 0;
    }
    return !strcmp(name, "root") ? 0 : 1;
}

static int digits(const char *text, unsigned limit_low, unsigned limit_high, unsigned *out) {
    unsigned value = 0;
    if (!*text) return 0;
    for (size_t i = 0; text[i]; i++) {
        if (!isdigit((unsigned char)text[i]) || i > 5) return 0;
        value = value * 10 + (unsigned)(text[i] - '0');
    }
    if (value < limit_low || value >= limit_high) return 0;
    *out = value;
    return 1;
}

static int crypt_char(unsigned char c) { return isalnum(c) || c == '.' || c == '/'; }

/* Exactly "!" (no password) or a default-round crypt sha512 record:
   $6$<1-16 salt chars>$<86 digest chars>. scripts/make-initramfs.py enforces
   the same grammar, so packaging cannot ship what the service would reject. */
static int hash_valid(const char *hash) {
    if (!strcmp(hash, "!")) return 1;
    if (strncmp(hash, "$6$", 3)) return 0;
    const char *salt = hash + 3;
    size_t index = 0;
    while (salt[index] && salt[index] != '$') {
        if (index >= 16 || !crypt_char((unsigned char)salt[index])) return 0;
        index++;
    }
    if (!index || salt[index] != '$') return 0;
    const char *digest = salt + index + 1;
    size_t length = 0;
    while (digest[length]) {
        if (!crypt_char((unsigned char)digest[length])) return 0;
        length++;
    }
    return length == 86;
}

static int home_valid(const char *home) {
    const char *prefix = "/home/";
    size_t length = strlen(home);
    if (length <= strlen(prefix) || length >= OMINX_LOGIN_MAX_PATH || strncmp(home, prefix, strlen(prefix))) return 0;
    const char *name = home + strlen(prefix);
    if (strchr(name, '/') || strstr(name, "..")) return 0;
    return ominx_account_name_valid(name);
}

int ominx_parse_account_line(const char *line, struct ominx_account *account) {
    size_t length = line ? strlen(line) : 0;
    if (!length || length > 600) return -1;
    char buffer[601];
    memcpy(buffer, line, length + 1);
    if (buffer[length - 1] == '\n') { buffer[length - 1] = 0; length--; }
    if (!length) return -1;
    char *fields[7];
    size_t index = 0;
    fields[index++] = buffer;
    for (size_t i = 0; i < length && index < 8; i++)
        if (buffer[i] == ':') {
            buffer[i] = 0;
            fields[index++] = buffer + i + 1;
        }
    if (index != 7 || strchr(fields[6], ':')) return -1;
    if (!ominx_account_name_valid(fields[0]) || !home_valid(fields[3]) ||
        strcmp(fields[4], OMINX_LOGIN_SESSION_SHELL) || !hash_valid(fields[6])) return -1;
    unsigned uid, gid, locked;
    if (!digits(fields[1], 1000, 60000, &uid) || !digits(fields[2], 1000, 60000, &gid) ||
        !digits(fields[5], 0, 2, &locked)) return -1;
    if (uid == OMINX_GREETER_UID || gid == OMINX_GREETER_GID) return -1;
    memset(account, 0, sizeof *account);
    snprintf(account->name, sizeof account->name, "%s", fields[0]);
    snprintf(account->home, sizeof account->home, "%s", fields[3]);
    snprintf(account->hash, sizeof account->hash, "%s", fields[6]);
    account->uid = uid;
    account->gid = gid;
    account->locked = (int)locked;
    return 0;
}
