#define _DEFAULT_SOURCE
#define _POSIX_C_SOURCE 200809L

#include "opkgx.h"

#include <dirent.h>
#include <stddef.h>
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#define BLOCK 512
#define PATH_BUF 4096
#define COPY_CHUNK (64 * 1024)

/* ---- helpers ---- */

static int set_err(char *err, size_t size, const char *reason) {
    size_t i = 0;
    if (!size) return -1;
    while (reason[i] && i + 1 < size) { err[i] = reason[i]; i++; }
    err[i] = '\0';
    return -1;
}

/* Joins a/b into out. Returns -1 if it would not fit. */
static int join(char *out, size_t size, const char *a, const char *b) {
    size_t la = strlen(a), lb = strlen(b);
    if (la + 1 + lb + 1 > size) return -1;
    memcpy(out, a, la);
    out[la] = '/';
    memcpy(out + la + 1, b, lb + 1);
    return 0;
}

static int starts_with(const char *s, const char *prefix) {
    return strncmp(s, prefix, strlen(prefix)) == 0;
}

static int ends_with_ci(const char *s, const char *suffix) {
    size_t ls = strlen(s), lx = strlen(suffix);
    if (ls < lx) return 0;
    for (size_t i = 0; i < lx; i++) {
        char a = s[ls - lx + i], b = suffix[i];
        if (a >= 'A' && a <= 'Z') a = (char)(a - 'A' + 'a');
        if (b >= 'A' && b <= 'Z') b = (char)(b - 'A' + 'a');
        if (a != b) return 0;
    }
    return 1;
}

static int mkdir_p(const char *path) {
    char buf[PATH_BUF];
    if (strlen(path) >= sizeof buf) return -1;
    strcpy(buf, path);
    for (char *p = buf + 1; *p; p++) {
        if (*p != '/') continue;
        *p = '\0';
        if (mkdir(buf, 0755) && errno != EEXIST) return -1;
        *p = '/';
    }
    if (mkdir(buf, 0755) && errno != EEXIST) return -1;
    struct stat st;
    if (stat(buf, &st) || !S_ISDIR(st.st_mode)) return -1;
    return 0;
}

static int path_exists(const char *path) {
    struct stat st;
    return lstat(path, &st) == 0;
}

static int rm_tree(const char *path, int depth) {
    struct stat st;
    if (lstat(path, &st)) return errno == ENOENT ? 0 : -1;
    if (!S_ISDIR(st.st_mode) || depth > 64) return unlink(path);
    DIR *d = opendir(path);
    if (!d) return -1;
    struct dirent *e;
    int rc = 0;
    while ((e = readdir(d))) {
        if (!strcmp(e->d_name, ".") || !strcmp(e->d_name, "..")) continue;
        char child[PATH_BUF];
        if (join(child, sizeof child, path, e->d_name) || rm_tree(child, depth + 1)) { rc = -1; break; }
    }
    closedir(d);
    if (rc) return -1;
    return rmdir(path);
}

/* ---- ustar reader ---- */

struct tar_hdr {
    char name[100];
    char mode[8];
    char uid[8];
    char gid[8];
    char size[12];
    char mtime[12];
    char chksum[8];
    char typeflag;
    char linkname[100];
    char magic[6];
    char version[2];
    char uname[32];
    char gname[32];
    char devmajor[8];
    char devminor[8];
    char prefix[155];
    char pad[12];
};

_Static_assert(sizeof(struct tar_hdr) == BLOCK, "tar header must be one block");

static int parse_octal(const char *s, size_t n, uint64_t *out) {
    uint64_t v = 0;
    size_t i = 0, digits = 0;
    while (i < n && s[i] == ' ') i++;
    for (; i < n && s[i] && s[i] != ' '; i++) {
        if (s[i] < '0' || s[i] > '7') return -1;
        if (v > (UINT64_MAX >> 3)) return -1;
        v = (v << 3) | (uint64_t)(s[i] - '0');
        digits++;
    }
    if (!digits) return -1;
    *out = v;
    return 0;
}

static int block_is_zero(const unsigned char *b) {
    for (size_t i = 0; i < BLOCK; i++) if (b[i]) return 0;
    return 1;
}

/* Reads one header block.
   Returns 1 at the end marker (two zero blocks), 0 with @hdr filled, or -1 with @err set.
   An archive that runs out before the marker is reported as truncated. */
