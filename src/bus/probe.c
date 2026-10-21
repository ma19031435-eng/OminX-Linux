/* Actual guest IPC/authorization tests. Never connect to a build-host bus. */
#define _GNU_SOURCE
#include <dbus/dbus.h>
#include <errno.h>
#include <grp.h>
#include <limits.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

#define SYSTEM_ADDRESS "unix:path=/run/dbus/system_bus_socket"
#define SESSION_ADDRESS "unix:path=/run/user/1000/bus"
static void fail(const char *text) { fprintf(stderr, "BUS FAIL: %s\n", text); exit(1); }
static void require(int condition, const char *text) { if (!condition) fail(text); }
static int source_boot(void) {
    if (getuid() == 0) {
        char path[128]; ssize_t n = readlink("/proc/1/exe", path, sizeof path - 1);
        if (n < 0) return 0;
        path[n] = 0; return !strcmp(path, "/init");
    }
    /* Linux correctly denies UID1000 readlink(/proc/1/exe) for root PID1.
       Require the root-only bootstrap lock (created only after the supervisor's
       strict /proc/1/exe guard), the init comm, and this source image identity. */
    FILE *f = fopen("/proc/1/comm", "r");
    char text[128];
    int init = f && fgets(text, sizeof text, f) && !strcmp(text, "init\n");
    if (f) fclose(f);
    if (!init) return 0;
    f = fopen("/etc/os-release", "r");
    int source = 0;
    while (f && fgets(text, sizeof text, f)) if (!strcmp(text, "ID=ominx\n")) source = 1;
    if (f) fclose(f);
    if (!source) return 0;
    for (int i = 0; i < 50; i++) {
        struct stat st;
        if (!lstat("/run/ominx/bus-service.lock", &st) && S_ISREG(st.st_mode) &&
            st.st_uid == 0 && st.st_nlink == 1 && (st.st_mode & 0777) == 0600) return 1;
        usleep(100000);
    }
    return 0;
}
static DBusConnection *connect_bus(const char *address) {
    DBusError error = DBUS_ERROR_INIT;
    DBusConnection *c = dbus_connection_open_private(address, &error);
    if (c) {
        dbus_connection_set_exit_on_disconnect(c, FALSE);
        if (!dbus_bus_register(c, &error)) { dbus_connection_close(c); dbus_connection_unref(c); c = NULL; }
    }
    dbus_error_free(&error);
    return c;
}
static DBusConnection *await_bus(const char *address) {
    for (int i = 0; i < 100; i++) {
        DBusConnection *c = connect_bus(address);
        if (c) return c;
        usleep(100000);
    }
    fail("bus startup timeout"); return NULL;
}
static void close_bus(DBusConnection *c) { dbus_connection_close(c); dbus_connection_unref(c); }
static dbus_uint32_t daemon_property(DBusConnection *c, const char *method) {
    DBusError error = DBUS_ERROR_INIT;
    const char *name = DBUS_SERVICE_DBUS;
    DBusMessage *m = dbus_message_new_method_call(DBUS_SERVICE_DBUS, DBUS_PATH_DBUS, DBUS_INTERFACE_DBUS, method);
    require(m && dbus_message_append_args(m, DBUS_TYPE_STRING, &name, DBUS_TYPE_INVALID), "property message");
    DBusMessage *r = dbus_connection_send_with_reply_and_block(c, m, 2000, &error);
    dbus_message_unref(m);
    dbus_uint32_t value = 0;
    require(r && dbus_message_get_args(r, &error, DBUS_TYPE_UINT32, &value, DBUS_TYPE_INVALID), method);
    dbus_message_unref(r); dbus_error_free(&error); return value;
}
static DBusMessage *wait_message(DBusConnection *c, int type, dbus_uint32_t serial) {
    for (int i = 0; i < 20; i++) {
        dbus_connection_read_write(c, 100);
        DBusMessage *m;
        while ((m = dbus_connection_pop_message(c))) {
            if (dbus_message_get_type(m) == type && (!serial || dbus_message_get_reply_serial(m) == serial)) return m;
            dbus_message_unref(m);
        }
    }
    fail("message routing timeout"); return NULL;
}
static void roundtrip(DBusConnection *a, DBusConnection *b) {
    DBusError error = DBUS_ERROR_INIT;
    require(dbus_bus_request_name(a, "org.ominx.Validation", DBUS_NAME_FLAG_DO_NOT_QUEUE, &error) == DBUS_REQUEST_NAME_REPLY_PRIMARY_OWNER, "session name ownership");
    require(dbus_bus_request_name(b, "org.ominx.Validation", DBUS_NAME_FLAG_DO_NOT_QUEUE, &error) == DBUS_REQUEST_NAME_REPLY_EXISTS, "duplicate session name");
    DBusMessage *m = dbus_message_new_method_call("org.ominx.Validation", "/org/ominx/Validation", "org.ominx.Validation", "Ping");
    dbus_uint32_t serial;
    require(m && dbus_connection_send(b, m, &serial), "send request");
    dbus_message_unref(m); dbus_connection_flush(b);
    m = wait_message(a, DBUS_MESSAGE_TYPE_METHOD_CALL, 0);
    require(dbus_message_is_method_call(m, "org.ominx.Validation", "Ping"), "received method");
    DBusMessage *reply = dbus_message_new_method_return(m);
    const char *payload = "source-bus-roundtrip";
    require(reply && dbus_message_append_args(reply, DBUS_TYPE_STRING, &payload, DBUS_TYPE_INVALID) && dbus_connection_send(a, reply, NULL), "send reply");
    dbus_message_unref(m); dbus_message_unref(reply); dbus_connection_flush(a);
    reply = wait_message(b, DBUS_MESSAGE_TYPE_METHOD_RETURN, serial);
    const char *value = NULL;
    require(dbus_message_get_args(reply, &error, DBUS_TYPE_STRING, &value, DBUS_TYPE_INVALID) && !strcmp(value, payload), "reply contents");
    dbus_message_unref(reply); dbus_error_free(&error);
}
static void restart_supervisor(void) {
    DBusConnection *c = await_bus(SYSTEM_ADDRESS);
    dbus_uint32_t old_daemon = daemon_property(c, "GetConnectionUnixProcessID");
    close_bus(c);
    FILE *f = fopen("/run/ominx/bus-service.lock", "r");
    char text[64], *end;
    require(f && fgets(text, sizeof text, f), "supervisor pid record");
    fclose(f);
    errno = 0;
    long pid = strtol(text, &end, 10);
    require(!errno && pid > 1 && pid <= INT_MAX && end[0] == '\n' && end[1] == 0, "valid supervisor pid");
    char proc[64], exe[128];
    snprintf(proc, sizeof proc, "/proc/%ld/exe", pid);
    ssize_t n = readlink(proc, exe, sizeof exe - 1);
    require(n > 0, "supervisor executable");
    exe[n] = 0;
    require(!strcmp(exe, "/sbin/ominx-desktop-bus"), "fixed supervisor identity");
    require(!kill((pid_t)pid, SIGKILL), "supervisor termination");
    usleep(500000);
    for (int i = 0; i < 100; i++) {
        usleep(100000);
        c = connect_bus(SYSTEM_ADDRESS);
        if (!c) continue;
        dbus_uint32_t daemon = daemon_property(c, "GetConnectionUnixProcessID");
        require(daemon_property(c, "GetConnectionUnixUser") == 81, "restarted system uid");
        close_bus(c);
        if (daemon != old_daemon) {
            /* No inherited root bus connection; verify the restarted user bus too. */
            pid_t child = fork(); require(child >= 0, "restart user test fork");
            if (!child) {
                require(!setgroups(0, NULL) && !setgid(1000) && !setuid(1000), "restart test drop");
                execl("/bin/ominx-bus-probe", "ominx-bus-probe", "--guest-test", (char *)NULL);
                _exit(1);
            }
            int status;
            require(waitpid(child, &status, 0) == child && WIFEXITED(status) && !WEXITSTATUS(status), "restarted user bus test");
            puts("PASS bus supervisor restart and child cleanup"); return;
        }
    }
    fail("PID1 supervisor restart timeout");
}
int main(int argc, char **argv) {
    if (!source_boot() || argc != 2) { fputs("requires explicit source guest test mode\n", stderr); return 2; }
    if (!strcmp(argv[1], "--restart-service") && getuid() == 0) { restart_supervisor(); return 0; }
    if (!strcmp(argv[1], "--deny-other-uid") && getuid() == 0) {
        DBusConnection *live = await_bus(SYSTEM_ADDRESS);
        require(daemon_property(live, "GetConnectionUnixUser") == 81, "live system bus before denial");
        dbus_uint32_t live_pid = daemon_property(live, "GetConnectionUnixProcessID");
        close_bus(live); /* Never give the dropped child an authorized root connection. */
        pid_t child = fork(); require(child >= 0, "fork");
        if (!child) {
            require(!setgroups(0, NULL) && !setgid(1001) && !setuid(1001), "drop to other uid");
            require(!connect_bus(SYSTEM_ADDRESS), "other uid on system bus");
            require(!connect_bus(SESSION_ADDRESS), "other uid on session bus");
            _exit(0);
        }
        int status; require(waitpid(child, &status, 0) == child && WIFEXITED(status) && !WEXITSTATUS(status), "cross-uid refusal");
        live = await_bus(SYSTEM_ADDRESS);
        require(daemon_property(live, "GetConnectionUnixProcessID") == live_pid, "same live system bus after denial");
        close_bus(live);
        puts("PASS bus cross-uid isolation"); return 0;
    }
    if (strcmp(argv[1], "--guest-test") || getuid() != 1000) return 2;
    DBusConnection *system = await_bus(SYSTEM_ADDRESS), *peer = await_bus(SYSTEM_ADDRESS);
    require(daemon_property(system, "GetConnectionUnixUser") == 81, "system daemon uid");
    pid_t system_pid = (pid_t)daemon_property(system, "GetConnectionUnixProcessID");
    require(system_pid > 1, "valid system daemon pid");
    require(kill(system_pid, SIGTERM) < 0 && errno == EPERM, "system service signal protection");
    DBusError error = DBUS_ERROR_INIT;
    require(dbus_bus_request_name(system, "org.ominx.Control", DBUS_NAME_FLAG_DO_NOT_QUEUE, &error) == -1 && dbus_error_has_name(&error, DBUS_ERROR_ACCESS_DENIED), "protected system name refusal");
    dbus_error_free(&error);
    DBusMessage *m = dbus_message_new_method_call(dbus_bus_get_unique_name(peer), "/org/ominx/Validation", "org.ominx.Validation", "Ping");
    require(m != NULL, "policy message");
    DBusMessage *reply = dbus_connection_send_with_reply_and_block(system, m, 2000, &error);
    require(!reply && dbus_error_has_name(&error, DBUS_ERROR_ACCESS_DENIED), "system peer messaging refusal");
    dbus_error_free(&error); dbus_message_unref(m); close_bus(peer); close_bus(system);
    DBusConnection *a = await_bus(SESSION_ADDRESS), *b = await_bus(SESSION_ADDRESS);
    require(daemon_property(a, "GetConnectionUnixUser") == 1000, "session daemon uid");
    roundtrip(a, b);
    pid_t previous = (pid_t)daemon_property(a, "GetConnectionUnixProcessID");
    close_bus(a); close_bus(b);
    require(previous > 1 && !kill(previous, SIGTERM), "session daemon termination");
    for (int i = 0; i < 100; i++) {
        usleep(100000);
        a = connect_bus(SESSION_ADDRESS);
        if (!a) continue;
        pid_t current = (pid_t)daemon_property(a, "GetConnectionUnixProcessID");
        close_bus(a);
        if (current != previous) { puts("PASS bus: external credentials, system policy, session roundtrip, supervised restart"); return 0; }
    }
    fail("session restart timeout"); return 1;
}
