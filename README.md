# lumen-benchmarks

The same GUI app implemented in eight frameworks and measured the same
way, so the numbers compare like with like. The app, the workloads, and
the measurement method are identical across frameworks; the per-framework
differences that remain are listed as caveats in `results.md`.

| dir | framework | notes |
|---|---|---|
| `lumen/` | Lumen (`.lmn` + CSS + Rhai) | run by `lumenc` from the Lumen repo |
| `slint/` | Slint 1.x, winit backend | `ListView` (virtualized) |
| `egui/` | eframe (latest) | `ScrollArea::show_rows` (virtualized) |
| `iced/` | iced 0.13 | plain `Column` in `scrollable` (iced has no virtualized list) |
| `qt-widgets/` | Qt6 Widgets, C++17 | `QListView` + `QAbstractListModel` (virtualized) |
| `gtk4/` | GTK4, C | `GtkListView` + `GtkStringList` factory (virtualized) |
| `flutter/` | Flutter (Dart, Impeller/Skia engine) | `ListView.builder` (virtualized); own renderer, not the system toolkit |
| `tauri/` | Tauri 2 (Rust shell + system webkit2gtk webview) | hand-rolled windowed/virtualized DOM list; UI is HTML/JS/CSS in a browser engine |

The GTK variant is plain C (chosen over the gtk4-rs bindings to keep the
build light and match the reference C API directly). Flutter renders with
its own engine (Impeller/Skia), so its window is a single engine surface,
not native widgets; this is the closest analogue to Lumen's own-renderer
model. Tauri renders in the system webkit2gtk webview: a browser engine
shipped as a shared library (like Qt/GTK's toolkit), driving real DOM.
Both honor the same CLI contract and are measured by the same
framework-neutral spawn -> `first_frame` path as the native apps. See the
fairness caveats in `results.md` (webview `performance.now()` is
1 ms-clamped; Flutter/Tauri size rows exclude their engine/toolkit shared
libs; Tauri PSS discounts pages shared with other WebKit users).

## The app

800x600 window titled "Bench":

* header: bold label **Bench** + a `Count: N` button that increments on click
* a scrollable list of **10,000 rows**; each row is one 36 px line:
  bold `Item {i}`, then grey `subtitle {i}` (12 px gap, 8 px left pad)
* footer: single-line text input (placeholder `Type here...`) +
  a 0-100 slider (start 50) with its value in an adjacent label

CLI modes (identical semantics in every implementation):

* `--startup`: print `startup_ms: <float>` (first line of `main` to
  first-presented-frame callback) and exit
* `--scroll-bench`: from the first frame, animate the list scroll at
  1000 px/s (bouncing at the ends) for `$BENCH_SCROLL_SECONDS` (the
  harness sets it; 6 s per pass), then print one frame delta (ms) per
  line and `done`
* `--interact`: (forms) drive the focus-walk + toggle-all cycles the
  harness sets via `$BENCH_INTERACT_CYCLES`, then print frame deltas + `done`
* no args: run normally (used for idle-RSS sampling)

Every implementation prints a `first_frame` marker line at its
first-frame callback so the harness measures startup externally
(process spawn to marker) in a framework-neutral way, plus a
`startup_ms:` line for the in-app (self) first-frame time. All eight
frameworks, including Lumen, are measured this same way.

The Lumen variant has no CLI modes of its own: `lumenc run` is the entry
point. For startup runs the harness sets `LUMEN_BOOT_TRACE=1`, and
lumenc's windowed backend prints the same `first_frame` stdout marker on
its first on-screen present (spawn to marker, read the same way as the
native apps) followed by `startup_ms:<exec->first-frame ms>` from an
in-app CLOCK_MONOTONIC, so Lumen reports both an external and a self
startup number like every other framework, with no MCP overhead in the
startup path. Only scrolling and interaction are driven externally via
MCP `lumen.simulate` wheel events (Lumen has no in-app per-frame hook, so
the scroll frame cadence is reconstructed from the MCP frame counter).
See the caveats section in `results.md`.

## Running

```sh
./run.sh build     # build all eight (release), record stripped sizes
./run.sh validate  # calibrate + two full matrix rounds + agreement table
./run.sh all       # build + calibrate + one round; writes results.md + results.json
```

Measurement runs happen entirely under a nested headless compositor;
nothing opens on your desktop. All eight frameworks run windowed under
that one compositor. The harness starts the compositor itself, so
`./run.sh` is the normal entry point; the command it runs is:

```sh
weston --backend=headless --renderer=gl --socket=wayland-bench \
       --width=1280 --height=1024
```

If neither weston nor Xvfb is installed, or no writable
`XDG_RUNTIME_DIR` is available, the harness stops with a clear error
instead of hanging.

## Requirements

Python 3 and a C compiler (`cc`) are needed for the harness itself. Each
framework needs its own toolchain; a missing toolchain skips that
framework's rows rather than failing the run.

| framework | needs |
|---|---|
| lumen | a Lumen framework checkout (see `LUMEN_REPO` below) and its Rust toolchain |
| slint / egui / iced | rustc + cargo |
| qt-widgets | CMake and Qt6 Widgets dev (`qmake6`, `Qt6WidgetsConfig`) |
| gtk4 | CMake, pkg-config, and GTK4 dev (`gtk4`) |
| flutter | the Flutter SDK (`flutter` on PATH, linux desktop enabled) |
| tauri | rustc + cargo, the Tauri CLI (`cargo tauri`), and webkit2gtk-4.1 dev |
| headless display | a Wayland compositor (`weston`, preferred) or `Xvfb` (fallback) |

Weston uses the GL renderer on a real GPU, so a working GPU/driver (Mesa
or equivalent) is needed for the GL present path. Under a software-only
stack Lumen's wgpu-Vulkan present path has no usable adapter; the other
frameworks still render.

## What the numbers are

Every metric is measured many times, and the report leads with the
**median** (the middle measurement) plus a **spread** (how much the
repeats disagreed). Point estimates on their own hide whether a
difference is real, so each headline number also carries its minimum (the
noise floor) and, for startup, a confidence interval.

* **startup**: process spawn to first presented frame, 20 launches per
  cell by default. Reported as median, IQR, MAD, min and a 95% bootstrap
  confidence interval on the median. When two frameworks' intervals
  overlap, the report says so: their difference is inside the noise and
  should not be quoted.
* **scroll / interact**: 3 passes per cell; each pass yields p50/p95/p99
  frame intervals, and the report gives the median across passes with the
  pass-to-pass spread.
* **memory**: PSS and RSS at fixed points, over 3 separate launches, so
  the idle footprint comes with a spread instead of a single sample.
* **outliers**: counted with Tukey fences (1.5 x IQR beyond the middle
  half) and reported next to the number as `(2o)`. They are never
  dropped, and every raw sample stays in `results.json`.
* **warmup**: the first launch of each startup cell and the first 30
  frames of each pass are discarded, so recorded numbers are
  steady-state. `results.md` states the full policy.
* **run-to-run agreement**: `./run.sh validate` measures the whole matrix
  twice and reports the relative difference of the two runs' medians per
  metric, calling out anything above 5%.

`results.json` keeps each metric's raw per-iteration samples plus the
settings that produced them, so any other statistic can be recomputed
without measuring again. Its layout carries a `schema_version`; the
report generator reads older files too, recomputing what they did not
record from their stored samples.

The statistics helpers live in `harness/stats.py` and are covered by
tests that need no display, compositor or build:

```sh
python3 harness/test_stats.py
```

## Configuration

The suite reads these environment variables:

* `LUMEN_REPO`: path to the Lumen framework checkout. If it is absent,
  the lumen rows are skipped with a note. Default: a `Lumen` directory
  beside this repo.
* `BENCH_CARGO_TARGET_DIR`: cargo target dir for the Rust builds. Kept
  separate from any `CARGO_TARGET_DIR` your shell exports so a shared
  Lumen target is not touched. Default: repo-local under `harness/out`
  (gitignored).
* `BENCH_TAURI_TARGET_DIR`: cargo target dir for the Tauri build.
  Default: repo-local under `harness/out`.
* `BENCH_APP_CPUS`: the CPU set the measured apps are pinned to. Accepts
  a single cpu (`4`), a list (`4,5,6`), or a range (`4-11`). A single
  cpu pins every framework to one core, for an efficiency comparison
  (each framework does the same work on the same one core). When unset,
  the harness picks a split for the machine: on a large host it reserves
  separate CPU sets for the compositor, the apps, and itself; on a small
  host it disables pinning and shares all cores. The chosen set is
  printed at startup and recorded in `results.json`.

Sample counts, in iterations per cell. Raising them narrows the
confidence intervals and costs wall time; every one is recorded in
`results.json` next to the numbers it produced.

| variable | default | what it controls |
|---|---|---|
| `BENCH_STARTUP_RUNS` | 20 | recorded launches per startup cell |
| `BENCH_STARTUP_WARMUP` | 1 | launches discarded before recording starts |
| `BENCH_SCROLL_PASSES` | 3 | scroll passes per cell |
| `BENCH_SCROLL_SECONDS` | 6 | seconds of scrolling per pass |
| `BENCH_INTERACT_PASSES` | 3 | interact passes per cell |
| `BENCH_INTERACT_CYCLES` | 4 | focus-walk + toggle cycles per interact pass |
| `BENCH_FRAME_WARMUP_FRAMES` | 30 | frames discarded at the start of each pass |
| `BENCH_MEM_RUNS` | 3 | launches per idle-memory cell |
| `BENCH_MEM_WARMUP` | 0 | idle-memory launches discarded |
| `BENCH_CALIB_RUNS` | 30 | calibration-probe launches |
| `BENCH_CALIB_WARMUP` | 1 | calibration launches discarded |

Statistics and thresholds:

| variable | default | what it controls |
|---|---|---|
| `BENCH_BOOTSTRAP_RESAMPLES` | 10000 | resamples behind each confidence interval |
| `BENCH_CI_CONFIDENCE` | 0.95 | confidence level of those intervals |
| `BENCH_BOOTSTRAP_SEED` | fixed | random seed, so a re-render gives the same interval |
| `BENCH_UNSTABLE_IQR_FRACTION` | 0.05 | IQR/median above which a cell is marked `(!)` |
| `BENCH_AGREEMENT_TOLERANCE` | 0.05 | relative difference above which run 1 and run 2 are called out as disagreeing |
| `BENCH_KEEP_FRAME_SAMPLES` | on | keep raw per-frame deltas in `results.json` (set to `0` for a smaller file) |

Output paths, useful for rendering a report without touching the
repository's files:

| variable | default | what it controls |
|---|---|---|
| `BENCH_RESULTS_JSON` | `results.json` | where recorded data is read and written |
| `BENCH_RESULTS_MD` | `results.md` | where the report is written |

Results land in `results.md` (with a methodology section explaining every
column, and a fairness-caveats section) and `results.json`. `./run.sh
report` re-renders `results.md` from `results.json` and never rewrites
the recorded data. Charts generated from a run live in `charts/`. Build
outputs (each framework's `build`/`target`/`.dart_tool`, `harness/out`)
are gitignored and not part of the repo.
