/* Host driver for gamesched. Drives the same code the daemon and seat use,
   against a fake sysroot, so tests never touch the real /sys.

   usage: ominx-gamesched-test SYSROOT GAMES_DIR ID ACTION [ARG]
     status              print the compatibility and scheduling line
     boost PID           plan and boost; print the knob report
     release PID         release; restores the GPU knob if it reads "high"
     prepare             root: create the ominx root and enable cpu/io
     enter UID PID       root: create the user's group and move PID into service/ */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <unistd.h>

#include "gamedb.h"
#include "gamesched.h"

static int read_knob(const char *path, char *out, size_t size) {
    FILE *f = fopen(path, "r");
    if (!f) return -1;
    if (!fgets(out, (int)size, f)) out[0] = '\0';
    fclose(f);
    out[strcspn(out, "\n")] = '\0';
    return 0;
}

int main(int argc, char **argv) {
    if (argc < 4) {
        fprintf(stderr, "usage: %s SYSROOT GAMES_DIR ID ACTION [ARG]\n", argv[0]);
        return 2;
    }
    const char *sysroot = argv[1], *games = argv[2], *id = argv[3];
    const char *action = argc > 4 ? argv[4] : "";
    char report[512], line[320], error[128], user_root[OMINX_SCHED_PATH_MAX];
    struct ominx_game game;
    struct ominx_sched_plan plan;
    const char *root = OMINX_SCHED_ROOT_DEFAULT;

    if (!strcmp(action, "prepare")) {
        int rc = ominx_sched_prepare(sysroot, root, report, sizeof report);
        printf("%s\n", report);
        return rc ? 1 : 0;
    }
    if (!strcmp(action, "enter") && argc >= 7) {
        int rc = ominx_sched_enter(sysroot, root, (unsigned)strtoul(argv[5], NULL, 10),
                                   (pid_t)strtol(argv[6], NULL, 10), report, sizeof report);
        printf("%s\n", report);
        return rc ? 1 : 0;
    }

    if (ominx_game_load(games, id, &game, error, sizeof error)) {
        printf("profile-error: %s\n", error);
        return 1;
    }
    /* The daemon's own uid selects its delegated group. */
    if (ominx_sched_user_root(root, (unsigned)getuid(), user_root, sizeof user_root)) return 1;

    if (!strcmp(action, "status")) {
        ominx_sched_status(&game, sysroot, user_root, line, sizeof line);
        printf("%s\n", line);
        return 0;
    }
    if (!strcmp(action, "boost") && argc >= 6) {
        ominx_sched_plan_game(&game, sysroot, user_root, &plan);
        int n = ominx_sched_boost(sysroot, &plan, (pid_t)strtol(argv[5], NULL, 10), report, sizeof report);
        printf("%s\n", report);
        printf("boosted-knobs: %d\n", n);
        return 0;
    }
    if (!strcmp(action, "release") && argc >= 6) {
        ominx_sched_plan_game(&game, sysroot, user_root, &plan);
        /* The daemon keeps the plan. Here the GPU flag is rebuilt from the knob. */
        char gpu[32], path[512];
        snprintf(path, sizeof path, "%s%s", strcmp(sysroot, "/") ? sysroot : "", OMINX_SCHED_GPU_KNOB);
        if (!read_knob(path, gpu, sizeof gpu) && !strcmp(gpu, "high")) plan.gpu_raised = 1;
        ominx_sched_release(sysroot, &plan, (pid_t)strtol(argv[5], NULL, 10));
        printf("released\n");
        return 0;
    }
    fprintf(stderr, "unknown action: %s\n", action);
    return 2;
}