static int read_header(FILE *f, struct tar_hdr *hdr, char *err, size_t err_size) {
    unsigned char raw[BLOCK];
    size_t n = fread(raw, 1, BLOCK, f);
    if (n != BLOCK) return set_err(err, err_size, "truncated"), -1;
    if (block_is_zero(raw)) {
        /* The end marker is two zero blocks. Without it the download was cut short. */
        unsigned char second[BLOCK];
        if (fread(second, 1, BLOCK, f) != BLOCK || !block_is_zero(second))
            return set_err(err, err_size, "truncated"), -1;
        return 1;
    }
    memcpy(hdr, raw, BLOCK);

    /* The checksum field counts as spaces. */
    unsigned sum = 0;
    for (size_t i = 0; i < BLOCK; i++) {
        int in_chksum = i >= offsetof(struct tar_hdr, chksum) && i < offsetof(struct tar_hdr, chksum) + 8;
        sum += in_chksum ? ' ' : raw[i];
    }
    uint64_t stored;
    if (parse_octal(hdr->chksum, sizeof hdr->chksum, &stored) || stored != sum)
        return set_err(err, err_size, "bad-checksum"), -1;
    if (memcmp(hdr->magic, "ustar\0", 6) || memcmp(hdr->version, "00", 2))
        return set_err(err, err_size, "not-ustar"), -1;
    return 0;
}

/* Full path: prefix/name. Strips one trailing slash from directory names. */
static int entry_path(const struct tar_hdr *hdr, char *out, size_t size, int is_dir) {
    char name[101], prefix[156];
    memcpy(name, hdr->name, 100); name[100] = '\0';
    memcpy(prefix, hdr->prefix, 155); prefix[155] = '\0';
    if (prefix[0]) {
        if (strlen(prefix) + 1 + strlen(name) + 1 > size) return -1;
        strcpy(out, prefix);
        strcat(out, "/");
        strcat(out, name);
    } else {
        if (strlen(name) + 1 > size) return -1;
        strcpy(out, name);
    }
    size_t n = strlen(out);
    if (is_dir && n > 1 && out[n - 1] == '/') out[n - 1] = '\0';
    return 0;
}

static int valid_path(const char *p) {
    size_t n = strlen(p);
    if (n == 0 || n > 255 || p[0] == '/') return 0;
    size_t i = 0;
    for (;;) {
        size_t start = i;
        while (p[i] && p[i] != '/') i++;
        size_t len = i - start;
        if (len == 0) return 0;
        if (len == 1 && p[start] == '.') return 0;
        if (len == 2 && p[start] == '.' && p[start + 1] == '.') return 0;
        for (size_t k = start; k < i; k++) {
            unsigned char c = (unsigned char)p[k];
            if (c < 0x20 || c == 0x7f || c == '\\') return 0;
        }
        if (!p[i]) break;
        i++;
    }
    return 1;
}

/* Maps a typeflag to 'f' (regular) or 'd' (directory); otherwise returns the refusal reason. */
static const char *entry_kind(char t, char *kind) {
    switch (t) {
    case '0': case '\0': *kind = 'f'; return NULL;
    case '5': *kind = 'd'; return NULL;
    case '1': case '2': return "link-entry";
    case '3': case '4': return "device-entry";
    case '6': return "fifo-entry";
    case 'x': case 'g': case 'L': case 'K': return "extension-entry";
    default: return "entry-type-unsupported";
    }
}

/* Only the layout in the spec is allowed: the manifest, the icon, and app/. */
static int allowed_entry(const char *path, char kind) {
    if (kind == 'd') return !strcmp(path, "app") || starts_with(path, "app/");
    if (!strcmp(path, "opkgx.manifest") || !strcmp(path, "icon.png")) return 1;
    return starts_with(path, "app/");
}

static uint64_t padded(uint64_t size) { return (size + BLOCK - 1) & ~(uint64_t)(BLOCK - 1); }

/* Skips @count bytes from the current position, refusing to pass the end of the file. */
static int skip_bytes(FILE *f, uint64_t count, uint64_t file_size) {
    long pos = ftell(f);
    if (pos < 0 || (uint64_t)pos + count > file_size) return -1;
    return fseek(f, (long)count, SEEK_CUR);
}

