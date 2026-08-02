// Bench forms app - Qt Quick variant: scrollable settings page (~40
// controls in 6 GroupBoxes; shared spec in the repo README), built from
// QtQuick.Controls.Basic so the controls paint through the scene graph
// rather than a native style.
//
// --interact drives, per cycle: a 40-step focus walk (real Tab QKeyEvents
// posted to the QQuickWindow, which advances the same focus chain the
// window uses for real keyboard input), then a 20-step toggle-all pass
// (toggle 8 checkboxes + 4 switches, advance both radio ButtonGroups
// through their 4 options - direct property writes, same as the other
// frameworks). One step per 16 ms of wall time; the footer status label
// changes every step so every step produces visible damage.
//
// Frame timestamps: every QQuickWindow::frameSwapped while recording.
// Unlike qt-widgets (whose raster QWindow emits no UpdateRequest under
// Wayland, forcing a paint-event filter on one label as the per-frame
// marker), the Quick scene graph's frameSwapped fires reliably for every
// presented frame regardless of backend, so no such workaround is needed.
// First-presented-frame proxy: QQuickWindow::frameSwapped, same as every
// other app here.
//
// Equivalence note: unlike Qt Widgets (no switch widget, QCheckBox stands
// in), QtQuick.Controls has a real Switch, used here directly. Radio
// groups are exposed to C++ as plain RadioButton objects grouped by a QML
// ButtonGroup, matching Qt's own exclusive-group semantics.

#include <QGuiApplication>
#include <QQuickView>
#include <QQuickWindow>
#include <QQuickItem>
#include <QCoreApplication>
#include <QKeyEvent>
#include <QMetaObject>
#include <QTimer>
#include <QUrl>
#include <QVariant>

#include <cstdio>
#include <vector>

#include "bench_common.h"

static constexpr double kStepS = 0.016;
static constexpr double kSettleS = 0.5;
static constexpr int kStepsPerCycle = 60; // 40 focus + 8 cb + 4 tg + 2x4 radio

int main(int argc, char **argv) {
    const Clock::time_point t0 = Clock::now();

    QGuiApplication app(argc, argv);
    const Mode mode = parseMode(argc, argv);
    const int cycles = interactCycles();

    QQuickView view;
    view.setResizeMode(QQuickView::SizeRootObjectToView);
    view.setTitle(QStringLiteral("Bench"));
    view.resize(800, 600);

    view.setSource(QUrl(QStringLiteral("qrc:/forms.qml")));
    if (view.status() == QQuickView::Error) {
        for (const auto &e : view.errors())
            std::fprintf(stderr, "%s\n", e.toString().toUtf8().constData());
        return 1;
    }

    QObject *root = view.rootObject();
    QQuickItem *firstInput =
        root->findChild<QQuickItem *>(QStringLiteral("input0"));
    QObject *status = root->findChild<QObject *>(QStringLiteral("status"));
    QObject *themeLabel =
        root->findChild<QObject *>(QStringLiteral("themeLabel"));
    QObject *telemetryLabel =
        root->findChild<QObject *>(QStringLiteral("telemetryLabel"));

    std::vector<QObject *> checks, toggles, radioA, radioB;
    for (int i = 0; i < 8; ++i)
        checks.push_back(
            root->findChild<QObject *>(QStringLiteral("check%1").arg(i)));
    for (int i = 0; i < 4; ++i)
        toggles.push_back(
            root->findChild<QObject *>(QStringLiteral("toggle%1").arg(i)));
    for (int i = 0; i < 4; ++i)
        radioA.push_back(
            root->findChild<QObject *>(QStringLiteral("radioA%1").arg(i)));
    for (int i = 0; i < 4; ++i)
        radioB.push_back(
            root->findChild<QObject *>(QStringLiteral("radioB%1").arg(i)));

    int radioAIdx = 0, radioBIdx = 0;

    std::vector<Clock::time_point> frames;
    bool recording = false;

    auto applyStep = [&](long long step) {
        if (status) status->setProperty("text", QStringLiteral("step %1").arg(step));
        const long long inCycle = step % kStepsPerCycle;
        if (inCycle < 40) {
            if (!view.activeFocusItem()) {
                if (firstInput)
                    QMetaObject::invokeMethod(firstInput, "forceActiveFocus");
                return;
            }
            QCoreApplication::postEvent(
                &view, new QKeyEvent(QEvent::KeyPress, Qt::Key_Tab, Qt::NoModifier));
            QCoreApplication::postEvent(
                &view, new QKeyEvent(QEvent::KeyRelease, Qt::Key_Tab, Qt::NoModifier));
            return;
        }
        const long long t = inCycle - 40;
        if (t <= 7) {
            QObject *c = checks[(size_t)t];
            if (c) c->setProperty("checked", !c->property("checked").toBool());
        } else if (t <= 11) {
            QObject *tg = toggles[(size_t)(t - 8)];
            if (tg) tg->setProperty("checked", !tg->property("checked").toBool());
        } else if (t <= 15) {
            radioAIdx = (radioAIdx + 1) % 4;
            QObject *r = radioA[(size_t)radioAIdx];
            if (r) {
                r->setProperty("checked", true);
                if (themeLabel)
                    themeLabel->setProperty(
                        "text", QStringLiteral("theme: %1")
                                    .arg(r->property("text").toString()));
            }
        } else {
            radioBIdx = (radioBIdx + 1) % 4;
            QObject *r = radioB[(size_t)radioBIdx];
            if (r) {
                r->setProperty("checked", true);
                if (telemetryLabel)
                    telemetryLabel->setProperty(
                        "text", QStringLiteral("telemetry: %1")
                                    .arg(r->property("text").toString()));
            }
        }
    };

    QTimer stepTimer;
    stepTimer.setTimerType(Qt::PreciseTimer);
    stepTimer.setInterval(4);
    Clock::time_point started{};
    bool startedSet = false;
    long long stepDone = 0;
    const long long totalSteps = (long long)kStepsPerCycle * cycles;
    bool reported = false;

    QObject::connect(&stepTimer, &QTimer::timeout, [&] {
        if (reported) return;
        const Clock::time_point now = Clock::now();
        if (!startedSet) {
            started = now;
            startedSet = true;
            recording = true;
            return;
        }
        const double el = std::chrono::duration<double>(now - started).count();
        long long due = (long long)(el / kStepS);
        if (due > totalSteps) due = totalSteps;
        while (stepDone < due) {
            applyStep(stepDone);
            ++stepDone;
        }
        if (stepDone >= totalSteps) {
            stepTimer.stop();
            recording = false;
            // Stay alive for the post-run memory sample.
            printDeltasDone(frames);
            reported = true;
        }
    });

    bool painted = false;
    QObject::connect(&view, &QQuickWindow::frameSwapped, &app, [&] {
        const Clock::time_point now = Clock::now();
        if (!painted) {
            painted = true;
            printFirstFrame();
            if (mode == Mode::Startup) {
                printStartupAndExit(t0, now);
            }
            if (mode == Mode::Interact) {
                if (firstInput)
                    QMetaObject::invokeMethod(firstInput, "forceActiveFocus");
                QTimer::singleShot(int(kSettleS * 1000), &app,
                                   [&stepTimer] { stepTimer.start(); });
            }
        }
        if (recording) {
            frames.push_back(now);
        }
    });

    view.show();
    return app.exec();
}
