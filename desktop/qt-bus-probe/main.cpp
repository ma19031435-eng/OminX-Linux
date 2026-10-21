#include <QCoreApplication>
#include <QDBusConnection>
#include <QDBusError>
#include <QDBusMessage>
#include <QDBusPendingCallWatcher>
#include <QDBusPendingReply>
#include <QDBusReply>
#include <QEventLoop>
#include <QFile>
#include <QTimer>
#include <cstdio>
#include <cstdlib>
#include <sys/stat.h>
#include <unistd.h>

static void require(bool ok, const char *message) {
    if (!ok) { std::fprintf(stderr, "FAIL Qt bus: %s\n", message); std::exit(1); }
}
static QByteArray readFile(const char *path) {
    QFile file(QString::fromLatin1(path));
    return file.open(QIODevice::ReadOnly) ? file.readAll() : QByteArray();
}
class Echo final : public QObject {
    Q_OBJECT
    Q_CLASSINFO("D-Bus Interface", "org.ominx.QtBusProbe")
public slots:
    QString Roundtrip(const QString &text) { return text; }
};
int main(int argc, char **argv) {
    require(argc == 2 && QByteArray(argv[1]) == "--guest-test" && getuid() == 1000 && geteuid() == 1000,
            "explicit unprivileged guest invocation required");
    struct stat st;
    require(readFile("/proc/1/comm").trimmed() == "init" &&
            readFile("/etc/os-release").contains("\nID=ominx\n") &&
            !lstat("/run/ominx/bus-service.lock", &st) && S_ISREG(st.st_mode) &&
            st.st_uid == 0 && (st.st_mode & 0777) == 0600 && st.st_nlink == 1,
            "protected source-boot identity");
    QCoreApplication app(argc, argv);
    auto system = QDBusConnection::connectToBus(QStringLiteral("unix:path=/run/dbus/system_bus_socket"),
                                               QStringLiteral("ominx-test-system"));
    require(system.isConnected(), "system connection");
    auto query = QDBusMessage::createMethodCall(QStringLiteral("org.freedesktop.DBus"),
                    QStringLiteral("/org/freedesktop/DBus"), QStringLiteral("org.freedesktop.DBus"),
                    QStringLiteral("GetConnectionUnixUser"));
    query << QStringLiteral("org.freedesktop.DBus");
    QDBusReply<uint> uid = system.call(query, QDBus::Block, 3000);
    require(uid.isValid() && uid.value() == 81, "system daemon identity");
    require(!system.registerService(QStringLiteral("org.ominx.QtBusProbe")) &&
            system.lastError().type() == QDBusError::AccessDenied, "system ownership policy");
    auto a = QDBusConnection::connectToBus(QStringLiteral("unix:path=/run/user/1000/bus"), QStringLiteral("ominx-test-a"));
    auto b = QDBusConnection::connectToBus(QStringLiteral("unix:path=/run/user/1000/bus"), QStringLiteral("ominx-test-b"));
    require(a.isConnected() && b.isConnected() && a.baseService() != b.baseService(), "distinct session connections");
    Echo echo;
    require(a.registerService(QStringLiteral("org.ominx.QtBusProbe")) &&
            a.registerObject(QStringLiteral("/Probe"), &echo, QDBusConnection::ExportAllSlots), "session object registration");
    require(!b.registerService(QStringLiteral("org.ominx.QtBusProbe")), "duplicate ownership refused");
    auto method = QDBusMessage::createMethodCall(QStringLiteral("org.ominx.QtBusProbe"), QStringLiteral("/Probe"),
                                               QStringLiteral("org.ominx.QtBusProbe"), QStringLiteral("Roundtrip"));
    method << QStringLiteral("ominx qt ipc");
    QDBusPendingCallWatcher watcher(b.asyncCall(method, 3000));
    QEventLoop loop;
    QObject::connect(&watcher, &QDBusPendingCallWatcher::finished, &loop, &QEventLoop::quit);
    QTimer::singleShot(5000, &loop, &QEventLoop::quit);
    if (!watcher.isFinished()) loop.exec();
    QDBusPendingReply<QString> reply = watcher;
    require(reply.isFinished() && reply.isValid() && reply.value() == QStringLiteral("ominx qt ipc"),
            "Qt asynchronous object roundtrip");
    std::puts("PASS Qt bus: source-linked Qt DBus, policy and asynchronous object roundtrip");
    return 0;
}
#include "main.moc"
