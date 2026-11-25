/* ominx-forge: the Forge toolchain and runtime for OminXOS.

   Usage (see docs/forge-studio.md and docs/forge-language.md):
     ominx-forge new <dir> --id <id> --name <name> [--version V] [--summary S]
     ominx-forge check <dir|file.fg> [--json]
     ominx-forge run   <dir|file.fg>
     ominx-forge test  <dir|file.fg>
     ominx-forge build <dir> [--out file.opkgx]
     ominx-forge exec  <file.fg>            (used by ominx-opkgx for installed apps)
     ominx-forge tree  <dir> [--json]
     ominx-forge read  <dir> <rel>
     ominx-forge write <dir> <rel>          (contents from stdin)
     ominx-forge version | help

   Forge runs only on OminXOS. Every command except version and help first checks
   that /etc/os-release identifies OminX (ID=ominx) and that the file is owned by
   root and not writable by others. A build for tests may read the identity from
   OMINX_FORGE_OS_RELEASE instead; that hook does not exist in the shipped binary. */
#define _DEFAULT_SOURCE

#include "../lib/opkgx.h"
#include "forge.h"

#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#define PROJECT_FILE "forge.project"
#define PROJECT_MAX 4096
#define REL_MAX 255

/* ---------- platform gate ---------- */

static int platform_is_ominx(void) {
    const char *path = "/etc/os-release";
#ifdef OMINX_FORGE_TEST
    const char *override = getenv("OMINX_FORGE_OS_RELEASE");
    if (override) path = override;
#endif
    struct stat st;
    if (stat(path, &st) || !S_ISREG(st.st_mode)) return 0;
#ifndef OMINX_FORGE_TEST
    if (st.st_uid != 0 || (st.st_mode & 022)) return 0;
#endif
    FILE *f = fopen(path, "r");
    if (!f) return 0;
    char line[256];
    int ok = 0;
    while (fgets(line, sizeof line, f)) {
        size_t len = strlen(line);
        if (len && line[len - 1] == '\n') line[--len] = '\0';
        if (!strcmp(line, "ID=ominx")) ok = 1;
    }
    fclose(f);
    return ok;
}

/* ---------- small helpers ---------- */

static int is_dir(const char *p) {
    struct stat st;
    return !stat(p, &st) && S_ISDIR(st.st_mode);
}

static int is_file(const char *p) {
    struct stat st;
    return !lstat(p, &st) && S_ISREG(st.st_mode);
}

static int join_path(char *out, size_t size, const char *a, const char *b) {
    size_t la = strlen(a), lb = strlen(b);
    if (la + lb + 2 > size) return -1;
    memcpy(out, a, la);
    out[la] = '/';
    memcpy(out + la + 1, b, lb + 1);
    return 0;
}

static int mkdir_p(const char *path) {
    char buf[PATH_MAX];
    if (strlen(path) >= sizeof buf) return -1;
    strcpy(buf, path);
    for (char *p = buf + 1; *p; p++) {
        if (*p == '/') {
            *p = '\0';
            if (mkdir(buf, 0755) && errno != EEXIST) return -1;
            *p = '/';
        }
    }
    if (mkdir(buf, 0755) && errno != EEXIST) return -1;
    return 0;
}

/* Relative paths the IDE may touch: no absolute paths, no "..", plain names only. */
static int safe_rel(const char *rel) {
    size_t n = strlen(rel);
    if (n == 0 || n > REL_MAX || rel[0] == '/' || rel[0] == '.') return 0;
    if (strstr(rel, "..") || strstr(rel, "//") || rel[n - 1] == '/') return 0;
    for (size_t i = 0; i < n; i++) {
        unsigned char ch = (unsigned char)rel[i];
        if (!(isalnum(ch) || ch == '.' || ch == '_' || ch == '-' || ch == '/')) return 0;
    }
    return 1;
}

/* What a project may contain in the editable tree. */
static int editable_rel(const char *rel) {
    if (!safe_rel(rel)) return 0;
    if (!strcmp(rel, PROJECT_FILE) || !strcmp(rel, "icon.png")) return 1;
    if (!strncmp(rel, "src/", 4)) {
        size_t n = strlen(rel);
        return n > 3 && !strcmp(rel + n - 3, ".fg");
    }
    return !strncmp(rel, "assets/", 7);
}

