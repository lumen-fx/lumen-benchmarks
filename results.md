# Cross-framework benchmark results

Generated: 2026-07-22 21:09:28 +0000  
Host: arch · kernel 7.1.3-arch1-2 · 12th Gen Intel(R) Core(TM) i9-12900K (24 cpus)  
Governors: powersave · governor pin: not permitted (wanted 'performance'; left as-is on cpus [4, 5, 6, 7, 8, 9, 10, 11]) · app cpus [4, 5, 6, 7, 8, 9, 10, 11]  
Mesa: mesa 1:26.1.4-1 · display: weston --renderer=gl (nested headless) · all six windowed · Lumen: 4ad458af11da (dirty)

Primary numbers below are **round 0**; the run-to-run agreement table compares round 0 vs round 1. Values are medians; ± is half the IQR (startup, n=15) or half the cross-pass spread (frame percentiles, 3 passes). ⚠ = unstable (IQR/median > 5%); (No) = N Tukey outliers retained. Memory is PSS in MiB with RSS in parentheses (both from /proc, idle = first frame + 2 s).

## hello - startup floor, baseline memory, binary size

| framework | version | binary (stripped) | startup ext ms | startup self ms | PSS idle MiB (RSS) | PSS @5 s |
|---|---|---|---|---|---|---|
| lumen | git 4ad458a | 20.1 MiB rt +0.7 KiB app | 211.4 ±21.9 ⚠ | - | 66.8 (186.8) | 66.8 (186.8) |
| slint | slint 1.17.1 | 19.4 MiB | 97.4 ±16.9 ⚠ (2o) | 94.1 ±15.5 ⚠ (2o) | 51.3 (168.4) | 51.3 (168.4) |
| egui | eframe 0.35.0 | 18.8 MiB | 36.0 ±0.5 (1o) | 34.5 ±0.4 (1o) | 52.9 (165.8) | 52.9 (165.8) |
| iced | iced 0.13.1 | 14.3 MiB | 56.2 ±1.2 (2o) | 52.6 ±1.1 (2o) | 62.4 (176.4) | 62.4 (176.4) |
| qt-widgets | Qt6Widgets 6.11.1 | 0.2 MiB | 17.4 ±0.3 (2o) | 12.6 ±0.2 (1o) | 22.2 (39.4) | 22.2 (39.4) |
| gtk4 | gtk4 4.22.4 | 0.0 MiB | 63.7 ±7.3 ⚠ | 38.3 ±0.3 (3o) | 39.1 (134.5) | 39.1 (134.5) |

## forms - ~40-widget settings page

Interact pass = 4 cycles x (40-step focus walk + 20-step toggle-all), one step per 16 ms; frame-interval percentiles over the pass.

| framework | binary | startup ext ms | interact p50 ms | interact p95 ms | interact p99 ms | PSS idle (RSS) | PSS post |
|---|---|---|---|---|---|---|---|
| lumen | 20.1 MiB rt +9.3 KiB app | 115.7 ±7.3 ⚠ (2o) | 16.55 ±0.03 | 17.15 ±0.06 | 17.69 ±0.28 | 72.7 (192.8) | 75.5 (196.8) |
| slint | 23.6 MiB | 65.3 ±0.5 (1o) | 16.67 ±0.01 | 17.00 ±1.05 | 17.89 ±1.57 | 57.0 (174.5) | 59.4 (177.4) |
| egui | 19.1 MiB | 37.0 ±0.3 | 16.67 ±0.00 | 16.73 ±0.01 | 16.75 ±0.01 | 53.9 (166.8) | 53.9 (166.9) |
| iced | 14.6 MiB | 56.5 ±0.4 (1o) | 16.67 ±0.00 | 16.89 ±0.10 | 33.35 ±0.02 | 62.6 (176.4) | 63.3 (177.2) |
| qt-widgets | 0.3 MiB | 38.4 ±6.9 ⚠ | 15.87 ±0.06 | 19.57 ±1.46 | 19.96 ±1.49 | 24.7 (42.1) | 26.5 (44.0) |
| gtk4 | 0.0 MiB | 69.4 ±5.6 ⚠ | 16.66 ±0.02 | 17.33 ±0.02 | 17.84 ±0.26 | 41.8 (137.3) | 42.0 (137.4) |

