#ifndef OMINX_GAMESCHED_H
#define OMINX_GAMESCHED_H
#include <stddef.h>
#include <sys/types.h>
#include "gamedb.h"

/* Game-aware scheduling for OminX.

   Layout (cgroup v2, all under OMINX_SCHED_ROOT_DEFAULT):

     ominx/                      root-owned; cpu+io enabled for children
     ominx/user-<uid>/           owned by the session user; cpu+io enabled
     ominx/user-<uid>/service/   the per-user daemon (a leaf, no game processes)
     ominx/user-<uid>/game-<appid>/   one per boosted title

   The kernel checks write access on the common ancestor when a process moves
   between cgroups. Games move between service/ and game-<appid>/, whose common
   ancestor is user-<uid>/, which the session user owns. That is why the user
   subtree is delegated and the root-owned parent is never touched by the user.

   A title is boosted only when ominx_game_gate() passes. Blocked titles never
   get a boost, and scheduling never makes a blocked title run. Every knob is
   optional: a missing or read-only knob is reported and skipped, and the launch
   still succeeds.

   All paths are absolute inside the target and are placed under @sysroot, so the
   host tests drive the same code against a fake /sys. */

#define OMINX_SCHED_ROOT_DEFAULT "/sys/fs/cgroup/ominx"
#define OMINX_SCHED_CPU_WEIGHT 1000 /* cgroup v2 cpu.weight: 1..10000, default 100 */
#define OMINX_SCHED_IO_WEIGHT 800   /* cgroup v2 io.weight: 1..10000, default 100 */
#define OMINX_SCHED_GPU_KNOB "/sys/class/drm/card0/device/power_dpm_force_performance_level"
#define OMINX_SCHED_PATH_MAX 256

struct ominx_sched_plan {
    int boost;                              /* 1 when the title may be boosted */
    int gpu_raised;                         /* set by boost when the GPU knob was written */
    char why[192];                          /* reason when boost is 0 */
    char root[OMINX_SCHED_PATH_MAX];        /* the user's delegated group, absolute */
    char group[OMINX_SCHED_PATH_MAX];       /* per-game group, absolute */
};

/* Builds "<root>/user-<uid>" into @out. Returns 0, or -1 when it does not fit. */
int ominx_sched_user_root(const char *root, unsigned uid, char *out, size_t size);

/* Decides whether a profile may be boosted. @root is the user's delegated group
   (see ominx_sched_user_root). */
void ominx_sched_plan_game(const struct ominx_game *game, const char *sysroot, const char *root,
                           struct ominx_sched_plan *plan);

/* Creates "<root>/game-<appid>", moves @pid into it and writes the weights. Each
   step appends "applied" or "skipped: reason" to @report. Returns the number of
   knobs applied. Never fails the launch. */
int ominx_sched_boost(const char *sysroot, struct ominx_sched_plan *plan, pid_t pid,
                      char *report, size_t report_size);

/* Moves @pid back to "<root>/service", removes the per-game group and returns the
   GPU knob to automatic when this plan raised it. Safe on a plan never boosted. */
void ominx_sched_release(const char *sysroot, const struct ominx_sched_plan *plan, pid_t pid);

/* Structured scheduling state for front ends. READY means a launch will be boosted
   when the daemon is running with its delegated group. */
enum ominx_sched_state {
    OMINX_SCHED_READY = 0,
    OMINX_SCHED_NOT_ELIGIBLE = 1,  /* the title is refused or not boosted by policy */
    OMINX_SCHED_NOT_DELEGATED = 2  /* eligible, but the user's group is not available */
};

/* Returns the state. @detail receives a short human-readable reason. */
enum ominx_sched_state ominx_sched_state_of(const struct ominx_game *game, const char *sysroot,
                                            const char *root, char *detail, size_t detail_size);
const char *ominx_sched_state_name(enum ominx_sched_state state);

/* One-line status: the compatibility status first, then whether scheduling can boost. */
void ominx_sched_status(const struct ominx_game *game, const char *sysroot, const char *root,
                        char *out, size_t out_size);

/* Root, idempotent: creates the ominx root and enables cpu and io for its children.
   Returns 0 when ready, -1 with the reason in @report. */
int ominx_sched_prepare(const char *sysroot, const char *root, char *report, size_t report_size);

/* Root, at session start: creates the user's delegated group and its service/
   leaf, hands both to @uid, and moves @pid (the per-user daemon) into service/.
   Returns 0 when the daemon is in place, -1 otherwise with the reason in @report. */
int ominx_sched_enter(const char *sysroot, const char *root, unsigned uid, pid_t pid,
                      char *report, size_t report_size);

#endif