static int write_all(int fd, const char *data, size_t n) {
    while (n) {
        ssize_t w = write(fd, data, n);
        if (w < 0) { if (errno == EINTR) continue; return -1; }
        data += w;
        n -= (size_t)w;
    }
    return 0;
}

static int read_file(const char *path, char **out, size_t *len, size_t max) {
    FILE *f = fopen(path, "rb");
    if (!f) return -1;
    struct stat st;
    if (fstat(fileno(f), &st) || !S_ISREG(st.st_mode) || (size_t)st.st_size > max) {
        fclose(f);
        return -1;
    }
    char *buf = malloc((size_t)st.st_size + 1);
    if (!buf) { fclose(f); return -1; }
    size_t n = fread(buf, 1, (size_t)st.st_size, f);
    fclose(f);
    buf[n] = '\0';
    *out = buf;
    *len = n;
    return 0;
}

/* Length of a well-formed UTF-8 sequence starting at s, or 0 if it is not one. */
static size_t utf8_seq_len(const unsigned char *s) {
    unsigned char c = s[0];
    size_t need;
    unsigned int minv;
    unsigned int v;
    if (c < 0x80) return 1;
    if (c >= 0xC2 && c <= 0xDF) { need = 1; minv = 0x80; v = c & 0x1F; }
    else if (c >= 0xE0 && c <= 0xEF) { need = 2; minv = 0x800; v = c & 0x0F; }
    else if (c >= 0xF0 && c <= 0xF4) { need = 3; minv = 0x10000; v = c & 0x07; }
    else return 0;
    for (size_t i = 1; i <= need; i++) {
        if ((s[i] & 0xC0) != 0x80) return 0;
        v = (v << 6) | (s[i] & 0x3F);
    }
    if (v < minv || v > 0x10FFFF || (v >= 0xD800 && v <= 0xDFFF)) return 0;
    return need + 1;
}

/* JSON string output. Invalid UTF-8 becomes U+FFFD so every consumer can parse the stream. */
static void json_str(FILE *out, const char *s) {
    const unsigned char *u = (const unsigned char *)s;
    fputc('"', out);
    while (*u) {
        unsigned char ch = *u;
        if (ch >= 0x80) {
            size_t n = utf8_seq_len(u);
            if (n == 0) { fputs("\\ufffd", out); u++; continue; }
            fwrite(u, 1, n, out);
            u += n;
            continue;
        }
        if (ch == '"' || ch == '\\') fprintf(out, "\\%c", ch);
        else if (ch == '\n') fputs("\\n", out);
        else if (ch == '\r') fputs("\\r", out);
        else if (ch == '\t') fputs("\\t", out);
        else if (ch < 0x20 || ch == 0x7f) fprintf(out, "\\u%04x", ch);
        else fputc(ch, out);
        u++;
    }
    fputc('"', out);
}

static void rm_tree(const char *path) {
    struct stat st;
    if (lstat(path, &st)) return;
    if (S_ISDIR(st.st_mode)) {
        DIR *d = opendir(path);
        if (d) {
            struct dirent *e;
            while ((e = readdir(d))) {
                if (!strcmp(e->d_name, ".") || !strcmp(e->d_name, "..")) continue;
                char child[PATH_MAX];
                if (join_path(child, sizeof child, path, e->d_name) == 0) rm_tree(child);
            }
            closedir(d);
        }
        rmdir(path);
    } else {
        unlink(path);
    }
}

/* ---------- projects ---------- */

struct project {
    char dir[PATH_MAX];    /* project root, or the directory of a single file */
    int is_project;
    char entry[PATH_MAX];  /* the file to load */
    char assets[PATH_MAX]; /* assets folder, or NULL-equivalent empty string */
    char id[128], name[128], version[64], summary[256], categories[128], main_rel[256];
    int has_icon;
};

static void diag_add(struct forge_diags *d, const char *file, int line, int col, const char *msg) {
    if (!d || d->n >= FORGE_MAX_DIAGS) return;
    struct forge_diag *x = &d->d[d->n++];
    snprintf(x->file, sizeof x->file, "%s", file);
    x->line = line;
    x->col = col;
    snprintf(x->msg, sizeof x->msg, "%s", msg);
}

