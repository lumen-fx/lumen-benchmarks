// Bench hello app - Qt Quick variant: minimal static window, one "Hello"
// label + one button, rendered through the Qt Quick scene graph (its own
// glyph atlas and batched geometry, not QStyle) rather than the platform
// style qt-widgets/hello.cpp uses. Isolates the startup floor and
// baseline memory for the own-renderer path.
// First-presented-frame proxy: QQuickWindow::frameSwapped (the scene
// graph's first completed buffer swap) - the same proxy every app in
// this directory uses.

#include <QGuiApplication>
#include <QQuickView>
#include <QQuickWindow>
#include <QUrl>

#include <cstdio>

#include "bench_common.h"

int main(int argc, char **argv) {
    const Clock::time_point t0 = Clock::now();

    QGuiApplication app(argc, argv);
    const Mode mode = parseMode(argc, argv);

    QQuickView view;
    view.setResizeMode(QQuickView::SizeRootObjectToView);
    view.setTitle(QStringLiteral("Bench"));
    view.resize(800, 600);

    view.setSource(QUrl(QStringLiteral("qrc:/hello.qml")));
    if (view.status() == QQuickView::Error) {
        for (const auto &e : view.errors())
            std::fprintf(stderr, "%s\n", e.toString().toUtf8().constData());
        return 1;
    }

    bool painted = false;
    QObject::connect(&view, &QQuickWindow::frameSwapped, &app, [&] {
        if (painted) return;
        painted = true;
        const Clock::time_point now = Clock::now();
        printFirstFrame();
        if (mode == Mode::Startup) {
            printStartupAndExit(t0, now);
        }
    });

    view.show();
    return app.exec();
}
