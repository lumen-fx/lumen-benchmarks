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

Results land in `results.md` (with a fairness-caveats section) and
`results.json`. Charts generated from a run live in `charts/`. Build
outputs (each framework's `build`/`target`/`.dart_tool`, `harness/out`)
are gitignored and not part of the repo.