/* Parses forge.project (key=value lines). Problems go to @d. Returns 0 on success. */
static int read_project(struct project *pr, struct forge_diags *d) {
    char path[PATH_MAX];
    if (join_path(path, sizeof path, pr->dir, PROJECT_FILE)) return -1;
    char *text;
    size_t len;
    if (read_file(path, &text, &len, PROJECT_MAX)) {
        diag_add(d, PROJECT_FILE, 0, 0, "forge.project is missing or unreadable");
        return -1;
    }
    int bad = 0, line_no = 0;
    int seen_format = 0;
    char *save = NULL;
    for (char *line = strtok_r(text, "\n", &save); line; line = strtok_r(NULL, "\n", &save)) {
        line_no++;
        size_t ll = strlen(line);
        if (ll && line[ll - 1] == '\r') line[--ll] = '\0';
        if (!ll || line[0] == '#') continue;
        char *eq = strchr(line, '=');
        if (!eq) { diag_add(d, PROJECT_FILE, line_no, 1, "expected key=value"); bad = 1; continue; }
        *eq = '\0';
        const char *key = line, *val = eq + 1;
        if (!strcmp(key, "format")) {
            seen_format = 1;
            if (strcmp(val, "1")) { diag_add(d, PROJECT_FILE, line_no, 1, "format must be 1"); bad = 1; }
        } else if (!strcmp(key, "id") || !strcmp(key, "name") || !strcmp(key, "version") ||
                   !strcmp(key, "summary") || !strcmp(key, "categories") || !strcmp(key, "main")) {
            /* Long values are refused, never silently cut short. */
            char *dst = !strcmp(key, "id") ? pr->id : !strcmp(key, "name") ? pr->name
                      : !strcmp(key, "version") ? pr->version : !strcmp(key, "summary") ? pr->summary
                      : !strcmp(key, "categories") ? pr->categories : pr->main_rel;
            size_t cap = !strcmp(key, "id") ? sizeof pr->id : !strcmp(key, "name") ? sizeof pr->name
                       : !strcmp(key, "version") ? sizeof pr->version : !strcmp(key, "summary") ? sizeof pr->summary
                       : !strcmp(key, "categories") ? sizeof pr->categories : sizeof pr->main_rel;
            if (strlen(val) >= cap) {
                char msg[128];
                snprintf(msg, sizeof msg, "%s is too long (at most %zu characters)", key, cap - 1);
                diag_add(d, PROJECT_FILE, line_no, 1, msg);
                bad = 1;
            } else {
                memcpy(dst, val, strlen(val) + 1);
            }
        } else {
            char msg[128];
            snprintf(msg, sizeof msg, "unknown key '%s'", key);
            diag_add(d, PROJECT_FILE, line_no, 1, msg);
            bad = 1;
        }
    }
    free(text);
    if (!seen_format) { diag_add(d, PROJECT_FILE, 0, 0, "format=1 is required"); bad = 1; }
    if (!pr->id[0]) { diag_add(d, PROJECT_FILE, 0, 0, "id is required"); bad = 1; }
    if (!pr->name[0]) { diag_add(d, PROJECT_FILE, 0, 0, "name is required"); bad = 1; }
    if (!pr->version[0]) { diag_add(d, PROJECT_FILE, 0, 0, "version is required"); bad = 1; }
    if (!pr->main_rel[0]) snprintf(pr->main_rel, sizeof pr->main_rel, "main.fg");
    size_t mn = strlen(pr->main_rel);
    if (!safe_rel(pr->main_rel) || mn < 4 || strcmp(pr->main_rel + mn - 3, ".fg")) {
        diag_add(d, PROJECT_FILE, 0, 0, "main must be a .fg file inside src/");
        bad = 1;
    }
    return bad ? -1 : 0;
}

