// Bench textview app - Qt6 Widgets variant: the shared ~1 MiB corpus
// (5,000 wrapped paragraphs) in a read-only QTextEdit (the idiomatic Qt
// long-document view; QTextDocument lays out lazily and scrolls per
// pixel).
// First-presented-frame proxy: first paintEvent on the top-level widget.
// Scroll-bench frame timestamps: paint events on the QTextEdit viewport,
// while a 16 ms QTimer drives the vertical scrollbar from wall-clock
// elapsed time (raster painting is synchronous and not vsync-locked, so
// the drive timer sets the paint cadence - see caveats).

#include <QtWidgets>

#include <functional>
#include <vector>

#include "bench_common.h"

static constexpr double kSpeed = 1000.0; // px/s

class BenchWindow : public QWidget {
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

class PaintRecorder : public QObject {
public:
    std::vector<Clock::time_point> frames;
    bool recording = false;

protected:
    bool eventFilter(QObject *obj, QEvent *ev) override {
        if (recording && ev->type() == QEvent::Paint)
            frames.push_back(Clock::now());
        return QObject::eventFilter(obj, ev);
    }
};

int main(int argc, char **argv) {
    const Clock::time_point t0 = Clock::now();

    QApplication app(argc, argv);
    const Mode mode = parseMode(argc, argv);
    const bool modeScroll = (mode == Mode::ScrollBench);
    const double durationS = scrollSeconds();

    QString corpus;
    {
        QFile f(QString::fromLocal8Bit(corpusPath()));
        if (!f.open(QIODevice::ReadOnly | QIODevice::Text)) {
            std::fprintf(stderr, "cannot read corpus %s\n", corpusPath());
            return 1;
        }
        corpus = QString::fromUtf8(f.readAll());
    }

    BenchWindow w;
    w.setWindowTitle(QStringLiteral("Bench"));
    w.resize(800, 600);

    auto *outer = new QVBoxLayout(&w);
    outer->setContentsMargins(0, 0, 0, 0);
    outer->setSpacing(0);

    // Header ---------------------------------------------------------
    auto *header = new QWidget;
    header->setFixedHeight(48);
    auto *hl = new QHBoxLayout(header);
    hl->setContentsMargins(8, 8, 8, 8);
    auto *title = new QLabel(QStringLiteral("Bench"));
    QFont titleFont = title->font();
    titleFont.setBold(true);
    titleFont.setPixelSize(18);
    title->setFont(titleFont);
    hl->addWidget(title);
    hl->addStretch();

    // Document -------------------------------------------------------
    auto *doc = new QTextEdit;
    doc->setReadOnly(true);
    doc->setFrameShape(QFrame::NoFrame);
    doc->setLineWrapMode(QTextEdit::WidgetWidth);
    doc->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    doc->setPlainText(corpus);

    outer->addWidget(header);
    outer->addWidget(doc, 1);

    // Instrumentation ------------------------------------------------
    auto *recorder = new PaintRecorder;
    doc->viewport()->installEventFilter(recorder);

    auto *scrollTimer = new QTimer(&w);
    scrollTimer->setTimerType(Qt::PreciseTimer);
    scrollTimer->setInterval(16);
    Clock::time_point scrollStart;

    QObject::connect(scrollTimer, &QTimer::timeout,
                     [doc, recorder, scrollTimer, &scrollStart, durationS] {
        const double elapsed =
            std::chrono::duration<double>(Clock::now() - scrollStart).count();
        if (elapsed >= durationS) {
            scrollTimer->stop();
            recorder->recording = false;
            // Stay alive for the post-run memory sample.
            printDeltasDone(recorder->frames);
            return;
        }
        auto *bar = doc->verticalScrollBar();
        bar->setValue(
            (int)std::lround(bounce(kSpeed * elapsed, bar->maximum())));
    });

    w.onFirstPaint = [t0, mode, modeScroll, recorder, scrollTimer,
                      &scrollStart] {
        const Clock::time_point now = Clock::now();
        printFirstFrame();
        if (mode == Mode::Startup) {
            printStartupAndExit(t0, now);
        }
        if (modeScroll) {
            scrollStart = now;
            recorder->recording = true;
            scrollTimer->start();
        }
    };

    w.show();
    return app.exec();
}
