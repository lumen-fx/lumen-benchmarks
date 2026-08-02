// Bench textview app - Qt Quick variant: the shared ~1 MiB corpus (5,000
// wrapped paragraphs) in a read-only TextArea (backed by the same
// QTextDocument layout engine QTextEdit uses, so it lays out lazily
// around the wrapped width - the Qt Quick long-document path, no
// virtualization, same as qt-widgets/textview.cpp).
// First-presented-frame proxy: QQuickWindow::frameSwapped.
// Scroll-bench frame timestamps: every frameSwapped while a 16 ms timer
// drives the hosting Flickable's `contentY` from wall-clock elapsed time.

#include <QGuiApplication>
#include <QQuickView>
#include <QQuickWindow>
#include <QQuickItem>
#include <QQmlContext>
#include <QFile>
#include <QIODevice>
#include <QTimer>
#include <QUrl>

#include <algorithm>
#include <cstdio>

#include "bench_common.h"

static constexpr double kSpeed = 1000.0; // px/s

int main(int argc, char **argv) {
    const Clock::time_point t0 = Clock::now();

    QGuiApplication app(argc, argv);
    const Mode mode = parseMode(argc, argv);
    const bool modeStartup = (mode == Mode::Startup);
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

    QQuickView view;
    view.setResizeMode(QQuickView::SizeRootObjectToView);
    view.setTitle(QStringLiteral("Bench"));
    view.resize(800, 600);
    view.rootContext()->setContextProperty("benchCorpus", corpus);

    view.setSource(QUrl(QStringLiteral("qrc:/textview.qml")));
    if (view.status() == QQuickView::Error) {
        for (const auto &e : view.errors())
            std::fprintf(stderr, "%s\n", e.toString().toUtf8().constData());
        return 1;
    }

    QQuickItem *flick =
        view.rootObject()->findChild<QQuickItem *>(QStringLiteral("flick"));

    std::vector<Clock::time_point> frames;
    bool recording = false;
    Clock::time_point scrollStart;

    QTimer scrollTimer;
    scrollTimer.setTimerType(Qt::PreciseTimer);
    scrollTimer.setInterval(16);
    QObject::connect(&scrollTimer, &QTimer::timeout, [&] {
        const double elapsed =
            std::chrono::duration<double>(Clock::now() - scrollStart).count();
        if (elapsed >= durationS) {
            scrollTimer.stop();
            recording = false;
            // Stay alive for the post-run memory sample.
            printDeltasDone(frames);
            return;
        }
        if (flick) {
            const double maxY = std::max(
                0.0, flick->property("contentHeight").toReal() -
                         flick->property("height").toReal());
            flick->setProperty("contentY", bounce(kSpeed * elapsed, maxY));
        }
    });

    bool painted = false;
    QObject::connect(&view, &QQuickWindow::frameSwapped, &app, [&] {
        const Clock::time_point now = Clock::now();
        if (!painted) {
            painted = true;
            printFirstFrame();
            if (modeStartup) {
                printStartupAndExit(t0, now);
            }
            if (modeScroll) {
                scrollStart = now;
                recording = true;
                scrollTimer.start();
            }
        }
        if (recording) {
            frames.push_back(now);
        }
    });

    view.show();
    return app.exec();
}