/* Works out what to load for a path that is either a project directory or a .fg file. */
static int resolve_target(const char *arg, struct project *pr, struct forge_diags *d) {
    memset(pr, 0, sizeof *pr);
    if (is_dir(arg)) {
        pr->is_project = 1;
        snprintf(pr->dir, sizeof pr->dir, "%s", arg);
        if (read_project(pr, d)) return -1;
        char entry[PATH_MAX];
        if (join_path(entry, sizeof entry, pr->dir, "src") || join_path(pr->entry, sizeof pr->entry, entry, pr->main_rel)) {
            diag_add(d, PROJECT_FILE, 0, 0, "project path is too long");
            return -1;
        }
        if (!is_file(pr->entry)) {
            char msg[300];
            snprintf(msg, sizeof msg, "main file src/%s is missing", pr->main_rel);
            diag_add(d, PROJECT_FILE, 0, 0, msg);
            return -1;
        }
        join_path(pr->assets, sizeof pr->assets, pr->dir, "assets");
        char icon[PATH_MAX];
        if (join_path(icon, sizeof icon, pr->dir, "icon.png") == 0 && is_file(icon)) pr->has_icon = 1;
        return 0;
    }
    if (!is_file(arg)) {
        diag_add(d, arg, 0, 0, "no such project folder or file");
        return -1;
    }
    snprintf(pr->entry, sizeof pr->entry, "%s", arg);
    snprintf(pr->dir, sizeof pr->dir, "%s", arg);
    char *slash = strrchr(pr->dir, '/');
    if (slash) *slash = '\0';
    else strcpy(pr->dir, ".");
    if (join_path(pr->assets, sizeof pr->assets, pr->dir, "assets")) pr->assets[0] = '\0';
    return 0;
}

/* Display names are relative to src/ for projects, so the IDE can open them. */
static void print_diags(const struct forge_diags *d, const struct project *pr, int json) {
    if (json) {
        printf("{\"ok\":%s,\"diagnostics\":[", d->n ? "false" : "true");
        for (size_t i = 0; i < d->n; i++) {
            const struct forge_diag *x = &d->d[i];
            char file[PATH_MAX];
            if (pr->is_project && strcmp(x->file, PROJECT_FILE)) snprintf(file, sizeof file, "src/%s", x->file);
            else snprintf(file, sizeof file, "%s", x->file);
            if (i) fputc(',', stdout);
            fputs("{\"file\":", stdout);
            json_str(stdout, file);
            printf(",\"line\":%d,\"col\":%d,\"message\":", x->line, x->col);
            json_str(stdout, x->msg);
            fputc('}', stdout);
        }
        printf("]}\n");
        return;
    }
    for (size_t i = 0; i < d->n; i++) {
        const struct forge_diag *x = &d->d[i];
        char file[PATH_MAX];
        if (pr->is_project && strcmp(x->file, PROJECT_FILE)) snprintf(file, sizeof file, "src/%s", x->file);
        else snprintf(file, sizeof file, "%s", x->file);
        if (x->line > 0) fprintf(stderr, "%s:%d:%d: error: %s\n", file, x->line, x->col, x->msg);
        else fprintf(stderr, "%s: error: %s\n", file, x->msg);
    }
}

/* ---------- commands ---------- */

static int usage(void) {
    fprintf(stderr,
            "usage: ominx-forge new <dir> --id <id> --name <name> [--version V] [--summary S]\n"
            "       ominx-forge check <dir|file.fg> [--json]\n"
            "       ominx-forge run <dir|file.fg>\n"
            "       ominx-forge test <dir|file.fg>\n"
            "       ominx-forge build <dir> [--out file.opkgx]\n"
            "       ominx-forge exec <file.fg>\n"
            "       ominx-forge tree <dir> [--json]\n"
            "       ominx-forge read <dir> <rel>\n"
            "       ominx-forge write <dir> <rel>   (contents from stdin)\n"
            "       ominx-forge version\n");
    return 2;
}

static const char *template_main =
    "// Your Forge program. Run it with: ominx-forge run .\n"
    "\n"
    "fn greet(name) {\n"
    "    return \"Hello, \" + name + \"!\"\n"
    "}\n"
    "\n"
    "fn main() {\n"
    "    print(greet(\"OminX\"))\n"
    "}\n"
    "\n"
    "fn test_greet() {\n"
    "    assert(greet(\"Forge\") == \"Hello, Forge!\", \"greet builds its message\")\n"
    "}\n";

