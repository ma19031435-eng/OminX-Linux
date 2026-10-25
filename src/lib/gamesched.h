#ifndef OMINX_GAMESCHED_H
#define OMINX_GAMESCHED_H
#include <stddef.h>
#include <sys/types.h>
#include "gamedb.h"

/* Game-aware scheduling for OminX.

   When a reviewed game profile launches, the foreground game's process is moved
   into its own cgroup v2 group with a higher CPU and I/O weight, and the GPU is
   asked for its high performance level where the driver exposes that knob.
   When the game exits, everything is restored.

   The boost is only ever applied to a title the launch gate already allows, so
   scheduling never makes a blocked title run and never bypasses anti-cheat.
   Every knob is optional: a missing or read-only knob is reported and skipped,
   and the launch itself is never failed by scheduling.

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
    char root[OMINX_SCHED_PATH_MAX];        /* delegated parent group, absolute */
    char group[OMINX_SCHED_PATH_MAX];       /* per-game group, absolute */
};

/* Decides whether a profile may be boosted. @root is the delegated parent group.
   A title the launch gate refuses is never boosted. */
void ominx_sched_plan_game(const struct ominx_game *game, const char *sysroot, const char *root,
                           struct ominx_sched_plan *plan);

/* Creates the per-game group, moves @pid into it and writes the weights. Each
   step appends "applied" or "skipped: reason" to @report. Returns the number of
   knobs applied. Never fails the launch. */
int ominx_sched_boost(const char *sysroot, struct ominx_sched_plan *plan, pid_t pid,
                      char *report, size_t report_size);

/* Moves @pid back to the delegated parent, removes the per-game group and returns
   the GPU knob to automatic when this plan raised it. Safe to call on a plan that
   was never boosted. */
void ominx_sched_release(const char *sysroot, const struct ominx_sched_plan *plan, pid_t pid);

/* One-line status shown before a launch: the compatibility status first, then
   whether scheduling can boost on this host. */
void ominx_sched_status(const struct ominx_game *game, const char *sysroot, const char *root,
                        char *out, size_t out_size);

/* Root, at boot: creates the delegated parent group, enables the cpu and io
   controllers for its children and hands the group to @uid. Returns 0 when the
   group is ready, -1 otherwise with the reason in @report. */
int ominx_sched_prepare(const char *sysroot, const char *root, unsigned uid,
                        char *report, size_t report_size);

#endif
