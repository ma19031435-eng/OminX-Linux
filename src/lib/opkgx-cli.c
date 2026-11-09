/* ominx-opkgx: command line front end for OPKGX apps. Runs as the user.
   Usage:
     ominx-opkgx validate <file.opkgx>
     ominx-opkgx install  <file.opkgx>
     ominx-opkgx remove   <id>
     ominx-opkgx list
     ominx-opkgx run      <id>
   Exit status: 0 on success, 1 on failure (reason on stderr), 2 on bad usage. */
#include "opkgx.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int usage(void) {
    fputs("usage: ominx-opkgx validate|install <file.opkgx>\n"
          "       ominx-opkgx remove|run <id>\n"
          "       ominx-opkgx list\n", stderr);
    return 2;
}

static int fail(const char *what, const char *reason) {
    fprintf(stderr, "ominx-opkgx: %s: %s\n", what, reason);
    return 1;
}

int main(int argc, char **argv) {
    const char *home = getenv("HOME");
    char err[256] = "";
    if (!home || !*home) return fail("setup", "HOME is not set");
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
    return usage();
}