static int cmd_new(int argc, char **argv) {
    if (argc < 3) return usage();
    const char *dir = argv[2];
    const char *id = NULL, *name = NULL, *version = "1.0.0", *summary = NULL;
    for (int i = 3; i < argc; i++) {
        if (!strcmp(argv[i], "--id") && i + 1 < argc) id = argv[++i];
        else if (!strcmp(argv[i], "--name") && i + 1 < argc) name = argv[++i];
        else if (!strcmp(argv[i], "--version") && i + 1 < argc) version = argv[++i];
        else if (!strcmp(argv[i], "--summary") && i + 1 < argc) summary = argv[++i];
        else return usage();
    }
    if (!id || !name) return usage();
    if (strchr(name, '\n') || (summary && strchr(summary, '\n'))) {
        fprintf(stderr, "ominx-forge: names must be on one line\n");
        return 1;
    }
    if (is_dir(dir) || is_file(dir)) {
        fprintf(stderr, "ominx-forge: %s already exists\n", dir);
        return 1;
    }
    char path[PATH_MAX], sub[PATH_MAX];
    if (mkdir_p(dir)) { fprintf(stderr, "ominx-forge: cannot create %s\n", dir); return 1; }
    if (join_path(sub, sizeof sub, dir, "src") || mkdir_p(sub)) return 1;
    if (join_path(sub, sizeof sub, dir, "assets") || mkdir_p(sub)) return 1;
    if (join_path(path, sizeof path, dir, PROJECT_FILE)) return 1;
    FILE *f = fopen(path, "w");
    if (!f) { fprintf(stderr, "ominx-forge: cannot write %s\n", path); return 1; }
    fprintf(f, "format=1\nid=%s\nname=%s\nversion=%s\n", id, name, version);
    if (summary) fprintf(f, "summary=%s\n", summary);
    fprintf(f, "categories=Utilities\nmain=main.fg\n");
    fclose(f);
    if (join_path(path, sizeof path, dir, "src/main.fg")) return 1;
    f = fopen(path, "w");
    if (!f) return 1;
    fputs(template_main, f);
    fclose(f);
    if (join_path(path, sizeof path, dir, "assets/README.txt")) return 1;
    f = fopen(path, "w");
    if (!f) return 1;
    fputs("Files here ship with the app. Read them from Forge with read_asset(\"name.txt\").\n", f);
    fclose(f);
    printf("created %s\n", dir);
    return 0;
}

static int cmd_check(int argc, char **argv) {
    if (argc < 3) return usage();
    int json = argc > 3 && !strcmp(argv[3], "--json");
    struct project pr;
    struct forge_diags d;
    memset(&d, 0, sizeof d);
    if (resolve_target(argv[2], &pr, &d)) {
        print_diags(&d, &pr, json);
        return 1;
    }
    forge_program *p = NULL;
    if (forge_load(pr.entry, &p, &d) != 0) {
        print_diags(&d, &pr, json);
        return 1;
    }
    forge_free(p);
    if (json) printf("{\"ok\":true,\"diagnostics\":[]}\n");
    else printf("ok\n");
    return 0;
}

static int cmd_run_like(int argc, char **argv, int mode /* 0 run, 1 test */) {
    if (argc < 3) return usage();
    struct project pr;
    struct forge_diags d;
    memset(&d, 0, sizeof d);
    if (resolve_target(argv[2], &pr, &d)) { print_diags(&d, &pr, 0); return 1; }
    forge_program *p = NULL;
    if (forge_load(pr.entry, &p, &d) != 0) { print_diags(&d, &pr, 0); return 1; }
    const char *assets = pr.assets[0] && is_dir(pr.assets) ? pr.assets : NULL;
    int code;
    if (mode == 0) {
        code = forge_run_main(p, assets, stdout, stderr);
    } else {
        size_t passed = 0, failed = 0;
        int r = forge_run_tests(p, assets, stdout, &passed, &failed);
        if (r < 0) { fprintf(stderr, "no test_ functions found\n"); code = 1; }
        else {
            printf("%zu passed, %zu failed\n", passed, failed);
            code = failed ? 1 : 0;
        }
    }
    forge_free(p);
    return code;
}

