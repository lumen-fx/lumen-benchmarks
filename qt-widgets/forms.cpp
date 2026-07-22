// Bench forms app - Qt6 Widgets variant: widget-dense settings page
// (~40 controls in 6 QGroupBoxes; shared spec in the repo README).
//
// --interact drives, per cycle: a 40-step focus walk (real Tab
// QKeyEvents posted to the focused widget, so the walk uses Qt's actual
// focus chain), then a 20-step toggle-all pass (toggle 8 checkboxes +
// 4 switch-standin checkboxes, advance both QButtonGroup radio groups
// through their 4 options - direct programmatic state changes, same as
// the other frameworks). One step per 16 ms of wall time; the footer
// status label changes every step so every step produces visible
// damage.
//
// Frame timestamps: Paint events on the footer status label. The label
// text changes on every interact step, so exactly the frames that
// contain step damage repaint it - one Paint per synced frame. (An
// UpdateRequest filter on the QWindow sees nothing under the Wayland
// backend; the label is the reliable per-frame marker.)
// First-presented-frame proxy: first paintEvent on the top-level
// widget, same as the other Qt apps.
//
// Equivalence caveat: Qt has no switch widget (QCheckBox stands in),
// and radio groups are one focus stop each in Qt's Tab order (arrow
// keys move within a group).

#include <QtWidgets>

#include <functional>
#include <vector>

#include "bench_common.h"

static constexpr double kStepS = 0.016;
static constexpr double kSettleS = 0.5;
static constexpr int kStepsPerCycle = 60; // 40 focus + 8 cb + 4 tg + 2x4 radio

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

