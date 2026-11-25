#include "forge_bridge.h"

#include <QDir>
#include <QFileInfo>
#include <QJsonDocument>
#include <QStringList>

namespace {

bool badText(const QString &s)
{
    return s.contains(QChar('\n')) || s.contains(QChar('\0'));
}

bool isEditableRel(const QString &rel)
{
    if (rel == QLatin1String("forge.project"))
        return true;
    const bool inTop = rel.startsWith(QLatin1String("src/")) || rel.startsWith(QLatin1String("assets/"));
    if (!inTop)
        return false;
    const QStringList parts = rel.split(QLatin1Char('/'));
    for (const QString &part : parts) {
        if (part.startsWith(QLatin1Char('.')) || part == QLatin1String(".."))
            return false;
    }
    return true;
}

} // namespace

ForgeBridge::ForgeBridge(QString binary, QObject *parent)
    : QObject(parent), m_binary(std::move(binary))
{
}

QString ForgeBridge::checkProjectDir(const QString &path)
{
    if (path.isEmpty() || badText(path))
        return QStringLiteral("project folder is not valid");
    if (!QFileInfo(path).isAbsolute())
        return QStringLiteral("project folder must be an absolute path");
    if (!QFileInfo(path).isDir())
        return QStringLiteral("project folder does not exist");
    return {};
}

QString ForgeBridge::checkRel(const QString &rel)
{
    if (rel.isEmpty())
        return QStringLiteral("no file was chosen");
    if (rel.startsWith(QLatin1Char('-')) || badText(rel) || rel.contains(QLatin1Char('\\')))
        return QStringLiteral("that file name is not allowed");
    if (!isEditableRel(rel))
        return QStringLiteral("only files in src/, assets/ and forge.project can be used in Studio");
    return {};
}

QString ForgeBridge::checkNewProject(const QString &folder, const QString &ident, const QString &name)
{
    if (folder.isEmpty() || !QFileInfo(folder).isAbsolute() || badText(folder))
        return QStringLiteral("new project folder must be an absolute path");
    if (QFileInfo::exists(folder))
        return QStringLiteral("that folder already exists");
    if (!QFileInfo(QFileInfo(folder).absolutePath()).isDir())
        return QStringLiteral("the parent folder does not exist");
    const QString trimmedIdent = ident.trimmed();
    const QString trimmedName = name.trimmed();
    if (trimmedIdent.isEmpty() || trimmedIdent.startsWith(QLatin1Char('-')) || badText(trimmedIdent))
        return QStringLiteral("the app ID is not valid");
    if (trimmedName.isEmpty() || trimmedName.startsWith(QLatin1Char('-')) || badText(trimmedName))
        return QStringLiteral("the name is not valid");
    return {};
}

void ForgeBridge::refuse(const QString &requestId, const QString &op, const QString &message)
{
    emit finished(requestId, op, false, -1, QString(), message, QString());
}

void ForgeBridge::request(const QString &requestId, const QString &op, const QString &projectDir,
                          const QString &rel, const QString &content)
{
    QStringList args;
    QByteArray input;
    bool wantsStdin = false;

    if (op == QLatin1String("new")) {
        const QString problem = checkNewProject(projectDir, rel, content);
        if (!problem.isEmpty()) {
            refuse(requestId, op, problem);
            return;
        }
        args << QStringLiteral("new") << projectDir << QStringLiteral("--id") << rel.trimmed()
             << QStringLiteral("--name") << content.trimmed();
    } else {
        QString problem = checkProjectDir(projectDir);
        if (!problem.isEmpty()) {
            refuse(requestId, op, problem);
            return;
        }
        if (op == QLatin1String("tree")) {
            args << QStringLiteral("tree") << projectDir << QStringLiteral("--json");
        } else if (op == QLatin1String("check")) {
            args << QStringLiteral("check") << projectDir << QStringLiteral("--json");
        } else if (op == QLatin1String("run") || op == QLatin1String("test") || op == QLatin1String("build")) {
            args << op << projectDir;
        } else if (op == QLatin1String("read") || op == QLatin1String("write")) {
            problem = checkRel(rel);
            if (!problem.isEmpty()) {
                refuse(requestId, op, problem);
                return;
            }
            args << op << projectDir << rel;
            if (op == QLatin1String("write")) {
                wantsStdin = true;
                input = content.toUtf8();
                if (input.size() > 1024 * 1024) {
                    refuse(requestId, op, QStringLiteral("file is too large for Studio (1 MiB limit)"));
                    return;
                }
            }
        } else {
            refuse(requestId, op, QStringLiteral("unknown operation"));
            return;
        }
    }

    auto *proc = new QProcess(this);
    proc->setProgram(m_binary);
    proc->setArguments(args);
    connect(proc, &QProcess::errorOccurred, this, [this, proc, requestId, op](QProcess::ProcessError) {
        if (proc->error() == QProcess::FailedToStart) {
            refuse(requestId, op, QStringLiteral("Studio could not start Forge"));
            proc->deleteLater();
        }
    });
    connect(proc, &QProcess::finished, this,
            [this, proc, requestId, op](int exitCode, QProcess::ExitStatus status) {
                const QString out = QString::fromUtf8(proc->readAllStandardOutput());
                const QString err = QString::fromUtf8(proc->readAllStandardError());
                const bool ok = status == QProcess::NormalExit && exitCode == 0;
                QString data;
                if (op == QLatin1String("tree") || op == QLatin1String("check")) {
                    const QJsonDocument doc = QJsonDocument::fromJson(out.toUtf8());
                    if (!doc.isNull())
                        data = QString::fromUtf8(doc.toJson(QJsonDocument::Compact));
                }
                emit finished(requestId, op, ok, status == QProcess::NormalExit ? exitCode : -1, out, err, data);
                proc->deleteLater();
            });
    proc->start();
    if (wantsStdin) {
        proc->write(input);
        proc->closeWriteChannel();
    }
}