/* Copies a tree of .fg sources (src) or any files (assets) into a staging folder. */
static int copy_file(const char *from, const char *to) {
    char *text;
    size_t len;
    if (read_file(from, &text, &len, 64u * 1024u * 1024u)) return -1;
    int fd = open(to, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd < 0) { free(text); return -1; }
    int rc = write_all(fd, text, len);
    close(fd);
    free(text);
    return rc;
}

static int copy_tree(const char *from, const char *to, int fg_only, char *err, size_t err_size) {
    if (mkdir_p(to)) { snprintf(err, err_size, "cannot create staging folder"); return -1; }
    DIR *d = opendir(from);
    if (!d) { snprintf(err, err_size, "cannot read %.200s", from); return -1; }
    struct dirent *e;
    int rc = 0;
    while (rc == 0 && (e = readdir(d))) {
        if (!strcmp(e->d_name, ".") || !strcmp(e->d_name, "..")) continue;
        char src[PATH_MAX], dst[PATH_MAX];
        if (join_path(src, sizeof src, from, e->d_name) || join_path(dst, sizeof dst, to, e->d_name)) {
            snprintf(err, err_size, "path too long");
            rc = -1;
            break;
        }
        struct stat st;
        if (lstat(src, &st)) { snprintf(err, err_size, "cannot read %.200s", src); rc = -1; break; }
        if (S_ISLNK(st.st_mode)) { snprintf(err, err_size, "symbolic links are not allowed in a project"); rc = -1; break; }
        if (S_ISDIR(st.st_mode)) {
            rc = copy_tree(src, dst, fg_only, err, err_size);
        } else if (S_ISREG(st.st_mode)) {
            size_t n = strlen(e->d_name);
            if (fg_only && (n < 4 || strcmp(e->d_name + n - 3, ".fg"))) {
                snprintf(err, err_size, "only .fg files belong in src/");
                rc = -1;
                break;
            }
            if (copy_file(src, dst)) { snprintf(err, err_size, "cannot copy %.200s", src); rc = -1; }
        } else {
            snprintf(err, err_size, "special files are not allowed in a project");
            rc = -1;
        }
    }
    closedir(d);
    return rc;
}

static int write_manifest(const struct project *pr, const char *path) {
    FILE *f = fopen(path, "w");
    if (!f) return -1;
    fprintf(f, "format=1\nid=%s\nname=%s\nversion=%s\n", pr->id, pr->name, pr->version);
    if (pr->summary[0]) fprintf(f, "summary=%s\n", pr->summary);
    fprintf(f, "arch=x86_64\nrunner=forge\nexec=app/%s\n", pr->main_rel);
    if (pr->has_icon) fprintf(f, "icon=icon.png\n");
    if (pr->categories[0]) fprintf(f, "categories=%s\n", pr->categories);
    return fclose(f) ? -1 : 0;
}

