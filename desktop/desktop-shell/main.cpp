// Original OminX desktop shell: themed login screen and user session.
// Authentication happens in the root broker; this process only asks and renders.
#include <QAbstractListModel>
#include <QEvent>
#include <QKeyEvent>
#include <QFont>
#include <QFontDatabase>
#include <QHash>
#include <QGuiApplication>
#include <QQmlContext>
#include <QQuickStyle>
#include <QQuickView>
#include <QStringList>
#include <QTimer>
#include <sys/socket.h>
#include <sys/time.h>
#include <sys/un.h>
#include <unistd.h>
#include <cstdio>
#include <cstring>

/* File scope (not an unnamed namespace) so moc output matches the accepted
   Qt Quick probe layout exactly. */
static const char *const kLoginSocket = "/run/ominx/login.sock";
static const char *const kPowerSocket = "/run/ominx/control.sock";

static void report(const char *text) {
    std::puts(text);
    std::fflush(stdout);
}
static void report(const QByteArray &text) { report(text.constData()); }

static bool datagram(const char *path, const QByteArray &request, QByteArray *reply, QString *error) {
    int fd = ::socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0);
    if (fd < 0) { *error = QStringLiteral("socket"); return false; }
    sockaddr_un address{};
    address.sun_family = AF_UNIX;
    std::strncpy(address.sun_path, path, sizeof(address.sun_path) - 1);
    timeval timeout{15, 0};
    ::setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof timeout);
    ::setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof timeout);
    if (::connect(fd, reinterpret_cast<sockaddr *>(&address), sizeof address) < 0) {
        ::close(fd); *error = QStringLiteral("connect"); return false;
    }
    if (::send(fd, request.constData(), size_t(request.size()), MSG_NOSIGNAL) < 0) {
        ::close(fd); *error = QStringLiteral("send"); return false;
    }
    char buffer[4096];
    ssize_t size = ::recv(fd, buffer, sizeof buffer - 1, 0);
    ::close(fd);
    if (size <= 0) { *error = QStringLiteral("recv"); return false; }
    *reply = QByteArray(buffer, int(size));
    return true;
}

class UserModel final : public QAbstractListModel {
    Q_OBJECT
    Q_PROPERTY(QString lastUser READ lastUser CONSTANT)
public:
    explicit UserModel(QObject *parent = nullptr) : QAbstractListModel(parent) {}
    /* Called only in greeter mode, once the login broker is reachable. */
    void reload() {
        QByteArray reply;
        QString error;
        if (!datagram(kLoginSocket, "LIST\n", &reply, &error)) {
            report("greeter: account list unavailable (" + error.toUtf8() + ")");
            return;
        }
        beginResetModel();
        m_names.clear();
        const QStringList lines = QString::fromUtf8(reply).split('\n', Qt::SkipEmptyParts);
        for (qsizetype index = 1; index < lines.size(); ++index) {
            const QStringList fields = lines.at(index).split('\t');
            if (fields.size() >= 3 && fields.at(2) == QLatin1String("0")) m_names << fields.at(0);
        }
        endResetModel();
        report("greeter: listed " + QByteArray::number(int(m_names.size())) + " unlocked accounts");
    }
    QString lastUser() const { return m_names.isEmpty() ? QString() : m_names.first(); }
    int rowCount(const QModelIndex & = QModelIndex()) const override { return m_names.size(); }
    QVariant data(const QModelIndex &index, int role) const override {
        if (role != Qt::UserRole + 1 || !index.isValid()) return {};
        return m_names.at(index.row());
    }
    QHash<int, QByteArray> roleNames() const override { return {{Qt::UserRole + 1, "name"}}; }
private:
    QStringList m_names;
};

class SessionModel final : public QAbstractListModel {
    Q_OBJECT
    Q_PROPERTY(int lastIndex READ lastIndex CONSTANT)
public:
    int lastIndex() const { return 0; }
    int rowCount(const QModelIndex & = QModelIndex()) const override { return 1; }
    QVariant data(const QModelIndex &index, int role) const override {
        if (role != Qt::DisplayRole || index.row() != 0) return {};
        return tr("OminX Desktop");
    }
    QHash<int, QByteArray> roleNames() const override { return {{Qt::DisplayRole, "name"}}; }
};

