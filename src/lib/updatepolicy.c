#include "updatepolicy.h"

#include <stdio.h>
#include <string.h>

void ominx_update_policy_default(struct ominx_update_policy *policy) {
    policy->download_start = 0;
    policy->download_end = 24;   /* downloads may run all day */
    policy->install_start = 2;
    policy->install_end = 5;
    policy->restart_start = 2;
    policy->restart_end = 5;
    policy->auto_install = 0;    /* the user starts installs */
    policy->auto_restart = 0;    /* the user starts restarts */
}

static int in_window(int hour, int start, int end) {
    if (start == end) return 1;           /* all day */
    if (start < end) return hour >= start && hour < end;
    return hour >= start || hour < end;   /* wraps past midnight */
}

static int parse_window(const char *value, int *start, int *end) {
    int a, b;
    char tail;
    if (sscanf(value, "%d-%d%c", &a, &b, &tail) != 2) return -1;
    if (a < 0 || a > 24 || b < 0 || b > 24) return -1;
    *start = a;
    *end = b;
    return 0;
}

static int parse_flag(const char *value, int *out) {
    if (!strcmp(value, "0")) { *out = 0; return 0; }
    if (!strcmp(value, "1")) { *out = 1; return 0; }
    return -1;
}

int ominx_update_policy_parse(struct ominx_update_policy *policy, const char *text,
                              char *error, size_t error_size) {
    char line[256];
    struct ominx_update_policy next;
    ominx_update_policy_default(&next);
    const char *p = text;
    while (*p) {
        size_t n = strcspn(p, "\n");
        if (n >= sizeof line) { snprintf(error, error_size, "line-too-long"); return -1; }
        memcpy(line, p, n);
        line[n] = '\0';
        p += n + (p[n] == '\n');
        if (!line[0] || line[0] == '#') continue;
        char *eq = strchr(line, '=');
        if (!eq) { snprintf(error, error_size, "missing-equals"); return -1; }
        *eq = '\0';
        const char *key = line, *value = eq + 1;
        if (!strcmp(key, "download_window")) {
            if (parse_window(value, &next.download_start, &next.download_end)) goto bad;
        } else if (!strcmp(key, "install_window")) {
            if (parse_window(value, &next.install_start, &next.install_end)) goto bad;
        } else if (!strcmp(key, "restart_window")) {
            if (parse_window(value, &next.restart_start, &next.restart_end)) goto bad;
        } else if (!strcmp(key, "auto_install")) {
            if (parse_flag(value, &next.auto_install)) goto bad;
        } else if (!strcmp(key, "auto_restart")) {
            if (parse_flag(value, &next.auto_restart)) goto bad;
        } else {
            snprintf(error, error_size, "unknown-key");
            return -1;
        }
        continue;
    bad:
        snprintf(error, error_size, "bad-value");
        return -1;
    }
    *policy = next;
    return 0;
}

void ominx_update_decide(const struct ominx_update_policy *policy, int hour,
                         enum ominx_activity activity, int restart_requested,
                         struct ominx_update_decision *decision) {
    memset(decision, 0, sizeof *decision);

    if (in_window(hour, policy->download_start, policy->download_end)) {
        decision->download = 1;
        snprintf(decision->reason, sizeof decision->reason, "download allowed in window");
    } else {
        snprintf(decision->reason, sizeof decision->reason, "download waits for its window");
    }

    /* Installs never interrupt a game, and only run when the user chose automatic installs. */
    if (activity == OMINX_ACT_GAMING) {
        snprintf(decision->reason, sizeof decision->reason, "install and restart wait: a game is running");
        return;
    }
    if (policy->auto_install && activity == OMINX_ACT_IDLE &&
        in_window(hour, policy->install_start, policy->install_end)) {
        decision->install = 1;
    }

    /* A restart the user asked for runs now, unless a game is running. */
    if (restart_requested) {
        decision->restart = 1;
        snprintf(decision->reason, sizeof decision->reason, "restart requested by the user");
        return;
    }
    if (policy->auto_restart && activity == OMINX_ACT_IDLE &&
        in_window(hour, policy->restart_start, policy->restart_end)) {
        decision->restart = 1;
    }
}
