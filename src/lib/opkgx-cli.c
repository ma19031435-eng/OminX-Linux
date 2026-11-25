/* ominx-opkgx: command line front end for OPKGX apps. Runs as the user.
   Usage:
     ominx-opkgx validate <file.opkgx>
     ominx-opkgx install  [--notify] <file.opkgx>
     ominx-opkgx remove   <id>
     ominx-opkgx list
     ominx-opkgx run      [--notify] <id>
     ominx-opkgx pack     <source-dir> <out.opkgx>
   --notify also shows the result in the desktop notification area (notify-send).
   Exit status: 0 on success, 1 on failure (reason on stderr), 2 on bad usage. */
#include "opkgx.h"

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

static int notify_wanted;

/* Shows a desktop notification. Best effort: a missing notify-send is not an error. */
static void notify(const char *urgency, const char *text) {
    if (!notify_wanted) return;
    pid_t pid = fork();
    if (pid == 0) {
        execlp("notify-send", "notify-send", "-u", urgency, "OminX", text, (char *)NULL);
        _exit(127);
    }
    if (pid > 0) while (waitpid(pid, NULL, 0) < 0 && errno == EINTR) {}
}

static int usage(void) {
    fputs("usage: ominx-opkgx validate|install <file.opkgx>\n"
          "       ominx-opkgx remove|run <id>\n"
          "       ominx-opkgx list\n"
          "       ominx-opkgx pack <source-dir> <out.opkgx>\n", stderr);
    return 2;
}

static int fail(const char *what, const char *reason) {
    fprintf(stderr, "ominx-opkgx: %s: %s\n", what, reason);
    char text[320];
    snprintf(text, sizeof text, "%s failed: %s", what, reason);
    notify("critical", text);
    return 1;
}

int main(int argc, char **argv) {
    const char *home = getenv("HOME");
    char err[256] = "";
    if (!home || !*home) return fail("setup", "HOME is not set");
    /* --notify may appear anywhere; remove it so the commands see clean arguments. */
    int kept = 1;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--notify")) notify_wanted = 1;
        else argv[kept++] = argv[i];
    }
    argc = kept;
    if (argc < 2) return usage();
    const char *cmd = argv[1];

    if (!strcmp(cmd, "validate") && argc == 3) {
        struct opkgx_manifest m;
        if (opkgx_validate(argv[2], &m, err, sizeof err)) return fail("invalid", err);
        printf("%s %s %s\n", m.id, m.version, m.runner == OPKGX_RUNNER_WINE ? "wine" : "native");
        return 0;
    }
    if (!strcmp(cmd, "install") && argc == 3) {
        if (opkgx_install(argv[2], home, err, sizeof err)) return fail("install", err);
        notify("normal", "Application installed");
        return 0;
    }
    if (!strcmp(cmd, "remove") && argc == 3) {
        if (opkgx_remove(argv[2], home, err, sizeof err)) return fail("remove", err);
        return 0;
    }
    if (!strcmp(cmd, "list") && argc == 2) {
        return opkgx_list(home, stdout) ? fail("list", "registry unreadable") : 0;
    }
    if (!strcmp(cmd, "run") && argc == 3) {
        if (opkgx_run(argv[2], home, err, sizeof err)) return fail("run", err);
        return 0;
    }
    if (!strcmp(cmd, "pack") && argc == 4) {
        if (opkgx_pack(argv[2], argv[3], err, sizeof err)) return fail("pack", err);
        return 0;
    }
    return usage();
}
