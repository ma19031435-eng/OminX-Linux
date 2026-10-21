#ifndef OMINX_GAMEDB_H
#define OMINX_GAMEDB_H
#include <stddef.h>
/* Game profiles for the OminX game framework.

   A profile is one declarative `<id>.game` file (see compat/games/README.md).
   Profiles describe how a title is launched and what its anti-cheat status is
   according to its publisher. They never describe a way around anti-cheat:
   a profile whose publisher has not enabled Linux support is refused by
   ominx_game_gate(), and the refusal is the same in the console, the desktop
   and the per-user daemon. */

#define OMINX_GAME_ID_MAX 32
#define OMINX_GAME_DIR_DEFAULT "/usr/share/ominx/games"
#define OMINX_GAME_PROFILE_MAX 8192

enum ominx_game_runner { OMINX_GAME_RUNNER_NONE = 0, OMINX_GAME_RUNNER_PROTON = 1, OMINX_GAME_RUNNER_WINE = 2 };

enum ominx_game_anticheat {
    OMINX_AC_NONE = 0,
    OMINX_AC_EAC = 1,      /* Epic Easy Anti-Cheat */
    OMINX_AC_BATTLEYE = 2, /* BattlEye */
    OMINX_AC_VANGUARD = 3, /* Riot Vanguard: Windows kernel driver, no Linux runtime */
    OMINX_AC_OTHER = 4
};

/* Publisher status for Linux. Only "vendor-opt-in" can launch, and only
   after the host meets the profile's requirements. */
enum ominx_game_ac_status {
    OMINX_AC_STATUS_NONE = 0,
    OMINX_AC_VENDOR_OPT_IN = 1, /* publisher enabled Linux/Proton for this title */
    OMINX_AC_PENDING = 2,       /* announced, not enabled: refused */
    OMINX_AC_DENIED = 3         /* publisher blocks Linux: refused */
};

enum ominx_game_requirement { OMINX_GAME_REQ_NONE = 0, OMINX_GAME_REQ_EAC_V2 = 1 };

struct ominx_game {
    char id[OMINX_GAME_ID_MAX + 1];
    char name[96];
    char appid[33];
    char dir[256];   /* relative to $HOME, e.g. Games/fortnite */
    char exe[256];   /* relative to dir */
    char notes[256];
    int runner;      /* enum ominx_game_runner */
    int anticheat;   /* enum ominx_game_anticheat */
    int status;      /* enum ominx_game_ac_status */
    int requires;    /* enum ominx_game_requirement */
};

/* Loads and strictly validates <games_dir>/<id>.game. Returns 0, or -1 with a
   stable, human-readable reason in @error. Unknown keys are errors. */
int ominx_game_load(const char *games_dir, const char *id, struct ominx_game *game,
                    char *error, size_t error_size);

/* Visits every *.game file in @games_dir in sorted order. @game is NULL and
   @error non-empty for a profile that failed validation. Returns the callback's
   last non-zero result, or -1 when the directory cannot be read. */
int ominx_game_for_each(const char *games_dir,
                        void (*visit)(const char *id, const struct ominx_game *game,
                                      const char *error, void *context),
                        void *context);

/* Launch policy. Returns 0 when the profile may launch on the host rooted at
   @sysroot ("/" on a real system). Otherwise returns -1 and writes a stable
   reason token such as "anticheat-denied" or
   "eac-v2-requirements-unmet:tpm2,secure-boot". */
int ominx_game_gate(const struct ominx_game *game, const char *sysroot,
                    char *reason, size_t reason_size);

/* Host checks required by Epic's published EAC Linux v2 requirements. These are
   read-only observations of kernel and firmware state; nothing is enabled or
   loaded. Writes the missing requirement names, comma-separated, into
   @missing. Returns 0 when all are present, -1 otherwise. */
int ominx_host_eac_v2_missing(const char *sysroot, char *missing, size_t missing_size);

const char *ominx_game_runner_name(int runner);
const char *ominx_game_anticheat_name(int anticheat);
const char *ominx_game_status_name(int status);
const char *ominx_game_requirement_name(int requirement);
#endif
