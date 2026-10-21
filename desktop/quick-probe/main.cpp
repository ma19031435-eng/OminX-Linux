// Target-side Qt Quick/theme compatibility test. No authentication implementation.
#include <QAbstractListModel>
#include <QFont>
#include <QFontDatabase>
#include <QGuiApplication>
#include <QKeyEvent>
#include <QQmlContext>
#include <QQuickItem>
#include <QQuickStyle>
#include <QQuickView>
#include <QTimer>
#include <cstdio>

static void report(const char *s) { std::puts(s); std::fflush(stdout); }
class NoSessions final : public QAbstractListModel {
    Q_OBJECT
    Q_PROPERTY(int lastIndex READ lastIndex CONSTANT)
public:
    int lastIndex() const { return -1; }
    int rowCount(const QModelIndex & = QModelIndex()) const override { return 0; }
    QVariant data(const QModelIndex &, int) const override { return {}; }
    QHash<int, QByteArray> roleNames() const override { return {{Qt::UserRole + 1, "name"}}; }
};
class DisabledContext final : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString lastUser READ lastUser CONSTANT)
    Q_PROPERTY(bool capsLock READ disabled CONSTANT)
    Q_PROPERTY(bool canPowerOff READ disabled CONSTANT)
    Q_PROPERTY(bool canReboot READ disabled CONSTANT)
public:
    QString lastUser() const { return {}; }
    bool disabled() const { return false; }
    Q_INVOKABLE void login(const QString &, const QString &, int) {
        report("OMINX_QUICK_UNEXPECTED_AUTH_CALL"); QGuiApplication::exit(1);
    }
    Q_INVOKABLE void powerOff() { report("OMINX_QUICK_UNEXPECTED_POWER_CALL"); QGuiApplication::exit(1); }
    Q_INVOKABLE void reboot() { powerOff(); }
signals:
    void loginFailed();
    void loginSucceeded();
};
class InputCheck final : public QObject {
    Q_OBJECT
    QQuickView &view;
    bool refused = false;
public:
    explicit InputCheck(QQuickView &v) : view(v) {}
    bool eventFilter(QObject *, QEvent *event) override {
        if (event->type() != QEvent::KeyPress) return false;
        int key = static_cast<QKeyEvent *>(event)->key();
        QTimer::singleShot(0, this, [this, key] {
            auto *root = view.rootObject();
            if (!root) return;
            auto *greeter = root->findChild<QObject *>("ominxGreeter");
            auto *password = root->findChild<QObject *>("password");
            auto *username = root->findChild<QObject *>("username");
            if (!greeter || !password || !username) { QGuiApplication::exit(1); return; }
            if (key == Qt::Key_Return && !refused &&
                greeter->property("failure").toString() == "No desktop session is installed." &&
                greeter->property("passwordIsMasked").toBool() &&
                username->property("text").toString() == "probe" &&
                password->property("text").toString() == "probe" &&
                !greeter->property("busy").toBool()) {
                refused = true;
                report("OMINX_QUICK_NO_SESSION_REFUSED");
            }
            if (key == Qt::Key_Escape && refused && password->property("text").toString().isEmpty()) {
                report("OMINX_QUICK_INPUT_OK"); QGuiApplication::exit(0);
            }
        });
        return false;
    }
};
int main(int argc, char **argv) {
    qputenv("QT_QUICK_BACKEND", "software");
    QGuiApplication app(argc, argv);
    QQuickStyle::setStyle("Basic");
    int font = QFontDatabase::addApplicationFont(":/fonts/DejaVuSans.ttf");
    if (font < 0) return 1;
    app.setFont(QFont(QFontDatabase::applicationFontFamilies(font).at(0)));
    NoSessions sessions;
    DisabledContext disabled;
    QQuickView view;
    InputCheck input(view);
    view.installEventFilter(&input);
    view.rootContext()->setContextProperty("sddm", &disabled);
    view.rootContext()->setContextProperty("keyboard", &disabled);
    view.rootContext()->setContextProperty("userModel", &disabled);
    view.rootContext()->setContextProperty("sessionModel", &sessions);
    view.setResizeMode(QQuickView::SizeRootObjectToView);
    view.setSource(QUrl("qrc:/qt/qml/OminX/Validation/Probe.qml"));
    if (view.status() != QQuickView::Ready) return 1;
    view.showFullScreen();
    bool reported = false;
    QObject::connect(&view, &QQuickWindow::frameSwapped, &app, [&reported] {
        if (!reported) { reported = true; report("OMINX_QUICK_FRAME_READY"); }
    });
    QTimer::singleShot(60000, &app, [] { report("OMINX_QUICK_TIMEOUT"); QGuiApplication::exit(1); });
    int result = app.exec();
    view.setSource(QUrl());
    return result;
}
#include "main.moc"