/* ---- manifest ---- */

enum key {
    K_FORMAT, K_ID, K_NAME, K_VERSION, K_SUMMARY, K_ARCH, K_RUNNER, K_EXEC,
    K_ICON, K_CATEGORIES, K_PERMISSIONS, K_COUNT
};

static const char *const key_names[K_COUNT] = {
    "format", "id", "name", "version", "summary", "arch", "runner", "exec",
    "icon", "categories", "permissions"
};

static int valid_text(const char *s, size_t min, size_t max) {
    size_t n = strlen(s);
    if (n < min || n > max) return 0;
    for (size_t i = 0; i < n; i++) {
        unsigned char c = (unsigned char)s[i];
        if (c < 0x20 || c == 0x7f) return 0;
    }
    return 1;
}

static int valid_id(const char *s) {
    size_t n = strlen(s);
    if (n < 2 || n > OPKGX_ID_MAX) return 0;
    if (!(s[0] >= 'a' && s[0] <= 'z')) return 0;
    for (size_t i = 0; i < n; i++) {
        char c = s[i];
        int ok = (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '.' || c == '-';
        if (!ok) return 0;
    }
    return strstr(s, "..") == NULL;
}

static int valid_version(const char *s) {
    int parts = 0;
    const char *p = s;
    for (;;) {
        size_t digits = 0;
        while (p[digits] >= '0' && p[digits] <= '9') digits++;
        if (digits < 1 || digits > 5) return 0;
        parts++;
        p += digits;
        if (*p == '\0') break;
        if (*p != '.') return 0;
        p++;
    }
    return parts == 3;
}

static unsigned category_bit(const char *name) {
    static const struct { const char *name; unsigned bit; } table[] = {
        {"Games", OPKGX_CAT_GAMES}, {"Office", OPKGX_CAT_OFFICE},
        {"Development", OPKGX_CAT_DEVELOPMENT}, {"Graphics", OPKGX_CAT_GRAPHICS},
        {"Audio", OPKGX_CAT_AUDIO}, {"Video", OPKGX_CAT_VIDEO},
        {"Utilities", OPKGX_CAT_UTILITIES}, {"Internet", OPKGX_CAT_INTERNET},
        {"Education", OPKGX_CAT_EDUCATION},
    };
    for (size_t i = 0; i < sizeof table / sizeof table[0]; i++)
        if (!strcmp(table[i].name, name)) return table[i].bit;
    return 0;
}

/* Parses and checks manifest text. Writes @m only when every check passes. */
static int parse_manifest(const char *text, size_t length, struct opkgx_manifest *m, char *err, size_t err_size) {
    if (length >= OPKGX_MANIFEST_MAX) return set_err(err, err_size, "too-large");
    char *buf = malloc(length + 1);
    if (!buf) return set_err(err, err_size, "out-of-memory");
    memcpy(buf, text, length);
    buf[length] = '\0';

    int seen[K_COUNT] = {0};
    char *values[K_COUNT] = {0};
    int rc = 0;
    char *p = buf;
    while (*p) {
        char *nl = strchr(p, '\n');
        if (nl) *nl = '\0';
        size_t len = strlen(p);
        if (len && p[len - 1] == '\r') p[--len] = '\0';
        if (len && p[0] != '#') {
            char *eq = strchr(p, '=');
            if (!eq) { rc = set_err(err, err_size, "bad-line"); break; }
            *eq = '\0';
            int k = -1;
            for (int i = 0; i < K_COUNT; i++) if (!strcmp(p, key_names[i])) k = i;
            if (k < 0) { rc = set_err(err, err_size, "unknown-key"); break; }
            if (seen[k]) { rc = set_err(err, err_size, "duplicate-key"); break; }
            seen[k] = 1;
            values[k] = eq + 1;
        }
        if (!nl) break;
        p = nl + 1;
    }
    if (rc) { free(buf); return rc; }

    struct opkgx_manifest out;
    memset(&out, 0, sizeof out);
    const int required[] = {K_FORMAT, K_ID, K_NAME, K_VERSION, K_ARCH, K_RUNNER, K_EXEC};
    for (size_t i = 0; i < sizeof required / sizeof required[0]; i++)
        if (!seen[required[i]]) { free(buf); return set_err(err, err_size, "missing-required-key"); }

#define FAIL(reason) do { free(buf); return set_err(err, err_size, (reason)); } while (0)
    if (strcmp(values[K_FORMAT], "1")) FAIL("format-unsupported");
    if (!valid_id(values[K_ID])) FAIL("bad-id");
    if (!valid_text(values[K_NAME], 1, OPKGX_NAME_MAX)) FAIL("bad-name");
    if (!valid_version(values[K_VERSION]) || strlen(values[K_VERSION]) >= OPKGX_VERSION_MAX) FAIL("bad-version");
    if (seen[K_SUMMARY] && !valid_text(values[K_SUMMARY], 0, OPKGX_SUMMARY_MAX)) FAIL("bad-summary");
    if (strcmp(values[K_ARCH], "x86_64")) FAIL("arch-unsupported");

    if (!strcmp(values[K_RUNNER], "native")) out.runner = OPKGX_RUNNER_NATIVE;
    else if (!strcmp(values[K_RUNNER], "wine")) out.runner = OPKGX_RUNNER_WINE;
    else FAIL("bad-runner");

    const char *exec = values[K_EXEC];
    if (strlen(exec) > OPKGX_EXEC_MAX || !starts_with(exec, "app/") || !valid_path(exec)) FAIL("exec-outside-app");
    if (out.runner == OPKGX_RUNNER_WINE) {
        if (ends_with_ci(exec, ".msi")) out.is_msi = 1;
        else if (!ends_with_ci(exec, ".exe")) FAIL("exec-not-windows");
    }

    if (seen[K_ICON]) {
        if (strcmp(values[K_ICON], "icon.png")) FAIL("bad-icon-key");
        out.has_icon = 1;
    }

    if (seen[K_CATEGORIES] && values[K_CATEGORIES][0]) {
        char copy[OPKGX_MANIFEST_MAX];
        if (strlen(values[K_CATEGORIES]) >= sizeof copy) FAIL("too-large");
        strcpy(copy, values[K_CATEGORIES]);
        char *save = NULL;
        for (char *tok = strtok_r(copy, ",", &save); tok; tok = strtok_r(NULL, ",", &save)) {
            unsigned bit = category_bit(tok);
            if (!bit) FAIL("bad-category");
            out.categories |= bit;
        }
    }

    if (seen[K_PERMISSIONS] && values[K_PERMISSIONS][0]) FAIL("permissions-unsupported");
#undef FAIL

    strcpy(out.id, values[K_ID]);
    strcpy(out.name, values[K_NAME]);
    strcpy(out.version, values[K_VERSION]);
    strcpy(out.summary, seen[K_SUMMARY] ? values[K_SUMMARY] : "");
    strcpy(out.exec, exec);
    free(buf);
    *m = out;
    return 0;
}

/* ---- validation ---- */

struct seen_list { char **names; size_t count, cap; };

/* Returns 0 if added, -1 if already present, -2 on allocation failure. */
static int seen_add(struct seen_list *s, const char *name) {
    for (size_t i = 0; i < s->count; i++) if (!strcmp(s->names[i], name)) return -1;
    if (s->count == s->cap) {
        size_t cap = s->cap ? s->cap * 2 : 64;
        char **n = realloc(s->names, cap * sizeof *n);
        if (!n) return -2;
        s->names = n;
        s->cap = cap;
    }
    s->names[s->count] = strdup(name);
    if (!s->names[s->count]) return -2;
    s->count++;
    return 0;
}

static void seen_free(struct seen_list *s) {
    for (size_t i = 0; i < s->count; i++) free(s->names[i]);
    free(s->names);
}

int opkgx_validate(const char *archive, struct opkgx_manifest *m, char *err, size_t err_size) {
    FILE *f = fopen(archive, "rb");
    if (!f) return set_err(err, err_size, "archive-unreadable");
    struct stat st;
    if (fstat(fileno(f), &st) || !S_ISREG(st.st_mode)) { fclose(f); return set_err(err, err_size, "archive-unreadable"); }
    uint64_t file_size = (uint64_t)st.st_size;

    struct opkgx_manifest man;
    memset(&man, 0, sizeof man);
    struct seen_list seen = {0};
    int have_manifest = 0, have_icon = 0, have_exec = 0, exec_executable = 0;
    uint64_t payload_total = 0;
    size_t payload_files = 0, entries = 0;
    int rc = -1;

    for (;;) {
        struct tar_hdr hdr;
        int h = read_header(f, &hdr, err, err_size);
        if (h == 1) break;
        if (h < 0) goto out;

        if (++entries > OPKGX_MAX_ENTRIES) { set_err(err, err_size, "too-many-entries"); goto out; }

        char kind;
        const char *refusal = entry_kind(hdr.typeflag, &kind);
        if (refusal) { set_err(err, err_size, refusal); goto out; }

        char path[256];
        if (entry_path(&hdr, path, sizeof path, kind == 'd')) { set_err(err, err_size, "path-too-long"); goto out; }
        if (!valid_path(path)) { set_err(err, err_size, "path-escape"); goto out; }
        if (!allowed_entry(path, kind)) { set_err(err, err_size, "unexpected-entry"); goto out; }

        uint64_t size = 0;
        if (parse_octal(hdr.size, sizeof hdr.size, &size)) { set_err(err, err_size, "bad-size"); goto out; }
        if (kind == 'd' && size != 0) { set_err(err, err_size, "bad-size"); goto out; }
        if (size > OPKGX_MAX_PAYLOAD) { set_err(err, err_size, "too-large"); goto out; }

        if (entries == 1 && (strcmp(path, "opkgx.manifest") || kind != 'f')) {
            set_err(err, err_size, "manifest-not-first");
            goto out;
        }

        if (kind == 'd') {
            if (seen_add(&seen, path) != 0) { set_err(err, err_size, "duplicate-entry"); goto out; }
            continue;
        }

        if (!strcmp(path, "opkgx.manifest")) {
            if (size >= OPKGX_MANIFEST_MAX) { set_err(err, err_size, "too-large"); goto out; }
            char *text = malloc(size + 1);
            if (!text) { set_err(err, err_size, "out-of-memory"); goto out; }
            if (fread(text, 1, size, f) != size) { free(text); set_err(err, err_size, "truncated"); goto out; }
            text[size] = '\0';
            int prc = parse_manifest(text, size, &man, err, err_size);
            free(text);
            if (prc) goto out;
            have_manifest = 1;
            if (skip_bytes(f, padded(size) - size, file_size)) { set_err(err, err_size, "truncated"); goto out; }
            if (seen_add(&seen, path) != 0) { set_err(err, err_size, "duplicate-entry"); goto out; }
            continue;
        }

        if (!have_manifest) { set_err(err, err_size, "manifest-missing"); goto out; }
        if (seen_add(&seen, path) != 0) { set_err(err, err_size, "duplicate-entry"); goto out; }

        if (!strcmp(path, "icon.png")) {
            if (size > OPKGX_ICON_MAX) { set_err(err, err_size, "too-large"); goto out; }
            if (size < 8) { set_err(err, err_size, "icon-not-png"); goto out; }
            unsigned char sig[8];
            const unsigned char png[8] = {0x89, 'P', 'N', 'G', '\r', '\n', 0x1a, '\n'};
            if (fread(sig, 1, 8, f) != 8 || memcmp(sig, png, 8)) { set_err(err, err_size, "icon-not-png"); goto out; }
            have_icon = 1;
            if (skip_bytes(f, padded(size) - 8, file_size)) { set_err(err, err_size, "truncated"); goto out; }
            continue;
        }

        if (!strcmp(path, man.exec)) {
            uint64_t mode = 0;
            have_exec = 1;
            exec_executable = !parse_octal(hdr.mode, sizeof hdr.mode, &mode) && (mode & 0111) != 0;
        }
        if (starts_with(path, "app/")) payload_files++;
        payload_total += size;
        if (payload_total > OPKGX_MAX_PAYLOAD) { set_err(err, err_size, "too-large"); goto out; }
        if (skip_bytes(f, padded(size), file_size)) { set_err(err, err_size, "truncated"); goto out; }
    }

    if (!have_manifest) { set_err(err, err_size, "manifest-missing"); goto out; }
    if (!have_exec) { set_err(err, err_size, "exec-missing"); goto out; }
    if (man.runner == OPKGX_RUNNER_NATIVE && !exec_executable) { set_err(err, err_size, "exec-not-executable"); goto out; }
    if (man.has_icon && !have_icon) { set_err(err, err_size, "icon-missing"); goto out; }
    if (have_icon && !man.has_icon) { set_err(err, err_size, "icon-undeclared"); goto out; }
    if (!payload_files) { set_err(err, err_size, "payload-missing"); goto out; }

    *m = man;
    rc = 0;
out:
    seen_free(&seen);
    fclose(f);
    return rc;
}

/* ---- extraction ---- */

static int extract_all(const char *archive, const char *staging, char *err, size_t err_size) {
    FILE *f = fopen(archive, "rb");
    if (!f) return set_err(err, err_size, "archive-unreadable");
    struct stat st;
    if (fstat(fileno(f), &st)) { fclose(f); return set_err(err, err_size, "archive-unreadable"); }
    uint64_t file_size = (uint64_t)st.st_size;
    char *chunk = malloc(COPY_CHUNK);
    if (!chunk) { fclose(f); return set_err(err, err_size, "out-of-memory"); }
    int rc = -1;

    for (;;) {
        struct tar_hdr hdr;
        int h = read_header(f, &hdr, err, err_size);
        if (h == 1) break;
        if (h < 0) goto out;
        char kind;
        if (entry_kind(hdr.typeflag, &kind)) { set_err(err, err_size, "link-entry"); goto out; }
        char path[256];
        if (entry_path(&hdr, path, sizeof path, kind == 'd')) { set_err(err, err_size, "path-too-long"); goto out; }
        uint64_t size = 0;
        if (parse_octal(hdr.size, sizeof hdr.size, &size)) { set_err(err, err_size, "bad-size"); goto out; }

        char target[PATH_BUF];
        if (join(target, sizeof target, staging, path)) { set_err(err, err_size, "path-too-long"); goto out; }

        if (kind == 'd') {
            if (mkdir_p(target)) { set_err(err, err_size, "extract-failed"); goto out; }
            continue;
        }

        /* Parent directories first, so a file never lands outside staging. */
        char parent[PATH_BUF];
        strcpy(parent, target);
        char *slash = strrchr(parent, '/');
        if (slash) {
            *slash = '\0';
            if (mkdir_p(parent)) { set_err(err, err_size, "extract-failed"); goto out; }
        }

        uint64_t mode_bits = 0;
        parse_octal(hdr.mode, sizeof hdr.mode, &mode_bits);
        int exec = (mode_bits & 0111) != 0;
        int fd = open(target, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0600);
        if (fd < 0) { set_err(err, err_size, "extract-failed"); goto out; }
        uint64_t left = size;
        while (left) {
            size_t want = left < COPY_CHUNK ? (size_t)left : COPY_CHUNK;
            if (fread(chunk, 1, want, f) != want) { close(fd); set_err(err, err_size, "truncated"); goto out; }
            const char *w = chunk;
            size_t remaining = want;
            while (remaining) {
                ssize_t wrote = write(fd, w, remaining);
                if (wrote <= 0) { close(fd); set_err(err, err_size, "extract-failed"); goto out; }
                w += wrote;
                remaining -= (size_t)wrote;
            }
            left -= want;
        }
        close(fd);
        if (chmod(target, exec ? 0755 : 0644)) { set_err(err, err_size, "extract-failed"); goto out; }
        if (skip_bytes(f, padded(size) - size, file_size)) { set_err(err, err_size, "truncated"); goto out; }
    }
    rc = 0;
out:
    free(chunk);
    fclose(f);
    return rc;
}

/* ---- install, remove, list, run ---- */

static int apps_dir(char *out, size_t size, const char *home) {
    char tmp[PATH_BUF];
    if (strlen(home) + 1 + strlen(".local/share/ominx/apps") + 1 > sizeof tmp) return -1;
    strcpy(tmp, home);
    strcat(tmp, "/.local/share/ominx/apps");
    if (strlen(tmp) >= size) return -1;
    strcpy(out, tmp);
    return 0;
}

/* Recovers from an interrupted swap: if the app is missing but .old-<id> exists, put it back. */
static void restore_old(const char *apps, const char *id) {
    char final[PATH_BUF], old[PATH_BUF], name[OPKGX_ID_MAX + 16];
    snprintf(name, sizeof name, ".old-%s", id);
    if (join(old, sizeof old, apps, name)) return;
    if (join(final, sizeof final, apps, id)) return;
    if (path_exists(old) && !path_exists(final)) rename(old, final);
}

/* Writes the desktop entry through a temp file, so a crash never leaves a half-written file. */
static int write_desktop(const char *home, const struct opkgx_manifest *m, const char *final_dir) {
    char dir[PATH_BUF];
    char dst[PATH_BUF + OPKGX_ID_MAX + 64], tmp[PATH_BUF + OPKGX_ID_MAX + 72];
    if (strlen(home) + 32 >= sizeof dir) return -1;
    snprintf(dir, sizeof dir, "%s/.local/share/applications", home);
    if (mkdir_p(dir)) return -1;
    snprintf(dst, sizeof dst, "%s/ominx-%s.desktop", dir, m->id);
    snprintf(tmp, sizeof tmp, "%s.tmp", dst);

    FILE *f = fopen(tmp, "w");
    if (!f) return -1;
    fprintf(f, "[Desktop Entry]\nType=Application\nName=%s\nComment=%s\n", m->name, m->summary);
    fprintf(f, "Exec=ominx-opkgx run %s\n", m->id);
    if (m->has_icon) fprintf(f, "Icon=%s/icon.png\n", final_dir);
    fprintf(f, "Terminal=false\nX-OminX-App=%s\nX-OminX-Runner=%s\n", m->id,
            m->runner == OPKGX_RUNNER_WINE ? "wine" : "native");
    if (m->categories) {
        static const char *const names[] = {"Games", "Office", "Development", "Graphics", "Audio",
                                            "Video", "Utilities", "Internet", "Education"};
        fputs("Categories=", f);
        for (size_t i = 0; i < sizeof names / sizeof names[0]; i++)
            if (m->categories & (1u << i)) fprintf(f, "%s;", names[i]);
        fputs("\n", f);
    }
    int bad = fclose(f) != 0;
    if (bad) { unlink(tmp); return -1; }
    if (rename(tmp, dst)) { unlink(tmp); return -1; }
    return 0;
}

/* Rewrites the registry: drops any line for @id, then appends @line when non-NULL. */
static int registry_rewrite(const char *apps, const char *id, const char *line) {
    char reg[PATH_BUF], tmp[PATH_BUF];
    if (join(reg, sizeof reg, apps, "registry")) return -1;
    if (snprintf(tmp, sizeof tmp, "%s.tmp", reg) >= (int)sizeof tmp) return -1;
    FILE *in = fopen(reg, "r");
    FILE *out = fopen(tmp, "w");
    if (!out) { if (in) fclose(in); return -1; }
    int ok = 1;
    if (in) {
        char buf[512];
        while (fgets(buf, sizeof buf, in)) {
            char first[OPKGX_ID_MAX + 2];
            size_t n = strcspn(buf, " \n");
            if (n >= sizeof first) n = sizeof first - 1;
            memcpy(first, buf, n);
            first[n] = '\0';
            if (strcmp(first, id) == 0) continue;
            if (fputs(buf, out) == EOF) ok = 0;
        }
        fclose(in);
    }
    if (line && fprintf(out, "%s\n", line) < 0) ok = 0;
    if (fclose(out) != 0) ok = 0;
    if (!ok || rename(tmp, reg)) { unlink(tmp); return -1; }
    return 0;
}

static int registry_add(const char *apps, const struct opkgx_manifest *m) {
    char line[512];
    snprintf(line, sizeof line, "%s %s %s %s", m->id, m->version,
             m->runner == OPKGX_RUNNER_WINE ? "wine" : "native",
             m->is_msi ? "setup-pending" : "ready");
    return registry_rewrite(apps, m->id, line);
}

/* Extracts the archive into a fresh staging directory. Refuses to write through anything but plain paths. */
int opkgx_install(const char *archive, const char *home, char *err, size_t err_size) {
    struct opkgx_manifest m;
    if (opkgx_validate(archive, &m, err, err_size)) return -1;

    char apps[PATH_BUF];
    if (apps_dir(apps, sizeof apps, home) || mkdir_p(apps)) return set_err(err, err_size, "apps-dir-unwritable");
    restore_old(apps, m.id);

    char staging[PATH_BUF], final[PATH_BUF], old[PATH_BUF], name[OPKGX_ID_MAX + 64];
    snprintf(name, sizeof name, ".staging-%s-%ld", m.id, (long)getpid());
    if (join(staging, sizeof staging, apps, name) || join(final, sizeof final, apps, m.id)) return set_err(err, err_size, "path-too-long");
    snprintf(name, sizeof name, ".old-%s", m.id);
    if (join(old, sizeof old, apps, name)) return set_err(err, err_size, "path-too-long");

    rm_tree(staging, 0);
    if (mkdir(staging, 0755)) return set_err(err, err_size, "extract-failed");
    if (extract_all(archive, staging, err, err_size)) { rm_tree(staging, 0); return -1; }

    if (path_exists(final)) {
        rm_tree(old, 0);
        if (rename(final, old)) { rm_tree(staging, 0); return set_err(err, err_size, "swap-failed"); }
    }
    if (rename(staging, final)) {
        if (path_exists(old)) rename(old, final);
        rm_tree(staging, 0);
        return set_err(err, err_size, "swap-failed");
    }
    rm_tree(old, 0);

    /* The registry is the source of truth, so it is written first. A failed menu entry
       leaves a working app that the user can still run, and is reported. */
    if (registry_add(apps, &m)) return set_err(err, err_size, "registry-failed");
    if (write_desktop(home, &m, final)) return set_err(err, err_size, "desktop-entry-failed");
    return 0;
}

int opkgx_remove(const char *id, const char *home, char *err, size_t err_size) {
    if (!valid_id(id)) return set_err(err, err_size, "bad-id");
    char apps[PATH_BUF], final[PATH_BUF], desk[PATH_BUF];
    if (apps_dir(apps, sizeof apps, home)) return set_err(err, err_size, "path-too-long");
    restore_old(apps, id);
    if (join(final, sizeof final, apps, id)) return set_err(err, err_size, "path-too-long");
    if (!path_exists(final)) return set_err(err, err_size, "not-installed");
    if (rm_tree(final, 0)) return set_err(err, err_size, "remove-failed");
    snprintf(desk, sizeof desk, "%s/.local/share/applications/ominx-%s.desktop", home, id);
    unlink(desk);
    if (registry_rewrite(apps, id, NULL)) return set_err(err, err_size, "registry-failed");
    return 0;
}

int opkgx_list(const char *home, FILE *out) {
    char apps[PATH_BUF], reg[PATH_BUF];
    if (apps_dir(apps, sizeof apps, home) || join(reg, sizeof reg, apps, "registry")) return -1;
    FILE *f = fopen(reg, "r");
    if (!f) return 0;
    char buf[512];
    while (fgets(buf, sizeof buf, f)) fputs(buf, out);
    fclose(f);
    return 0;
}

int opkgx_run(const char *id, const char *home, char *err, size_t err_size) {
    if (!valid_id(id)) return set_err(err, err_size, "bad-id");
    char apps[PATH_BUF], dir[PATH_BUF], mpath[PATH_BUF];
    if (apps_dir(apps, sizeof apps, home) || join(dir, sizeof dir, apps, id)) return set_err(err, err_size, "path-too-long");
    if (join(mpath, sizeof mpath, dir, "opkgx.manifest")) return set_err(err, err_size, "path-too-long");
    if (!path_exists(dir)) return set_err(err, err_size, "not-installed");

    FILE *f = fopen(mpath, "rb");
    if (!f) return set_err(err, err_size, "manifest-missing");
    char text[OPKGX_MANIFEST_MAX];
    size_t n = fread(text, 1, sizeof text - 1, f);
    fclose(f);
    text[n] = '\0';
    struct opkgx_manifest m;
    if (parse_manifest(text, n, &m, err, err_size)) return -1;
    if (strcmp(m.id, id)) return set_err(err, err_size, "manifest-id-mismatch");

    if (m.runner == OPKGX_RUNNER_WINE)
        return set_err(err, err_size, "wine-launch-not-wired");

    char exe[PATH_BUF];
    if (join(exe, sizeof exe, dir, m.exec)) return set_err(err, err_size, "path-too-long");
    pid_t pid = fork();
    if (pid < 0) return set_err(err, err_size, "fork-failed");
    if (pid == 0) {
        if (chdir(dir)) _exit(127);
        char *argv[] = {exe, NULL};
        execv(exe, argv);
        _exit(127);
    }
    return 0;
}
