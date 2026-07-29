# Cross-framework benchmark results

Generated: 2026-07-23 19:11:43 +0000  
Host: arch | kernel 7.1.3-arch1-2 | 12th Gen Intel(R) Core(TM) i9-12900K (24 cpus)  
Governors: performance | governor pin: 'performance' on cpus [4, 5, 6, 7, 8, 9, 10, 11] | app cpus [4, 5, 6, 7, 8, 9, 10, 11]  
Mesa: mesa 1:26.1.4-1 | display: weston --renderer=gl (nested headless) | all eight windowed | Lumen: 7ee3bbe9bdfe (dirty)

The suite runs the whole matrix twice; each full pass is a run. The tables below report run 1. The run-to-run agreement table near the end checks that a second identical run (run 2) lands within the stated error bars. Values are medians; +/- is half the IQR (interquartile range) for startup (n=15) or half the cross-pass spread for frame percentiles (3 passes). (!) marks an unstable cell (IQR/median > 5%). (No) means N Tukey-fence outliers were kept in the sample, e.g. (2o) = 2 outliers. Memory is PSS (proportional set size) in MiB with RSS (resident set size) in parentheses, both from /proc, idle = first frame + 2 s. In the binary column, Lumen is shown as `<n> MiB rt +<n> KiB app`: rt is the shared lumenc runtime, app is the compiled app payload; every other framework shows a single stripped binary size.

Startup is measured the same way across all eight frameworks: external = harness CLOCK_MONOTONIC spawn -> first `first_frame` stdout marker; self = the app's own CLOCK_MONOTONIC exec/main -> first-frame (`startup_ms:`). This includes Lumen, whose windowed backend emits both markers under `LUMEN_BOOT_TRACE`; there is no MCP (the harness control channel to Lumen) connect/poll in the startup path (MCP drives only the scroll/interact passes). See the clock-sources table and caveats below.

## hello - startup floor, baseline memory, binary size

| framework | version | binary (stripped) | startup ext ms | startup self ms | PSS idle MiB (RSS) | PSS @5 s |
|---|---|---|---|---|---|---|
| lumen | git 7ee3bbe | 22.4 MiB rt +0.7 KiB app | 104.1 +/-0.5 (1o) | 96.0 +/-0.5 (1o) | 62.9 (174.8) | 62.9 (174.8) |
| slint | slint 1.17.1 | 19.4 MiB | 51.3 +/-0.3 | 49.4 +/-0.3 | 47.4 (156.4) | 47.4 (156.4) |
| egui | eframe 0.35.0 | 18.8 MiB | 58.6 +/-1.9 (!) (1o) | 55.5 +/-1.9 (!) (1o) | 48.4 (152.9) | 48.4 (152.9) |
| iced | iced 0.13.1 | 14.3 MiB | 92.1 +/-3.7 (!) | 86.1 +/-3.9 (!) | 58.0 (163.0) | 58.0 (163.0) |
| qt-widgets | Qt6Widgets 6.11.1 | 0.2 MiB | 54.9 +/-6.2 (!) | 35.1 +/-6.0 (!) | 23.6 (41.4) | 23.6 (41.4) |
| gtk4 | gtk4 4.22.4 | 0.0 MiB | 55.1 +/-2.0 (!) (2o) | 41.2 +/-1.6 (!) (2o) | 38.2 (135.2) | 38.2 (135.2) |
| flutter | Flutter 3.44.7 - channel stable - https://github.com/flutter/flutter.git | 5.1 MiB | 126.8 +/-3.4 (!) (1o) | 30.7 +/-0.6 (2o) | 78.2 (206.5) | 83.5 (212.3) |
| tauri | tauri 2.11.5 · webkit2gtk 2.52.5 | 5.3 MiB | 163.9 +/-15.4 (!) (1o) | 138.0 +/-7.4 (!) (2o) | 59.0 (204.3) | 59.0 (204.3) |

## forms - ~40-widget settings page

Interact pass = 4 cycles x (40-step focus walk + 20-step toggle-all), one step per 16 ms; frame-interval percentiles over the pass.

