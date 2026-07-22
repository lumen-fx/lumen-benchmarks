# Cross-framework benchmark results

Generated: 2026-07-22 18:27:02 +0000  
Host: arch · kernel 7.1.3-arch1-2 · 12th Gen Intel(R) Core(TM) i9-12900K (24 cpus)  
Governors: powersave · governor pin: not permitted (wanted 'performance'; left as-is on cpus [4, 5, 6, 7, 8, 9, 10, 11]) · app cpus [4, 5, 6, 7, 8, 9, 10, 11]  
Mesa: mesa 1:26.1.4-1 · display: weston (nested headless) · Lumen: 93088f1f5d27 (dirty)

Primary numbers below are **round 0**; the run-to-run agreement table compares round 0 vs round 1. Values are medians; ± is half the IQR (startup, n=15) or half the cross-pass spread (frame percentiles, 3 passes). ⚠ = unstable (IQR/median > 5%); (No) = N Tukey outliers retained. Memory is PSS in MiB with RSS in parentheses (both from /proc, idle = first frame + 2 s).

## hello - startup floor, baseline memory, binary size

| framework | version | binary (stripped) | startup ext ms | startup self ms | PSS idle MiB (RSS) | PSS @5 s |
|---|---|---|---|---|---|---|
| lumen | git 93088f1 | 20.0 MiB rt +0.7 KiB app | 73.2 ±5.9 ⚠ | - | 67.3 (182.4) | 67.4 (182.4) |
| slint | slint 1.17.1 | 19.4 MiB | - | - | - | - |
| egui | eframe 0.35.0 | 18.8 MiB | - | - | - | - |
| iced | iced 0.13.1 | 14.2 MiB | - | - | - | - |
| qt-widgets | Qt6Widgets 6.11.1 | 0.2 MiB | - | - | - | - |
| gtk4 | gtk4 4.22.4 | 0.0 MiB | 125.6 ±3.6 ⚠ (1o) | 102.0 ±2.4 | 104.8 (225.5) | 104.8 (225.5) |

## forms - ~40-widget settings page

Interact pass = 4 cycles x (40-step focus walk + 20-step toggle-all), one step per 16 ms; frame-interval percentiles over the pass.

| framework | binary | startup ext ms | interact p50 ms | interact p95 ms | interact p99 ms | PSS idle (RSS) | PSS post |
|---|---|---|---|---|---|---|---|
| lumen | 20.0 MiB rt +9.3 KiB app | 69.8 ±5.8 ⚠ | 15.57 ±0.02 | 16.85 ±0.07 | 17.13 ±0.05 | 77.3 (187.6) | 79.9 (191.4) |
| slint | 23.6 MiB | 119.6 ±11.9 ⚠ (1o) | 16.60 ±0.17 | 22.92 ±0.27 | 24.32 ±0.68 | 80.3 (188.9) | 83.8 (193.0) |
| egui | 19.1 MiB | 83.8 ±8.5 ⚠ (2o) | 16.67 ±0.00 | 16.74 ±0.01 | 16.78 ±0.01 | 84.7 (191.2) | 83.8 (190.1) |
| iced | 14.5 MiB | 106.2 ±5.9 ⚠ (1o) | 16.00 ±0.00 | 20.01 ±0.00 | 20.02 ±0.02 | 66.5 (170.2) | 65.5 (170.1) |
| qt-widgets | 0.3 MiB | 35.1 ±6.1 ⚠ | 15.79 ±0.05 | 16.94 ±1.38 | 19.74 ±1.33 | 24.7 (41.9) | 25.7 (43.9) |
| gtk4 | 0.0 MiB | 142.2 ±5.5 ⚠ | 16.68 ±0.01 | 19.69 ±0.32 | 20.88 ±0.45 | 108.9 (231.7) | 112.5 (235.5) |

## list - 10,000-row list scrolled at 1000 px/s

