# lumen-benchmarks

Honest, apples-to-apples benchmarks: the **same app** implemented in six
GUI frameworks, measured the same way.

| dir | framework | notes |
|---|---|---|
| `lumen/` | Lumen (`.lmn` + CSS + Rhai) | run by `lumenc` from the Lumen repo |
| `slint/` | Slint 1.x, winit backend | `ListView` (virtualized) |
| `egui/` | eframe (latest) | `ScrollArea::show_rows` (virtualized) |
| `iced/` | iced 0.13 | plain `Column` in `scrollable` (iced has no virtualized list) |
| `qt-widgets/` | Qt6 Widgets, C++17 | `QListView` + `QAbstractListModel` (virtualized) |
| `gtk4/` | GTK4, C | `GtkListView` + `GtkStringList` factory (virtualized) |

GTK variant is plain C (chosen over the gtk4-rs bindings to keep the
build light and match the reference C API directly).

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
  1000 px/s for 10 s (bouncing at the ends), then print one frame delta
  (ms) per line and `done`
* no args - run normally (used for idle-RSS sampling)

Every implementation prints a `first_frame` marker line at its
first-frame callback so the harness can also measure startup externally
(process spawn -> marker) in a framework-neutral way.

The Lumen variant has no CLI modes of its own: `lumenc run` is the
entry point, the app prints one `f:<dt-ms>` diagnostic line per tick
(the first one doubles as the first-frame marker), and the harness
drives scrolling externally via MCP `lumen.simulate` wheel events. See
the caveats section in `results.md`.

## Running

```sh
./run.sh build     # build all six (release), record stripped sizes
./run.sh measure   # startup x10, 10 s scroll bench, idle RSS
./run.sh all       # everything; writes results.md + results.json
```

Requirements: Rust toolchain, Qt6 dev, GTK4 dev, CMake, Python 3, and -
for `measure` - `weston` (headless backend; `Xvfb` is the fallback).
Measurement runs happen entirely under a nested headless compositor
(`weston --backend=headless --socket=wayland-bench`); nothing opens on
your desktop. Lumen measures through `lumenc run --headless` (its own
offscreen pipeline).

Environment:

* `CARGO_TARGET_DIR` - private cargo target dir for **all** Rust builds,
  including `lumenc` (default `/Storage/cargo-target-benchcomp`)
* `LUMEN_REPO` - path to the Lumen framework checkout
  (default `/home/artur/Lumen`)

Results land in `results.md` (with a mandatory fairness-caveats section)
and `results.json`.
