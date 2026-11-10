// Runtime test for the native Forge Studio bridge (ForgeBridge) against real Qt Core.
// Usage: bridge_native_test <ominx-forge binary> <scratch directory>
// The binary must accept the OMINX_FORGE_OS_RELEASE override (test builds only).
#include "../forge_bridge.h"

#include <QCoreApplication>
#include <QDir>
#include <QEventLoop>
#include <QFile>
#include <QTimer>

#include <cstdio>

namespace {

struct Result {
    QString requestId, op, out, err, data;
    bool ok = false;
    int code = 0;
    bool seen = false;
};

int failures = 0;

void check(bool cond, const char *what)
{
    std::printf("%s %s\n", cond ? "ok  " : "FAIL", what);
    if (!cond)
        ++failures;
}

// Sends one request and waits for its finished() signal (or 20 s).
Result call(ForgeBridge &bridge, const QString &id, const QString &op, const QString &dir,
            const QString &rel, const QString &content)
{
    Result r;
    QEventLoop loop;
    const QMetaObject::Connection link = QObject::connect(
        &bridge, &ForgeBridge::finished, &loop,
        [&](const QString &rid, const QString &o, bool ok, int code, const QString &out,
            const QString &err, const QString &data) {
            if (rid != id)
                return;
            r.requestId = rid;
            r.op = o;
            r.ok = ok;
            r.code = code;
            r.out = out;
            r.err = err;
            r.data = data;
            r.seen = true;
            loop.quit();
        });
    QTimer::singleShot(20000, &loop, &QEventLoop::quit);
    bridge.request(id, op, dir, rel, content);
    loop.exec();
    QObject::disconnect(link);
    return r;
}

} // namespace

int main(int argc, char *argv[])
{
    QCoreApplication app(argc, argv);
    if (argc != 3) {
        std::fputs("usage: bridge_native_test <ominx-forge> <scratch dir>\n", stderr);
        return 2;
    }
    const QString forge = QString::fromLocal8Bit(argv[1]);
    const QString scratch = QString::fromLocal8Bit(argv[2]);
    ForgeBridge bridge(forge);

    const QString proj = QDir(scratch).filePath(QStringLiteral("native-demo"));
    QDir(proj).removeRecursively();

    Result r = call(bridge, QStringLiteral("1"), QStringLiteral("new"), proj,
                    QStringLiteral("org.example.native"), QStringLiteral("Native"));
    check(r.ok && r.code == 0, "new creates a project");
    check(QFile::exists(proj + QStringLiteral("/forge.project")), "new writes forge.project");

    r = call(bridge, QStringLiteral("2"), QStringLiteral("tree"), proj, QString(), QString());
    check(r.ok, "tree succeeds");
    check(r.data.contains(QStringLiteral("src/main.fg")), "tree JSON lists src/main.fg");

    r = call(bridge, QStringLiteral("3"), QStringLiteral("check"), proj, QString(), QString());
    check(r.ok, "check runs on the new project");

    r = call(bridge, QStringLiteral("4"), QStringLiteral("read"), proj, QStringLiteral("src/main.fg"),
             QString());
    check(r.ok && r.out.contains(QStringLiteral("fn main")), "read returns the file");

    const QString edited = QStringLiteral("fn main() {\n    print(\"native\")\n}\n");
    r = call(bridge, QStringLiteral("5"), QStringLiteral("write"), proj, QStringLiteral("src/main.fg"),
             edited);
    check(r.ok, "write saves the file");
    r = call(bridge, QStringLiteral("6"), QStringLiteral("read"), proj, QStringLiteral("src/main.fg"),
             QString());
    check(r.out == edited, "write then read round-trips the bytes");

    r = call(bridge, QStringLiteral("7"), QStringLiteral("read"), proj, QStringLiteral("../etc/passwd"),
             QString());
    check(!r.ok && r.code == -1 && r.err.contains(QStringLiteral("not allowed")),
          "path traversal is refused before any process starts");

    r = call(bridge, QStringLiteral("8"), QStringLiteral("write"), proj, QStringLiteral("forge.project.bak"),
             QStringLiteral("x"));
    check(!r.ok && r.code == -1, "write outside the editable set is refused");

    r = call(bridge, QStringLiteral("9"), QStringLiteral("exec"), proj, QString(), QString());
    check(!r.ok && r.err.contains(QStringLiteral("unknown operation")), "unknown operation is refused");

    r = call(bridge, QStringLiteral("10"), QStringLiteral("tree"), QStringLiteral("relative/dir"), QString(),
             QString());
    check(!r.ok && r.err.contains(QStringLiteral("absolute")), "relative project folder is refused");

    r = call(bridge, QStringLiteral("11"), QStringLiteral("tree"), QStringLiteral("/nonexistent/forge-dir"),
             QString(), QString());
    check(!r.ok && r.err.contains(QStringLiteral("does not exist")), "missing project folder is refused");

    std::printf("%d failure(s)\n", failures);
    return failures == 0 ? 0 : 1;
}
