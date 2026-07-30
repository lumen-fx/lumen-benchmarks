# Cross-framework benchmark results

Generated: 2026-07-23 19:11:43 +0000  
Host: arch | 12th Gen Intel(R) Core(TM) i9-12900K | display: weston (nested headless) | schema 1

The whole matrix is measured twice; each full pass over it is a run. The tables below report run 1. The run-to-run agreement section near the end compares run 1 with run 2 metric by metric and names anything that moved more than the stated threshold.

Startup is measured the same way across all eight frameworks: external = harness CLOCK_MONOTONIC spawn -> first `first_frame` stdout marker; self = the app's own CLOCK_MONOTONIC exec/main -> first-frame (`startup_ms:`). This includes Lumen, whose windowed backend emits both markers under `LUMEN_BOOT_TRACE`; there is no MCP (the harness control channel to Lumen) connect/poll in the startup path (MCP drives only the scroll/interact passes). See the clock-sources table and caveats below.

## Environment

Machine facts that move the numbers. A result is only comparable with another run on the same block.

| item | value |
|---|---|
| host / kernel | arch / 7.1.3-arch1-2 |
| CPU | 12th Gen Intel(R) Core(TM) i9-12900K (24 logical cpus) |
| app cpus | [4, 5, 6, 7, 8, 9, 10, 11] |
| cpu governor | performance on the app cpus; pin attempt: 'performance' on cpus [4, 5, 6, 7, 8, 9, 10, 11] |
| memory | 32588116 kB |
| display | weston, nested headless |
| display command | `weston --backend=headless --renderer=gl --socket=wayland-bench --width=1280 --height=1024` |
| GPU stack | mesa 1:26.1.4-1 |
| load at start | 2.23 2.17 1.55 4/1982 850501 |
| rustc / python | rustc 1.97.0 (2d8144b78 2026-07-07) / python 3.14.6 |
| lumen checkout | 7ee3bbe9bdfe (dirty) |

Toolkit version per framework: lumen git 7ee3bbe; slint slint 1.17.1; egui eframe 0.35.0; iced iced 0.13.1; qt-widgets Qt6Widgets 6.11.1; gtk4 gtk4 4.22.4; flutter Flutter 3.44.7 - channel stable - https://github.com/flutter/flutter.git; tauri tauri 2.11.5 - webkit2gtk 2.52.5.

## How to read these tables

Every number is a **median**: the middle value of the repeated measurements, so one slow launch cannot drag it around. Next to it is a **spread**, showing how much the repeats disagreed. Small spread means the number is solid; large spread means the machine, not the framework, is doing the talking.

Terms used in the columns:

* **median**: the middle measurement. Half were faster, half slower.
* **IQR** (interquartile range): the width of the middle half of the measurements. A spread that ignores the extremes.
* **MAD** (median absolute deviation): the typical distance of a measurement from the median. A second spread, even less sensitive to extremes than the IQR. Shown in parentheses after the IQR.
* **min**: the fastest measurement seen. Treated as the noise floor: work cannot go faster than itself, so anything above min is interference or variance.
* **95% CI** (confidence interval) on startup: the range where the median would plausibly land if the same cell were measured again. It is computed by resampling the recorded launches (10000 times, a percentile bootstrap). **If two frameworks' intervals overlap, the data does not separate them**; do not read the gap between their medians as real. Overlapping pairs are listed under the startup table.
* **(!)**: unstable cell, meaning IQR divided by median is above 5%. Treat that number as indicative, not precise.
* **(2o)**: two measurements fell outside the outlier fences and were kept in the sample. See the outlier policy below.
* **frame percentile columns** (p50/p95/p99): p50 is the typical frame interval, p95 and p99 are the slow tail; a 16.7 ms p50 with a 40 ms p99 means smooth scrolling with visible hitches. Each frame cell reads `median (spread, min)`: the median across passes, the gap between the best and worst pass, and the best pass itself as the floor.
* **`+/-`**: half the IQR, the form used where a table has no room for its own spread column (the startup column of the forms/list/textview tables, and the calibration figures).
* **memory columns**: PSS (proportional set size, the process's share of physical memory, counting shared pages only in proportion) in MiB, with RSS (resident set size, all resident pages) in parentheses. `+/-` on PSS is half the IQR across the repeated launches.

**Sample counts.** startup: 15 launches per cell; scroll: 3 passes x 6.0 s; interact: 3 passes x 4 cycles. Every count is an environment knob (see README.md) and is recorded in `results.json` next to the numbers it produced, together with each metric's raw per-iteration samples, so any other statistic can be recomputed without measuring again.

**Warmup.** Measurements thrown away before recording starts, and why:

* **startup**: the first BENCH_STARTUP_WARMUP launches of a cell (default
  1) are discarded. They pay for cold file-cache and dynamic-linker work
  the later launches do not, so every recorded startup number is a
  warm-cache launch. `--cold` mode instead evicts the file cache before
  every launch, warmup included, and says so on the cell.
* **scroll / interact frames**: the first BENCH_FRAME_WARMUP_FRAMES frames
  of each pass (default 30, about half a second at 60 Hz) are discarded.
  Those frames carry first-scroll glyph/texture caching, not steady-state
  cost. Whole passes are never discarded.
* **memory**: no iterations are discarded. Each idle-memory launch is
  sampled at a fixed point (first frame + 2 s), which is the warmup: the
  app has finished starting and has not been touched since.
* **calibration**: the first BENCH_CALIB_WARMUP launches of the probe
  binary (default 1) are discarded, same reason as startup.

**Outliers.** Outliers are counted, never dropped. A sample is an outlier when it falls outside the Tukey fences: below q1 - 1.5 x IQR or above q3 + 1.5 x IQR, where q1 and q3 bound the middle half of the samples. The count appears next to the affected number as `(2o)`, and every sample, outliers included, stays in results.json. Nothing in the report is computed on a filtered sample set: the median and the IQR already resist the extremes, and the outlier count tells you how much interference the run saw.

This report renders a schema-1 `results.json` (the current harness writes schema 2). That run recorded every startup sample but no interval, minimum or MAD, so those are recomputed here from the stored samples. Columns the run never recorded, such as per-frame samples, read `-`.

## hello - startup floor, baseline memory, binary size

| framework | version | binary (stripped) | startup ext ms | ext IQR (MAD) | ext min | startup self ms | PSS idle MiB (RSS) | PSS @5 s |
|---|---|---|---|---|---|---|---|---|
| lumen | git 7ee3bbe | 22.4 MiB rt +0.7 KiB app | 104.1 (1o) | 0.9 (0.5) | 102.7 | 96.0 (1o) | 62.9 (174.8) | 62.9 (174.8) |
| slint | slint 1.17.1 | 19.4 MiB | 51.3 | 0.7 (0.4) | 50.2 | 49.4 | 47.4 (156.4) | 47.4 (156.4) |
| egui | eframe 0.35.0 | 18.8 MiB | 58.6 (!) (1o) | 3.9 (2.6) | 45.4 | 55.5 (!) (1o) | 48.4 (152.9) | 48.4 (152.9) |
| iced | iced 0.13.1 | 14.3 MiB | 92.1 (!) | 7.5 (1.6) | 74.6 | 86.1 (!) | 58.0 (163.0) | 58.0 (163.0) |
| qt-widgets | Qt6Widgets 6.11.1 | 0.2 MiB | 54.9 (!) | 12.4 (6.9) | 34.1 | 35.1 (!) | 23.6 (41.4) | 23.6 (41.4) |
| gtk4 | gtk4 4.22.4 | 0.0 MiB | 55.1 (!) (2o) | 4.0 (2.1) | 52.2 | 41.2 (!) (2o) | 38.2 (135.2) | 38.2 (135.2) |
| flutter | Flutter 3.44.7 - channel stable - https://github.com/flutter/flutter.git | 5.1 MiB | 126.8 (!) (1o) | 6.7 (3.4) | 117.5 | 30.7 (2o) | 78.2 (206.5) | 83.5 (212.3) |
| tauri | tauri 2.11.5 - webkit2gtk 2.52.5 | 5.3 MiB | 163.9 (!) (1o) | 30.7 (9.0) | 153.0 | 138.0 (!) (2o) | 59.0 (204.3) | 59.0 (204.3) |

## forms - ~40-widget settings page

Interact pass = 4 cycles x (40-step focus walk + 20-step toggle-all), one step per 16 ms; frame-interval percentiles over the pass. Each frame cell reads `median (spread, min)`: the median across passes, the gap between the best and worst pass, and the best pass itself as the floor.

| framework | binary | startup ext ms | interact p50 ms | interact p95 ms | interact p99 ms | PSS idle (RSS) | PSS post |
|---|---|---|---|---|---|---|---|
| lumen | 22.4 MiB rt +9.3 KiB app | 123.9 +/-0.5 (1o) | 16.51 (0.00, min 16.51) | 17.00 (0.00, min 17.00) | 17.02 (0.01, min 17.01) | 68.9 (180.9) | 71.6 (184.8) |
| slint | 23.6 MiB | 80.2 +/-6.3 (!) | 16.66 (0.03, min 16.64) | 17.08 (0.23, min 17.03) | 17.65 (0.99, min 17.60) | 53.7 (162.8) | 56.0 (165.6) |
| egui | 19.1 MiB | 61.2 +/-1.2 (1o) | 16.67 (0.00, min 16.66) | 16.72 (0.01, min 16.72) | 16.84 (0.01, min 16.83) | 49.3 (153.8) | 49.6 (154.1) |
| iced | 14.6 MiB | 180.9 +/-26.0 (!) (1o) | 16.73 (0.04, min 16.73) | 30.52 (8.06, min 23.93) | 34.31 (1.06, min 34.26) | 57.6 (163.9) | 58.2 (164.4) |
| qt-widgets | 0.3 MiB | 49.2 +/-6.5 (!) | 15.73 (0.02, min 15.72) | 16.75 (0.04, min 16.73) | 19.67 (1.79, min 18.01) | 24.2 (42.0) | 25.9 (44.0) |
| gtk4 | 0.0 MiB | 66.0 +/-4.1 (!) (2o) | 16.66 (0.01, min 16.66) | 16.93 (0.07, min 16.89) | 17.34 (1.09, min 16.97) | 40.5 (137.6) | 39.9 (137.0) |
| flutter | 5.1 MiB | 154.2 +/-5.3 (!) (2o) | 16.78 (0.12, min 16.68) | 18.16 (0.55, min 18.05) | 18.58 (433.34, min 18.43) | 96.1 (225.6) | 99.3 (228.8) |
| tauri | 5.3 MiB | 174.8 +/-4.7 (!) (2o) | 16.00 (0.00, min 16.00) | 17.00 (0.00, min 17.00) | 17.00 (0.00, min 17.00) | 59.1 (204.7) | 59.0 (204.7) |

## list - 10,000-row list scrolled at 1000 px/s

Each frame cell reads `median (spread, min)`: the median across passes, the gap between the best and worst pass, and the best pass itself as the floor.

| framework | binary | startup ext ms | scroll p50 ms | scroll p95 ms | scroll p99 ms | PSS idle (RSS) | PSS post |
|---|---|---|---|---|---|---|---|
| lumen | 22.4 MiB rt +2.4 KiB app | 157.2 +/-12.6 (!) | 16.50 (0.00, min 16.50) | 17.01 (0.00, min 17.00) | 17.01 (0.01, min 17.01) | 83.9 (196.0) | 84.3 (196.3) |
| slint | 22.3 MiB | 57.1 +/-0.5 | 16.67 (0.01, min 16.67) | 16.95 (0.01, min 16.94) | 17.04 (0.03, min 17.04) | 50.3 (159.2) | 51.3 (160.2) |
| egui | 19.0 MiB | 60.0 +/-1.3 (2o) | 16.67 (0.00, min 16.67) | 17.21 (0.36, min 16.98) | 18.38 (0.77, min 17.98) | 50.0 (154.6) | 49.7 (154.2) |
| iced | 14.5 MiB | 241.7 +/-10.7 (!) | 21.28 (0.94, min 21.01) | 28.07 (4.58, min 26.59) | 37.71 (4.59, min 35.35) | 160.2 (265.3) | 159.1 (265.3) |
| qt-widgets | 0.3 MiB | 72.2 +/-4.5 (!) (2o) | 15.99 (0.05, min 15.94) | 17.11 (0.89, min 16.87) | 18.64 (1.28, min 17.61) | 25.2 (42.9) | 24.3 (42.8) |
| gtk4 | 0.0 MiB | 76.9 +/-6.8 (!) | 16.66 (0.05, min 16.66) | 16.88 (9188.64, min 16.84) | 17.09 (9188.56, min 16.92) | 42.6 (139.5) | 42.8 (139.9) |
| flutter | 5.1 MiB | 147.8 +/-3.0 (2o) | 16.74 (0.29, min 16.72) | 18.05 (43.86, min 17.42) | 18.40 (5567.19, min 18.12) | 78.1 (206.8) | 89.4 (218.9) |
| tauri | 5.3 MiB | 160.6 +/-5.8 (!) | 16.00 (0.00, min 16.00) | 17.00 (2.00, min 17.00) | 17.00 (5.00, min 17.00) | 59.0 (204.3) | 58.2 (204.6) |

## textview - 5,000 wrapped paragraphs (~1.1 MiB) scrolled at 1000 px/s

Each frame cell reads `median (spread, min)`: the median across passes, the gap between the best and worst pass, and the best pass itself as the floor.

| framework | binary | startup ext ms | scroll p50 ms | scroll p95 ms | scroll p99 ms | PSS idle (RSS) | PSS post |
|---|---|---|---|---|---|---|---|
| lumen | 22.4 MiB rt +1367.8 KiB app | 208.1 +/-1.3 | 16.68 (0.01, min 16.68) | 17.02 (0.06, min 16.99) | 17.57 (0.44, min 17.17) | 113.8 (225.8) | 113.1 (225.2) |
| slint | 19.3 MiB | 1638.6 +/-175.5 (!) | 166.95 (33.25, min 163.69) | 198.69 (14.55, min 193.47) | 199.60 (20.22, min 193.66) | 209.5 (318.6) | 214.2 (323.2) |
| egui | 18.8 MiB | 240.3 +/-9.2 (!) (3o) | 16.67 (0.00, min 16.66) | 16.74 (0.01, min 16.74) | 17.14 (0.60, min 16.91) | 250.4 (354.9) | 250.6 (354.8) |
| iced | 14.4 MiB | 649.4 +/-36.1 (!) (1o) | 48.79 (11.63, min 48.55) | 65.93 (18.32, min 62.53) | 72.77 (31.28, min 67.52) | 382.4 (488.6) | 382.7 (488.9) |
| qt-widgets | 0.3 MiB | 54.4 +/-9.8 (!) (1o) | 15.77 (0.02, min 15.76) | 16.75 (0.04, min 16.73) | 28.50 (16.39, min 26.70) | 90.8 (109.4) | 90.9 (109.5) |
| gtk4 | 0.0 MiB | 68.4 +/-0.9 (1o) | 16.66 (0.01, min 16.66) | 17.24 (0.08, min 17.18) | 17.58 (0.19, min 17.46) | 39.8 (136.8) | 41.0 (138.1) |
| flutter | 5.1 MiB | 542.2 +/-12.0 (2o) | 16.73 (0.08, min 16.68) | 18.38 (0.39, min 18.35) | 19.34 (0.34, min 19.09) | 336.0 (464.8) | 344.3 (473.1) |
| tauri | 5.3 MiB | 246.1 +/-3.5 | 16.00 (0.00, min 16.00) | 17.00 (0.00, min 17.00) | 17.00 (0.00, min 17.00) | 60.9 (206.4) | 60.6 (206.0) |

## Startup detail (external, ms)

External startup is process spawn to the first presented frame, measured identically for all eight frameworks. This is the one metric where the report carries confidence intervals, because it is the one most often quoted as a single number.

### hello

| framework | median ms | IQR (MAD) | min | 95% CI | outliers | n |
|---|---|---|---|---|---|---|
| slint | 51.3 | 0.7 (0.4) | 50.2 | 50.8-51.7 | 0 | 15 |
| qt-widgets | 54.9 (!) | 12.4 (6.9) | 34.1 | 48.0-58.3 | 0 | 15 |
| gtk4 | 55.1 (!) (2o) | 4.0 (2.1) | 52.2 | 53.0-57.2 | 2 | 15 |
| egui | 58.6 (!) (1o) | 3.9 (2.6) | 45.4 | 55.2-59.6 | 1 | 15 |
| iced | 92.1 (!) | 7.5 (1.6) | 74.6 | 85.6-93.2 | 0 | 15 |
| lumen | 104.1 (1o) | 0.9 (0.5) | 102.7 | 104.0-104.9 | 1 | 15 |
| flutter | 126.8 (!) (1o) | 6.7 (3.4) | 117.5 | 125.2-132.2 | 1 | 15 |
| tauri | 163.9 (!) (1o) | 30.7 (9.0) | 153.0 | 156.1-194.6 | 1 | 15 |

Intervals overlap for slint/qt-widgets, qt-widgets/gtk4, qt-widgets/egui, gtk4/egui. The data does not separate those pairs; read them as the same startup time.

### list

| framework | median ms | IQR (MAD) | min | 95% CI | outliers | n |
|---|---|---|---|---|---|---|
| slint | 57.1 | 1.0 (0.5) | 55.9 | 56.6-57.6 | 0 | 15 |
| egui | 60.0 (2o) | 2.6 (1.4) | 48.5 | 58.5-61.3 | 2 | 15 |
| qt-widgets | 72.2 (!) (2o) | 9.0 (5.4) | 53.6 | 67.1-77.6 | 2 | 15 |
| gtk4 | 76.9 (!) | 13.7 (6.8) | 69.3 | 70.2-85.9 | 0 | 15 |
| flutter | 147.8 (2o) | 5.9 (3.5) | 141.2 | 145.6-152.5 | 2 | 15 |
| lumen | 157.2 (!) | 25.1 (14.2) | 139.2 | 141.8-168.2 | 0 | 15 |
| tauri | 160.6 (!) | 11.6 (4.4) | 156.0 | 158.4-174.1 | 0 | 15 |
| iced | 241.7 (!) | 21.5 (8.8) | 196.2 | 232.9-250.1 | 0 | 15 |

Intervals overlap for qt-widgets/gtk4, flutter/lumen, lumen/tauri. The data does not separate those pairs; read them as the same startup time.

### forms

| framework | median ms | IQR (MAD) | min | 95% CI | outliers | n |
|---|---|---|---|---|---|---|
| qt-widgets | 49.2 (!) | 12.9 (6.4) | 38.7 | 46.0-54.7 | 0 | 15 |
| egui | 61.2 (1o) | 2.5 (1.5) | 55.9 | 59.7-62.0 | 1 | 15 |
| gtk4 | 66.0 (!) (2o) | 8.2 (1.2) | 62.8 | 64.8-79.1 | 2 | 15 |
| slint | 80.2 (!) | 12.5 (6.1) | 63.9 | 75.9-88.9 | 0 | 15 |
| lumen | 123.9 (1o) | 1.1 (0.5) | 122.4 | 123.6-124.6 | 1 | 15 |
| flutter | 154.2 (!) (2o) | 10.6 (3.3) | 149.4 | 151.4-165.8 | 2 | 15 |
| tauri | 174.8 (!) (2o) | 9.5 (3.8) | 170.8 | 172.1-183.4 | 2 | 15 |
| iced | 180.9 (!) (1o) | 52.0 (30.0) | 126.2 | 149.1-200.4 | 1 | 15 |

Intervals overlap for gtk4/slint, flutter/iced, tauri/iced. The data does not separate those pairs; read them as the same startup time.

### textview

| framework | median ms | IQR (MAD) | min | 95% CI | outliers | n |
|---|---|---|---|---|---|---|
| qt-widgets | 54.4 (!) (1o) | 19.6 (10.2) | 40.3 | 44.3-66.1 | 1 | 15 |
| gtk4 | 68.4 (1o) | 1.9 (0.8) | 65.3 | 67.7-69.1 | 1 | 15 |
| lumen | 208.1 | 2.5 (1.7) | 204.3 | 205.9-208.6 | 0 | 15 |
| egui | 240.3 (!) (3o) | 18.3 (5.0) | 231.2 | 237.2-258.5 | 3 | 15 |
| tauri | 246.1 | 7.1 (4.0) | 234.5 | 241.6-248.3 | 0 | 15 |
| flutter | 542.2 (2o) | 24.0 (7.5) | 523.0 | 535.6-572.3 | 2 | 15 |
| iced | 649.4 (!) (1o) | 72.1 (34.2) | 501.0 | 618.5-694.8 | 1 | 15 |
| slint | 1638.6 (!) | 351.0 (229.1) | 1189.1 | 1382.8-1729.9 | 0 | 15 |

Intervals overlap for egui/tauri. The data does not separate those pairs; read them as the same startup time.

## Calibration - bounding systematic error

Each line is median ms, then half the IQR as the spread, the minimum, and the confidence interval where one is available.

* spawn->marker floor (trivial C binary, n=30): **0.81 (!) (1o) ms** +/-0.03, min 0.68, CI 0.79-0.82. Harness plus fork/exec overhead, baked identically into every external startup number.
* harness-vs-kernel spawn timestamp (independent, /proc starttime): **-0.38 (2o) ms** +/-0.02. Bounds the harness's spawn-anchor error.
* marker pipe latency (app clock vs harness clock): **0.02 (!) ms** +/-0.00, CI 0.02-0.02. Bounds marker-arrival skew.
* Consequence: cross-framework startup deltas below ~1 ms are inside the systematic error band and not meaningful, whatever the medians say.

## Run-to-run agreement (run 1 vs run 2)

The same matrix was measured twice. For each headline number, agreement is the **relative difference** of the two runs' medians: the gap between them divided by their average. A metric agrees when that difference is at or below **5%**. A metric that disagrees is not necessarily wrong, but its single-run number should not be quoted to better than the difference shown.

95/136 metrics agree within 5%.

Over threshold (41), largest first (top 15; the rest are in the table below):

* **iced/forms interact p99_ms**: 34.309 vs 454.428 (171.9% apart)
* **qt-widgets/list startup ext ms**: 72.219 vs 17.743 (121.1% apart)
* **qt-widgets/hello startup ext ms**: 54.917 vs 17.926 (101.6% apart)
* **iced/forms startup ext ms**: 180.945 vs 62.311 (97.5% apart)
* **qt-widgets/forms startup ext ms**: 49.244 vs 18.694 (89.9% apart)
* **iced/list scroll p99_ms**: 37.711 vs 19.185 (65.1% apart)
* **qt-widgets/textview startup ext ms**: 54.43 vs 27.938 (64.3% apart)
* **iced/textview startup ext ms**: 649.397 vs 385.064 (51.1% apart)
* **egui/forms startup ext ms**: 61.236 vs 37.68 (47.6% apart)
* **egui/hello startup ext ms**: 58.554 vs 36.213 (47.1% apart)
* **iced/hello startup ext ms**: 92.066 vs 57.691 (45.9% apart)
* **egui/list startup ext ms**: 59.966 vs 38.349 (44.0% apart)
* **iced/list scroll p95_ms**: 28.072 vs 18.074 (43.3% apart)
* **iced/list startup ext ms**: 241.688 vs 157.455 (42.2% apart)
* **slint/textview startup ext ms**: 1638.615 vs 1076.748 (41.4% apart)

| framework | app | metric | run 1 | run 2 | abs delta | rel diff | within threshold |
|---|---|---|---|---|---|---|---|
| lumen | hello | startup ext ms | 104.108 | 109.639 | 5.531 | 5.2% | no |
| lumen | hello | idle PSS kB | 64394 | 63647 | 747 | 1.2% | yes |
| lumen | list | startup ext ms | 157.181 | 145.566 | 11.615 | 7.7% | no |
| lumen | list | scroll p50_ms | 16.504 | 16.507 | 0.003 | 0.0% | yes |
| lumen | list | scroll p95_ms | 17.006 | 17.015 | 0.009 | 0.1% | yes |
| lumen | list | scroll p99_ms | 17.013 | 17.04 | 0.027 | 0.2% | yes |
| lumen | list | idle PSS kB | 85958 | 85491 | 467 | 0.5% | yes |
| lumen | forms | startup ext ms | 123.915 | 148.803 | 24.888 | 18.2% | no |
| lumen | forms | interact p50_ms | 16.507 | 16.511 | 0.004 | 0.0% | yes |
| lumen | forms | interact p95_ms | 17.003 | 17.005 | 0.002 | 0.0% | yes |
| lumen | forms | interact p99_ms | 17.018 | 17.028 | 0.01 | 0.1% | yes |
| lumen | forms | idle PSS kB | 70557 | 69929 | 628 | 0.9% | yes |
| lumen | textview | startup ext ms | 208.129 | 211.215 | 3.086 | 1.5% | yes |
| lumen | textview | scroll p50_ms | 16.679 | 16.679 | 0.0 | 0.0% | yes |
| lumen | textview | scroll p95_ms | 17.017 | 17.192 | 0.175 | 1.0% | yes |
| lumen | textview | scroll p99_ms | 17.574 | 17.652 | 0.078 | 0.4% | yes |
| lumen | textview | idle PSS kB | 116503 | 114883 | 1620 | 1.4% | yes |
| slint | hello | startup ext ms | 51.277 | 52.214 | 0.937 | 1.8% | yes |
| slint | hello | idle PSS kB | 48585 | 47636 | 949 | 2.0% | yes |
| slint | list | startup ext ms | 57.117 | 58.916 | 1.799 | 3.1% | yes |
| slint | list | scroll p50_ms | 16.669 | 16.669 | 0.0 | 0.0% | yes |
| slint | list | scroll p95_ms | 16.945 | 17.003 | 0.058 | 0.3% | yes |
| slint | list | scroll p99_ms | 17.044 | 17.121 | 0.077 | 0.4% | yes |
| slint | list | idle PSS kB | 51504 | 50581 | 923 | 1.8% | yes |
| slint | forms | startup ext ms | 80.226 | 65.881 | 14.345 | 19.6% | no |
| slint | forms | interact p50_ms | 16.655 | 16.663 | 0.008 | 0.1% | yes |
| slint | forms | interact p95_ms | 17.081 | 17.073 | 0.008 | 0.1% | yes |
| slint | forms | interact p99_ms | 17.65 | 17.464 | 0.186 | 1.1% | yes |
| slint | forms | idle PSS kB | 55018 | 53698 | 1320 | 2.4% | yes |
| slint | textview | startup ext ms | 1638.615 | 1076.748 | 561.867 | 41.4% | no |
| slint | textview | scroll p50_ms | 166.951 | 144.512 | 22.439 | 14.4% | no |
| slint | textview | scroll p95_ms | 198.69 | 147.316 | 51.374 | 29.7% | no |
| slint | textview | scroll p99_ms | 199.602 | 150.024 | 49.578 | 28.4% | no |
| slint | textview | idle PSS kB | 214570 | 213631 | 939 | 0.4% | yes |
| egui | hello | startup ext ms | 58.554 | 36.213 | 22.341 | 47.1% | no |
| egui | hello | idle PSS kB | 49604 | 48620 | 984 | 2.0% | yes |
| egui | list | startup ext ms | 59.966 | 38.349 | 21.617 | 44.0% | no |
| egui | list | scroll p50_ms | 16.666 | 16.659 | 0.007 | 0.0% | yes |
| egui | list | scroll p95_ms | 17.211 | 16.77 | 0.441 | 2.6% | yes |
| egui | list | scroll p99_ms | 18.378 | 16.813 | 1.565 | 8.9% | no |
| egui | list | idle PSS kB | 51241 | 49335 | 1906 | 3.8% | yes |
| egui | forms | startup ext ms | 61.236 | 37.68 | 23.556 | 47.6% | no |
| egui | forms | interact p50_ms | 16.667 | 16.662 | 0.005 | 0.0% | yes |
| egui | forms | interact p95_ms | 16.722 | 16.75 | 0.028 | 0.2% | yes |
| egui | forms | interact p99_ms | 16.836 | 16.814 | 0.022 | 0.1% | yes |
| egui | forms | idle PSS kB | 50492 | 49764 | 728 | 1.5% | yes |
| egui | textview | startup ext ms | 240.257 | 239.474 | 0.783 | 0.3% | yes |
| egui | textview | scroll p50_ms | 16.666 | 16.663 | 0.003 | 0.0% | yes |
| egui | textview | scroll p95_ms | 16.736 | 16.751 | 0.015 | 0.1% | yes |
| egui | textview | scroll p99_ms | 17.137 | 16.816 | 0.321 | 1.9% | yes |
| egui | textview | idle PSS kB | 256364 | 255833 | 531 | 0.2% | yes |
| iced | hello | startup ext ms | 92.066 | 57.691 | 34.375 | 45.9% | no |
| iced | hello | idle PSS kB | 59401 | 58916 | 485 | 0.8% | yes |
| iced | list | startup ext ms | 241.688 | 157.455 | 84.233 | 42.2% | no |
| iced | list | scroll p50_ms | 21.278 | 16.606 | 4.672 | 24.7% | no |
| iced | list | scroll p95_ms | 28.072 | 18.074 | 9.998 | 43.3% | no |
| iced | list | scroll p99_ms | 37.711 | 19.185 | 18.526 | 65.1% | no |
| iced | list | idle PSS kB | 164077 | 163627 | 450 | 0.3% | yes |
| iced | forms | startup ext ms | 180.945 | 62.311 | 118.634 | 97.5% | no |
| iced | forms | interact p50_ms | 16.735 | 16.67 | 0.065 | 0.4% | yes |
| iced | forms | interact p95_ms | 30.518 | 32.708 | 2.19 | 6.9% | no |
| iced | forms | interact p99_ms | 34.309 | 454.428 | 420.119 | 171.9% | no |
| iced | forms | idle PSS kB | 58960 | 59871 | 911 | 1.5% | yes |
| iced | textview | startup ext ms | 649.397 | 385.064 | 264.333 | 51.1% | no |
| iced | textview | scroll p50_ms | 48.79 | 44.766 | 4.024 | 8.6% | no |
| iced | textview | scroll p95_ms | 65.93 | 47.363 | 18.567 | 32.8% | no |
| iced | textview | scroll p99_ms | 72.768 | 49.764 | 23.004 | 37.5% | no |
| iced | textview | idle PSS kB | 391600 | 392931 | 1331 | 0.3% | yes |
| qt-widgets | hello | startup ext ms | 54.917 | 17.926 | 36.991 | 101.6% | no |
| qt-widgets | hello | idle PSS kB | 24189 | 22236 | 1953 | 8.4% | no |
| qt-widgets | list | startup ext ms | 72.219 | 17.743 | 54.476 | 121.1% | no |
| qt-widgets | list | scroll p50_ms | 15.99 | 15.71 | 0.28 | 1.8% | yes |
| qt-widgets | list | scroll p95_ms | 17.114 | 16.71 | 0.404 | 2.4% | yes |
| qt-widgets | list | scroll p99_ms | 18.642 | 16.772 | 1.87 | 10.6% | no |
| qt-widgets | list | idle PSS kB | 25794 | 23847 | 1947 | 7.8% | no |
| qt-widgets | forms | startup ext ms | 49.244 | 18.694 | 30.55 | 89.9% | no |
| qt-widgets | forms | interact p50_ms | 15.729 | 15.717 | 0.012 | 0.1% | yes |
| qt-widgets | forms | interact p95_ms | 16.75 | 19.515 | 2.765 | 15.2% | no |
| qt-widgets | forms | interact p99_ms | 19.67 | 19.805 | 0.135 | 0.7% | yes |
| qt-widgets | forms | idle PSS kB | 24819 | 25027 | 208 | 0.8% | yes |
| qt-widgets | textview | startup ext ms | 54.43 | 27.938 | 26.492 | 64.3% | no |
| qt-widgets | textview | scroll p50_ms | 15.769 | 15.724 | 0.045 | 0.3% | yes |
| qt-widgets | textview | scroll p95_ms | 16.755 | 16.726 | 0.029 | 0.2% | yes |
| qt-widgets | textview | scroll p99_ms | 28.505 | 27.419 | 1.086 | 3.9% | yes |
| qt-widgets | textview | idle PSS kB | 93011 | 93357 | 346 | 0.4% | yes |
| gtk4 | hello | startup ext ms | 55.082 | 51.474 | 3.608 | 6.8% | no |
| gtk4 | hello | idle PSS kB | 39116 | 38763 | 353 | 0.9% | yes |
| gtk4 | list | startup ext ms | 76.946 | 68.185 | 8.761 | 12.1% | no |
| gtk4 | list | scroll p50_ms | 16.663 | 16.665 | 0.002 | 0.0% | yes |
| gtk4 | list | scroll p95_ms | 16.876 | 16.86 | 0.016 | 0.1% | yes |
| gtk4 | list | scroll p99_ms | 17.092 | 16.946 | 0.146 | 0.9% | yes |
| gtk4 | list | idle PSS kB | 43585 | 44201 | 616 | 1.4% | yes |
| gtk4 | forms | startup ext ms | 65.975 | 61.945 | 4.03 | 6.3% | no |
| gtk4 | forms | interact p50_ms | 16.66 | 16.662 | 0.002 | 0.0% | yes |
| gtk4 | forms | interact p95_ms | 16.929 | 16.872 | 0.057 | 0.3% | yes |
| gtk4 | forms | interact p99_ms | 17.344 | 17.09 | 0.254 | 1.5% | yes |
| gtk4 | forms | idle PSS kB | 41508 | 41308 | 200 | 0.5% | yes |
| gtk4 | textview | startup ext ms | 68.385 | 67.029 | 1.356 | 2.0% | yes |
| gtk4 | textview | scroll p50_ms | 16.665 | 16.674 | 0.009 | 0.1% | yes |
| gtk4 | textview | scroll p95_ms | 17.236 | 17.174 | 0.062 | 0.4% | yes |
| gtk4 | textview | scroll p99_ms | 17.583 | 17.478 | 0.105 | 0.6% | yes |
| gtk4 | textview | idle PSS kB | 40752 | 41450 | 698 | 1.7% | yes |
| flutter | hello | startup ext ms | 126.834 | 118.725 | 8.109 | 6.6% | no |
| flutter | hello | idle PSS kB | 80038 | 84421 | 4383 | 5.3% | no |
| flutter | list | startup ext ms | 147.847 | 141.969 | 5.878 | 4.1% | yes |
| flutter | list | scroll p50_ms | 16.738 | 16.795 | 0.057 | 0.3% | yes |
| flutter | list | scroll p95_ms | 18.054 | 18.093 | 0.039 | 0.2% | yes |
| flutter | list | scroll p99_ms | 18.398 | 18.239 | 0.159 | 0.9% | yes |
| flutter | list | idle PSS kB | 79944 | 87237 | 7293 | 8.7% | no |
| flutter | forms | startup ext ms | 154.245 | 150.427 | 3.818 | 2.5% | yes |
| flutter | forms | interact p50_ms | 16.78 | 16.719 | 0.061 | 0.4% | yes |
| flutter | forms | interact p95_ms | 18.165 | 18.32 | 0.155 | 0.9% | yes |
| flutter | forms | interact p99_ms | 18.576 | 18.615 | 0.039 | 0.2% | yes |
| flutter | forms | idle PSS kB | 98392 | 97450 | 942 | 1.0% | yes |
| flutter | textview | startup ext ms | 542.244 | 499.062 | 43.182 | 8.3% | no |
| flutter | textview | scroll p50_ms | 16.725 | 16.791 | 0.066 | 0.4% | yes |
| flutter | textview | scroll p95_ms | 18.38 | 18.255 | 0.125 | 0.7% | yes |
| flutter | textview | scroll p99_ms | 19.345 | 18.878 | 0.467 | 2.4% | yes |
| flutter | textview | idle PSS kB | 344077 | 343655 | 422 | 0.1% | yes |
| tauri | hello | startup ext ms | 163.928 | 154.928 | 9.0 | 5.7% | no |
| tauri | hello | idle PSS kB | 60406 | 59833 | 573 | 0.9% | yes |
| tauri | list | startup ext ms | 160.554 | 158.748 | 1.806 | 1.1% | yes |
| tauri | list | scroll p50_ms | 16.0 | 16.0 | 0.0 | 0.0% | yes |
| tauri | list | scroll p95_ms | 17.0 | 17.0 | 0.0 | 0.0% | yes |
| tauri | list | scroll p99_ms | 17.0 | 17.0 | 0.0 | 0.0% | yes |
| tauri | list | idle PSS kB | 60433 | 60636 | 203 | 0.3% | yes |
| tauri | forms | startup ext ms | 174.783 | 198.207 | 23.424 | 12.6% | no |
| tauri | forms | interact p50_ms | 16.0 | 16.0 | 0.0 | 0.0% | yes |
| tauri | forms | interact p95_ms | 17.0 | 17.0 | 0.0 | 0.0% | yes |
| tauri | forms | interact p99_ms | 17.0 | 17.0 | 0.0 | 0.0% | yes |
| tauri | forms | idle PSS kB | 60530 | 60613 | 83 | 0.1% | yes |
| tauri | textview | startup ext ms | 246.127 | 244.782 | 1.345 | 0.5% | yes |
| tauri | textview | scroll p50_ms | 16.0 | 16.0 | 0.0 | 0.0% | yes |
| tauri | textview | scroll p95_ms | 17.0 | 17.0 | 0.0 | 0.0% | yes |
| tauri | textview | scroll p99_ms | 17.0 | 17.0 | 0.0 | 0.0% | yes |
| tauri | textview | idle PSS kB | 62353 | 62519 | 166 | 0.3% | yes |

### Clock sources

| framework | first-frame proxy | frame timestamps | clock |
|---|---|---|---|
| lumen | stdout `first_frame` marker on first on-screen present (spawn->marker, same as the native apps) | scroll/interact: reconstructed from MCP frame counter (0.5 ms sampling) | startup external: harness CLOCK_MONOTONIC; startup self: app CLOCK_MONOTONIC exec->first-frame (`startup_ms:`); frame deltas: harness CLOCK_MONOTONIC |
| slint | rendering notifier `AfterRendering` (frame submitted) | rendering notifier | `std::time::Instant` (CLOCK_MONOTONIC) |
| egui | end of first `App::update` pass | top of every update pass | `std::time::Instant` (CLOCK_MONOTONIC) |
| iced | first `window::frames()` delivery | `window::frames()` deliveries | `std::time::Instant` (CLOCK_MONOTONIC) |
| qt-widgets | first `paintEvent` on the top-level widget | list/textview: viewport Paint events; forms: `UpdateRequest` on the QWindow (one per backing-store sync) | `std::chrono::steady_clock` (CLOCK_MONOTONIC) |
| gtk4 | GdkFrameClock `after-paint` | GdkFrameClock `after-paint` | `g_get_monotonic_time` (CLOCK_MONOTONIC) |
| flutter | first `addPostFrameCallback` (engine presented frame 1) | one `SchedulerBinding` persistent frame callback per rendered frame | Dart `Stopwatch` (CLOCK_MONOTONIC) |
| tauri | first `requestAnimationFrame` after initial DOM paint | `performance.now()` per `requestAnimationFrame` in the webview | startup: Rust `Instant`; frame deltas: JS `performance.now()` (1 ms-clamped) |

The harness itself timestamps with Python `time.monotonic()`
(CLOCK_MONOTONIC). Every clock in the table is the same kernel clock, so
cross-source skew is scheduling/pipe latency, bounded by the calibration
section.

## Fairness / equivalence caveats

Same app specs everywhere (800x600 "Bench" window, release builds,
stripped binaries):

* **hello**: one bold "Hello" label + one "Press" button, centered.
* **list**: header (bold title + count button), 10,000-row list
  (bold "Item {i}" + grey "subtitle {i}", 36 px rows), footer (text
  input + 0-100 slider + value label).
* **forms**: header, scrollable settings page: 6 groups, ~40 controls
  (8 text inputs, 8 checkboxes, 4 switches, 2 radio groups x 4, 4
  sliders, 4 dropdowns, 6 buttons), footer status labels that change on
  every interact step.
* **textview**: header + the shared deterministic corpus (5,000
  paragraphs, ~1.1 MiB) word-wrapped in the framework's idiomatic
  long-document widget, scrolled at 1000 px/s.

Known asymmetries, read before quoting numbers:

* **Lumen** runs windowed under the same nested compositor as the other
  five: a real winit window presenting through `weston --renderer=gl` via
  wgpu `AutoVsync`. It shares one present path with the rest; the
  asymmetry of the earlier offscreen `--headless` runs (no compositor at
  all) is gone. Lumen startup includes compiling the `.lmn/.css/.rhai`
  sources (that is how Lumen apps launch today) plus the window
  map/first-present cost the other five also pay. Lumen's size row is the
  generic `lumenc` runtime plus a few KB of app text. Startup is measured
  the same way as the native frameworks: with `LUMEN_BOOT_TRACE=1`,
  lumenc's windowed backend prints a bare `first_frame` stdout line on the
  first on-screen present (the same spawn->marker signal every native bench
  app prints, read the same way) plus `startup_ms:<exec->first-frame ms>`
  from an in-app CLOCK_MONOTONIC; so Lumen reports both an external and a
  self startup number like everyone else, with no MCP connect/poll overhead
  in the path. Only the **scroll/interact frame cadence** is still observed
  externally: Lumen has no in-app per-frame callback by design, so the MCP
  frame counter is sampled every 0.5 ms over a persistent connection
  (reading it does not wake the parked loop; only injected events do), and
  frame boundaries are reconstructed from counter advances (quantized at
  ~0.5 ms). A headless compositor has no physical display refresh, so
  wgpu's `AutoVsync` present does not reliably block; Lumen's redraw loop
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
  into view and click it; this is real input-pipeline work (hit-testing,
  scrolling) that the other frameworks' direct state writes do not
  perform, so Lumen's interact numbers are an upper bound. A few toggle
  steps near the scroll extremes (rows that cannot be centred in the
  viewport band) do not land; the count is reported as `step_errors` and
  those steps are omitted, not counted as frames.
* **iced** has no virtualized list widget: the 10k rows are a plain
  `Column` in a `scrollable`, rebuilt every view pass; idiomatic iced,
  inherently disadvantaged on the list workload. iced renders through
  wgpu, so under `weston --renderer=gl` its present throttles on the
  compositor (~60 Hz, ~17 ms deltas) rather than free-running as it did
  under the earlier software-renderer compositor (~7 ms); its scroll
  cadence now matches the other frameworks. Its textview lays out the
  full corpus each pass.
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
* **Flutter** renders with its own engine (Impeller/Skia), not the
  system toolkit; the closest analogue to Lumen's own-renderer model.
  Startup(external) includes the engine's warm-up the same neutral
  spawn->`first_frame` way as every native app (no engine pre-warm or
  daemon). Frame timestamps come from a `SchedulerBinding` persistent
  frame callback (one per rendered frame). A bare vsync `Ticker` stalls
  under the headless compositor when a frame carries no damage, so (like
  the Qt/GTK retained variants) a periodic `Timer` (6 ms) drives the
  animation/steps and dirties the tree each tick, forcing a full-surface
  commit every vsync; p50 sits at ~16.7 ms. list is `ListView.builder`
  (virtualized). textview is the whole corpus in one wrapped `Text`
  inside a scroll view (full layout, like Slint/iced, no
  virtualization). Interact: Tab focus-walk advances the real focus
  chain; toggles are direct state writes (checkbox stands in for the
  switch-standin toggles, same as Qt/egui/gtk conceptually; Flutter does
  have a real `Switch`, used here). The four apps share one AOT `libapp.so`
  + runner ELF selected by executable basename.
* **Tauri** renders in the **system webkit2gtk** webview (shared library,
  like Qt/GTK's toolkit); a browser engine, not a native toolkit. First
  paint is the webview's first `requestAnimationFrame`; frame deltas are
  `performance.now()` deltas captured in the rAF loop, clamped to 1 ms
  resolution by WebKit's timer hardening (so Tauri's frame percentiles
  carry a 1 ms granularity floor the native clocks do not). list is a
  hand-rolled windowed/virtualized DOM list (only visible rows
  materialized), for a fair 10k comparison; textview is plain DOM (5,000
  `<p>` in an `overflow:auto` container; the browser paint-culls
  offscreen content, its idiomatic long-document path, not explicit
  virtualization). Interact: focus-walk calls `.focus()` down the real
  focusable chain; toggles are direct DOM state writes (checkbox stands in
  for the switch). `WEBKIT_DISABLE_DMABUF_RENDERER=1` is set by the app so
  first paint is reliable under the nested headless compositor. Memory is
  reported as measured (PSS/RSS of the main process); a webview app also
  runs shared WebKit network/GPU helper processes and links the large
  shared `libwebkit2gtk`; its private footprint (PSS) already discounts
  pages shared with other WebKit users on the box, which no native
  framework here shares.
* Binary sizes are not comparable across linkage models: the Rust apps
  statically link their framework; **Qt**, **GTK4** and **Tauri** sizes
  exclude the dynamically linked toolkit/engine libraries
  (libQt6*/libgtk-4/libwebkit2gtk). **Flutter**'s size is runner ELF +
  the shared AOT `libapp.so`, excluding the ~17 MiB `libflutter` engine
  (the analogue of those toolkit libs); all four Flutter apps share one
  `libapp.so`, so their size rows are identical. Lumen's size is a generic
  runtime, not an app-specific link.
* Startup runs are warm-cache: the discarded warmup launches pay the
  cold-cache cost, and nothing evicts the page cache between recorded
  launches. The optional `--cold` mode evicts file-backed pages of the
  binary + linked libraries + data before every launch, warmup included;
  labeled *partial* cold: anonymous pages, compositor state, and anything
  another process keeps mapped stay warm. No default results use it.
* startup(external) includes the harness's spawn overhead identically
  for every framework, quantified in the calibration section.
  startup(self) starts at the first line of main, so external-self =
  fork/exec + dynamic linking + pre-main init (not available for Lumen).