| framework | binary | startup ext ms | scroll p50 ms | scroll p95 ms | scroll p99 ms | PSS idle (RSS) | PSS post |
|---|---|---|---|---|---|---|---|
| lumen | 20.0 MiB rt +2.4 KiB app | 86.4 ±4.9 ⚠ | 16.54 ±0.01 | 17.52 ±0.01 | 17.94 ±0.21 | 92.8 (203.1) | 88.0 (203.1) |
| slint | 22.3 MiB | - | - | - | - | - | - |
| egui | 19.0 MiB | - | - | - | - | - | - |
| iced | 14.4 MiB | - | - | - | - | - | - |
| qt-widgets | 0.3 MiB | - | - | - | - | - | - |
| gtk4 | 0.0 MiB | - | - | - | - | - | - |

## textview - 5,000 wrapped paragraphs (~1.1 MiB) scrolled at 1000 px/s

| framework | binary | startup ext ms | scroll p50 ms | scroll p95 ms | scroll p99 ms | PSS idle (RSS) | PSS post |
|---|---|---|---|---|---|---|---|
| lumen | 20.0 MiB rt +1367.8 KiB app | 1346.6 ±4.2 (2o) | 16.68 ±0.04 | 18.51 ±0.15 | 19.50 ±0.14 | 120.9 (231.4) | 121.3 (231.6) |
| slint | 19.3 MiB | 1152.8 ±4.9 | 194.92 ±0.66 | 196.84 ±1.44 | 197.97 ±0.69 | 365.5 (472.2) | 373.0 (479.7) |
| egui | 18.8 MiB | 281.0 ±3.2 (1o) | 16.66 ±0.00 | 16.75 ±0.01 | 16.78 ±0.01 | 287.1 (391.2) | 287.3 (391.3) |
| iced | 14.2 MiB | 1027.2 ±5.7 (3o) | 350.85 ±2.15 | 358.17 ±0.49 | 359.13 ±0.76 | 383.5 (488.0) | 383.8 (488.3) |
| qt-widgets | 0.3 MiB | 28.7 ±0.7 (3o) | 15.82 ±0.03 | 16.76 ±0.01 | 27.39 ±0.22 | 91.3 (109.4) | 91.4 (109.5) |
| gtk4 | 0.0 MiB | 147.2 ±7.4 ⚠ | 16.75 ±0.08 | 20.02 ±0.28 | 21.67 ±0.69 | 100.5 (227.5) | 105.5 (232.7) |

### Clock sources

| framework | first-frame proxy | frame timestamps | clock |
|---|---|---|---|
| lumen | MCP frame counter >= 1, sampled every 0.5 ms | reconstructed from MCP frame counter (0.5 ms sampling) | harness CLOCK_MONOTONIC |
| slint | rendering notifier `AfterRendering` (frame submitted) | rendering notifier | `std::time::Instant` (CLOCK_MONOTONIC) |
| egui | end of first `App::update` pass | top of every update pass | `std::time::Instant` (CLOCK_MONOTONIC) |
| iced | first `window::frames()` delivery | `window::frames()` deliveries | `std::time::Instant` (CLOCK_MONOTONIC) |
| qt-widgets | first `paintEvent` on the top-level widget | list/textview: viewport Paint events; forms: `UpdateRequest` on the QWindow (one per backing-store sync) | `std::chrono::steady_clock` (CLOCK_MONOTONIC) |
| gtk4 | GdkFrameClock `after-paint` | GdkFrameClock `after-paint` | `g_get_monotonic_time` (CLOCK_MONOTONIC) |

The harness itself timestamps with Python `time.monotonic()`
(CLOCK_MONOTONIC). Every clock in the table is the same kernel clock, so
cross-source skew is scheduling/pipe latency, bounded by the calibration
section.

## Fairness / equivalence caveats

Same app specs everywhere (800x600 "Bench" window, release builds,
stripped binaries):

* **hello** - one bold "Hello" label + one "Press" button, centered.
* **list** - header (bold title + count button), 10,000-row list
  (bold "Item {i}" + grey "subtitle {i}", 36 px rows), footer (text
  input + 0-100 slider + value label).
* **forms** - header, scrollable settings page: 6 groups, ~40 controls
  (8 text inputs, 8 checkboxes, 4 switches, 2 radio groups x 4, 4
  sliders, 4 dropdowns, 6 buttons), footer status labels that change on
  every interact step.
* **textview** - header + the shared deterministic corpus (5,000
  paragraphs, ~1.1 MiB) word-wrapped in the framework's idiomatic
  long-document widget, scrolled at 1000 px/s.

