// Bench hello app - Qt6 Widgets variant: minimal static window, one
// "Hello" label + one button. Isolates the startup floor and baseline
// memory.
// First-presented-frame proxy: first paintEvent hit on the top-level
// widget (raster QWidget windows do not emit QWindow::frameSwapped) -
// same proxy as the other Qt apps.

#include <QtWidgets>

#include <functional>

#include "bench_common.h"

class HelloWindow : public QWidget {
public:
    std::function<void()> onFirstPaint;

protected:
    void paintEvent(QPaintEvent *e) override {
        QWidget::paintEvent(e);
        if (!m_painted) {
            m_painted = true;
            if (onFirstPaint) onFirstPaint();
        }
    }

private:
    bool m_painted = false;
};

int main(int argc, char **argv) {
    const Clock::time_point t0 = Clock::now();

    QApplication app(argc, argv);
    const Mode mode = parseMode(argc, argv);

    HelloWindow w;
    w.setWindowTitle(QStringLiteral("Bench"));
    w.resize(800, 600);

    auto *layout = new QVBoxLayout(&w);
    layout->addStretch();
    auto *label = new QLabel(QStringLiteral("Hello"));
    QFont f = label->font();
    f.setBold(true);
    f.setPixelSize(18);
    label->setFont(f);
    label->setAlignment(Qt::AlignHCenter);
    auto *btn = new QPushButton(QStringLiteral("Press"));
    layout->addWidget(label, 0, Qt::AlignHCenter);
    layout->addSpacing(12);
    layout->addWidget(btn, 0, Qt::AlignHCenter);
    layout->addStretch();

    w.onFirstPaint = [t0, mode] {
        const Clock::time_point now = Clock::now();
        printFirstFrame();
        if (mode == Mode::Startup) {
            printStartupAndExit(t0, now);
        }
    };

    w.show();
    return app.exec();
}