| framework | binary | startup ext ms | interact p50 ms | interact p95 ms | interact p99 ms | PSS idle (RSS) | PSS post |
|---|---|---|---|---|---|---|---|
| lumen | 22.4 MiB rt +9.3 KiB app | 123.9 +/-0.5 (1o) | 16.51 +/-0.00 | 17.00 +/-0.00 | 17.02 +/-0.01 | 68.9 (180.9) | 71.6 (184.8) |
| slint | 23.6 MiB | 80.2 +/-6.3 (!) | 16.66 +/-0.02 | 17.08 +/-0.12 | 17.65 +/-0.49 | 53.7 (162.8) | 56.0 (165.6) |
| egui | 19.1 MiB | 61.2 +/-1.2 (1o) | 16.67 +/-0.00 | 16.72 +/-0.00 | 16.84 +/-0.01 | 49.3 (153.8) | 49.6 (154.1) |
| iced | 14.6 MiB | 180.9 +/-26.0 (!) (1o) | 16.73 +/-0.02 | 30.52 +/-4.03 | 34.31 +/-0.53 | 57.6 (163.9) | 58.2 (164.4) |
| qt-widgets | 0.3 MiB | 49.2 +/-6.5 (!) | 15.73 +/-0.01 | 16.75 +/-0.02 | 19.67 +/-0.90 | 24.2 (42.0) | 25.9 (44.0) |
| gtk4 | 0.0 MiB | 66.0 +/-4.1 (!) (2o) | 16.66 +/-0.01 | 16.93 +/-0.04 | 17.34 +/-0.55 | 40.5 (137.6) | 39.9 (137.0) |
| flutter | 5.1 MiB | 154.2 +/-5.3 (!) (2o) | 16.78 +/-0.06 | 18.16 +/-0.28 | 18.58 +/-216.67 | 96.1 (225.6) | 99.3 (228.8) |
| tauri | 5.3 MiB | 174.8 +/-4.7 (!) (2o) | 16.00 +/-0.00 | 17.00 +/-0.00 | 17.00 +/-0.00 | 59.1 (204.7) | 59.0 (204.7) |

## list - 10,000-row list scrolled at 1000 px/s

| framework | binary | startup ext ms | scroll p50 ms | scroll p95 ms | scroll p99 ms | PSS idle (RSS) | PSS post |
|---|---|---|---|---|---|---|---|
| lumen | 22.4 MiB rt +2.4 KiB app | 157.2 +/-12.6 (!) | 16.50 +/-0.00 | 17.01 +/-0.00 | 17.01 +/-0.00 | 83.9 (196.0) | 84.3 (196.3) |
| slint | 22.3 MiB | 57.1 +/-0.5 | 16.67 +/-0.00 | 16.95 +/-0.00 | 17.04 +/-0.01 | 50.3 (159.2) | 51.3 (160.2) |
| egui | 19.0 MiB | 60.0 +/-1.3 (2o) | 16.67 +/-0.00 | 17.21 +/-0.18 | 18.38 +/-0.39 | 50.0 (154.6) | 49.7 (154.2) |
| iced | 14.5 MiB | 241.7 +/-10.7 (!) | 21.28 +/-0.47 | 28.07 +/-2.29 | 37.71 +/-2.30 | 160.2 (265.3) | 159.1 (265.3) |
| qt-widgets | 0.3 MiB | 72.2 +/-4.5 (!) (2o) | 15.99 +/-0.02 | 17.11 +/-0.44 | 18.64 +/-0.64 | 25.2 (42.9) | 24.3 (42.8) |
| gtk4 | 0.0 MiB | 76.9 +/-6.8 (!) | 16.66 +/-0.03 | 16.88 +/-4594.32 | 17.09 +/-4594.28 | 42.6 (139.5) | 42.8 (139.9) |
| flutter | 5.1 MiB | 147.8 +/-3.0 (2o) | 16.74 +/-0.15 | 18.05 +/-21.93 | 18.40 +/-2783.59 | 78.1 (206.8) | 89.4 (218.9) |
| tauri | 5.3 MiB | 160.6 +/-5.8 (!) | 16.00 +/-0.00 | 17.00 +/-1.00 | 17.00 +/-2.50 | 59.0 (204.3) | 58.2 (204.6) |

## textview - 5,000 wrapped paragraphs (~1.1 MiB) scrolled at 1000 px/s

