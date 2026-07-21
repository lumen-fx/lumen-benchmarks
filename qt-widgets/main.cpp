// Bench app - Qt6 Widgets variant. See repo README for the shared spec.
//
// List: QListView + QAbstractListModel + QStyledItemDelegate (the
// idiomatic virtualized path), per-pixel scrolling.
// First-presented-frame proxy: first paintEvent hit on the top-level
// widget (raster QWidget windows do not emit QWindow::frameSwapped).
// Scroll-bench frame timestamps: paint events on the list viewport,
// captured with an event filter, while an 8 ms QTimer drives the
// vertical scrollbar from wall-clock elapsed time.

#include <QtWidgets>

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <functional>
#include <vector>

using Clock = std::chrono::steady_clock;

static constexpr int kRows = 10000;
static constexpr int kRowH = 36;
static constexpr double kSpeed = 1000.0; // px/s
static constexpr double kDurationS = 10.0;

static double bounce(double dist, double max) {
    if (max <= 0.0) return 0.0;
    const double period = 2.0 * max;
    double m = std::fmod(dist, period);
    return m < max ? m : period - m;
}

static double msBetween(Clock::time_point a, Clock::time_point b) {
    return std::chrono::duration<double, std::milli>(b - a).count();
}

class BenchModel : public QAbstractListModel {
public:
    using QAbstractListModel::QAbstractListModel;
    int rowCount(const QModelIndex &parent = QModelIndex()) const override {
        return parent.isValid() ? 0 : kRows;
    }
    QVariant data(const QModelIndex &idx, int role) const override {
        if (!idx.isValid()) return {};
        if (role == Qt::DisplayRole)
            return QStringLiteral("Item %1").arg(idx.row());
        if (role == Qt::UserRole)
            return QStringLiteral("subtitle %1").arg(idx.row());
        return {};
    }
};

class BenchDelegate : public QStyledItemDelegate {
public:
    using QStyledItemDelegate::QStyledItemDelegate;
    void paint(QPainter *p, const QStyleOptionViewItem &opt,
               const QModelIndex &idx) const override {
        p->save();
        const QRect r = opt.rect.adjusted(8, 0, 0, 0);
        QFont bold = opt.font;
        bold.setBold(true);
        p->setFont(bold);
        QRect used;
        p->drawText(r, Qt::AlignVCenter | Qt::AlignLeft,
                    idx.data(Qt::DisplayRole).toString(), &used);
        p->setFont(opt.font);
        p->setPen(QColor(0x77, 0x77, 0x77));
        p->drawText(r.adjusted(used.width() + 12, 0, 0, 0),
                    Qt::AlignVCenter | Qt::AlignLeft,
                    idx.data(Qt::UserRole).toString());
        p->restore();
    }
    QSize sizeHint(const QStyleOptionViewItem &,
                   const QModelIndex &) const override {
        return QSize(0, kRowH);
    }
};

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
    QString mode;
    if (argc > 1) mode = QString::fromLocal8Bit(argv[1]);
    const bool modeStartup = (mode == QLatin1String("--startup"));
    const bool modeScroll = (mode == QLatin1String("--scroll-bench"));

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
    hl->setSpacing(12);
    auto *title = new QLabel(QStringLiteral("Bench"));
    QFont titleFont = title->font();
    titleFont.setBold(true);
    titleFont.setPixelSize(18);
    title->setFont(titleFont);
    auto *countBtn = new QPushButton(QStringLiteral("Count: 0"));
    int count = 0;
    QObject::connect(countBtn, &QPushButton::clicked, [countBtn, &count] {
        countBtn->setText(QStringLiteral("Count: %1").arg(++count));
    });
    hl->addWidget(title);
    hl->addStretch();
    hl->addWidget(countBtn);

    // List -----------------------------------------------------------
    auto *list = new QListView;
    auto *model = new BenchModel(list);
    list->setModel(model);
    list->setItemDelegate(new BenchDelegate(list));
    list->setUniformItemSizes(true);
    list->setVerticalScrollMode(QAbstractItemView::ScrollPerPixel);
    list->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    list->setSelectionMode(QAbstractItemView::NoSelection);
    list->setFrameShape(QFrame::NoFrame);

    // Footer ---------------------------------------------------------
    auto *footer = new QWidget;
    footer->setFixedHeight(56);
    auto *fl = new QHBoxLayout(footer);
    fl->setContentsMargins(8, 8, 8, 8);
    fl->setSpacing(12);
    auto *input = new QLineEdit;
    input->setPlaceholderText(QStringLiteral("Type here..."));
    input->setFixedWidth(240);
    auto *sliderW = new QSlider(Qt::Horizontal);
    sliderW->setRange(0, 100);
    sliderW->setValue(50);
    sliderW->setFixedWidth(200);
    auto *sliderLabel = new QLabel(QStringLiteral("50"));
    QObject::connect(sliderW, &QSlider::valueChanged, [sliderLabel](int v) {
        sliderLabel->setText(QString::number(v));
    });
    fl->addWidget(input);
    fl->addWidget(sliderW);
    fl->addWidget(sliderLabel);
    fl->addStretch();

    outer->addWidget(header);
    outer->addWidget(list, 1);
    outer->addWidget(footer);

    // Instrumentation ------------------------------------------------
    auto *recorder = new PaintRecorder;
    list->viewport()->installEventFilter(recorder);

    // 16 ms: raster QWidget painting is synchronous and not vsync-locked,
    // so the drive timer sets the paint cadence; 16 ms matches the ~60 Hz
    // presentation cadence the other frameworks are throttled to.
    auto *scrollTimer = new QTimer(&w);
    scrollTimer->setTimerType(Qt::PreciseTimer);
    scrollTimer->setInterval(16);
    Clock::time_point scrollStart;

    QObject::connect(scrollTimer, &QTimer::timeout,
                     [list, recorder, scrollTimer, &scrollStart] {
        const double elapsed =
            std::chrono::duration<double>(Clock::now() - scrollStart).count();
        if (elapsed >= kDurationS) {
            scrollTimer->stop();
            recorder->recording = false;
            QString out;
            for (size_t i = 1; i < recorder->frames.size(); ++i)
                out += QString::number(
                           msBetween(recorder->frames[i - 1],
                                     recorder->frames[i]),
                           'f', 3) +
                       QLatin1Char('\n');
            out += QLatin1String("done\n");
            std::fputs(out.toUtf8().constData(), stdout);
            std::fflush(stdout);
            std::exit(0);
        }
        auto *bar = list->verticalScrollBar();
        bar->setValue(
            (int)std::lround(bounce(kSpeed * elapsed, bar->maximum())));
    });

    w.onFirstPaint = [t0, modeStartup, modeScroll, recorder, scrollTimer,
                      &scrollStart] {
        const Clock::time_point now = Clock::now();
        std::puts("first_frame");
        std::fflush(stdout);
        if (modeStartup) {
            std::printf("startup_ms: %.3f\n", msBetween(t0, now));
            std::fflush(stdout);
            std::exit(0);
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
