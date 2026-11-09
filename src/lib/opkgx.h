/* OPKGX version 1: validator and installer. See docs/opkgx-format.md.
   Installs run as the user, under $HOME. Nothing here needs root. */
#ifndef OMINX_OPKGX_H
#define OMINX_OPKGX_H

#include <stddef.h>
#include <stdio.h>

#define OPKGX_ID_MAX 64
#define OPKGX_NAME_MAX 64
#define OPKGX_SUMMARY_MAX 120
#define OPKGX_VERSION_MAX 32
#define OPKGX_EXEC_MAX 255
#define OPKGX_MANIFEST_MAX 16384
#define OPKGX_ICON_MAX (512u * 1024u)
#define OPKGX_MAX_ENTRIES 10000
#define OPKGX_MAX_PAYLOAD (2ull * 1024ull * 1024ull * 1024ull)

enum opkgx_runner { OPKGX_RUNNER_NATIVE = 0, OPKGX_RUNNER_WINE = 1 };

/* Category bits, in the order the manifest lists them. */
#define OPKGX_CAT_GAMES (1u << 0)
#define OPKGX_CAT_OFFICE (1u << 1)
#define OPKGX_CAT_DEVELOPMENT (1u << 2)
#define OPKGX_CAT_GRAPHICS (1u << 3)
#define OPKGX_CAT_AUDIO (1u << 4)
#define OPKGX_CAT_VIDEO (1u << 5)
#define OPKGX_CAT_UTILITIES (1u << 6)
#define OPKGX_CAT_INTERNET (1u << 7)
#define OPKGX_CAT_EDUCATION (1u << 8)

struct opkgx_manifest {
    char id[OPKGX_ID_MAX + 1];
    char name[OPKGX_NAME_MAX + 1];
    char version[OPKGX_VERSION_MAX];
    char summary[OPKGX_SUMMARY_MAX + 1];
    char exec[OPKGX_EXEC_MAX + 1];
    enum opkgx_runner runner;
    unsigned categories;
    int has_icon;
    int is_msi;
};

/* Reads the whole archive and checks every rule in the spec. Writes nothing.
   Returns 0 with @m filled in, or -1 with a short reason in @err. */
int opkgx_validate(const char *archive, struct opkgx_manifest *m, char *err, size_t err_size);

/* Validates, then installs under @home. Returns 0, or -1 with a reason in @err.
   On validation failure nothing is written. */
int opkgx_install(const char *archive, const char *home, char *err, size_t err_size);

/* Removes an installed app and its desktop entry. Returns 0, or -1 if it is not installed. */
int opkgx_remove(const char *id, const char *home, char *err, size_t err_size);

/* Prints the registry, one line per app: id version runner state. */
int opkgx_list(const char *home, FILE *out);

/* Starts an installed app. Native apps run directly; wine apps are handed to
   the Wine service. Returns 0 when the launch was started. */
int opkgx_run(const char *id, const char *home, char *err, size_t err_size);

#endif
