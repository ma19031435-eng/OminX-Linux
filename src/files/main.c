/* Original OminX Files backend. Repository license applies. */
#define _GNU_SOURCE
#include "../lib/files.h"
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

/* Valid UTF-8 passes unchanged; invalid bytes display as replacement characters.
   name_hex in directory listings preserves the exact POSIX filename bytes. */
static void json_string(const char *text) {
    putchar('"');
    const unsigned char *s = (const unsigned char *)text;
    while (*s) {
        unsigned c = *s;
        if (c == '"' || c == '\\') { printf("\\%c", c); s++; }
        else if (c < 32 || c == 127) { printf("\\u%04x", c); s++; }
        else if (c < 128) putchar(*s++);
        else {
            unsigned length = c >= 0xc2 && c <= 0xdf ? 2 : c >= 0xe0 && c <= 0xef ? 3 : c >= 0xf0 && c <= 0xf4 ? 4 : 0;
            unsigned value = length ? c & ((1u << (7 - length)) - 1) : 0;
            unsigned i = 1;
            for (; i < length && s[i] >= 0x80 && s[i] <= 0xbf; i++) value = (value << 6) | (s[i] & 63);
            if (!length || i != length || (length == 3 && value < 0x800) ||
                (length == 4 && value < 0x10000) || value > 0x10ffff || (value >= 0xd800 && value <= 0xdfff)) {
                fputs("\\ufffd", stdout); s++;
            } else { fwrite(s, 1, length, stdout); s += length; }
        }
    }
    putchar('"');
}
static void metadata(const struct stat *st) {
    const char *type = S_ISREG(st->st_mode) ? "file" : S_ISDIR(st->st_mode) ? "directory" : S_ISLNK(st->st_mode) ? "symlink" : "other";
    printf("\"type\":\"%s\",\"size\":%jd,\"mode\":%u", type, (intmax_t)st->st_size, st->st_mode & 07777);
}
static int compare_names(const void *a, const void *b) {
    return strcmp(*(const char *const *)a, *(const char *const *)b);
}
static int listing(const char *path) {
    int fd = open(path, O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    if (fd < 0) return -1;
    DIR *directory = fdopendir(fd);
    if (!directory) { int saved = errno; close(fd); errno = saved; return -1; }
    char **names = NULL;
    size_t count = 0;
    struct dirent *entry;
    for (;;) {
        errno = 0;
        entry = readdir(directory);
        if (!entry) {
            if (errno) goto failed;
            break;
        }
        char **grown = realloc(names, (count + 1) * sizeof *names);
        if (!grown) goto failed;
        names = grown;
        names[count] = strdup(entry->d_name);
        if (!names[count]) goto failed;
        count++;
    }
    if (count) qsort(names, count, sizeof *names, compare_names);
    printf("{\"entries\":[");
    int first = 1, failed = 0;
    for (size_t i = 0; i < count; i++) {
        const char *name = names[i];
        if (strcmp(name, ".") && strcmp(name, "..")) {
            struct stat st;
            if (!first) putchar(',');
            first = 0;
            fputs("{\"name\":", stdout); json_string(name);
            fputs(",\"name_hex\":\"", stdout);
            for (const unsigned char *p = (const unsigned char *)name; *p; p++) printf("%02x", *p);
            fputs("\",", stdout);
            if (fstatat(fd, name, &st, AT_SYMLINK_NOFOLLOW)) {
                fputs("\"error\":", stdout); json_string(strerror(errno)); failed = 1;
            } else metadata(&st);
            putchar('}');
        }
        free(names[i]);
    }
    free(names); closedir(directory);
    printf("],\"complete\":%s}\n", failed ? "false" : "true");
    return failed ? 1 : 0;
failed:;
    int saved = errno;
    for (size_t i = 0; i < count; i++) free(names[i]);
    free(names); closedir(directory); errno = saved;
    return -1;
}
int main(int argc, char **argv) {
    if (argc == 2 && !strcmp(argv[1], "help")) {
        puts("OminX Files: list PATH | info PATH | copy SOURCE DEST | move SOURCE DEST\n"
             "mkdir PATH | remove --confirm FILE\n"
             "JSON output; copy/move never overwrite. Copy handles regular files only.\n"
             "No recursive deletion. Cross-filesystem moves are refused; copy explicitly.");
        return 0;
    }
    int result = -1;
    if (argc == 3 && !strcmp(argv[1], "list")) result = listing(argv[2]);
    else if (argc == 3 && !strcmp(argv[1], "info")) {
        struct stat st;
        if (!(result = lstat(argv[2], &st))) { putchar('{'); metadata(&st); puts("}"); }
    } else if (argc == 4 && !strcmp(argv[1], "copy")) result = ominx_copy(argv[2], argv[3]);
    else if (argc == 4 && !strcmp(argv[1], "move")) result = ominx_move(argv[2], argv[3]);
    else if (argc == 3 && !strcmp(argv[1], "mkdir")) result = mkdir(argv[2], 0755);
    else if (argc == 4 && !strcmp(argv[1], "remove") && !strcmp(argv[2], "--confirm")) result = unlink(argv[3]);
    else { fputs("Usage: ominx-files help\n", stderr); return 2; }
    if (result < 0) {
        fputs("{\"error\":", stdout); json_string(strerror(errno)); puts("}"); return 1;
    }
    if (strcmp(argv[1], "list") && strcmp(argv[1], "info")) puts("{\"ok\":true}");
    return result;
}