## list - 10,000-row list scrolled at 1000 px/s

| framework | binary | startup ext ms | scroll p50 ms | scroll p95 ms | scroll p99 ms | PSS idle (RSS) | PSS post |
|---|---|---|---|---|---|---|---|
| lumen | 20.1 MiB rt +2.4 KiB app | 276.1 ±13.1 ⚠ | 16.77 ±0.16 | 18.66 ±0.82 | 19.63 ±1.19 | 86.7 (206.9) | 89.6 (209.8) |
| slint | 22.3 MiB | 74.5 ±12.7 ⚠ | 16.67 ±0.00 | 17.07 ±0.23 | 17.64 ±0.37 | 54.0 (171.1) | 54.6 (171.8) |
| egui | 19.0 MiB | 36.8 ±0.3 (3o) | 16.66 ±0.00 | 16.73 ±0.00 | 16.75 ±0.01 | 53.7 (166.5) | 53.7 (166.6) |
| iced | 14.5 MiB | 150.3 ±1.1 (1o) | 16.63 ±0.02 | 17.55 ±0.04 | 18.21 ±0.33 | 164.1 (278.0) | 164.2 (278.1) |
| qt-widgets | 0.3 MiB | 17.7 ±0.2 | 15.70 ±0.05 | 16.70 ±0.02 | 16.79 ±0.06 | 23.7 (40.8) | 24.8 (42.8) |
| gtk4 | 0.0 MiB | 77.3 ±9.6 ⚠ (2o) | 16.67 ±0.00 | 17.25 ±0.32 | 17.85 ±1.57 | 44.7 (140.0) | 44.9 (140.3) |

## textview - 5,000 wrapped paragraphs (~1.1 MiB) scrolled at 1000 px/s

| framework | binary | startup ext ms | scroll p50 ms | scroll p95 ms | scroll p99 ms | PSS idle (RSS) | PSS post |
|---|---|---|---|---|---|---|---|
| lumen | 20.1 MiB rt +1367.8 KiB app | 1518.0 ±11.6 | 16.76 ±0.08 | 19.75 ±1.51 | 24.10 ±3.42 | 118.9 (239.2) | 118.7 (238.9) |
| slint | 19.3 MiB | 1087.6 ±4.3 (3o) | 143.94 ±0.14 | 145.58 ±0.19 | 146.82 ±0.91 | 213.2 (330.5) | 218.3 (335.7) |
| egui | 18.8 MiB | 233.9 ±2.6 (2o) | 16.66 ±0.00 | 16.72 ±0.01 | 16.77 ±0.01 | 254.7 (367.5) | 255.1 (367.8) |
| iced | 14.4 MiB | 365.4 ±0.5 (2o) | 44.49 ±0.15 | 44.86 ±0.12 | 45.11 ±0.05 | 387.8 (501.6) | 388.2 (502.0) |
| qt-widgets | 0.3 MiB | 43.4 ±4.6 ⚠ | 15.85 ±0.02 | 16.77 ±0.05 | 27.18 ±5.19 | 91.3 (109.4) | 91.5 (109.6) |
| gtk4 | 0.0 MiB | 74.7 ±4.4 ⚠ | 16.66 ±0.03 | 17.89 ±0.05 | 18.31 ±0.07 | 41.8 (137.3) | 43.0 (138.5) |

## Calibration - bounding systematic error