static int cmd_build(int argc, char **argv) {
    if (argc < 3) return usage();
    const char *out_arg = NULL;
    for (int i = 3; i < argc; i++) {
        if (!strcmp(argv[i], "--out") && i + 1 < argc) out_arg = argv[++i];
        else return usage();
    }
    struct project pr;
    struct forge_diags d;
    memset(&d, 0, sizeof d);
    if (resolve_target(argv[2], &pr, &d) || !pr.is_project) {
        if (!pr.is_project && !d.n) diag_add(&d, argv[2], 0, 0, "build needs a project folder");
        print_diags(&d, &pr, 0);
        return 1;
    }
    forge_program *p = NULL;
    if (forge_load(pr.entry, &p, &d) != 0) { print_diags(&d, &pr, 0); return 1; }
    forge_free(p);

    char out_path[PATH_MAX];
    if (out_arg) snprintf(out_path, sizeof out_path, "%s", out_arg);
    else {
        char buildDir[PATH_MAX], name[300];
        if (join_path(buildDir, sizeof buildDir, pr.dir, "build")) return 1;
        snprintf(name, sizeof name, "%s-%s.opkgx", pr.id, pr.version);
        if (mkdir_p(buildDir) || join_path(out_path, sizeof out_path, buildDir, name)) return 1;
    }

    char stage[PATH_MAX], buildDir[PATH_MAX];
    if (join_path(buildDir, sizeof buildDir, pr.dir, "build")) return 1;
    char stage_name[64];
    snprintf(stage_name, sizeof stage_name, ".stage-%ld", (long)getpid());
    if (mkdir_p(buildDir) || join_path(stage, sizeof stage, buildDir, stage_name)) return 1;
    rm_tree(stage);
    char err[256] = "";
    char app[PATH_MAX], assets_dst[PATH_MAX], man[PATH_MAX], icon_dst[PATH_MAX], icon_src[PATH_MAX];
    int ok = 0;
    if (mkdir_p(stage) || join_path(app, sizeof app, stage, "app")) goto done;
    if (join_path(man, sizeof man, stage, "opkgx.manifest") || write_manifest(&pr, man)) {
        snprintf(err, sizeof err, "cannot write the manifest");
        goto done;
    }
    char src_dir[PATH_MAX];
    if (join_path(src_dir, sizeof src_dir, pr.dir, "src") || copy_tree(src_dir, app, 1, err, sizeof err)) goto done;
    if (is_dir(pr.assets)) {
        if (join_path(assets_dst, sizeof assets_dst, app, "assets") || copy_tree(pr.assets, assets_dst, 0, err, sizeof err))
            goto done;
    }
    if (pr.has_icon) {
        if (join_path(icon_src, sizeof icon_src, pr.dir, "icon.png") || join_path(icon_dst, sizeof icon_dst, stage, "icon.png") ||
            copy_file(icon_src, icon_dst)) {
            snprintf(err, sizeof err, "cannot copy icon.png");
            goto done;
        }
    }
    if (opkgx_pack(stage, out_path, err, sizeof err)) goto done;
    ok = 1;
done:
    rm_tree(stage);
    if (!ok) {
        fprintf(stderr, "ominx-forge: build failed: %s\n", err[0] ? err : "unknown error");
        return 1;
    }
    printf("built %s\n", out_path);
    return 0;
}

/* Lists the editable tree: forge.project, icon.png, and the src and assets folders. */
static void list_tree(const char *root, const char *rel, FILE *out, int *first, int json, int depth) {
    if (depth > 8) return;
    char full[PATH_MAX];
    if (rel[0]) { if (join_path(full, sizeof full, root, rel)) return; }
    else snprintf(full, sizeof full, "%s", root);
    DIR *d = opendir(full);
    if (!d) return;
    struct dirent *e;
    char names[256][256];
    size_t count = 0;
    while ((e = readdir(d)) && count < 256) {
        if (!strcmp(e->d_name, ".") || !strcmp(e->d_name, "..") || e->d_name[0] == '.') continue;
        if (!strcmp(e->d_name, "build")) continue;
        snprintf(names[count++], sizeof names[0], "%s", e->d_name);
    }
    closedir(d);
    for (size_t i = 0; i < count; i++) {
        for (size_t j = i + 1; j < count; j++) if (strcmp(names[j], names[i]) < 0) {
            char tmp[256];
            memcpy(tmp, names[i], sizeof tmp);
            memcpy(names[i], names[j], sizeof tmp);
            memcpy(names[j], tmp, sizeof tmp);
        }
    }
    for (size_t i = 0; i < count; i++) {
        char child_rel[PATH_MAX], child_full[PATH_MAX];
        if (rel[0]) snprintf(child_rel, sizeof child_rel, "%.250s/%.250s", rel, names[i]);
        else snprintf(child_rel, sizeof child_rel, "%.250s", names[i]);
        if (join_path(child_full, sizeof child_full, root, child_rel)) continue;
        int dir = is_dir(child_full);
        if (!dir && !editable_rel(child_rel)) continue;
        if (dir && strcmp(child_rel, "src") && strcmp(child_rel, "assets") &&
            strncmp(child_rel, "src/", 4) && strncmp(child_rel, "assets/", 7))
            continue;
        if (json) {
            if (!*first) fputc(',', out);
            fputs("{\"path\":", out);
            json_str(out, child_rel);
            fprintf(out, ",\"kind\":\"%s\"}", dir ? "dir" : "file");
        } else {
            fprintf(out, "%s%s\n", child_rel, dir ? "/" : "");
        }
        *first = 0;
        if (dir) list_tree(root, child_rel, out, first, json, depth + 1);
    }
}

