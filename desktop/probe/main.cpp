// Original target-side graphics acceptance application. Not a login manager.
#include <QApplication>
#include <QKeyEvent>
#include <QPainter>
#include <QTimer>
#include <QWidget>
#include <cstdio>

static void report(const char *line) { std::puts(line); std::fflush(stdout); }
class Probe final : public QWidget {
    bool painted = false;
    bool input = false;
public:
    Probe() {
        setWindowFlags(Qt::FramelessWindowHint);
        setFocusPolicy(Qt::StrongFocus);
        QTimer::singleShot(40000, this, [] { report("OMINX_QT_TIMEOUT"); QApplication::exit(1); });
    }
    void paintEvent(QPaintEvent *) override {
        QPainter painter(this);
        painter.fillRect(rect(), QColor("#0b1220"));
        painter.fillRect(width()/4, height()/4, width()/2, height()/2, QColor("#334155"));
        painter.fillRect(width()/4, height()/4, width()/2, height()/8,
                         QColor(input ? "#ffb454" : "#34d3c6"));
        if (!painted) {
            painted = true;
            QTimer::singleShot(0, this, [] { report("OMINX_QT_FRAME_PAINTED"); });
        }
    }
    void keyPressEvent(QKeyEvent *event) override {
        if (event->key() == Qt::Key_Space) {
            input = true;
            update();
            report("OMINX_QT_INPUT_OK");
        } else if (event->key() == Qt::Key_Return && input) {
            report("OMINX_QT_EXIT_OK");
            QApplication::exit(0);
        }
    }
};
int main(int argc, char **argv) {
    QApplication app(argc, argv);
    Probe probe;
    probe.showFullScreen();
    probe.setFocus();
    return app.exec();
}