/* Tracks the physical Caps Lock key through real key events. The framebuffer
   backend exposes no LED query, so state is only what this greeter observed. */
class CapsLock final : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool capsLock READ capsLock NOTIFY capsLockChanged)
public:
    explicit CapsLock(QObject *parent = nullptr) : QObject(parent) {
        qApp->installEventFilter(this);
    }
    bool capsLock() const { return m_state; }
signals:
    void capsLockChanged();
protected:
    bool eventFilter(QObject *, QEvent *event) override {
        if (event->type() != QEvent::KeyPress) return false;
        if (static_cast<QKeyEvent *>(event)->key() != Qt::Key_CapsLock) return false;
        m_state = !m_state;
        emit capsLockChanged();
        return false;
    }
private:
    bool m_state = false;
};

class LoginContext final : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool canPowerOff READ allowed CONSTANT)
    Q_PROPERTY(bool canReboot READ allowed CONSTANT)
    Q_PROPERTY(QString lastUser READ lastUser CONSTANT)
public:
    explicit LoginContext(UserModel *users, QObject *parent = nullptr) : QObject(parent), m_users(users) {}
    bool allowed() const { return true; }
    QString lastUser() const { return m_users->lastUser(); }
    Q_INVOKABLE void login(const QString &user, const QString &password, int session) {
        Q_UNUSED(session);
        QByteArray reply;
        QString error;
        const QByteArray request = "AUTH\t" + user.toUtf8() + "\t" + password.toUtf8() + "\n";
        if (!datagram(kLoginSocket, request, &reply, &error)) {
            report("greeter: broker unavailable (" + error.toUtf8() + ")");
            emit loginFailed();
            return;
        }
        if (reply.startsWith("OK\t")) {
            report("OMINX_LOGIN_ACCEPTED user=" + user.toUtf8() + " uid=" + reply.mid(3).trimmed());
            emit loginSucceeded();
            QTimer::singleShot(400, qApp, [] { QGuiApplication::exit(0); });
            return;
        }
        const QByteArray reason = reply.startsWith("DENY\t") ? reply.mid(5).trimmed() : QByteArray("refused");
        report("OMINX_LOGIN_DENIED user=" + user.toUtf8() + " reason=" + reason);
        emit loginFailed();
    }
    Q_INVOKABLE void powerOff() { request("off"); }
    Q_INVOKABLE void reboot() { request("reboot"); }
signals:
    void loginFailed();
    void loginSucceeded();
private:
    void request(const char *action) {
        QByteArray reply;
        QString error;
        const QByteArray payload = QByteArray("POWER\t") + (std::strcmp(action, "off") ? "reboot" : "off") + "\n";
        if (!datagram(kLoginSocket, payload, &reply, &error) || !reply.startsWith("OK")) {
            report("greeter: power request refused");
            return;
        }
        report(QByteArray("OMINX_LOGIN_POWER ") + action);
        QTimer::singleShot(300, qApp, [] { QGuiApplication::exit(0); });
    }
    UserModel *m_users;
};

class SessionContext final : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString userName READ userName CONSTANT)
    Q_PROPERTY(QStringList facts READ facts CONSTANT)
    /* Windows (Wine/Proton) state, refreshed from the per-user background
       service the seat starts at login. The panel in Session.qml renders
       these; it must stay truthful when the runtime is not installed. */
    Q_PROPERTY(QString winSummary READ winSummary NOTIFY winChanged)
    Q_PROPERTY(int winPercent READ winPercent NOTIFY winChanged)
    Q_PROPERTY(bool winReady READ winReady NOTIFY winChanged)
    Q_PROPERTY(QStringList winApps READ winApps NOTIFY winChanged)