static int cmd_tree(int argc, char **argv) {
    if (argc < 3) return usage();
    int json = argc > 3 && !strcmp(argv[3], "--json");
    if (!is_dir(argv[2])) { fprintf(stderr, "ominx-forge: not a project folder\n"); return 1; }
    int first = 1;
    if (json) fputs("[", stdout);
    list_tree(argv[2], "", stdout, &first, json, 0);
    if (json) fputs("]\n", stdout);
    return 0;
}

static int cmd_read(int argc, char **argv) {
    if (argc != 4 || !is_dir(argv[2])) return usage();
    if (!editable_rel(argv[3])) { fprintf(stderr, "ominx-forge: that path is not part of a project\n"); return 1; }
    char path[PATH_MAX];
    if (join_path(path, sizeof path, argv[2], argv[3])) return 1;
    char *text;
    size_t len;
    if (read_file(path, &text, &len, FORGE_MAX_SOURCE)) { fprintf(stderr, "ominx-forge: cannot read %s\n", argv[3]); return 1; }
    fwrite(text, 1, len, stdout);
    free(text);
    return 0;
}

static int cmd_write(int argc, char **argv) {
    if (argc != 4 || !is_dir(argv[2])) return usage();
    if (!editable_rel(argv[3])) { fprintf(stderr, "ominx-forge: that path is not part of a project\n"); return 1; }
    char path[PATH_MAX], parent[PATH_MAX];
    if (join_path(path, sizeof path, argv[2], argv[3])) return 1;
    snprintf(parent, sizeof parent, "%s", path);
    char *slash = strrchr(parent, '/');
    if (slash) { *slash = '\0'; if (mkdir_p(parent)) return 1; }
    char tmp[PATH_MAX];
    if (snprintf(tmp, sizeof tmp, "%s.tmp-%ld", path, (long)getpid()) >= (int)sizeof tmp) return 1;
    int fd = open(tmp, O_WRONLY | O_CREAT | O_TRUNC | O_NOFOLLOW, 0644);
    if (fd < 0) { fprintf(stderr, "ominx-forge: cannot write %s\n", argv[3]); return 1; }
    char buf[8192];
    ssize_t r;
    size_t total = 0;
    int rc = 0;
    while ((r = read(STDIN_FILENO, buf, sizeof buf)) != 0) {
        if (r < 0) { if (errno == EINTR) continue; rc = -1; break; }
        total += (size_t)r;
        if (total > FORGE_MAX_SOURCE) { rc = -1; break; }
        if (write_all(fd, buf, (size_t)r)) { rc = -1; break; }
    }
    if (close(fd)) rc = -1;
    if (rc || rename(tmp, path)) {
        unlink(tmp);
        fprintf(stderr, "ominx-forge: cannot save %s\n", argv[3]);
        return 1;
    }
    return 0;
}

int main(int argc, char **argv) {
    if (argc < 2) return usage();
    const char *cmd = argv[1];
    if (!strcmp(cmd, "version")) { printf("Forge 1.0 (ominx-forge)\n"); return 0; }
    if (!strcmp(cmd, "help") || !strcmp(cmd, "--help")) { usage(); return 0; }

    if (!platform_is_ominx()) {
        fprintf(stderr, "ominx-forge: Forge runs only on OminXOS.\n");
        return 3;
    }
    if (!strcmp(cmd, "new")) return cmd_new(argc, argv);
    if (!strcmp(cmd, "check")) return cmd_check(argc, argv);
    if (!strcmp(cmd, "run") || !strcmp(cmd, "exec")) return cmd_run_like(argc, argv, 0);
    if (!strcmp(cmd, "test")) return cmd_run_like(argc, argv, 1);
    if (!strcmp(cmd, "build")) return cmd_build(argc, argv);
    if (!strcmp(cmd, "tree")) return cmd_tree(argc, argv);
    if (!strcmp(cmd, "read")) return cmd_read(argc, argv);
    if (!strcmp(cmd, "write")) return cmd_write(argc, argv);
    return usage();
}
