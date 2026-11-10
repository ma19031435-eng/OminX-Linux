/* Original single-seat development-session policy; not an authentication service. */
#define _GNU_SOURCE
#include "session.h"
#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <unistd.h>

int ominx_recovery_requested(const char *line) {
    const char flag[] = "ominx.recovery=1";
    while (*line) {
        while (isspace((unsigned char)*line)) line++;
        const char *start = line;
        while (*line && !isspace((unsigned char)*line)) line++;
        if ((size_t)(line - start) == sizeof flag - 1 && !memcmp(start, flag, sizeof flag - 1)) return 1;
    }
    return 0;
}
static int directory(const char *path, uid_t uid, gid_t gid, mode_t mode) {
    if (mkdir(path, mode) && errno != EEXIST) return -1;
    int fd = open(path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0) return -1;
    int result = fchown(fd, uid, gid) || fchmod(fd, mode);
    int saved = errno;
    close(fd); errno = saved;
    return result ? -1 : 0;
}
int ominx_prepare_session(void) {
    if (directory("/root", 0, 0, 0700) || directory("/home", 0, 0, 0755) ||
        directory("/home/ominx", OMINX_UID, OMINX_GID, 0700) ||
        directory("/run/user", 0, 0, 0755) ||
        directory("/run/user/1000", OMINX_UID, OMINX_GID, 0700)) return -1;
    /* Windows-compatibility state lives under the user's data directory so
       a persistent installed home keeps the Wine and Proton prefixes. */
    if (!access("/bin/ominx-wined", X_OK) &&
        (directory("/home/ominx/.local", OMINX_UID, OMINX_GID, 0700) ||
         directory("/home/ominx/.local/share", OMINX_UID, OMINX_GID, 0700) ||
         directory("/home/ominx/.local/share/ominx", OMINX_UID, OMINX_GID, 0700) ||
         directory("/home/ominx/.local/share/ominx/wine", OMINX_UID, OMINX_GID, 0700) ||
         directory("/home/ominx/.local/share/ominx/proton", OMINX_UID, OMINX_GID, 0700) ||
         directory("/home/ominx/.local/share/ominx/proton/compatdata", OMINX_UID, OMINX_GID, 0700)))
        return -1;
    return 0;
}
int ominx_enter_session(int recovery) {
    if (clearenv()) return -1;
    const char *home = recovery ? "/root" : "/home/ominx";
    const char *user = recovery ? "root" : "ominx";
    if (setenv("HOME", home, 1) || setenv("USER", user, 1) ||
        setenv("LOGNAME", user, 1) || setenv("PATH", "/bin", 1) ||
        setenv("SHELL", "/init", 1) || setenv("LANG", "C.UTF-8", 1) ||
        setenv("TERM", "linux", 1)) return -1;
    if (!access("/sbin/ominx-desktop-bus", X_OK)) {
        if (setenv("DBUS_SYSTEM_BUS_ADDRESS", "unix:path=/run/dbus/system_bus_socket", 1)) return -1;
        if (!recovery && setenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=/run/user/1000/bus", 1)) return -1;
    }
    if (!recovery && !access("/bin/ominx-wined", X_OK)) {
        if (setenv("WINEPREFIX", "/home/ominx/.local/share/ominx/wine/prefix", 1) ||
            setenv("WINEARCH", "win64", 1) ||
            setenv("OMINX_WINED_SOCKET", "/run/user/1000/ominx-wined.sock", 1)) return -1;
    }
    if (!recovery) {
        gid_t groups[] = {OMINX_VIDEO, OMINX_INPUT, OMINX_RENDER};
        if (setenv("XDG_RUNTIME_DIR", "/run/user/1000", 1) ||
            setgroups(sizeof groups / sizeof groups[0], groups) ||
            setresgid(OMINX_GID, OMINX_GID, OMINX_GID) ||
            setresuid(OMINX_UID, OMINX_UID, OMINX_UID) ||
            prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)) return -1;
        /* Verify all identity slots; do not fall back to root on any error. */
        uid_t r, e, s;
        gid_t gr, ge, gs;
        if (getresuid(&r, &e, &s) || getresgid(&gr, &ge, &gs) ||
            r != OMINX_UID || e != OMINX_UID || s != OMINX_UID ||
            gr != OMINX_GID || ge != OMINX_GID || gs != OMINX_GID) { errno = EPERM; return -1; }
    }
    umask(recovery ? 022 : 077);
    return chdir(home);
}
static int numbered(const char *name, const char *prefix) {
    size_t length = strlen(prefix);
    if (strncmp(name, prefix, length) || !isdigit((unsigned char)name[length])) return 0;
    for (const char *p = name + length; *p; p++) if (!isdigit((unsigned char)*p)) return 0;
    return 1;
}
static void devices(const char *path, const char *prefix, gid_t group) {
    DIR *directory = opendir(path);
    if (!directory) return;
    struct dirent *entry;
    while ((entry = readdir(directory))) {
        if (!numbered(entry->d_name, prefix)) continue;
        struct stat st;
        int fd = dirfd(directory);
        if (fstatat(fd, entry->d_name, &st, AT_SYMLINK_NOFOLLOW) || !S_ISCHR(st.st_mode)) continue;
        /* /dev and its subdirectories are root-owned; ordinary users cannot
           replace these entries. Never grant access to block devices. */
        if (st.st_gid == group && (st.st_mode & 07777) == 0660) continue;
        if (fchownat(fd, entry->d_name, 0, group, AT_SYMLINK_NOFOLLOW) ||
            fchmodat(fd, entry->d_name, 0660, 0)) perror("device access policy");
    }
    closedir(directory);
}
void ominx_device_policy(void) {
    devices("/dev/dri", "card", OMINX_VIDEO);
    devices("/dev/dri", "renderD", OMINX_RENDER);
    devices("/dev/input", "event", OMINX_INPUT);
    devices("/dev", "fb", OMINX_VIDEO);
}
