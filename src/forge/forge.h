/* Forge 1.0: the application language for OminXOS.
   Dynamically typed and interpreted. The language is specified in
   docs/forge-language.md. This header is the public API used by the
   ominx-forge tool (src/forge/main.c) and by the tests. */
#ifndef OMINX_FORGE_H
#define OMINX_FORGE_H

#include <stddef.h>
#include <stdio.h>

#define FORGE_MAX_FILES 256
#define FORGE_MSG_MAX 512
#define FORGE_MAX_DIAGS 64
#define FORGE_MAX_SOURCE (1024u * 1024u)
#define FORGE_MAX_DEPTH 400
#define FORGE_MAX_HEAP (256u * 1024u * 1024u)
#define FORGE_MAX_OUTPUT (16u * 1024u * 1024u)

struct forge_diag {
    char file[256];
    int line;
    int col;
    char msg[FORGE_MSG_MAX];
};

struct forge_diags {
    struct forge_diag d[FORGE_MAX_DIAGS];
    size_t n;
};

typedef struct forge_program forge_program;

/* Reads @entry, follows its imports, parses every file and checks names.
   Returns 0 with @out set when the program is clean; otherwise -1 with
   every problem found in @diags. @out is NULL on failure. */
int forge_load(const char *entry, forge_program **out, struct forge_diags *diags);

void forge_free(forge_program *p);

/* Runs the program's main() function. Program output goes to @out and
   runtime errors to @err. @assets is the directory read_asset() reads from.
   Returns 0, the value passed to exit(), or 1 after a runtime error. */
int forge_run_main(forge_program *p, const char *assets, FILE *out, FILE *err);

/* Runs every top-level function whose name starts with test_. Each test
   gets a fresh call. Prints "ok name" or "FAIL name: message" to @out.
   Returns 0 when every test passed, -1 if there are no tests, or 1 on
   any failure. @passed and @failed receive the counts. */
int forge_run_tests(forge_program *p, const char *assets, FILE *out, size_t *passed, size_t *failed);

/* Returns 1 when the program defines a top-level function called @name. */
int forge_has_function(const forge_program *p, const char *name);

#endif
