// Forge Studio native bridge: the QML-facing `forge` object.
// It mirrors host/forge_bridge.py. Operations are fixed, arguments are passed as a
// list (never through a shell), and every request is validated before it runs.
#ifndef FORGE_STUDIO_BRIDGE_H
#define FORGE_STUDIO_BRIDGE_H

#include <QObject>
#include <QProcess>
#include <QString>

class ForgeBridge : public QObject {
    Q_OBJECT

public:
    explicit ForgeBridge(QString binary, QObject *parent = nullptr);

    // Fixed program path on OminXOS. Studio never accepts a path from QML.
    static constexpr const char *kForgeBinary = "/bin/ominx-forge";

    // Validation shared with the Python host. Returns an empty string when valid.
    static QString checkProjectDir(const QString &path);
    static QString checkRel(const QString &rel);
    static QString checkNewProject(const QString &folder, const QString &ident, const QString &name);

public slots:
    // Starts one operation. Exactly one `finished` signal follows for every request.
    void request(const QString &requestId, const QString &op, const QString &projectDir,
                 const QString &rel, const QString &content);

signals:
    void finished(const QString &requestId, const QString &op, bool ok, int exitCode,
                  const QString &stdoutText, const QString &stderrText, const QString &dataJson);

private:
    void refuse(const QString &requestId, const QString &op, const QString &message);

    QString m_binary;
};

#endif
