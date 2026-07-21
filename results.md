# Cross-framework benchmark results

Generated: 2026-07-21 22:12:59 +0000  
Host: arch 7.1.3-arch1-2  
Display backend: weston

| framework | version | binary (stripped) | startup median (external) | startup median (self) | scroll p50 | scroll p95 | scroll p99 | idle RSS |
|---|---|---|---|---|---|---|---|---|
| lumen | git f2b4de6 | 29667 KiB (+2.4 KiB app) | 341.4 ms | - | 18.80 ms | 19.33 ms | 19.58 ms | 141.6 MiB |
| slint | slint 1.17.1 | 22852 KiB | 124.7 ms | 117.3 ms | 16.60 ms | 18.80 ms | 20.07 ms | 129.1 MiB |
| egui | eframe 0.35.0 | 19459 KiB | 54.4 ms | 52.6 ms | 16.66 ms | 16.79 ms | 16.83 ms | 132.9 MiB |
| iced | iced 0.13.1 | 14706 KiB | 219.9 ms | 198.4 ms | 6.94 ms | 7.99 ms | 9.02 ms | 193.7 MiB |
| qt-widgets | Qt6Widgets 6.11.1 | 276 KiB | 36.9 ms | 20.7 ms | 15.78 ms | 16.76 ms | 16.94 ms | 38.4 MiB |
| gtk4 | gtk4 4.22.4 | 19 KiB | 171.4 ms | 131.9 ms | 16.66 ms | 18.02 ms | 19.39 ms | 172.3 MiB |

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
  app itself is a few KB of text (reported separately). Lumen currently
  exposes **no in-app per-frame callback** (`on_tick` is documented but
  unimplemented) and **no scroll-offset setter**, so all Lumen numbers
  are measured externally over its MCP introspection server:
  "first frame" = MCP frame counter reaching 1 (polled every 2 ms);
  scroll is driven by injected wheel events at ~60 Hz x 16.7 px
  (sensitivity 1.0, inertia 0 -> 1 wheel px = 1 scroll px); scroll
  p50/p95/p99 are wall frame intervals **reconstructed from the MCP
  frame counter** sampled at the drive cadence - quantized by that
  sampling, so fine-grained jitter is smoothed compared to the other
  frameworks' in-process timestamps. The MCP server itself
  runs during all Lumen measurements, and each MCP poll wakes the
  demand-driven loop. `lumenc run --headless` also needs a display
  connection for GPU discovery (it segfaults with none), so the Lumen
  process gets DISPLAY pointed at the harness Xvfb; it still opens no
  window.
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
* Startup runs are warm-cache (no page-cache eviction between runs);
  "cold start" claims should not be made from these numbers.
* startup(external) includes Python's process-spawn overhead and pipe
  latency, identically for every framework. startup(self) is measured
  inside each app from the first line of main to its first-frame
  callback - not available for Lumen (no app-visible process start).