* spawn->marker floor (trivial C binary, n=30): **2.78 ±0.58 ⚠ ms** - harness+fork/exec overhead baked identically into every external startup number.
* harness-vs-kernel spawn timestamp (independent, /proc starttime): **-1.06 ±0.37 (7o) ms** - bounds the harness's spawn-anchor error.
* marker pipe latency (app clock vs harness clock): **0.05 ±0.25 ⚠ (3o) ms** - bounds marker-arrival skew.
* Consequence: cross-framework startup deltas below ~1 ms are inside the systematic error band and not meaningful.

## Run-to-run agreement (round 0 vs round 1)

85/102 headline medians agree within their stated error bars (startup: IQR; frame percentiles: cross-pass spread, floored at 5%; idle PSS: max(3%, 1 MiB)).

| framework | app | metric | round 0 | round 1 | |Δ| | error bar | agree |
|---|---|---|---|---|---|---|---|
| lumen | hello | startup ext ms | 211.429 | 112.534 | 98.895 | 43.79 | ✗ MISMATCH |
| lumen | hello | idle PSS kB | 68360 | 67813 | 547 | 2050.8 | ✓ |
| lumen | list | startup ext ms | 276.148 | 152.648 | 123.5 | 26.142 | ✗ MISMATCH |
| lumen | list | scroll p50_ms | 16.768 | 16.937 | 0.169 | 0.838 | ✓ |
| lumen | list | scroll p95_ms | 18.659 | 17.523 | 1.136 | 1.635 | ✓ |
| lumen | list | scroll p99_ms | 19.633 | 17.569 | 2.064 | 2.388 | ✓ |
| lumen | list | idle PSS kB | 88778 | 89668 | 890 | 2663.34 | ✓ |
| lumen | forms | startup ext ms | 115.683 | 130.127 | 14.444 | 14.614 | ✓ |
| lumen | forms | interact p50_ms | 16.546 | 16.586 | 0.04 | 0.827 | ✓ |
| lumen | forms | interact p95_ms | 17.153 | 17.181 | 0.028 | 0.858 | ✓ |
| lumen | forms | interact p99_ms | 17.687 | 18.099 | 0.412 | 0.884 | ✓ |
| lumen | forms | idle PSS kB | 74401 | 73845 | 556 | 2232.03 | ✓ |
| lumen | textview | startup ext ms | 1517.972 | 1499.685 | 18.287 | 30.359 | ✓ |
| lumen | textview | scroll p50_ms | 16.763 | 16.725 | 0.038 | 0.838 | ✓ |
| lumen | textview | scroll p95_ms | 19.752 | 18.324 | 1.428 | 3.014 | ✓ |
| lumen | textview | scroll p99_ms | 24.098 | 18.925 | 5.173 | 6.831 | ✓ |
| lumen | textview | idle PSS kB | 121788 | 121294 | 494 | 3653.64 | ✓ |
| slint | hello | startup ext ms | 97.422 | 73.352 | 24.07 | 33.72 | ✓ |
| slint | hello | idle PSS kB | 52488 | 52454 | 34 | 1574.64 | ✓ |
| slint | list | startup ext ms | 74.505 | 68.975 | 5.53 | 25.446 | ✓ |
| slint | list | scroll p50_ms | 16.667 | 16.665 | 0.002 | 0.833 | ✓ |
| slint | list | scroll p95_ms | 17.068 | 18.112 | 1.044 | 0.853 | ✗ MISMATCH |
| slint | list | scroll p99_ms | 17.645 | 18.659 | 1.014 | 0.882 | ✗ MISMATCH |
| slint | list | idle PSS kB | 55248 | 55119 | 129 | 1657.44 | ✓ |
| slint | forms | startup ext ms | 65.275 | 84.625 | 19.35 | 13.577 | ✗ MISMATCH |
| slint | forms | interact p50_ms | 16.666 | 16.683 | 0.017 | 0.833 | ✓ |
| slint | forms | interact p95_ms | 16.999 | 18.862 | 1.863 | 2.091 | ✓ |
| slint | forms | interact p99_ms | 17.893 | 20.433 | 2.54 | 3.143 | ✓ |
| slint | forms | idle PSS kB | 58391 | 58701 | 310 | 1751.73 | ✓ |
| slint | textview | startup ext ms | 1087.647 | 1095.009 | 7.362 | 21.753 | ✓ |
| slint | textview | scroll p50_ms | 143.943 | 143.375 | 0.568 | 7.197 | ✓ |
| slint | textview | scroll p95_ms | 145.583 | 145.89 | 0.307 | 7.279 | ✓ |
| slint | textview | scroll p99_ms | 146.824 | 146.565 | 0.259 | 7.341 | ✓ |
| slint | textview | idle PSS kB | 218367 | 218458 | 91 | 6551.01 | ✓ |
| egui | hello | startup ext ms | 36.025 | 69.277 | 33.252 | 20.362 | ✗ MISMATCH |
| egui | hello | idle PSS kB | 54125 | 54068 | 57 | 1623.75 | ✓ |
| egui | list | startup ext ms | 36.806 | 71.822 | 35.016 | 7.712 | ✗ MISMATCH |
| egui | list | scroll p50_ms | 16.664 | 16.665 | 0.001 | 0.833 | ✓ |
| egui | list | scroll p95_ms | 16.725 | 16.717 | 0.008 | 0.836 | ✓ |
| egui | list | scroll p99_ms | 16.75 | 16.752 | 0.002 | 0.838 | ✓ |
| egui | list | idle PSS kB | 54970 | 54826 | 144 | 1649.1 | ✓ |
| egui | forms | startup ext ms | 37.015 | 72.569 | 35.554 | 7.704 | ✗ MISMATCH |
| egui | forms | interact p50_ms | 16.669 | 16.667 | 0.002 | 0.833 | ✓ |
| egui | forms | interact p95_ms | 16.727 | 16.713 | 0.014 | 0.836 | ✓ |
| egui | forms | interact p99_ms | 16.752 | 16.753 | 0.001 | 0.838 | ✓ |
| egui | forms | idle PSS kB | 55186 | 55278 | 92 | 1655.58 | ✓ |
| egui | textview | startup ext ms | 233.854 | 268.963 | 35.109 | 11.262 | ✗ MISMATCH |
| egui | textview | scroll p50_ms | 16.665 | 16.664 | 0.001 | 0.833 | ✓ |
| egui | textview | scroll p95_ms | 16.72 | 16.723 | 0.003 | 0.836 | ✓ |
| egui | textview | scroll p99_ms | 16.766 | 16.757 | 0.009 | 0.838 | ✓ |
| egui | textview | idle PSS kB | 260831 | 260634 | 197 | 7824.93 | ✓ |
| iced | hello | startup ext ms | 56.19 | 67.85 | 11.66 | 14.082 | ✓ |
| iced | hello | idle PSS kB | 63880 | 63581 | 299 | 1916.4 | ✓ |
| iced | list | startup ext ms | 150.336 | 184.097 | 33.761 | 15.605 | ✗ MISMATCH |
| iced | list | scroll p50_ms | 16.632 | 16.704 | 0.072 | 0.832 | ✓ |
| iced | list | scroll p95_ms | 17.555 | 17.818 | 0.263 | 0.878 | ✓ |
| iced | list | scroll p99_ms | 18.208 | 19.33 | 1.122 | 2.068 | ✓ |
| iced | list | idle PSS kB | 167995 | 167990 | 5 | 5039.85 | ✓ |
| iced | forms | startup ext ms | 56.472 | 96.349 | 39.877 | 12.176 | ✗ MISMATCH |
| iced | forms | interact p50_ms | 16.673 | 16.671 | 0.002 | 0.834 | ✓ |
| iced | forms | interact p95_ms | 16.886 | 17.551 | 0.665 | 0.844 | ✓ |
| iced | forms | interact p99_ms | 33.352 | 33.351 | 0.001 | 1.668 | ✓ |
| iced | forms | idle PSS kB | 64066 | 64129 | 63 | 1921.98 | ✓ |
| iced | textview | startup ext ms | 365.395 | 407.547 | 42.152 | 9.337 | ✗ MISMATCH |
| iced | textview | scroll p50_ms | 44.487 | 44.874 | 0.387 | 2.583 | ✓ |
| iced | textview | scroll p95_ms | 44.859 | 45.319 | 0.46 | 2.698 | ✓ |
| iced | textview | scroll p99_ms | 45.113 | 45.988 | 0.875 | 2.577 | ✓ |
| iced | textview | idle PSS kB | 397087 | 396980 | 107 | 11912.61 | ✓ |
| qt-widgets | hello | startup ext ms | 17.364 | 28.301 | 10.937 | 10.946 | ✓ |
| qt-widgets | hello | idle PSS kB | 22762 | 22759 | 3 | 1024 | ✓ |
| qt-widgets | list | startup ext ms | 17.72 | 32.619 | 14.899 | 8.303 | ✗ MISMATCH |
| qt-widgets | list | scroll p50_ms | 15.699 | 15.809 | 0.11 | 0.785 | ✓ |
| qt-widgets | list | scroll p95_ms | 16.703 | 16.734 | 0.031 | 0.835 | ✓ |
| qt-widgets | list | scroll p99_ms | 16.785 | 16.887 | 0.102 | 0.839 | ✓ |
| qt-widgets | list | idle PSS kB | 24256 | 24259 | 3 | 1024 | ✓ |
| qt-widgets | forms | startup ext ms | 38.393 | 30.754 | 7.639 | 13.817 | ✓ |
| qt-widgets | forms | interact p50_ms | 15.868 | 15.871 | 0.003 | 0.793 | ✓ |
| qt-widgets | forms | interact p95_ms | 19.567 | 16.908 | 2.659 | 2.914 | ✓ |
| qt-widgets | forms | interact p99_ms | 19.964 | 19.843 | 0.121 | 2.971 | ✓ |
| qt-widgets | forms | idle PSS kB | 25331 | 25217 | 114 | 1024 | ✓ |
| qt-widgets | textview | startup ext ms | 43.391 | 47.541 | 4.15 | 15.276 | ✓ |
| qt-widgets | textview | scroll p50_ms | 15.85 | 15.844 | 0.006 | 0.792 | ✓ |
| qt-widgets | textview | scroll p95_ms | 16.767 | 16.756 | 0.011 | 0.838 | ✓ |
| qt-widgets | textview | scroll p99_ms | 27.182 | 26.949 | 0.233 | 10.383 | ✓ |
| qt-widgets | textview | idle PSS kB | 93499 | 93532 | 33 | 2804.97 | ✓ |
| gtk4 | hello | startup ext ms | 63.703 | 63.547 | 0.156 | 14.516 | ✓ |
| gtk4 | hello | idle PSS kB | 40029 | 38450 | 1579 | 1200.87 | ✗ MISMATCH |
| gtk4 | list | startup ext ms | 77.264 | 80.958 | 3.694 | 19.196 | ✓ |
| gtk4 | list | scroll p50_ms | 16.667 | 16.65 | 0.017 | 0.833 | ✓ |
| gtk4 | list | scroll p95_ms | 17.249 | 17.425 | 0.176 | 0.862 | ✓ |
| gtk4 | list | scroll p99_ms | 17.849 | 17.867 | 0.018 | 3.135 | ✓ |
| gtk4 | list | idle PSS kB | 45726 | 44030 | 1696 | 1371.78 | ✗ MISMATCH |
| gtk4 | forms | startup ext ms | 69.355 | 70.951 | 1.596 | 11.217 | ✓ |
| gtk4 | forms | interact p50_ms | 16.663 | 16.67 | 0.007 | 0.833 | ✓ |
| gtk4 | forms | interact p95_ms | 17.328 | 17.306 | 0.022 | 0.866 | ✓ |
| gtk4 | forms | interact p99_ms | 17.839 | 18.074 | 0.235 | 0.892 | ✓ |
| gtk4 | forms | idle PSS kB | 42775 | 40978 | 1797 | 1283.25 | ✗ MISMATCH |
| gtk4 | textview | startup ext ms | 74.69 | 72.795 | 1.895 | 8.828 | ✓ |
| gtk4 | textview | scroll p50_ms | 16.664 | 16.604 | 0.06 | 0.833 | ✓ |
| gtk4 | textview | scroll p95_ms | 17.894 | 17.881 | 0.013 | 0.895 | ✓ |
| gtk4 | textview | scroll p99_ms | 18.308 | 18.476 | 0.168 | 0.915 | ✓ |
| gtk4 | textview | idle PSS kB | 42837 | 41102 | 1735 | 1285.11 | ✗ MISMATCH |

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