Known asymmetries - read before quoting numbers:

* **Lumen** runs via `lumenc run --headless` (its own offscreen wgpu
  pipeline, demand-driven, no compositor and no vsync), while the other
  five run windowed under a nested headless compositor with their normal
  present paths. Lumen startup includes compiling the `.lmn/.css/.rhai`
  sources (that is how Lumen apps launch today). Lumen's size row is the
  generic `lumenc` runtime plus a few KB of app text. Lumen has no
  in-app per-frame callback by design, so all Lumen numbers are external:
  the MCP frame counter is sampled every 0.5 ms over a persistent
  connection (reading it does not wake the parked loop; only injected
  events do). Frame intervals are therefore quantized at ~0.5 ms, and
  Lumen's demand-driven loop has no compositor vsync: frames land
  against a 16.7 ms deadline anchor, so sub-16.7 p50 readings mean early
  frames, not faster rendering - p95/p99 are the honest cross-framework
  comparison. Scroll is driven by injected wheel events at ~60 Hz x
  16.7 px (sensitivity 1.0, inertia 0 -> 1 wheel px = 1 scroll px).
  The interact pass differs structurally: Tab focus-walk uses real key
  events (like Qt/Slint), but Lumen has no externally reachable state
  setter, so toggle steps scroll the control into view and click it -
  real input-pipeline work (hit-testing, scrolling) that the other
  frameworks' direct state writes do not perform. Lumen's interact
  numbers are therefore an upper bound.
* **iced** has no virtualized list widget: the 10k rows are a plain
  `Column` in a `scrollable`, rebuilt every view pass - idiomatic iced,
  inherently disadvantaged on the list workload and honestly so. Under
  the headless compositor iced's redraw loop is not vsync-throttled
  (~7 ms deltas): its scroll numbers measure raw redraw throughput, not
  presentation cadence. Its textview lays out the full corpus each pass.
* **egui** is immediate-mode: the whole UI re-lays-out every frame by
  design. Its textview shapes the document into one cached galley
  (cache keyed by text+width), so scrolling costs cache lookup +
  visible-region tessellation. Focus-walk steps use
  `Memory::request_focus` (egui has no synthetic-key path); each radio
  is its own focus stop. No switch widget (checkbox stands in).
* **Qt** raster widget painting is synchronous and not vsync-locked, so
  the 16 ms drive timer sets the paint cadence for scroll passes; delta
  spikes above 16 ms still expose jank. Scrollbar values are integers
  (whole-pixel scroll motion). Radio groups are one Tab stop each
  (arrow keys move within a group), so its 40-step focus walk cycles
  the chain more often. No switch widget (QCheckBox stands in).
  textview uses read-only QTextEdit (lazy document layout).
* **Slint** frame timestamps are `AfterRendering` (submitted, not
  presented); scroll/step driving uses 8/4 ms timers rather than a
  per-frame callback. std-widgets has no RadioButton: radio groups are
  exclusive CheckBoxes (each its own Tab stop). Its textview lays the
  whole corpus out as one Text item (no virtualization).
* **GTK4** timestamps are GdkFrameClock "after-paint" (frame handed to
  the compositor, not presented). Its radio groups are grouped
  GtkCheckButtons (GTK4's radio primitive). textview uses GtkTextView
  (lazy layout around the viewport).
* Binary sizes are not comparable across linkage models: the Rust apps
  statically link their framework; **Qt** and **GTK4** sizes exclude
  the dynamically linked toolkit libraries (libQt6*/libgtk-4). Lumen's
  size is a generic runtime, not an app-specific link.
* Startup runs are warm-cache (one discarded warmup run per cell; no
  page-cache eviction between runs). The optional `--cold` mode evicts
  file-backed pages of the binary + linked libraries + data before each
  run via posix_fadvise - labeled *partial* cold: anonymous pages,
  compositor state, and anything another process keeps mapped stay warm.
  No default results use it.
* startup(external) includes the harness's spawn overhead identically
  for every framework - quantified in the calibration section.
  startup(self) starts at the first line of main, so external-self =
  fork/exec + dynamic linking + pre-main init (not available for Lumen).