// Records one timestamp per QEvent::Paint on the watched widget.
class FrameRecorder : public QObject {
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

static QWidget *labeled(const char *name, QWidget *control) {
    auto *rowW = new QWidget;
    auto *l = new QHBoxLayout(rowW);
    l->setContentsMargins(0, 0, 0, 0);
    l->setSpacing(12);
    auto *lab = new QLabel(QString::fromUtf8(name));
    lab->setFixedWidth(110);
    l->addWidget(lab);
    l->addWidget(control);
    l->addStretch();
    return rowW;
}

int main(int argc, char **argv) {
    const Clock::time_point t0 = Clock::now();

    QApplication app(argc, argv);
    const Mode mode = parseMode(argc, argv);
    const int cycles = interactCycles();

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

    // Form -----------------------------------------------------------
    std::vector<QLineEdit *> inputs;
    std::vector<QCheckBox *> checks;   // 8 labeled checkboxes
    std::vector<QCheckBox *> toggles;  // 4 switch stand-ins
    std::vector<QRadioButton *> radioA, radioB;
    int radioAIdx = 0, radioBIdx = 0;

    auto *form = new QWidget;
    auto *fv = new QVBoxLayout(form);
    fv->setContentsMargins(8, 8, 8, 8);
    fv->setSpacing(12);

    auto makeInput = [&](const char *ph, int width) {
        auto *e = new QLineEdit;
        e->setPlaceholderText(QString::fromUtf8(ph));
        e->setFixedWidth(width);
        inputs.push_back(e);
        return e;
    };
    auto makeCheck = [&](const char *label) {
        auto *c = new QCheckBox(QString::fromUtf8(label));
        checks.push_back(c);
        return c;
    };
    auto makeToggle = [&]() {
        auto *c = new QCheckBox; // Qt has no switch widget; see caveats
        toggles.push_back(c);
        return c;
    };
    auto makeSlider = [&]() {
        auto *s = new QSlider(Qt::Horizontal);
        s->setRange(0, 100);
        s->setValue(50);
        s->setFixedWidth(200);
        return s;
    };
    auto makeCombo = [&](std::initializer_list<const char *> opts) {
        auto *c = new QComboBox;
        for (const char *o : opts) c->addItem(QString::fromUtf8(o));
        return c;
    };
    auto makeRadioCol = [&](std::vector<QRadioButton *> &group,
                            std::initializer_list<const char *> names) {
        auto *col = new QWidget;
        auto *cl = new QVBoxLayout(col);
        cl->setContentsMargins(0, 0, 0, 0);
        cl->setSpacing(4);
        auto *bg = new QButtonGroup(col);
        bool first = true;
        for (const char *n : names) {
            auto *r = new QRadioButton(QString::fromUtf8(n));
            if (first) r->setChecked(true);
            first = false;
            bg->addButton(r);
            group.push_back(r);
            cl->addWidget(r);
        }
        return col;
    };
    auto makeGroup = [&](const char *tit, std::initializer_list<QWidget *> rows) {
        auto *g = new QGroupBox(QString::fromUtf8(tit));
        auto *gl = new QVBoxLayout(g);
        gl->setSpacing(8);
        for (QWidget *r : rows) gl->addWidget(r);
        fv->addWidget(g);
    };
    auto checkRow = [&](QCheckBox *a, QCheckBox *b) {
        auto *rw = new QWidget;
        auto *l = new QHBoxLayout(rw);
        l->setContentsMargins(0, 0, 0, 0);
        l->setSpacing(12);
        l->addWidget(a);
        l->addWidget(b);
        l->addStretch();
        return rw;
    };
    auto buttonRow = [&](const char *text) {
        auto *rw = new QWidget;
        auto *l = new QHBoxLayout(rw);
        l->setContentsMargins(0, 0, 0, 0);
        l->addWidget(new QPushButton(QString::fromUtf8(text)));
        l->addStretch();
        return rw;
    };

    makeGroup("Account",
              {labeled("Username:", makeInput("Username", 220)),
               labeled("Email:", makeInput("Email", 220)),
               checkRow(makeCheck("Remember me"),
                        makeCheck("Subscribe to newsletter")),
               buttonRow("Sign out")});
    makeGroup("Appearance",
              {labeled("Theme:", makeRadioCol(radioA, {"System", "Light", "Dark",
                                                       "High contrast"})),
               labeled("Font size:", makeSlider()),
               labeled("Density:", makeCombo({"Compact", "Cozy", "Normal",
                                              "Comfortable", "Spacious"})),
               labeled("Animations:", makeToggle())});
    makeGroup("Network",
              {labeled("Proxy host:", makeInput("proxy.example.com", 220)),
               labeled("Proxy port:", makeInput("8080", 100)),
               checkRow(makeCheck("Use proxy"),
                        makeCheck("Verify TLS certificates")),
               labeled("Timeout:", makeSlider()),
               labeled("Protocol:", makeCombo({"Auto", "HTTP/1.1", "HTTP/2",
                                               "HTTP/3", "SOCKS5"})),
               buttonRow("Test connection")});
    makeGroup("Editor",
              {labeled("Font family:", makeInput("monospace", 220)),
               labeled("Tab width:", makeInput("4", 100)),
               checkRow(makeCheck("Word wrap"), makeCheck("Line numbers")),
               labeled("Line endings:", makeCombo({"Auto", "LF", "CRLF", "CR",
                                                   "Keep mixed"})),
               labeled("Rulers:", makeSlider()),
               labeled("Autosave:", makeToggle())});
    makeGroup("Privacy",
              {labeled("Telemetry:",
                       makeRadioCol(radioB, {"Off", "Crash reports only",
                                             "Basic", "Full"})),
               checkRow(makeCheck("Upload crash reports"),
                        makeCheck("Share usage statistics")),
               labeled("Do not track:", makeToggle()),
               buttonRow("Clear data")});
    makeGroup("Advanced",
              {labeled("Config path:", makeInput("~/.config/bench", 220)),
               labeled("Log filter:", makeInput("info", 220)),
               labeled("Log level:", makeCombo({"Error", "Warn", "Info", "Debug",
                                                "Trace"})),
               labeled("Cache size:", makeSlider()),
               labeled("Experimental:", makeToggle()),
               buttonRow("Reset all")});
    fv->addStretch();

    auto *scroll = new QScrollArea;
    scroll->setWidget(form);
    scroll->setWidgetResizable(true);
    scroll->setFrameShape(QFrame::NoFrame);
    scroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);

