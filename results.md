# Cross-framework benchmark results

Generated: 2026-07-22 17:10:48 +0000  
Host: arch 7.1.3-arch1-2  
Display backend: weston

| framework | version | binary (stripped) | startup median (external) | startup median (self) | scroll p50 | scroll p95 | scroll p99 | idle RSS |
|---|---|---|---|---|---|---|---|---|
| lumen | git d220a72 | 27640 KiB (+2.4 KiB app) | 78.4 ms | - | 16.78 ms | 17.69 ms | 18.23 ms | 209.0 MiB |
| slint | slint 1.17.1 | 22852 KiB | 133.1 ms | 125.6 ms | 16.61 ms | 18.68 ms | 19.38 ms | 189.6 MiB |
| egui | eframe 0.35.0 | 19459 KiB | 92.7 ms | 87.3 ms | 16.67 ms | 16.79 ms | 16.90 ms | 190.2 MiB |
| iced | iced 0.13.1 | 14706 KiB | 212.8 ms | 190.8 ms | 6.70 ms | 8.21 ms | 9.65 ms | 265.9 MiB |
| qt-widgets | Qt6Widgets 6.11.1 | 276 KiB | 33.3 ms | 20.9 ms | 15.74 ms | 16.74 ms | 16.85 ms | 40.7 MiB |
| gtk4 | gtk4 4.22.4 | 19 KiB | 145.6 ms | 121.6 ms | 16.67 ms | 17.87 ms | 19.21 ms | 231.7 MiB |

## Fairness / equivalence caveats

Same app spec everywhere: 800x600 "Bench" window; header (bold label +
count button); 10,000-row list (row = bold "Item {i}" + grey
"subtitle {i}", 36 px rows); footer (text input with placeholder +
0-100 slider + value label). Release builds, stripped binaries.

Known asymmetries - read before quoting numbers:

* **Lumen** runs via `lumenc run --headless` (its own offscreen wgpu
  pipeline, demand-driven, no compositor and no vsync), while the other
  five run windowed under a nested headless compositor with their normal
  present paths. Lumen startup includes compiling the `.lmn/.css/.rhai`
  sources (that is how Lumen apps launch today; `lumenc bundle` exists
  but the dev runner is the shipping path). Lumen's binary size row is
  the whole generic `lumenc` runtime, not an app-specific binary - the
  app itself is a few KB of text (reported separately). Lumen has
  **no in-app per-frame callback by design** (reactive signals/events
  only); a signal-bindable scroll offset (`bind-scroll`) exists, but a
  constant-velocity animation still needs an external driver, so all
  Lumen numbers are measured externally over its MCP introspection
  server:
  "first frame" = MCP frame counter reaching 1 (polled every 2 ms);
  scroll is driven by injected wheel events at ~60 Hz x 16.7 px
  (sensitivity 1.0, inertia 0 -> 1 wheel px = 1 scroll px); scroll
  p50/p95/p99 are wall frame intervals **reconstructed from the MCP
  frame counter** sampled at the drive cadence - quantized by that
  sampling, so fine-grained jitter is smoothed compared to the other
  frameworks' in-process timestamps. The MCP server itself
  runs during all Lumen measurements, and each MCP poll wakes the
  demand-driven loop. Lumen's demand-driven headless loop has no
  compositor vsync: frames land against a 16.7 ms deadline anchor, so
  sub-16.7 p50 readings mean early frames, not faster rendering -
  p95/p99 are the honest cross-framework comparison. The Lumen process
  gets DISPLAY pointed at the harness Xvfb for parity with the other
  runs; it no longer requires one (display-less headless runs work).
* **iced** has no virtualized list widget: the 10k rows are a plain
  `Column` in a `scrollable`, rebuilt every view pass. That is the
  idiomatic iced approach; it is inherently disadvantaged on this
  workload and honestly so. Under the headless compositor iced's
  redraw loop was **not vsync-throttled** (~7 ms deltas): its scroll
  numbers measure raw redraw throughput, not presentation cadence.
* **egui** is immediate-mode: `show_rows` virtualizes, but the whole UI
  is re-laid-out every frame by design. "First frame" is the end of the
  first update pass (no present callback exists).
* **Qt** "first frame" is the top-level widget's first `paintEvent`
  (raster windows have no frameSwapped); scroll frame timestamps are
  viewport paint events. Raster widget painting is synchronous and not
  vsync-locked, so the 16 ms drive timer sets the paint cadence (chosen
  to match the ~60 Hz presentation the other frameworks are throttled
  to); delta spikes above 16 ms still expose jank. Scrollbar values are
  integers, so scroll motion quantizes to whole pixels.
* **Slint** frame timestamps come from the rendering notifier
  (AfterRendering = frame submitted, not presented); the scroll position
  is advanced by an 8 ms timer rather than a per-frame callback.
* **GTK4** timestamps are GdkFrameClock "after-paint" (frame handed to
  the compositor, not presented).
* Binary sizes are not directly comparable across linkage models: the
  Rust apps statically link their framework; **Qt** and **GTK4** sizes
  exclude the dynamically linked toolkit libraries (libQt6*/libgtk-4)
  that must be present on the target system.
* Idle RSS rose ~60-70 MiB for EVERY GPU framework between the 02:39
  and 17:10 runs (Slint 129->190, egui 133->190, GTK4 172->232, iced
  195->266, Lumen 139->209) with Qt (raster) flat - a host environment
  shift (driver/compositor allocation), not a framework change. Compare
  RSS within a run, not across runs.
* Startup runs are warm-cache (no page-cache eviction between runs);
  "cold start" claims should not be made from these numbers.
* startup(external) includes Python's process-spawn overhead and pipe
  latency, identically for every framework. startup(self) is measured
  inside each app from the first line of main to its first-frame
  callback - not available for Lumen (no app-visible process start).