* **Lumen** runs windowed under the same nested compositor as the other
  five: a real winit window presenting through `weston --renderer=gl` via
  wgpu `AutoVsync`. It shares one present path with the rest - the
  asymmetry of the earlier offscreen `--headless` runs (no compositor at
  all) is gone. Lumen startup includes compiling the `.lmn/.css/.rhai`
  sources (that is how Lumen apps launch today) plus the window
  map/first-present cost the other five also pay. Lumen's size row is the
  generic `lumenc` runtime plus a few KB of app text. Lumen has no in-app
  per-frame callback by design, so all Lumen numbers are external: the MCP
  frame counter is sampled every 0.5 ms over a persistent connection
  (reading it does not wake the parked loop; only injected events do), and
  frame boundaries are reconstructed from counter advances (quantized at
  ~0.5 ms). A headless compositor has no physical display refresh, so
  wgpu's `AutoVsync` present does not reliably block - Lumen's redraw loop
  is paced to ~60 Hz by the backend's own animation-frame deadline (a
  no-op on a real vsync display, where the compositor is the clock; it
  only bites when present() returns immediately, capping what would
  otherwise be an uncapped spin). This is the same self-pacing regime the
  other frameworks fall into under a headless compositor (Qt's 16 ms
  timer, Slint's 8/4 ms timers): p50 sits near 16.7 ms and p95/p99 expose
  the jitter/jank tail (visible on textview, where the ~5.7 ms tick work
  widens it). The per-frame CPU cost is reported separately as
  `tick_cpu_us` (real layout + paint + encode span). Scroll is driven by
  injected wheel events at ~60 Hz x 16.7 px (sensitivity 1.0, inertia
  0 -> 1 wheel px = 1 scroll px). The interact pass differs structurally:
  Tab focus-walk uses real key events (like Qt/Slint), but Lumen has no
  externally reachable state setter, so toggle steps scroll the control
  into view and click it - real input-pipeline work (hit-testing,
  scrolling) that the other frameworks' direct state writes do not
  perform, so Lumen's interact numbers are an upper bound. A few toggle
  steps near the scroll extremes (rows that cannot be centred in the
  viewport band) do not land; the count is reported as `step_errors` and
  those steps are omitted, not counted as frames.
* **iced** has no virtualized list widget: the 10k rows are a plain
  `Column` in a `scrollable`, rebuilt every view pass - idiomatic iced,
  inherently disadvantaged on the list workload and honestly so. iced
  renders through wgpu, so under `weston --renderer=gl` its present
  throttles on the compositor (≈60 Hz, ~17 ms deltas) rather than
  free-running as it did under the earlier software-renderer compositor
  (~7 ms) - its scroll cadence now matches the other frameworks. Its
  textview lays out the full corpus each pass.
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