    // Footer ---------------------------------------------------------
    auto *footer = new QWidget;
    footer->setFixedHeight(32);
    auto *fl = new QHBoxLayout(footer);
    fl->setContentsMargins(8, 4, 8, 4);
    fl->setSpacing(8);
    auto *status = new QLabel(QStringLiteral("idle"));
    auto *themeLabel = new QLabel(QStringLiteral("theme: System"));
    auto *telemetryLabel = new QLabel(QStringLiteral("telemetry: Off"));
    for (QLabel *l : {status, themeLabel, telemetryLabel})
        l->setStyleSheet(QStringLiteral("color: #777777;"));
    fl->addWidget(status);
    fl->addWidget(themeLabel);
    fl->addWidget(telemetryLabel);
    fl->addStretch();

    outer->addWidget(header);
    outer->addWidget(scroll, 1);
    outer->addWidget(footer);

    // Interact driver ------------------------------------------------
    auto *recorder = new FrameRecorder;

    auto *stepTimer = new QTimer(&w);
    stepTimer->setTimerType(Qt::PreciseTimer);
    stepTimer->setInterval(4);
    Clock::time_point started{};
    bool startedSet = false;
    qint64 stepDone = 0;
    const qint64 totalSteps = qint64(kStepsPerCycle) * cycles;

    auto applyStep = [&](qint64 step) {
        status->setText(QStringLiteral("step %1").arg(step));
        const qint64 inCycle = step % kStepsPerCycle;
        if (inCycle < 40) {
            QWidget *f = QApplication::focusWidget();
            if (!f) {
                inputs[0]->setFocus(Qt::OtherFocusReason);
                return;
            }
            QApplication::postEvent(
                f, new QKeyEvent(QEvent::KeyPress, Qt::Key_Tab, Qt::NoModifier));
            QApplication::postEvent(
                f, new QKeyEvent(QEvent::KeyRelease, Qt::Key_Tab, Qt::NoModifier));
            return;
        }
        const qint64 t = inCycle - 40;
        if (t <= 7) {
            checks[t]->toggle();
        } else if (t <= 11) {
            toggles[t - 8]->toggle();
        } else if (t <= 15) {
            radioAIdx = (radioAIdx + 1) % 4;
            radioA[radioAIdx]->setChecked(true);
            themeLabel->setText(QStringLiteral("theme: %1").arg(radioA[radioAIdx]->text()));
        } else {
            radioBIdx = (radioBIdx + 1) % 4;
            radioB[radioBIdx]->setChecked(true);
            telemetryLabel->setText(
                QStringLiteral("telemetry: %1").arg(radioB[radioBIdx]->text()));
        }
    };

    bool reported = false;
    QObject::connect(stepTimer, &QTimer::timeout, [&] {
        if (reported) return;
        const Clock::time_point now = Clock::now();
        if (!startedSet) {
            started = now;
            startedSet = true;
            recorder->recording = true;
            return;
        }
        const double el = std::chrono::duration<double>(now - started).count();
        qint64 due = (qint64)(el / kStepS);
        if (due > totalSteps) due = totalSteps;
        while (stepDone < due) {
            applyStep(stepDone);
            ++stepDone;
        }
        if (stepDone >= totalSteps) {
            stepTimer->stop();
            recorder->recording = false;
            // Stay alive for the post-run memory sample.
            printDeltasDone(recorder->frames);
            reported = true;
        }
    });

    w.onFirstPaint = [&, t0, mode] {
        const Clock::time_point now = Clock::now();
        printFirstFrame();
        if (mode == Mode::Startup) {
            printStartupAndExit(t0, now);
        }
        if (mode == Mode::Interact) {
            // Frame timestamps: Paint events on the per-step status label.
            status->installEventFilter(recorder);
            inputs[0]->setFocus(Qt::OtherFocusReason);
            QTimer::singleShot(int(kSettleS * 1000), &w,
                               [stepTimer] { stepTimer->start(); });
        }
    };

    w.show();
    return app.exec();
}