public:
    SessionContext() {
        /* The greeter process also constructs this object; the per-user
           Windows service must only be contacted from a real session. */
        if (qEnvironmentVariable("USER") == QLatin1String("greeter")) return;
        auto *timer = new QTimer(this);
        timer->setInterval(3000);
        connect(timer, &QTimer::timeout, this, [this] { refreshWin(); });
        timer->start();
        QTimer::singleShot(0, this, [this] { refreshWin(); });
    }
    QString userName() const { return qEnvironmentVariable("USER", "ominx"); }
    QString winSummary() const {
        if (m_winState == QLatin1String("ready"))
            return tr("Windows apps are ready (Wine %1, Proton %2).")
                .arg(m_winVersion.isEmpty() ? tr("runtime") : m_winVersion,
                     m_winProton == QLatin1String("ready") ? tr("ready") : tr("preparing"));
        if (m_winState == QLatin1String("setting-up"))
            return tr("Preparing your Windows environment... %1% (%2)")
                .arg(m_winPercent).arg(m_winStep);
        if (m_winState == QLatin1String("runtime-missing"))
            return tr("The Wine/Proton runtime is not installed in this image yet.");
        if (m_winState == QLatin1String("failed"))
            return tr("Windows setup did not finish. Choose Set up Windows apps to retry.");
        return tr("Windows service is starting...");
    }
    int winPercent() const { return m_winPercent; }
    bool winReady() const { return m_winState == QLatin1String("ready"); }
    QStringList winApps() const { return m_winAppNames; }
    Q_INVOKABLE void refreshWin() {
        QByteArray reply;
        QString error;
        const QByteArray socketPath = winSocket().toUtf8();
        if (socketPath.isEmpty() ||
            !datagram(socketPath.constData(), "STATUS\n", &reply, &error)) {
            if (m_winState != QLatin1String("unavailable")) {
                m_winState = QStringLiteral("unavailable");
                emit winChanged();
            }
            return;
        }
        QHash<QString, QString> values;
        const QStringList lines = QString::fromUtf8(reply).split('\n', Qt::SkipEmptyParts);
        for (const QString &line : lines) {
            const qsizetype at = line.indexOf('=');
            if (at > 0) values.insert(line.left(at), line.mid(at + 1));
        }
        m_winState = values.value(QStringLiteral("state"), QStringLiteral("unavailable"));
        m_winStep = values.value(QStringLiteral("step"));
        m_winVersion = values.value(QStringLiteral("version"));
        m_winProton = values.value(QStringLiteral("proton-default"));
        m_winPercent = values.value(QStringLiteral("percent")).toInt();
        if (winReady() && datagram(socketPath.constData(), "APPS\n", &reply, &error)) {
            m_winAppNames.clear();
            m_winAppPaths.clear();
            const QStringList appLines = QString::fromUtf8(reply).split('\n', Qt::SkipEmptyParts);
            for (const QString &line : appLines) {
                const QStringList fields = line.split('\t');
                if (fields.size() == 3 && fields.at(0) == QLatin1String("APP")) {
                    m_winAppNames << fields.at(1);
                    m_winAppPaths << fields.at(2);
                }
            }
        }
        emit winChanged();
    }
    Q_INVOKABLE void setupWindows() {
        QByteArray reply;
        QString error;
        const QByteArray socketPath = winSocket().toUtf8();
        if (!socketPath.isEmpty())
            (void)datagram(socketPath.constData(), "SETUP\n", &reply, &error);
        refreshWin();
    }
    Q_INVOKABLE void launchWinApp(int index) {
        if (index < 0 || index >= m_winAppPaths.size()) return;
        QByteArray reply;
        QString error;
        const QByteArray socketPath = winSocket().toUtf8();
        const QByteArray request = "RUN\t" + m_winAppPaths.at(index).toUtf8() + "\n";
        if (socketPath.isEmpty() ||
            !datagram(socketPath.constData(), request, &reply, &error) ||
            !reply.startsWith("OK")) {
            report("OMINX_WIN_LAUNCH_REFUSED " + m_winAppPaths.at(index).toUtf8());
            return;
        }
        report("OMINX_WIN_LAUNCH " + m_winAppPaths.at(index).toUtf8());
    }
signals:
    void winChanged();
private:
    static QString winSocket() {
        const QString direct = qEnvironmentVariable("OMINX_WINED_SOCKET");
        if (!direct.isEmpty()) return direct;
        const QString runtime = qEnvironmentVariable("XDG_RUNTIME_DIR");
        return runtime.isEmpty() ? QString() : runtime + QStringLiteral("/ominx-wined.sock");
    }
    QString m_winState = QStringLiteral("unavailable");
    QString m_winStep;
    QString m_winVersion;
    QString m_winProton;
    int m_winPercent = 0;
    QStringList m_winAppNames;
    QStringList m_winAppPaths;
