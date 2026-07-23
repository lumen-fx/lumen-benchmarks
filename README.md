# lumen-benchmarks

Honest, apples-to-apples benchmarks: the **same app** implemented in
eight GUI frameworks, measured the same way.

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

GTK variant is plain C (chosen over the gtk4-rs bindings to keep the
build light and match the reference C API directly). Flutter renders
with its **own engine** (Impeller/Skia) - the closest analogue to
Lumen's own-renderer model - so its window is a single engine surface,
not native widgets. Tauri renders in the **system webkit2gtk** webview:
a browser engine shipped as a shared library (like Qt/GTK's toolkit),
driving real DOM. Both honor the identical CLI contract and are measured
by the same framework-neutral spawn -> `first_frame` path as the native
apps; see the fairness caveats in `results.md` (webview `performance.now()`
is 1 ms-clamped; Flutter/Tauri size rows exclude their engine/toolkit
shared libs; Tauri PSS discounts pages shared with other WebKit users).

## The app

800x600 window titled "Bench":

* header: bold label **Bench** + a `Count: N` button that increments on click
* a scrollable list of **10,000 rows** - each row is one 36 px line:
  bold `Item {i}`, then grey `subtitle {i}` (12 px gap, 8 px left pad)
* footer: single-line text input (placeholder `Type here...`) +
  a 0-100 slider (start 50) with its value in an adjacent label

CLI modes (identical semantics in every implementation):

* `--startup` - print `startup_ms: <float>` (first line of `main` ->
  first-presented-frame callback) and exit
* `--scroll-bench` - from the first frame, animate the list scroll at
  1000 px/s (bouncing at the ends) for `$BENCH_SCROLL_SECONDS` (the
  harness sets it; 6 s per pass), then print one frame delta (ms) per
  line and `done`
* `--interact` - (forms) drive the focus-walk + toggle-all cycles the
  harness sets via `$BENCH_INTERACT_CYCLES`, then print frame deltas + `done`
* no args - run normally (used for idle-RSS sampling)

Every implementation prints a `first_frame` marker line at its
first-frame callback so the harness measures startup externally
(process spawn -> marker) in a framework-neutral way, plus a
`startup_ms:` line for the in-app (self) first-frame time. **All eight
frameworks - including Lumen - are measured this identical way.**

The Lumen variant has no CLI modes of its own: `lumenc run` is the
entry point. For startup runs the harness sets `LUMEN_BOOT_TRACE=1`, and
lumenc's windowed backend prints the same `first_frame` stdout marker on
its first on-screen present (spawn -> marker, read the same way as the
native apps) followed by `startup_ms:<exec->first-frame ms>` from an
in-app CLOCK_MONOTONIC - so Lumen reports both an external and a self
startup number like every other framework, with no MCP overhead in the
startup path. Only scrolling/interaction is driven externally via MCP
`lumen.simulate` wheel events (Lumen has no in-app per-frame hook, so
the scroll frame cadence is reconstructed from the MCP frame counter).
See the caveats section in `results.md`.

## Running

```sh
./run.sh build     # build all eight (release), record stripped sizes
./run.sh validate  # calibrate + two full matrix rounds + agreement table
./run.sh all       # build + calibrate + one round; writes results.md + results.json
```

Requirements: Rust toolchain, Qt6 dev, GTK4 dev, CMake, Python 3, the
Flutter SDK (`flutter` on PATH, linux desktop enabled), the Tauri CLI
(`cargo tauri`) + webkit2gtk-4.1, and - for `measure` - `weston`
(headless backend; `Xvfb` is the fallback). Measurement runs happen
entirely under a nested headless compositor
(`weston --backend=headless --renderer=gl --socket=wayland-bench`);
nothing opens on your desktop. All eight frameworks run windowed under
that one compositor. All eight print a `first_frame` marker + `startup_ms:`
for startup (Lumen via `LUMEN_BOOT_TRACE`); the native apps also print
their own per-frame deltas, while Lumen's scroll/interact cadence is
observed externally over its MCP server (no in-app per-frame hook).
Flutter build output is redirected onto `/Storage`
(the `flutter/build` symlink) and Tauri builds into its own `/Storage`
cargo target, so neither touches the root disk or the Lumen shared target.

Environment:

* `CARGO_TARGET_DIR` - private cargo target dir for **all** Rust builds,
  including `lumenc` (default `/Storage/cargo-target-benchcomp`)
* `LUMEN_REPO` - path to the Lumen framework checkout
  (default `/home/artur/Lumen`)

Results land in `results.md` (with a mandatory fairness-caveats section)
and `results.json`.
