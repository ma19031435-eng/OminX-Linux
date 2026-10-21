#ifndef OMINX_LOGIN_H
#define OMINX_LOGIN_H
/* Fixed original login service layout. Nothing here is user configurable. */
#define OMINX_LOGIN_SOCKET "/run/ominx/login.sock"
#define OMINX_LOGIN_LOCK "/run/ominx/login-service.lock"
#define OMINX_LOGIN_SEAT_LOCK "/run/ominx/seat-service.lock"
#define OMINX_LOGIN_ACCOUNTS "/etc/ominx/accounts"
#define OMINX_LOGIN_MARKER "/etc/ominx/graphical-login"
#define OMINX_LOGIN_GREETER_DIR "/run/ominx/greeter"
#define OMINX_LOGIN_GREETER_LOG "/run/ominx/greeter.log"
#define OMINX_LOGIN_BROKER_LOG "/run/ominx/login-service.log"
#define OMINX_LOGIN_SEAT_LOG "/run/ominx/seat.log"
#define OMINX_LOGIN_SESSION_LOG "/run/ominx/session.log"
#define OMINX_LOGIN_TTY "/dev/tty1"
#define OMINX_LOGIN_SESSION_PROGRAM "/bin/ominx-desktop"
#define OMINX_LOGIN_SESSION_SHELL "/bin/ominx-desktop"
#define OMINX_GREETER_UID 1001
#define OMINX_GREETER_GID 1001
#define OMINX_LOGIN_MAX_ACCOUNTS 8
#define OMINX_LOGIN_MAX_NAME 32
#define OMINX_LOGIN_MAX_PATH 64
#define OMINX_LOGIN_MAX_HASH 256
#define OMINX_LOGIN_MAX_REQUEST 512
#define OMINX_LOGIN_MAX_PASSWORD 128
#define OMINX_LOGIN_PROTOCOL "OK service=ominx-login protocol=1"
/* Real sha512crypt of a 64-byte random string: unknown names still pay the
   full verification cost, so response time cannot disclose account names.
   Generated with scripts/ominx-hash.py; the plaintext is not stored anywhere. */
#define OMINX_LOGIN_DUMMY_HASH \
    "$6$OMINXDUMMYsalt00$7Z4Wf0.rVL5/x1gZPfaa8nwPxUcmohEV0bXwM6oTbANK0VuVjaQqf3diV0uhJPx85Z1Tjp8Gq0QZ64ILt.WVO."
struct ominx_account {
    char name[OMINX_LOGIN_MAX_NAME];
    char home[OMINX_LOGIN_MAX_PATH];
    char hash[OMINX_LOGIN_MAX_HASH];
    unsigned uid;
    unsigned gid;
    int locked;
};
/* Shared, allocation-free parsing so the tool and the service cannot disagree. */
int ominx_parse_account_line(const char *line, struct ominx_account *account);
int ominx_account_name_valid(const char *name);
#endif