public:
    QStringList facts() const {
        return {tr("User: %1").arg(userName()),
                tr("Home: %1").arg(qEnvironmentVariable("HOME")),
                tr("Runtime directory: %1").arg(qEnvironmentVariable("XDG_RUNTIME_DIR")),
                tr("Session bus: %1").arg(qEnvironmentVariable("DBUS_SESSION_BUS_ADDRESS", tr("none"))),
                tr("System bus: %1").arg(qEnvironmentVariable("DBUS_SYSTEM_BUS_ADDRESS", tr("none")))};
    }
    Q_INVOKABLE void logout() {
        report("OMINX_SESSION_LOGOUT");
        QTimer::singleShot(300, qApp, [] { QGuiApplication::exit(0); });
    }
    Q_INVOKABLE void powerOff() { power("poweroff"); }
    Q_INVOKABLE void reboot() { power("reboot"); }
private:
    void power(const char *command) {
        QByteArray reply;
        QString error;
        if (!datagram(kPowerSocket, QByteArray(command) + "\n", &reply, &error)) {
            report(QByteArray("OMINX_SESSION_POWER_REFUSED ") + command);
            return;
        }
        report(QByteArray("OMINX_SESSION_POWER ") + command + " " + reply.trimmed());
        if (reply.startsWith("OK poweroff") || reply.startsWith("OK reboot"))
            QTimer::singleShot(300, qApp, [] { QGuiApplication::exit(0); });
    }
};
int main(int argc, char **argv) {
    const bool greeter = argc == 2 && !std::strcmp(argv[1], "--greeter");
    const bool session = argc == 2 && !std::strcmp(argv[1], "--session");
    if (!greeter && !session) {
        std::fputs("usage: ominx-desktop --greeter | --session\n", stderr);
        return 2;
    }
    qputenv("QT_QUICK_BACKEND", "software");
    QGuiApplication app(argc, argv);
    QQuickStyle::setStyle("Basic");
    const int font = QFontDatabase::addApplicationFont(":/fonts/DejaVuSans.ttf");
    if (font < 0) return 1;
    app.setFont(QFont(QFontDatabase::applicationFontFamilies(font).at(0)));
    /* QML keeps unowned pointers to these, so they must outlive app.exec(). */
    UserModel users;
    SessionModel sessions;
    CapsLock caps;
    LoginContext login(&users);
    SessionContext context;
    QQuickView view;
    view.setResizeMode(QQuickView::SizeRootObjectToView);
    if (greeter) {
        users.reload();
        view.rootContext()->setContextProperty("sddm", &login);
        view.rootContext()->setContextProperty("keyboard", &caps);
        view.rootContext()->setContextProperty("userModel", &users);
        view.rootContext()->setContextProperty("sessionModel", &sessions);
        view.setSource(QUrl("qrc:/qt/qml/OminX/Shell/GreeterRoot.qml"));
    } else {
        view.rootContext()->setContextProperty("session", &context);
        view.setSource(QUrl("qrc:/qt/qml/OminX/Shell/Session.qml"));
    }
    if (view.status() != QQuickView::Ready) {
        report(greeter ? "OMINX_GREETER_QML_FAILED" : "OMINX_SESSION_QML_FAILED");
        return 1;
    }
    view.showFullScreen();
    bool announced = false;
    QObject::connect(&view, &QQuickWindow::frameSwapped, &app, [&announced, greeter] {
        if (announced) return;
        announced = true;
        const QString ready = greeter
            ? QStringLiteral("OMINX_GREETER_READY")
            : QStringLiteral("OMINX_SESSION_READY user=%1 home=%2")
                  .arg(qEnvironmentVariable("USER"), qEnvironmentVariable("HOME"));
        report(ready.toUtf8());
    });
    // A login screen that never paints must not hold the console forever.
    QTimer::singleShot(120000, &app, [] {
        report("OMINX_SHELL_TIMEOUT");
        QGuiApplication::exit(1);
    });
    const int result = app.exec();
    view.setSource(QUrl());
    return result;
}

#include "main.moc"
