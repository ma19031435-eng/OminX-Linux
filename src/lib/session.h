#ifndef OMINX_SESSION_H
#define OMINX_SESSION_H
#define OMINX_UID 1000
#define OMINX_GID 1000
#define OMINX_VIDEO 44
#define OMINX_INPUT 104
#define OMINX_RENDER 107
int ominx_recovery_requested(const char *cmdline);
int ominx_prepare_session(void);
int ominx_enter_session(int recovery);
void ominx_device_policy(void);
#endif