| framework | binary | startup ext ms | scroll p50 ms | scroll p95 ms | scroll p99 ms | PSS idle (RSS) | PSS post |
|---|---|---|---|---|---|---|---|
| lumen | 22.4 MiB rt +1367.8 KiB app | 208.1 +/-1.3 | 16.68 +/-0.00 | 17.02 +/-0.03 | 17.57 +/-0.22 | 113.8 (225.8) | 113.1 (225.2) |
| slint | 19.3 MiB | 1638.6 +/-175.5 (!) | 166.95 +/-16.63 | 198.69 +/-7.27 | 199.60 +/-10.11 | 209.5 (318.6) | 214.2 (323.2) |
| egui | 18.8 MiB | 240.3 +/-9.2 (!) (3o) | 16.67 +/-0.00 | 16.74 +/-0.01 | 17.14 +/-0.30 | 250.4 (354.9) | 250.6 (354.8) |
| iced | 14.4 MiB | 649.4 +/-36.1 (!) (1o) | 48.79 +/-5.81 | 65.93 +/-9.16 | 72.77 +/-15.64 | 382.4 (488.6) | 382.7 (488.9) |
| qt-widgets | 0.3 MiB | 54.4 +/-9.8 (!) (1o) | 15.77 +/-0.01 | 16.75 +/-0.02 | 28.50 +/-8.19 | 90.8 (109.4) | 90.9 (109.5) |
| gtk4 | 0.0 MiB | 68.4 +/-0.9 (1o) | 16.66 +/-0.01 | 17.24 +/-0.04 | 17.58 +/-0.09 | 39.8 (136.8) | 41.0 (138.1) |
| flutter | 5.1 MiB | 542.2 +/-12.0 (2o) | 16.73 +/-0.04 | 18.38 +/-0.19 | 19.34 +/-0.17 | 336.0 (464.8) | 344.3 (473.1) |
| tauri | 5.3 MiB | 246.1 +/-3.5 | 16.00 +/-0.00 | 17.00 +/-0.00 | 17.00 +/-0.00 | 60.9 (206.4) | 60.6 (206.0) |

## Calibration - bounding systematic error

* spawn->marker floor (trivial C binary, n=30): **0.81 +/-0.03 (!) (1o) ms**; harness+fork/exec overhead baked identically into every external startup number.
* harness-vs-kernel spawn timestamp (independent, /proc starttime): **-0.38 +/-0.02 (2o) ms**; bounds the harness's spawn-anchor error.
* marker pipe latency (app clock vs harness clock): **0.02 +/-0.00 (!) ms**; bounds marker-arrival skew.
* Consequence: cross-framework startup deltas below ~1 ms are inside the systematic error band and not meaningful.

## Run-to-run agreement (run 1 vs run 2)

109/136 headline medians agree within their stated error bars (startup: IQR; frame percentiles: cross-pass spread, floored at 5%; idle PSS: max(3%, 1 MiB)).

