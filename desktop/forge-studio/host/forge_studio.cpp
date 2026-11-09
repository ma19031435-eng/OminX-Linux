// Forge Studio entry point. It runs only on OminXOS: /etc/os-release must say ID=ominx.
// That is a product gate, not a security boundary. Confinement lives in ominx-forge.
#include "forge_bridge.h"

#include <QFile>
#include <QStringList>
#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>

#include <cstdio>

namespace {

bool runsOnOminx()
{
    QFile release(QStringLiteral("/etc/os-release"));
    if (!release.open(QIODevice::ReadOnly | QIODevice::Text))
        return false;
    const QStringList lines = QString::fromUtf8(release.readAll()).split(QLatin1Char('\n'));
    for (const QString &line : lines) {
        if (line.trimmed() == QLatin1String("ID=ominx"))
            return true;
    }
    return false;
}

} // namespace

int main(int argc, char *argv[])
{
    if (!runsOnOminx()) {
        std::fputs("Forge Studio runs only on OminXOS.\n", stderr);
        return 3;
    }

    QGuiApplication app(argc, argv);
    app.setApplicationName(QStringLiteral("Forge Studio"));
    app.setOrganizationName(QStringLiteral("OminX"));

    QQmlApplicationEngine engine;
    ForgeBridge bridge(QLatin1String(ForgeBridge::kForgeBinary));
    engine.rootContext()->setContextProperty(QStringLiteral("forge"), &bridge);
    engine.loadFromModule(QStringLiteral("ForgeStudio"), QStringLiteral("Main"));
    if (engine.rootObjects().isEmpty())
        return 1;
    return app.exec();
}
