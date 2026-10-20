#ifndef OMINX_CONTROL_H
#define OMINX_CONTROL_H
#define OMINX_CONTROL_SOCKET "/run/ominx/control.sock"
int ominx_control_request(const char *command, char *reply, unsigned capacity);
#endif