| framework | app | metric | run 1 | run 2 | abs delta | error bar | agree |
|---|---|---|---|---|---|---|---|
| lumen | hello | startup ext ms | 104.108 | 109.639 | 5.531 | 6.492 | yes |
| lumen | hello | idle PSS kB | 64394 | 63647 | 747 | 1931.82 | yes |
| lumen | list | startup ext ms | 157.181 | 145.566 | 11.615 | 25.129 | yes |
| lumen | list | scroll p50_ms | 16.504 | 16.507 | 0.003 | 0.825 | yes |
| lumen | list | scroll p95_ms | 17.006 | 17.015 | 0.009 | 0.85 | yes |
| lumen | list | scroll p99_ms | 17.013 | 17.04 | 0.027 | 16.374 | yes |
| lumen | list | idle PSS kB | 85958 | 85491 | 467 | 2578.74 | yes |
| lumen | forms | startup ext ms | 123.915 | 148.803 | 24.888 | 36.273 | yes |
| lumen | forms | interact p50_ms | 16.507 | 16.511 | 0.004 | 0.825 | yes |
| lumen | forms | interact p95_ms | 17.003 | 17.005 | 0.002 | 0.85 | yes |
| lumen | forms | interact p99_ms | 17.018 | 17.028 | 0.01 | 0.851 | yes |
| lumen | forms | idle PSS kB | 70557 | 69929 | 628 | 2116.71 | yes |
| lumen | textview | startup ext ms | 208.129 | 211.215 | 3.086 | 4.929 | yes |
| lumen | textview | scroll p50_ms | 16.679 | 16.679 | 0.0 | 0.834 | yes |
| lumen | textview | scroll p95_ms | 17.017 | 17.192 | 0.175 | 0.851 | yes |
| lumen | textview | scroll p99_ms | 17.574 | 17.652 | 0.078 | 0.879 | yes |
| lumen | textview | idle PSS kB | 116503 | 114883 | 1620 | 3495.09 | yes |
| slint | hello | startup ext ms | 51.277 | 52.214 | 0.937 | 1.313 | yes |
| slint | hello | idle PSS kB | 48585 | 47636 | 949 | 1457.55 | yes |
| slint | list | startup ext ms | 57.117 | 58.916 | 1.799 | 2.58 | yes |
| slint | list | scroll p50_ms | 16.669 | 16.669 | 0.0 | 0.833 | yes |
| slint | list | scroll p95_ms | 16.945 | 17.003 | 0.058 | 0.847 | yes |
| slint | list | scroll p99_ms | 17.044 | 17.121 | 0.077 | 0.852 | yes |
| slint | list | idle PSS kB | 51504 | 50581 | 923 | 1545.12 | yes |
| slint | forms | startup ext ms | 80.226 | 65.881 | 14.345 | 12.512 | no |
| slint | forms | interact p50_ms | 16.655 | 16.663 | 0.008 | 0.833 | yes |
| slint | forms | interact p95_ms | 17.081 | 17.073 | 0.008 | 0.854 | yes |
| slint | forms | interact p99_ms | 17.65 | 17.464 | 0.186 | 0.987 | yes |
| slint | forms | idle PSS kB | 55018 | 53698 | 1320 | 1650.54 | yes |
| slint | textview | startup ext ms | 1638.615 | 1076.748 | 561.867 | 351.004 | no |
| slint | textview | scroll p50_ms | 166.951 | 144.512 | 22.439 | 33.251 | yes |
| slint | textview | scroll p95_ms | 198.69 | 147.316 | 51.374 | 14.549 | no |
| slint | textview | scroll p99_ms | 199.602 | 150.024 | 49.578 | 20.22 | no |
| slint | textview | idle PSS kB | 214570 | 213631 | 939 | 6437.1 | yes |
| egui | hello | startup ext ms | 58.554 | 36.213 | 22.341 | 3.896 | no |
| egui | hello | idle PSS kB | 49604 | 48620 | 984 | 1488.12 | yes |
| egui | list | startup ext ms | 59.966 | 38.349 | 21.617 | 2.57 | no |
| egui | list | scroll p50_ms | 16.666 | 16.659 | 0.007 | 0.833 | yes |
| egui | list | scroll p95_ms | 17.211 | 16.77 | 0.441 | 0.861 | yes |
| egui | list | scroll p99_ms | 18.378 | 16.813 | 1.565 | 0.919 | no |
| egui | list | idle PSS kB | 51241 | 49335 | 1906 | 1537.23 | no |
| egui | forms | startup ext ms | 61.236 | 37.68 | 23.556 | 2.453 | no |
| egui | forms | interact p50_ms | 16.667 | 16.662 | 0.005 | 0.833 | yes |
| egui | forms | interact p95_ms | 16.722 | 16.75 | 0.028 | 0.836 | yes |
| egui | forms | interact p99_ms | 16.836 | 16.814 | 0.022 | 0.842 | yes |
| egui | forms | idle PSS kB | 50492 | 49764 | 728 | 1514.76 | yes |
| egui | textview | startup ext ms | 240.257 | 239.474 | 0.783 | 185.117 | yes |
| egui | textview | scroll p50_ms | 16.666 | 16.663 | 0.003 | 0.833 | yes |
| egui | textview | scroll p95_ms | 16.736 | 16.751 | 0.015 | 0.837 | yes |
| egui | textview | scroll p99_ms | 17.137 | 16.816 | 0.321 | 0.857 | yes |
| egui | textview | idle PSS kB | 256364 | 255833 | 531 | 7690.92 | yes |
| iced | hello | startup ext ms | 92.066 | 57.691 | 34.375 | 743.746 | yes |
| iced | hello | idle PSS kB | 59401 | 58916 | 485 | 1782.03 | yes |
| iced | list | startup ext ms | 241.688 | 157.455 | 84.233 | 21.456 | no |
| iced | list | scroll p50_ms | 21.278 | 16.606 | 4.672 | 1.064 | no |
| iced | list | scroll p95_ms | 28.072 | 18.074 | 9.998 | 4.583 | no |
| iced | list | scroll p99_ms | 37.711 | 19.185 | 18.526 | 4.593 | no |
| iced | list | idle PSS kB | 164077 | 163627 | 450 | 4922.31 | yes |
| iced | forms | startup ext ms | 180.945 | 62.311 | 118.634 | 52.042 | no |
| iced | forms | interact p50_ms | 16.735 | 16.67 | 0.065 | 0.837 | yes |
| iced | forms | interact p95_ms | 30.518 | 32.708 | 2.19 | 16.149 | yes |
| iced | forms | interact p99_ms | 34.309 | 454.428 | 420.119 | 763.986 | yes |
| iced | forms | idle PSS kB | 58960 | 59871 | 911 | 1768.8 | yes |
| iced | textview | startup ext ms | 649.397 | 385.064 | 264.333 | 72.119 | no |
| iced | textview | scroll p50_ms | 48.79 | 44.766 | 4.024 | 11.628 | yes |
| iced | textview | scroll p95_ms | 65.93 | 47.363 | 18.567 | 18.316 | no |
| iced | textview | scroll p99_ms | 72.768 | 49.764 | 23.004 | 31.284 | yes |
| iced | textview | idle PSS kB | 391600 | 392931 | 1331 | 11748.0 | yes |
| qt-widgets | hello | startup ext ms | 54.917 | 17.926 | 36.991 | 12.396 | no |
| qt-widgets | hello | idle PSS kB | 24189 | 22236 | 1953 | 1024 | no |
| qt-widgets | list | startup ext ms | 72.219 | 17.743 | 54.476 | 9.014 | no |
| qt-widgets | list | scroll p50_ms | 15.99 | 15.71 | 0.28 | 0.8 | yes |
| qt-widgets | list | scroll p95_ms | 17.114 | 16.71 | 0.404 | 0.888 | yes |
| qt-widgets | list | scroll p99_ms | 18.642 | 16.772 | 1.87 | 1.282 | no |
| qt-widgets | list | idle PSS kB | 25794 | 23847 | 1947 | 1024 | no |
| qt-widgets | forms | startup ext ms | 49.244 | 18.694 | 30.55 | 12.927 | no |
| qt-widgets | forms | interact p50_ms | 15.729 | 15.717 | 0.012 | 0.786 | yes |
| qt-widgets | forms | interact p95_ms | 16.75 | 19.515 | 2.765 | 3.044 | yes |
| qt-widgets | forms | interact p99_ms | 19.67 | 19.805 | 0.135 | 3.1 | yes |
| qt-widgets | forms | idle PSS kB | 24819 | 25027 | 208 | 1024 | yes |
| qt-widgets | textview | startup ext ms | 54.43 | 27.938 | 26.492 | 19.55 | no |
| qt-widgets | textview | scroll p50_ms | 15.769 | 15.724 | 0.045 | 0.788 | yes |
| qt-widgets | textview | scroll p95_ms | 16.755 | 16.726 | 0.029 | 0.838 | yes |
| qt-widgets | textview | scroll p99_ms | 28.505 | 27.419 | 1.086 | 16.388 | yes |
| qt-widgets | textview | idle PSS kB | 93011 | 93357 | 346 | 2790.33 | yes |
| gtk4 | hello | startup ext ms | 55.082 | 51.474 | 3.608 | 4.031 | yes |
| gtk4 | hello | idle PSS kB | 39116 | 38763 | 353 | 1173.48 | yes |
| gtk4 | list | startup ext ms | 76.946 | 68.185 | 8.761 | 13.691 | yes |
| gtk4 | list | scroll p50_ms | 16.663 | 16.665 | 0.002 | 0.833 | yes |
| gtk4 | list | scroll p95_ms | 16.876 | 16.86 | 0.016 | 9188.643 | yes |
| gtk4 | list | scroll p99_ms | 17.092 | 16.946 | 0.146 | 9188.562 | yes |
| gtk4 | list | idle PSS kB | 43585 | 44201 | 616 | 1307.55 | yes |
| gtk4 | forms | startup ext ms | 65.975 | 61.945 | 4.03 | 8.2 | yes |
| gtk4 | forms | interact p50_ms | 16.66 | 16.662 | 0.002 | 0.833 | yes |
| gtk4 | forms | interact p95_ms | 16.929 | 16.872 | 0.057 | 0.846 | yes |
| gtk4 | forms | interact p99_ms | 17.344 | 17.09 | 0.254 | 1.093 | yes |
| gtk4 | forms | idle PSS kB | 41508 | 41308 | 200 | 1245.24 | yes |
| gtk4 | textview | startup ext ms | 68.385 | 67.029 | 1.356 | 3.614 | yes |
| gtk4 | textview | scroll p50_ms | 16.665 | 16.674 | 0.009 | 0.833 | yes |
| gtk4 | textview | scroll p95_ms | 17.236 | 17.174 | 0.062 | 0.862 | yes |
| gtk4 | textview | scroll p99_ms | 17.583 | 17.478 | 0.105 | 0.879 | yes |
| gtk4 | textview | idle PSS kB | 40752 | 41450 | 698 | 1222.56 | yes |
| flutter | hello | startup ext ms | 126.834 | 118.725 | 8.109 | 6.747 | no |
| flutter | hello | idle PSS kB | 80038 | 84421 | 4383 | 2401.14 | no |
| flutter | list | startup ext ms | 147.847 | 141.969 | 5.878 | 5.933 | yes |
| flutter | list | scroll p50_ms | 16.738 | 16.795 | 0.057 | 0.837 | yes |
| flutter | list | scroll p95_ms | 18.054 | 18.093 | 0.039 | 4282.664 | yes |
| flutter | list | scroll p99_ms | 18.398 | 18.239 | 0.159 | 5766.517 | yes |
| flutter | list | idle PSS kB | 79944 | 87237 | 7293 | 2398.32 | no |
| flutter | forms | startup ext ms | 154.245 | 150.427 | 3.818 | 10.565 | yes |
| flutter | forms | interact p50_ms | 16.78 | 16.719 | 0.061 | 0.839 | yes |
| flutter | forms | interact p95_ms | 18.165 | 18.32 | 0.155 | 0.908 | yes |
| flutter | forms | interact p99_ms | 18.576 | 18.615 | 0.039 | 433.338 | yes |
| flutter | forms | idle PSS kB | 98392 | 97450 | 942 | 2951.76 | yes |
| flutter | textview | startup ext ms | 542.244 | 499.062 | 43.182 | 23.984 | no |
| flutter | textview | scroll p50_ms | 16.725 | 16.791 | 0.066 | 0.836 | yes |
| flutter | textview | scroll p95_ms | 18.38 | 18.255 | 0.125 | 0.919 | yes |
| flutter | textview | scroll p99_ms | 19.345 | 18.878 | 0.467 | 0.967 | yes |
| flutter | textview | idle PSS kB | 344077 | 343655 | 422 | 10322.31 | yes |
| tauri | hello | startup ext ms | 163.928 | 154.928 | 9.0 | 30.739 | yes |
| tauri | hello | idle PSS kB | 60406 | 59833 | 573 | 1812.18 | yes |
| tauri | list | startup ext ms | 160.554 | 158.748 | 1.806 | 11.619 | yes |
| tauri | list | scroll p50_ms | 16.0 | 16.0 | 0.0 | 0.8 | yes |
| tauri | list | scroll p95_ms | 17.0 | 17.0 | 0.0 | 2.0 | yes |
| tauri | list | scroll p99_ms | 17.0 | 17.0 | 0.0 | 5.0 | yes |
| tauri | list | idle PSS kB | 60433 | 60636 | 203 | 1812.99 | yes |
| tauri | forms | startup ext ms | 174.783 | 198.207 | 23.424 | 40.573 | yes |
| tauri | forms | interact p50_ms | 16.0 | 16.0 | 0.0 | 0.8 | yes |
| tauri | forms | interact p95_ms | 17.0 | 17.0 | 0.0 | 0.85 | yes |
| tauri | forms | interact p99_ms | 17.0 | 17.0 | 0.0 | 0.85 | yes |
| tauri | forms | idle PSS kB | 60530 | 60613 | 83 | 1815.9 | yes |
| tauri | textview | startup ext ms | 246.127 | 244.782 | 1.345 | 8.503 | yes |
| tauri | textview | scroll p50_ms | 16.0 | 16.0 | 0.0 | 0.8 | yes |
| tauri | textview | scroll p95_ms | 17.0 | 17.0 | 0.0 | 0.85 | yes |
| tauri | textview | scroll p99_ms | 17.0 | 17.0 | 0.0 | 0.85 | yes |
| tauri | textview | idle PSS kB | 62353 | 62519 | 166 | 1870.59 | yes |

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
* Startup runs are warm-cache (one discarded warmup run per cell; no
  page-cache eviction between runs). The optional `--cold` mode evicts
  file-backed pages of the binary + linked libraries + data before each
  run via posix_fadvise; labeled *partial* cold: anonymous pages,
  compositor state, and anything another process keeps mapped stay warm.
  No default results use it.
* startup(external) includes the harness's spawn overhead identically
  for every framework, quantified in the calibration section.
  startup(self) starts at the first line of main, so external-self =
  fork/exec + dynamic linking + pre-main init (not available for Lumen).

