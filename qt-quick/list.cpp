// Bench list app - Qt Quick variant. See repo README for the shared spec
// (header + 10k-row virtualized list + footer).
//
// List: QML ListView bound to a C++ QAbstractListModel (BenchListModel,
// same row data as qt-widgets' BenchModel) - the idiomatic Quick
// virtualized path, per-pixel scrolling via `contentY` (ListView
// instantiates only the on-screen delegates, same virtualization
// guarantee QListView gives Qt Widgets).
// First-presented-frame proxy: QQuickWindow::frameSwapped.
// Scroll-bench frame timestamps: every frameSwapped while a 16 ms timer
// drives the ListView's `contentY` from wall-clock elapsed time (the
// same bounce() drive qt-widgets uses on its QScrollBar).

#include <QGuiApplication>
#include <QQuickView>
#include <QQuickWindow>
#include <QQuickItem>
#include <QQmlContext>
#include <QAbstractListModel>
#include <QTimer>
#include <QUrl>
#include <QVariant>

#include <algorithm>
#include <cstdio>

#include "bench_common.h"

static constexpr int kRows = 10000;
static constexpr double kSpeed = 1000.0; // px/s

class BenchListModel : public QAbstractListModel {
public:
    enum Roles { TitleRole = Qt::UserRole + 1, SubtitleRole };
    using QAbstractListModel::QAbstractListModel;

    int rowCount(const QModelIndex &parent = QModelIndex()) const override {
        return parent.isValid() ? 0 : kRows;
    }
    QVariant data(const QModelIndex &idx, int role) const override {
        if (!idx.isValid()) return {};
        if (role == TitleRole) return QStringLiteral("Item %1").arg(idx.row());
        if (role == SubtitleRole)
            return QStringLiteral("subtitle %1").arg(idx.row());
        return {};
    }
    QHash<int, QByteArray> roleNames() const override {
        return {{TitleRole, "title"}, {SubtitleRole, "subtitle"}};
    }
};

int main(int argc, char **argv) {
    const Clock::time_point t0 = Clock::now();

    QGuiApplication app(argc, argv);
    const Mode mode = parseMode(argc, argv);
    const bool modeStartup = (mode == Mode::Startup);
    const bool modeScroll = (mode == Mode::ScrollBench);
    const double durationS = scrollSeconds();

    BenchListModel model;

    QQuickView view;
    view.setResizeMode(QQuickView::SizeRootObjectToView);
    view.setTitle(QStringLiteral("Bench"));
    view.resize(800, 600);
    view.rootContext()->setContextProperty("benchListModel", &model);

    view.setSource(QUrl(QStringLiteral("qrc:/list.qml")));
    if (view.status() == QQuickView::Error) {
        for (const auto &e : view.errors())
            std::fprintf(stderr, "%s\n", e.toString().toUtf8().constData());
        return 1;
    }

    QQuickItem *listItem =
        view.rootObject()->findChild<QQuickItem *>(QStringLiteral("benchList"));

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
        if (listItem) {
            const double maxY = std::max(
                0.0, listItem->property("contentHeight").toReal() -
                         listItem->property("height").toReal());
            listItem->setProperty("contentY", bounce(kSpeed * elapsed, maxY));
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
