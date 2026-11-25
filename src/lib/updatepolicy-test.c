/* Host driver for the update policy. The daemon and the update client call the
   same functions.

   usage: ominx-updatepolicy-test POLICY_FILE|- HOUR idle|active|gaming RESTART_REQUESTED
     Prints one line: download=N install=N restart=N reason=TEXT
     POLICY_FILE "-" uses the defaults. A missing or unreadable file is an error. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "updatepolicy.h"

static int read_file(const char *path, char *out, size_t size) {
    FILE *f = fopen(path, "r");
    if (!f) return -1;
    size_t n = fread(out, 1, size - 1, f);
    int ok = !ferror(f) && feof(f);
    fclose(f);
    if (!ok) return -1;
    out[n] = '\0';
    return 0;
}

int main(int argc, char **argv) {
    if (argc != 5) {
        fprintf(stderr, "usage: %s POLICY_FILE|- HOUR idle|active|gaming RESTART_REQUESTED\n", argv[0]);
        return 2;
    }
    struct ominx_update_policy policy;
    char text[4096], error[64];
    if (!strcmp(argv[1], "-")) {
        ominx_update_policy_default(&policy);
    } else {
        if (read_file(argv[1], text, sizeof text)) { fprintf(stderr, "policy-unreadable\n"); return 1; }
        if (ominx_update_policy_parse(&policy, text, error, sizeof error)) {
            fprintf(stderr, "policy-invalid: %s\n", error);
            return 1;
        }
    }

    char *end = NULL;
    long hour = strtol(argv[2], &end, 10);
    if (!end || *end || hour < 0 || hour > 23) { fprintf(stderr, "bad-hour\n"); return 2; }

    enum ominx_activity activity;
    if (!strcmp(argv[3], "idle")) activity = OMINX_ACT_IDLE;
    else if (!strcmp(argv[3], "active")) activity = OMINX_ACT_ACTIVE;
    else if (!strcmp(argv[3], "gaming")) activity = OMINX_ACT_GAMING;
    else { fprintf(stderr, "bad-activity\n"); return 2; }

    if (strcmp(argv[4], "0") && strcmp(argv[4], "1")) { fprintf(stderr, "bad-restart-flag\n"); return 2; }
    int restart_requested = !strcmp(argv[4], "1");

    struct ominx_update_decision d;
    ominx_update_decide(&policy, (int)hour, activity, restart_requested, &d);
    printf("download=%d install=%d restart=%d reason=%s\n", d.download, d.install, d.restart, d.reason);
    return 0;
}
