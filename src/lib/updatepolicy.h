/* User-controlled update policy.

   The user decides when updates download, when they install and when the
   system restarts. This module only decides; it never runs an update. The
   defaults download inside a window but never install or restart on their own,
   so nothing changes until the user turns it on. Updates never install or
   restart while a game is running, and an automatic restart never happens
   while the user is active. */
#ifndef OMINX_UPDATEPOLICY_H
#define OMINX_UPDATEPOLICY_H

#include <stddef.h>

enum ominx_activity { OMINX_ACT_IDLE = 0, OMINX_ACT_ACTIVE = 1, OMINX_ACT_GAMING = 2 };

/* Hour windows are [start, end) in local hours 0..24. start > end wraps past
   midnight, so 23-6 means 23:00 to 06:00. start == end means all day. */
struct ominx_update_policy {
    int download_start, download_end;
    int install_start, install_end;
    int restart_start, restart_end;
    int auto_install;   /* 0 = install only when the user starts it */
    int auto_restart;   /* 0 = restart only when the user asks */
};

struct ominx_update_decision {
    int download;       /* 1 = may download now */
    int install;        /* 1 = may install now */
    int restart;        /* 1 = may restart now */
    char reason[128];   /* plain-language reason for the decision */
};

void ominx_update_policy_default(struct ominx_update_policy *policy);

/* Parses lines of key=value. Keys: download_window, install_window,
   restart_window (H-H), auto_install and auto_restart (0 or 1). Unknown keys
   are an error. Returns 0, or -1 with a short reason in @error. */
int ominx_update_policy_parse(struct ominx_update_policy *policy, const char *text,
                              char *error, size_t error_size);

/* @restart_requested is 1 when the user has asked to restart now. */
void ominx_update_decide(const struct ominx_update_policy *policy, int hour,
                         enum ominx_activity activity, int restart_requested,
                         struct ominx_update_decision *decision);

#endif
