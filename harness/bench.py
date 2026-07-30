#!/usr/bin/env python3
"""Cross-framework GUI benchmark harness.

Four apps (hello / list / forms / textview), each implemented in eight
frameworks (Lumen, Slint, egui, iced, Qt6 Widgets, GTK4 C, Flutter,
Tauri), measured the same way:

  * startup: process spawn -> first presented frame, repeated
    BENCH_STARTUP_RUNS times (default 20) after BENCH_STARTUP_WARMUP
    discarded launches; median, IQR, MAD, min, bootstrap confidence
    interval on the median, Tukey-fence outlier count
  * scroll (list, textview): 3 passes x 6 s of programmatic scrolling at
    1000 px/s; per-frame deltas -> p50/p95/p99 per pass, cross-pass median
    + spread
  * interact (forms): 3 passes x 4 cycles of (40-step focus walk + 20-step
    toggle-all), one step / 16 ms; same frame-delta stats
  * memory: PSS primary (smaps_rollup) + RSS secondary, at two fixed
    points: idle (2 s after first frame) and post-workload (right after a
    pass ends; for hello, 5 s after first frame); the idle point is
    repeated over BENCH_MEM_RUNS separate launches (default 3)
  * stripped binary size per app

Every metric keeps its raw per-iteration samples in results.json, so any
statistic can be recomputed later without measuring again. Sample counts,
warmup counts and thresholds are environment knobs, recorded next to the
numbers they produced by config_block(); see the Configuration section of
README.md. Outlier and warmup policy are stated once, in OUTLIER_POLICY
and WARMUP_POLICY, and printed into results.md from there. The
statistics themselves live in stats.py, with tests in test_stats.py.

All eight frameworks run windowed under the same nested headless
compositor (weston --backend=headless --renderer=gl, fallback Xvfb);
nothing appears on the desktop. Lumen runs `lumenc run` windowed (real
winit window + wgpu AutoVsync present through weston, like the other
five). Startup is measured identically to the native apps
(spawn->`first_frame` stdout marker + in-app `startup_ms:`, via
LUMEN_BOOT_TRACE); only the scroll/interact frame cadence is observed
over its MCP server (persistent connection, `lumen.tick` sampled every
0.5 ms). See the caveats section of results.md. The GL renderer
accumulates GPU-side state across the many short-lived clients a full
round spawns, so the compositor is restarted at each framework boundary
(and on a wedged pass) to keep every cell on a fresh compositor, the
regime every cell passes in isolation.

Usage:
    harness/bench.py build                    # build + size everything
    harness/bench.py calibrate                # measurement-error anchors
    harness/bench.py measure [fw] [app] [--round N] [--cold]
    harness/bench.py all                      # build + calibrate + one run + report
    harness/bench.py validate                 # calibrate + two runs + agreement
    harness/bench.py report                   # re-render results.md from
                                              # results.json; recorded data
                                              # is read, never rewritten

The suite runs the whole matrix one or more times; each full pass is a run.
--round N selects a pass, 0-indexed internally; results.md labels the first
pass "run 1", the second "run 2", and so on.
"""

import hashlib
import json
import os
import shutil
import signal
import socket
import statistics
import subprocess
import sys
import threading
import time
import queue
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import stats as st  # noqa: E402  (needs the path insert above)

ROOT = HERE.parent
OUT = ROOT / "harness" / "out"
BIN_OUT = OUT / "bin"
CORPUS = OUT / "corpus.txt"
# Output paths. Overridable so a report can be rendered somewhere else
# (CI check, a scratch copy) without touching the repo's files.
RESULTS_JSON = Path(os.environ.get("BENCH_RESULTS_JSON",
                                   str(ROOT / "results.json")))
RESULTS_MD = Path(os.environ.get("BENCH_RESULTS_MD", str(ROOT / "results.md")))

# results.json layout version. 1: startup/calibration samples under
# `runs`, no min/MAD/CI, single idle-memory sample, no per-frame samples.
# 2: samples under `samples`, min/MAD/outlier counts everywhere, bootstrap
# CI on startup medians, repeated idle-memory launches, raw frame deltas,
# recorded sample/warmup counts. The report generator reads both.
SCHEMA_VERSION = 2

# Cargo target dir for the Rust builds here. Kept separate from any
# CARGO_TARGET_DIR the surrounding shell exports: building into a shared
# Lumen target would poison its fingerprints. Override with
# BENCH_CARGO_TARGET_DIR; the default is repo-local and gitignored.
CARGO_TARGET = os.environ.get("BENCH_CARGO_TARGET_DIR",
                              str(OUT / "cargo-target"))
# Path to the Lumen framework checkout. If it is absent, the lumen rows
# are skipped with a note instead of failing the run. Override LUMEN_REPO.
LUMEN_REPO = Path(os.environ.get("LUMEN_REPO", str(ROOT.parent / "Lumen")))
# Flutter builds into flutter/build (gitignored); Tauri builds into its
# own target dir (BENCH_TAURI_TARGET_DIR), off the shared cargo target.
FLUTTER_BUNDLE = (ROOT / "flutter" / "build" / "linux" / "x64" / "release"
                  / "bundle")
TAURI_TARGET = Path(os.environ.get("BENCH_TAURI_TARGET_DIR",
                                   str(OUT / "tauri-target")))
# Must match lumen/*/lumen.toml [mcp].port. Not 7878; other lumenc
# instances (dev tooling) commonly hold the default port.
LUMEN_MCP_PORT = 7941

APPS = ("hello", "list", "forms", "textview")


def _env_int(name, default):
    try:
        return max(0, int(os.environ[name]))
    except (KeyError, ValueError):
        return default


def _env_float(name, default):
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default


def _env_bool(name, default):
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() not in ("0", "false", "no", "off", "")


# --- Sample counts -------------------------------------------------------
# How many times each metric is measured. Every count is recorded in
# results.json under `config`, so a report always states the n behind its
# numbers. Startup dominates wall time: one launch costs roughly
# 0.3 s + the app's own startup, so 20 launches x 32 cells is a few
# minutes of the round.
STARTUP_RUNS = _env_int("BENCH_STARTUP_RUNS", 20)
SCROLL_PASSES = _env_int("BENCH_SCROLL_PASSES", 3)
SCROLL_SECONDS = _env_float("BENCH_SCROLL_SECONDS", 6.0)
SCROLL_PX_PER_S = 1000.0
INTERACT_PASSES = _env_int("BENCH_INTERACT_PASSES", 3)
INTERACT_CYCLES = _env_int("BENCH_INTERACT_CYCLES", 4)
INTERACT_STEP_S = 0.016
MEM_RUNS = _env_int("BENCH_MEM_RUNS", 3)
CALIB_RUNS = _env_int("BENCH_CALIB_RUNS", 30)
LUMEN_SCROLL_INTERVAL_S = 1.0 / 60.0
LUMEN_TICK_SAMPLE_S = 0.0005   # 0.5 ms monotonic lumen.tick sampling

# --- Warmup --------------------------------------------------------------
# Iterations thrown away before recording starts, per metric class. See
# WARMUP_POLICY for what each one is for. Warmup values are still written
# to results.json (as `warmup_samples` / `warmup_frames`), just kept out of
# the statistics.
STARTUP_WARMUP_RUNS = _env_int("BENCH_STARTUP_WARMUP", 1)
CALIB_WARMUP_RUNS = _env_int("BENCH_CALIB_WARMUP", 1)
FRAME_WARMUP_FRAMES = _env_int("BENCH_FRAME_WARMUP_FRAMES", 30)
MEM_WARMUP_RUNS = _env_int("BENCH_MEM_WARMUP", 0)

WARMUP_POLICY = """\
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
  binary (default 1) are discarded, same reason as startup."""

OUTLIER_POLICY = """\
Outliers are counted, never dropped. A sample is an outlier when it falls
outside the Tukey fences: below q1 - 1.5 x IQR or above q3 + 1.5 x IQR,
where q1 and q3 bound the middle half of the samples. The count appears
next to the affected number as `(2o)`, and every sample, outliers
included, stays in results.json. Nothing in the report is computed on a
filtered sample set: the median and the IQR already resist the extremes,
and the outlier count tells you how much interference the run saw."""

# CPU pinning. Measured apps, the compositor, and the harness get
# disjoint CPU sets when the machine has enough cores; on a small machine
# pinning is disabled and everything shares all cores. Set BENCH_APP_CPUS
# to choose the app CPU set explicitly: a single cpu ("4") pins every
# framework to one core for an efficiency comparison; a list ("4,5,6") or
# a range ("4-11") pins to that set. The chosen sets go in the env capture.
N_CPUS = os.cpu_count() or 4


def _parse_cpu_set(spec):
    out = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.update(range(int(a), int(b) + 1))
        else:
            out.add(int(part))
    return {c for c in out if 0 <= c < N_CPUS}


_app_cpus_env = os.environ.get("BENCH_APP_CPUS")
if _app_cpus_env:
    APP_CPUS = _parse_cpu_set(_app_cpus_env) or set(range(N_CPUS))
    _rest = sorted(set(range(N_CPUS)) - APP_CPUS)
    if len(_rest) >= 2:
        _half = max(1, len(_rest) // 2)
        DISPLAY_CPUS = set(_rest[:_half])
        HARNESS_CPUS = set(_rest[_half:])
    elif _rest:
        DISPLAY_CPUS = HARNESS_CPUS = set(_rest)
    else:
        DISPLAY_CPUS = HARNESS_CPUS = set(APP_CPUS)
    CPU_PIN_NOTE = f"BENCH_APP_CPUS={_app_cpus_env}: app cpus {sorted(APP_CPUS)}"
elif N_CPUS >= 16:
    APP_CPUS = set(range(4, 12))
    DISPLAY_CPUS = {2, 3}
    HARNESS_CPUS = set(range(12, 16))
    CPU_PIN_NOTE = f"16+ cores: app cpus {sorted(APP_CPUS)}"
elif N_CPUS >= 8:
    DISPLAY_CPUS = {0, 1}
    HARNESS_CPUS = {N_CPUS - 2, N_CPUS - 1}
    APP_CPUS = set(range(2, N_CPUS - 2))
    CPU_PIN_NOTE = f"{N_CPUS} cores: app cpus {sorted(APP_CPUS)}"
else:
    APP_CPUS = DISPLAY_CPUS = HARNESS_CPUS = set(range(N_CPUS))
    CPU_PIN_NOTE = f"{N_CPUS} cores: pinning disabled, all cpus shared"

WESTON_SOCKET = "wayland-bench"
XVFB_DISPLAY = ":97"

# --- Thresholds ----------------------------------------------------------
# IQR/median above this flags the cell as unstable in the report.
UNSTABLE_IQR_FRACTION = _env_float("BENCH_UNSTABLE_IQR_FRACTION", 0.05)
# Bootstrap confidence interval on startup medians.
CI_CONFIDENCE = _env_float("BENCH_CI_CONFIDENCE", st.DEFAULT_CONFIDENCE)
CI_RESAMPLES = _env_int("BENCH_BOOTSTRAP_RESAMPLES", st.DEFAULT_RESAMPLES)
CI_SEED = _env_int("BENCH_BOOTSTRAP_SEED", st.DEFAULT_SEED)
# Run-to-run agreement: two runs agree on a metric when the relative
# difference of their medians is at or below this fraction.
AGREEMENT_TOLERANCE = _env_float("BENCH_AGREEMENT_TOLERANCE", 0.05)
# Keep raw per-frame deltas in results.json (a full round adds a few MB).
KEEP_FRAME_SAMPLES = _env_bool("BENCH_KEEP_FRAME_SAMPLES", True)


def config_block():
    """Everything that shapes the numbers, recorded next to them."""
    return {
        "schema_version": SCHEMA_VERSION,
        "startup_runs": STARTUP_RUNS,
        "startup_warmup_runs": STARTUP_WARMUP_RUNS,
        "scroll_passes": SCROLL_PASSES,
        "scroll_seconds": SCROLL_SECONDS,
        "interact_passes": INTERACT_PASSES,
        "interact_cycles": INTERACT_CYCLES,
        "frame_warmup_frames": FRAME_WARMUP_FRAMES,
        "mem_runs": MEM_RUNS,
        "mem_warmup_runs": MEM_WARMUP_RUNS,
        "calibration_runs": CALIB_RUNS,
        "calibration_warmup_runs": CALIB_WARMUP_RUNS,
        "lumen_tick_sample_ms": LUMEN_TICK_SAMPLE_S * 1000,
        "unstable_iqr_fraction": UNSTABLE_IQR_FRACTION,
        "ci_confidence": CI_CONFIDENCE,
        "ci_resamples": CI_RESAMPLES,
        "ci_seed": CI_SEED,
        "ci_method": "percentile bootstrap on the median",
        "agreement_tolerance": AGREEMENT_TOLERANCE,
        "outlier_rule": "Tukey fences, k=1.5; counted, kept in the samples",
        "keep_frame_samples": KEEP_FRAME_SAMPLES,
    }


def cargo_env():
    env = os.environ.copy()
    env["CARGO_TARGET_DIR"] = CARGO_TARGET
    return env


# --------------------------------------------------------------------------
# Framework / app table
# --------------------------------------------------------------------------

def fw_bin(fw, app):
    """Executable path for a (framework, app) cell."""
    rel = {
        "lumen": Path(CARGO_TARGET) / "release" / "lumenc",
        "slint": Path(CARGO_TARGET) / "release" / f"bench-slint-{app}",
        "egui": Path(CARGO_TARGET) / "release" / f"bench-egui-{app}",
        "iced": Path(CARGO_TARGET) / "release" / f"bench-iced-{app}",
        "qt-widgets": ROOT / "qt-widgets" / "build" / f"bench_qt_{app}",
        "gtk4": ROOT / "gtk4" / "build" / f"bench_gtk4_{app}",
        # One built binary per framework; per-app hardlinks let the app
        # pick its variant from its own basename (mode still comes from the
        # CLI flag). See flutter/lib/main.dart and tauri/src-tauri/src/main.rs.
        "flutter": FLUTTER_BUNDLE / f"bench_flutter_{app}",
        "tauri": TAURI_TARGET / "release" / f"bench-tauri-{app}",
    }
    return rel[fw]


FRAMEWORKS = ("lumen", "slint", "egui", "iced", "qt-widgets", "gtk4",
              "flutter", "tauri")


def lumen_available():
    """True when the Lumen framework checkout is present (its Cargo.toml
    exists). When absent, the lumen rows are skipped with a note."""
    return (LUMEN_REPO / "Cargo.toml").is_file()


def log(msg):
    print(f"[bench] {msg}", flush=True)


def run_checked(cmd, **kw):
    log("$ " + " ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True, **kw)


# --------------------------------------------------------------------------
# Environment capture
# --------------------------------------------------------------------------

def _read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def _cmd_out(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=10).stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _sha256(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]
    except OSError:
        return None


def try_set_governor(target="performance"):
    """Attempt to pin the app CPUs' cpufreq governor. Usually needs root;
    the failure is recorded, never fatal."""
    changed, failed = [], []
    for cpu in sorted(APP_CPUS):
        p = f"/sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_governor"
        try:
            cur = Path(p).read_text().strip()
            if cur == target:
                changed.append(cpu)
                continue
            Path(p).write_text(target)
            changed.append(cpu)
        except OSError:
            failed.append(cpu)
    if failed:
        return f"not permitted (wanted '{target}'; left as-is on cpus {sorted(failed)})"
    return f"'{target}' on cpus {changed}"


def _cpu_attr(cpu, name):
    return _read(f"/sys/devices/system/cpu/cpu{cpu}/cpufreq/{name}")


def capture_cpu():
    """CPU facts that change the numbers: model, how many cores, which
    ones the apps are pinned to, and how those cores are clocked."""
    model = None
    for line in (_read("/proc/cpuinfo") or "").splitlines():
        if line.startswith("model name"):
            model = line.split(":", 1)[1].strip()
            break
    app_governors = sorted({_cpu_attr(c, "scaling_governor") or "?"
                            for c in sorted(APP_CPUS)})
    max_khz = [int(v) for v in (_cpu_attr(c, "scaling_max_freq")
                                for c in sorted(APP_CPUS)) if v]
    return {
        "model": model,
        "count": N_CPUS,
        "app_cpus": sorted(APP_CPUS),
        "display_cpus": sorted(DISPLAY_CPUS),
        "harness_cpus": sorted(HARNESS_CPUS),
        "pin_note": CPU_PIN_NOTE,
        "pinned_with_taskset": bool(_taskset_prefix()),
        "app_cpu_governors": app_governors,
        "all_governors": sorted({
            _cpu_attr(c, "scaling_governor") or "?" for c in range(N_CPUS)}),
        "scaling_driver": _cpu_attr(sorted(APP_CPUS)[0], "scaling_driver"),
        "app_cpu_max_mhz": (max(max_khz) // 1000) if max_khz else None,
        "cpufreq_boost": _read("/sys/devices/system/cpu/cpufreq/boost"),
        "smt_control": _read("/sys/devices/system/cpu/smt/control"),
    }


def capture_env():
    u = os.uname()
    cpu = capture_cpu()
    meminfo = {}
    for line in (_read("/proc/meminfo") or "").splitlines():
        k, _, v = line.partition(":")
        if k in ("MemTotal", "SwapTotal", "SwapFree"):
            meminfo[k] = v.strip()
    lumen_sha = _cmd_out(["git", "-C", str(LUMEN_REPO), "rev-parse", "HEAD"])
    lumen_dirty = bool(_cmd_out(
        ["git", "-C", str(LUMEN_REPO), "status", "--porcelain"]))
    return {
        "captured": time.strftime("%Y-%m-%d %H:%M:%S %z"),
        "hostname": u.nodename,
        "kernel": u.release,
        "cpu": cpu,
        # Flat aliases kept so a reader (and the schema-1 report path) finds
        # the same facts where they have always been.
        "cpu_model": cpu["model"],
        "cpu_count": cpu["count"],
        "governors": cpu["all_governors"],
        "cpufreq_boost": cpu["cpufreq_boost"],
        "app_cpus": cpu["app_cpus"],
        "display_cpus": cpu["display_cpus"],
        "harness_cpus": cpu["harness_cpus"],
        "cpu_pin_note": CPU_PIN_NOTE,
        "mem": meminfo,
        "loadavg_start": _read("/proc/loadavg"),
        "mesa": _cmd_out(["pacman", "-Q", "mesa"]),
        "host_compositor": os.environ.get("XDG_CURRENT_DESKTOP"),
        "weston": (_cmd_out(["weston", "--version"]) or "").splitlines()[:1],
        "qt": _cmd_out(["pkg-config", "--modversion", "Qt6Widgets"]),
        "gtk4": _cmd_out(["pkg-config", "--modversion", "gtk4"]),
        "webkit2gtk": _cmd_out(["pkg-config", "--modversion", "webkit2gtk-4.1"]),
        "flutter": ((_cmd_out(["flutter", "--version"]) or "").splitlines()
                    or [None])[0],
        "rustc": _cmd_out(["rustc", "-V"]),
        "cc": ((_cmd_out(["cc", "--version"]) or "").splitlines() or [None])[0],
        "cmake": ((_cmd_out(["cmake", "--version"]) or "").splitlines()
                  or [None])[0],
        "python": sys.version.split()[0],
        # Per-framework toolchain versions, captured whether or not this
        # invocation built anything.
        "toolchains": toolkit_versions(),
        "lumen_git": {"sha": lumen_sha, "dirty": lumen_dirty},
        "lockfile_sha256_16": {
            "egui": _sha256(ROOT / "egui" / "Cargo.lock"),
            "iced": _sha256(ROOT / "iced" / "Cargo.lock"),
            "slint": _sha256(ROOT / "slint" / "Cargo.lock"),
            "lumen": _sha256(LUMEN_REPO / "Cargo.lock"),
            "tauri": _sha256(ROOT / "tauri" / "src-tauri" / "Cargo.lock"),
            "flutter": _sha256(ROOT / "flutter" / "pubspec.lock"),
        },
        "corpus_sha256_16": _sha256(CORPUS),
    }


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------

CALIB_C = r"""
/* Calibration probe: prints the first_frame marker immediately, plus its
 * own CLOCK_MONOTONIC timestamp, so the harness can measure its
 * spawn->marker overhead floor independently of any GUI toolkit. */
#include <stdio.h>
#include <time.h>
int main(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    printf("first_frame\n");
    printf("mono_ns: %lld\n",
           (long long)ts.tv_sec * 1000000000LL + ts.tv_nsec);
    fflush(stdout);
    return 0;
}
"""


def _hardlink_variants(src, dsts):
    """Point each dst at src via a hardlink (replacing any stale copy), so
    the four per-app launcher names share the one built inode."""
    for dst in dsts:
        try:
            dst.unlink()
        except OSError:
            pass
        os.link(src, dst)


def _stripped_size(src):
    """Size of a stripped copy of `src` (never strip build outputs in
    place). Returns bytes."""
    dst = BIN_OUT / src.name
    shutil.copy2(src, dst)
    subprocess.run(["strip", str(dst)], check=True)
    return dst.stat().st_size


def _lock_version(lock, pkg):
    """Version of `pkg` as pinned by a Cargo.lock."""
    if not Path(lock).exists():
        return None
    lines = Path(lock).read_text().splitlines()
    for i, l in enumerate(lines):
        if l == f'name = "{pkg}"' and i + 1 < len(lines):
            return lines[i + 1].split('"')[1]
    return None


def toolkit_versions():
    """The toolkit version behind each framework's rows: the thing that
    changes when a number changes for a reason other than the app."""
    versions = {}
    sha = _cmd_out(["git", "-C", str(LUMEN_REPO), "rev-parse", "--short", "HEAD"])
    if sha:
        versions["lumen"] = f"git {sha}"
    for name, pkg in (("slint", "slint"), ("egui", "eframe"), ("iced", "iced")):
        v = _lock_version(ROOT / name / "Cargo.lock", pkg)
        if v:
            versions[name] = f"{pkg} {v}"
    for name, pkg in (("qt-widgets", "Qt6Widgets"), ("gtk4", "gtk4")):
        v = _cmd_out(["pkg-config", "--modversion", pkg])
        if v:
            versions[name] = f"{pkg} {v}"
    fl = (_cmd_out(["flutter", "--version"]) or "").splitlines()
    if fl:
        versions["flutter"] = fl[0].strip()  # e.g. "Flutter 3.44.7 - channel ..."
    # Tauri: crate version from its Cargo.lock + the system webkit2gtk.
    tver = _lock_version(ROOT / "tauri" / "src-tauri" / "Cargo.lock", "tauri")
    wk = _cmd_out(["pkg-config", "--modversion", "webkit2gtk-4.1"])
    parts = []
    if tver:
        parts.append(f"tauri {tver}")
    if wk:
        parts.append(f"webkit2gtk {wk}")
    if parts:
        versions["tauri"] = " - ".join(parts)
    return versions


def _preflight():
    """Log which per-framework toolchains are present. A missing toolchain
    skips that framework during the build; it does not fail the run."""
    tools = (("rust/cargo", "cargo"), ("cmake", "cmake"), ("flutter", "flutter"),
             ("tauri cli (cargo-tauri)", "cargo-tauri"), ("c compiler (cc)", "cc"),
             ("strip", "strip"))
    for label, exe in tools:
        state = "found" if shutil.which(exe) else "missing (frameworks needing it are skipped)"
        log(f"toolchain {label}: {state}")
    log(f"lumen framework at {LUMEN_REPO}: "
        f"{'found' if lumen_available() else 'absent (lumen rows skipped)'}")


def _sizes_for(fw):
    """Stripped-copy sizes for one framework (never strip build outputs in
    place)."""
    s = {}
    if fw == "lumen":
        src = fw_bin("lumen", "x")
        dst = BIN_OUT / src.name
        shutil.copy2(src, dst)
        subprocess.run(["strip", str(dst)], check=True)
        s["runtime_stripped_bytes"] = dst.stat().st_size
        for app in APPS:
            d = ROOT / "lumen" / app
            s[app] = {"app_payload_bytes": sum(
                f.stat().st_size for f in d.iterdir() if f.is_file())}
        return s
    if fw == "flutter":
        # One shared runner ELF + libapp.so (all four apps compile into the
        # same AOT Dart library). Report runner + libapp, without
        # libflutter_linux_gtk.so (the engine; the dynamically linked
        # toolkit, analogous to Qt/GTK excluding libQt6*/libgtk-4).
        runner = _stripped_size(FLUTTER_BUNDLE / "bench_flutter")
        libapp = _stripped_size(FLUTTER_BUNDLE / "lib" / "libapp.so")
        for app in APPS:
            s[app] = {"stripped_bytes": runner + libapp}
        return s
    for app in APPS:
        s[app] = {"stripped_bytes": _stripped_size(fw_bin(fw, app))}
    return s


def build_all():
    BIN_OUT.mkdir(parents=True, exist_ok=True)
    _preflight()

    # Deterministic corpus + generated Lumen textview markup.
    run_checked([sys.executable, str(ROOT / "harness" / "gen_corpus.py")])

    # Calibration probe.
    calib_src = OUT / "calib.c"
    calib_src.write_text(CALIB_C)
    run_checked(["cc", "-O2", "-o", str(BIN_OUT / "calib"), str(calib_src)])

    built = set()

    def stage(name, fn):
        """Run one framework's build; on failure log a skip and continue so
        a missing toolchain never sinks the whole build."""
        try:
            fn()
            built.add(name)
        except Exception as e:
            log(f"skip {name}: build failed or toolchain missing: {e}")

    def _build_lumen():
        # Build the lumenc runner from the framework repo, validate apps.
        if not lumen_available():
            raise RuntimeError(f"Lumen checkout not found at {LUMEN_REPO}")
        run_checked(
            ["cargo", "build", "--release", "-p", "lumenc",
             "--manifest-path", str(LUMEN_REPO / "Cargo.toml")],
            env=cargo_env())
        for app in APPS:
            run_checked([str(fw_bin("lumen", "x")), "check",
                         str(ROOT / "lumen" / app)])
    stage("lumen", _build_lumen)

    for name in ("slint", "egui", "iced"):
        stage(name, lambda name=name: run_checked(
            ["cargo", "build", "--release"], cwd=ROOT / name, env=cargo_env()))

    def _build_cmake(name):
        d = ROOT / name
        run_checked(["cmake", "-S", str(d), "-B", str(d / "build"),
                     "-DCMAKE_BUILD_TYPE=Release"])
        run_checked(["cmake", "--build", str(d / "build"), "-j",
                     str(os.cpu_count() or 4)])
    for name in ("qt-widgets", "gtk4"):
        stage(name, lambda name=name: _build_cmake(name))

    def _build_flutter():
        # One linux-desktop release build; per-app hardlinks next to the
        # runner ELF so the app resolves `data/` + `lib/` and its variant.
        run_checked(["flutter", "build", "linux", "--release"],
                    cwd=ROOT / "flutter")
        _hardlink_variants(FLUTTER_BUNDLE / "bench_flutter",
                           [FLUTTER_BUNDLE / f"bench_flutter_{a}" for a in APPS])
    stage("flutter", _build_flutter)

    def _build_tauri():
        # One release binary (--no-bundle: the harness needs only the
        # executable), into its own target dir; per-app hardlinks.
        tauri_env = os.environ.copy()
        tauri_env["CARGO_TARGET_DIR"] = str(TAURI_TARGET)
        run_checked(["cargo", "tauri", "build", "--no-bundle"],
                    cwd=ROOT / "tauri" / "src-tauri", env=tauri_env)
        _hardlink_variants(TAURI_TARGET / "release" / "bench-tauri",
                           [TAURI_TARGET / "release" / f"bench-tauri-{a}"
                            for a in APPS])
    stage("tauri", _build_tauri)

    # Stripped-copy sizes for the frameworks that built.
    sizes = {}
    for fw in FRAMEWORKS:
        if fw not in built:
            continue
        try:
            sizes[fw] = _sizes_for(fw)
        except Exception as e:
            log(f"skip sizes for {fw}: {e}")

    return sizes, toolkit_versions()


# --------------------------------------------------------------------------
# Headless display
# --------------------------------------------------------------------------

class Display:
    """Nested headless compositor. Prefers weston, falls back to Xvfb."""

    WIDTH = 1280
    HEIGHT = 1024
    # weston's headless backend has no physical display; it drives its
    # output off a timer whose default rate is 60 Hz (--refresh changes
    # it). Xvfb likewise reports a nominal 60 Hz mode. Recorded as
    # nominal, not measured: there is no scanout to measure.
    NOMINAL_REFRESH_HZ = 60

    def __init__(self):
        self.proc = None
        self.xvfb = None
        self.backend = None
        self.command = None

    def describe(self):
        """What the apps presented to, for the environment block."""
        return {
            "backend": self.backend,
            "nested_headless": True,
            "command": " ".join(self.command) if self.command else None,
            "size": f"{self.WIDTH}x{self.HEIGHT}",
            "refresh_hz": self.NOMINAL_REFRESH_HZ,
            "refresh_source": ("nominal: headless output timer, no physical "
                               "display to scan out"),
        }

    def _preexec(self):
        os.setsid()
        try:
            os.sched_setaffinity(0, DISPLAY_CPUS)
        except OSError:
            pass

    def _start_xvfb(self):
        if shutil.which("Xvfb"):
            cmd = ["Xvfb", XVFB_DISPLAY, "-screen", "0",
                   f"{self.WIDTH}x{self.HEIGHT}x24"]
            self.command = cmd
            self.xvfb = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                preexec_fn=self._preexec)
            time.sleep(1.0)
            if self.xvfb.poll() is not None:
                self.xvfb = None

    def start(self):
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        self._start_xvfb()
        if shutil.which("weston"):
            if not Path(runtime_dir).is_dir():
                raise RuntimeError(
                    f"XDG_RUNTIME_DIR ({runtime_dir}) does not exist; weston "
                    "cannot create its socket. Log in on a seat that provides "
                    "it, or export XDG_RUNTIME_DIR to a writable dir.")
            env = os.environ.copy()
            env["XDG_RUNTIME_DIR"] = runtime_dir
            env.pop("WAYLAND_DISPLAY", None)
            # --renderer=gl: weston uses EGL on the real GPU (surfaceless)
            # instead of the noop/pixman software path, so wayland clients
            # get hardware, dmabuf-backed surfaces. Required for Lumen's
            # wgpu-Vulkan present path; under a software renderer the only
            # surface-presentable Vulkan adapter is Lavapipe, which is
            # downlevel and Lumen refuses it. The other five frameworks
            # render fine under GL too (superset of the software path), so
            # all six share one compositor and present path.
            cmd = ["weston", "--backend=headless", "--renderer=gl",
                   f"--socket={WESTON_SOCKET}", f"--width={self.WIDTH}",
                   f"--height={self.HEIGHT}"]
            self.command = cmd
            self.proc = subprocess.Popen(
                cmd, env=env, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, preexec_fn=self._preexec)
            sock = Path(runtime_dir) / WESTON_SOCKET
            for _ in range(100):
                if sock.exists():
                    self.backend = "weston"
                    log(f"weston headless up on {WESTON_SOCKET}")
                    return
                if self.proc.poll() is not None:
                    break
                time.sleep(0.1)
            raise RuntimeError(
                "weston did not create its socket within 10 s. Command: "
                + " ".join(cmd) + f" (XDG_RUNTIME_DIR={runtime_dir}). Check "
                "that a GL-capable GPU/driver is available.")
        if self.xvfb is not None:
            self.backend = "xvfb"
            log(f"Xvfb up on {XVFB_DISPLAY}")
            return
        raise RuntimeError(
            "no usable headless display: neither weston nor Xvfb is "
            "installed. Install weston (preferred) and re-run. Manual "
            "check: weston --backend=headless --renderer=gl "
            f"--socket={WESTON_SOCKET} --width=1280 --height=1024")

    def app_env(self, fw_name):
        env = os.environ.copy()
        # Never let an app reach the real session.
        env.pop("WAYLAND_DISPLAY", None)
        env.pop("DISPLAY", None)
        env["BENCH_SCROLL_SECONDS"] = str(SCROLL_SECONDS)
        env["BENCH_INTERACT_CYCLES"] = str(INTERACT_CYCLES)
        env["BENCH_CORPUS"] = str(CORPUS)
        # Lumen runs windowed under the same nested compositor as the other
        # five (winit picks the wayland backend from WAYLAND_DISPLAY, the x11
        # backend from DISPLAY) so every framework shares one present path
        # and vsync source. The QT/GDK vars are inert for winit.
        if self.backend == "weston":
            env["WAYLAND_DISPLAY"] = WESTON_SOCKET
            env["QT_QPA_PLATFORM"] = "wayland"
            env["GDK_BACKEND"] = "wayland"
        else:
            env["DISPLAY"] = XVFB_DISPLAY
            env["QT_QPA_PLATFORM"] = "xcb"
            env["GDK_BACKEND"] = "x11"
        return env

    def stop(self):
        for p in (self.proc, self.xvfb):
            if p and p.poll() is None:
                os.killpg(p.pid, signal.SIGTERM)
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(p.pid, signal.SIGKILL)
        self.proc = None
        self.xvfb = None
        # Remove any stale weston socket + lock so a subsequent start()
        # (see `restart`) can bind the same name instead of failing.
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        for suffix in ("", ".lock"):
            try:
                os.unlink(os.path.join(runtime_dir, WESTON_SOCKET + suffix))
            except OSError:
                pass

    def restart(self):
        """Tear down and relaunch the compositor from scratch. The GL
        renderer accumulates GPU-side state across the many short-lived
        clients a full round spawns; on a long single-compositor run the
        heaviest later passes (egui/textview, egui/forms, gtk4/list) can
        hit transient allocation/surface-loss failures that the same
        binaries clear cleanly on a fresh compositor. Restarting on a
        clean boundary (between frameworks) keeps each framework's cells
        on a compositor that has served only a handful of clients; the
        regime every cell passes in isolation."""
        self.stop()
        time.sleep(0.5)
        self.start()


# --------------------------------------------------------------------------
# Process helpers
# --------------------------------------------------------------------------

class LineReader:
    """Reads a stream on a thread, queueing (monotonic_ts, line)."""

    def __init__(self, stream):
        self.q = queue.Queue()
        self.t = threading.Thread(target=self._pump, args=(stream,), daemon=True)
        self.t.start()

    def _pump(self, stream):
        for raw in stream:
            self.q.put((time.monotonic(), raw.decode(errors="replace").rstrip("\n")))
        self.q.put((time.monotonic(), None))  # EOF

    def wait_for(self, predicate, timeout):
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return (None, None)
            try:
                ts, line = self.q.get(timeout=remaining)
            except queue.Empty:
                return (None, None)
            if line is None:
                return (None, None)
            if predicate(line):
                return (ts, line)


def _taskset_prefix():
    """Pin measured apps via the taskset wrapper instead of preexec_fn:
    preexec_fn forces CPython onto its slow fork path (full page-table
    copy of the interpreter), which added ~10 ms IQR of spawn jitter to
    external startup numbers."""
    if shutil.which("taskset") and len(APP_CPUS) < N_CPUS:
        cpus = ",".join(str(c) for c in sorted(APP_CPUS))
        return ["taskset", "-c", cpus]
    return []


def app_popen(cmd, env):
    return subprocess.Popen(_taskset_prefix() + cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, env=env,
                            start_new_session=True)


def spawn(fw_name, app, mode_args, display, extra_env=None):
    if fw_name == "lumen":
        # Windowed: real winit window + AutoVsync present through the
        # compositor, same as the other five. Window size comes from the
        # app's lumen.toml [window] (800x600). No --headless (that path
        # renders offscreen with no compositor and no vsync).
        cmd = [str(fw_bin("lumen", app)), "run", str(ROOT / "lumen" / app)]
    else:
        cmd = [str(fw_bin(fw_name, app))] + mode_args
    env = display.app_env(fw_name)
    if extra_env:
        env.update(extra_env)
    return app_popen(cmd, env)


def kill(proc):
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=5)
        except (subprocess.TimeoutExpired, ProcessLookupError):
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    for s in (proc.stdout, proc.stderr):
        if s:
            s.close()


def wait_port_free(port, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return
        time.sleep(0.2)
    # Never measure against a foreign MCP server.
    raise RuntimeError(
        f"port {port} is held by another process; refusing to measure")


def sample_mem(pid):
    """PSS primary (smaps_rollup), RSS secondary (status). kB, or None."""
    pss = rss = None
    try:
        for line in Path(f"/proc/{pid}/smaps_rollup").read_text().splitlines():
            if line.startswith("Pss:"):
                pss = int(line.split()[1])
                break
    except OSError:
        pass
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                rss = int(line.split()[1])
                break
    except OSError:
        pass
    return {"pss_kb": pss, "rss_kb": rss}


def proc_start_monotonic(pid):
    """Kernel-recorded process start, mapped onto CLOCK_MONOTONIC.

    Independent cross-check for the harness's own spawn timestamps:
    /proc/<pid>/stat field 22 is the process creation time in clock
    ticks since boot. Assumes no suspend between boot and now (maps
    /proc/uptime onto CLOCK_MONOTONIC directly)."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        starttime_ticks = int(stat.rsplit(")", 1)[1].split()[19])
        hz = os.sysconf("SC_CLK_TCK")
        uptime_now = float(Path("/proc/uptime").read_text().split()[0])
        mono_now = time.monotonic()
        return mono_now - (uptime_now - starttime_ticks / hz)
    except (OSError, ValueError, IndexError):
        return None


def evict_page_cache(fw_name, app):
    """Best-effort partial cold-start: drop file-backed page cache for the
    app binary, its dynamically linked libraries, the corpus, and (Lumen)
    the app sources. Unprivileged; anonymous pages and already-mapped
    files of other processes stay warm. Labeled 'partial cold'."""
    files = [fw_bin(fw_name, app), CORPUS]
    if fw_name == "lumen":
        files += list((ROOT / "lumen" / app).iterdir())
    ldd = _cmd_out(["ldd", str(fw_bin(fw_name, app))]) or ""
    for line in ldd.splitlines():
        parts = line.split()
        for p in parts:
            if p.startswith("/") and Path(p).exists():
                files.append(Path(p))
    dropped = 0
    for f in files:
        try:
            fd = os.open(f, os.O_RDONLY)
            try:
                os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
                dropped += 1
            finally:
                os.close(fd)
        except OSError:
            pass
    return dropped


# --------------------------------------------------------------------------
# Statistics
# --------------------------------------------------------------------------

def run_stats(vals, ci=False, warmup=None):
    """Robust summary of repeated measurements of one metric.

    median, IQR, MAD, min/max, Tukey-fence outliers (kept), the unstable
    flag, and the raw samples. With ci=True it also carries a bootstrap
    confidence interval on the median. Discarded warmup values ride along
    under `warmup_samples` so nothing measured is thrown away."""
    out = st.summarize(vals, unstable_iqr_fraction=UNSTABLE_IQR_FRACTION,
                       ci=ci, confidence=CI_CONFIDENCE,
                       resamples=CI_RESAMPLES, seed=CI_SEED)
    if warmup:
        out["warmup_samples"] = [round(v, 3) for v in warmup]
        out["warmup_discarded"] = len(warmup)
    return out


def frame_stats(deltas, warmup_frames=None):
    """Percentiles of one pass's frame intervals.

    The first `warmup_frames` deltas are dropped before the statistics
    (see WARMUP_POLICY) and reported as `warmup_frames`; the raw deltas,
    warmup included, are kept when KEEP_FRAME_SAMPLES is on."""
    if warmup_frames is None:
        warmup_frames = FRAME_WARMUP_FRAMES
    raw = list(deltas)
    if not raw:
        return {"frames": 0, "warmup_frames": 0}
    # Never let warmup eat a whole pass: with fewer than twice the warmup
    # count, keep everything and say so.
    dropped = warmup_frames if len(raw) > 2 * warmup_frames else 0
    kept = raw[dropped:]
    out = {
        "frames": len(kept),
        "warmup_frames": dropped,
        "p50_ms": round(st.percentile(kept, 50), 3),
        "p95_ms": round(st.percentile(kept, 95), 3),
        "p99_ms": round(st.percentile(kept, 99), 3),
        "min_ms": round(min(kept), 3),
        "max_ms": round(max(kept), 3),
        "mean_ms": round(statistics.fmean(kept), 3),
        "mad_ms": round(st.mad(kept), 3),
        "n_outliers": len(st.outliers(kept)),
    }
    if KEEP_FRAME_SAMPLES:
        out["samples_ms"] = [round(v, 3) for v in raw]
    return out


def combine_passes(passes):
    """Cross-pass summary of each percentile metric.

    Passes are the repeated unit here, so the headline number for, say,
    p95 is the median of the passes' p95 values, with the pass-to-pass
    spread (max - min) as its error bar and the smallest pass value as the
    floor."""
    out = {"passes": passes}
    for key in ("p50_ms", "p95_ms", "p99_ms"):
        vals = [p[key] for p in passes if key in p]
        if not vals:
            continue
        out[key + "_median"] = round(statistics.median(vals), 3)
        out[key + "_spread"] = round(max(vals) - min(vals), 3)
        out[key + "_min"] = round(min(vals), 3)
        out[key + "_mad"] = round(st.mad(vals), 3)
        out[key + "_n"] = len(vals)
    out["frames_total"] = sum(p.get("frames", 0) for p in passes)
    out["warmup_frames_per_pass"] = FRAME_WARMUP_FRAMES
    return out


# --------------------------------------------------------------------------
# Lumen MCP client
# --------------------------------------------------------------------------

class McpClient:
    """Persistent line-delimited JSON-RPC connection to lumenc's MCP port."""

    def __init__(self, port, timeout=2.0, connect_timeout=30.0):
        deadline = time.monotonic() + connect_timeout
        last_err = None
        while time.monotonic() < deadline:
            try:
                self.sock = socket.create_connection(("127.0.0.1", port),
                                                     timeout=timeout)
                self.f = self.sock.makefile("rb")
                self._id = 0
                return
            except OSError as e:
                last_err = e
                time.sleep(0.05)
        raise RuntimeError(f"cannot connect to lumen MCP :{port}: {last_err}")

    def call(self, method, params=None):
        self._id += 1
        req = json.dumps({"jsonrpc": "2.0", "id": self._id, "method": method,
                          "params": params or {}}) + "\n"
        self.sock.sendall(req.encode())
        line = self.f.readline()
        if not line:
            raise OSError("MCP connection closed")
        return json.loads(line)

    def close(self):
        try:
            self.f.close()
            self.sock.close()
        except OSError:
            pass


class LumenTickSampler:
    """Samples `lumen.tick` every LUMEN_TICK_SAMPLE_S on its own persistent
    connection, recording (monotonic_midpoint, frame, last_tick_micros).
    Reading the snapshot does not wake Lumen's parked demand-driven loop
    (only `lumen.simulate` does), so sampling is passive."""

    def __init__(self, port):
        self.client = McpClient(port)
        self.samples = []
        self.errors = 0
        self.stop_flag = threading.Event()
        self.t = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        next_t = time.monotonic()
        while not self.stop_flag.is_set():
            t0 = time.monotonic()
            try:
                resp = self.client.call("lumen.tick")
                r = resp.get("result", {})
                t1 = time.monotonic()
                self.samples.append(((t0 + t1) / 2.0, r.get("frame"),
                                     r.get("last_tick_micros")))
            except (OSError, ValueError, AttributeError):
                self.errors += 1
                if self.stop_flag.is_set():
                    break
                time.sleep(0.01)
            next_t += LUMEN_TICK_SAMPLE_S
            dt = next_t - time.monotonic()
            if dt > 0:
                time.sleep(dt)
            else:
                next_t = time.monotonic()

    def start(self):
        self.t.start()

    def stop(self):
        self.stop_flag.set()
        self.t.join(timeout=2)
        self.client.close()

    def frame_intervals_ms(self):
        """Wall frame intervals reconstructed from counter advances:
        each counter change marks a frame boundary at the observing
        sample's timestamp (quantized by the 0.5 ms sampling cadence);
        a multi-frame advance between adjacent samples (rare at 0.5 ms)
        spreads its boundaries evenly across the gap. Intervals are the
        diffs between consecutive boundaries."""
        good = [s for s in self.samples if s[1] is not None]
        boundaries = []
        for (t1, f1, _), (t2, f2, _) in zip(good, good[1:]):
            df = f2 - f1
            if df > 0:
                for k in range(1, df + 1):
                    boundaries.append(t1 + (t2 - t1) * k / df)
        return [(b - a) * 1000.0 for a, b in zip(boundaries, boundaries[1:])]

    def tick_micros(self):
        seen = {}
        for _, f, us in self.samples:
            if f is not None and us is not None:
                seen[f] = us
        return list(seen.values())


def lumen_wait_first_frame(client, timeout=90.0):
    """Poll `lumen.tick` (0.5 ms cadence) until the frame counter reaches 1.
    'First presented frame' for Lumen = first windowed tick+render
    presented through the compositor, observed through the MCP frame
    counter."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = client.call("lumen.tick")
            frame = resp.get("result", {}).get("frame", 0)
            if frame and frame >= 1:
                return time.monotonic()
        except (OSError, AttributeError, ValueError):
            pass
        time.sleep(LUMEN_TICK_SAMPLE_S)
    return None


# --------------------------------------------------------------------------
# Native (non-Lumen) measurements
# --------------------------------------------------------------------------

def is_marker(line):
    return line == "first_frame"


def measure_startup_native(fw, app, display, cold=False):
    external, internal = [], []
    warm_external, warm_internal = [], []
    spawn_deltas = []  # harness-vs-kernel spawn timestamp deltas
    for i in range(STARTUP_WARMUP_RUNS + STARTUP_RUNS):
        warmup = i < STARTUP_WARMUP_RUNS
        if cold:
            evict_page_cache(fw, app)
        t_spawn = time.monotonic()
        proc = spawn(fw, app, ["--startup"], display)
        kstart = proc_start_monotonic(proc.pid)
        reader = LineReader(proc.stdout)
        ts, _ = reader.wait_for(is_marker, timeout=120)
        if ts is None:
            err = proc.stderr.read().decode(errors="replace")[-400:]
            kill(proc)
            raise RuntimeError(f"{fw}/{app}: no first-frame marker (run {i}): {err}")
        ts2, line2 = reader.wait_for(lambda l: l.startswith("startup_ms:"),
                                     timeout=10)
        proc.wait(timeout=10)
        kill(proc)
        ext_ms = (ts - t_spawn) * 1000.0
        self_ms = float(line2.split(":")[1]) if line2 else None
        if warmup:
            warm_external.append(ext_ms)
            if self_ms is not None:
                warm_internal.append(self_ms)
            time.sleep(0.3)
            continue
        external.append(ext_ms)
        if self_ms is not None:
            internal.append(self_ms)
        if kstart is not None:
            spawn_deltas.append((t_spawn - kstart) * 1000.0)
        time.sleep(0.3)
    out = {
        "external_ms": run_stats(external, ci=True, warmup=warm_external),
        "self_ms": (run_stats(internal, ci=True, warmup=warm_internal)
                    if internal else None),
        "clock_note": "external: harness CLOCK_MONOTONIC spawn->marker; "
                      "self: app CLOCK_MONOTONIC main->first-frame callback",
    }
    if spawn_deltas:
        out["harness_vs_kernel_spawn_ms"] = run_stats(spawn_deltas)
    if cold:
        out["cold"] = ("partial cold: file-backed pages of binary+libs+data "
                       "evicted via posix_fadvise before each run; no full "
                       "page-cache drop (needs root)")
    return out


def measure_pass_native(fw, app, mode_arg, display):
    """One scroll/interact pass: returns (frame_stats, post_mem)."""
    proc = spawn(fw, app, [mode_arg], display)
    reader = LineReader(proc.stdout)
    ts, _ = reader.wait_for(is_marker, timeout=120)
    if ts is None:
        err = proc.stderr.read().decode(errors="replace")[-400:]
        kill(proc)
        raise RuntimeError(f"{fw}/{app}: pass produced no first frame: {err}")
    deltas = []
    deadline = time.monotonic() + SCROLL_SECONDS + 60
    saw_done = False
    while time.monotonic() < deadline:
        try:
            _, line = reader.q.get(timeout=1.0)
        except queue.Empty:
            continue  # app buffers output until the pass ends
        if line is None:
            break
        if line == "done":
            saw_done = True
            break
        try:
            deltas.append(float(line))
        except ValueError:
            pass
    post = sample_mem(proc.pid) if saw_done else {"pss_kb": None, "rss_kb": None}
    kill(proc)
    if not saw_done:
        raise RuntimeError(f"{fw}/{app}: pass never printed done")
    return frame_stats(deltas), post


def measure_pass_native_retry(fw, app, mode_arg, display, attempts=3):
    """measure_pass_native with retries. Under full-round load a transient
    compositor surface loss (VK_ERROR_SURFACE_LOST_KHR) or a momentarily
    stalled frame clock occasionally drops a single pass; the same binary
    passes cleanly in isolation (verified: egui/forms, egui/textview,
    gtk4/list all pass on a fresh GL compositor). The failure is
    accumulated GPU-side state on the long-lived weston, so a retry on the
    same compositor doesn't clear it; restart the compositor between
    attempts to recover a wedged one before surfacing."""
    last = None
    for i in range(attempts):
        try:
            return measure_pass_native(fw, app, mode_arg, display)
        except RuntimeError as e:
            last = e
            log(f"  {fw}/{app}: pass attempt {i + 1}/{attempts} failed: {e}")
            if i < attempts - 1 and display.backend == "weston":
                log(f"  {fw}/{app}: restarting compositor before retry")
                display.restart()
            else:
                time.sleep(1.0)
    raise last


def measure_idle_mem_native(fw, app, display):
    proc = spawn(fw, app, [], display)
    reader = LineReader(proc.stdout)
    ts, _ = reader.wait_for(is_marker, timeout=120)
    if ts is None:
        kill(proc)
        raise RuntimeError(f"{fw}/{app}: idle run produced no first frame")
    time.sleep(2.0)
    idle = sample_mem(proc.pid)
    late = None
    if app == "hello":
        time.sleep(3.0)
        late = sample_mem(proc.pid)
    kill(proc)
    return idle, late


# --------------------------------------------------------------------------
# Lumen measurements
# --------------------------------------------------------------------------

def lumen_spawn_and_wait(app, display):
    wait_port_free(LUMEN_MCP_PORT)
    t_spawn = time.monotonic()
    proc = spawn("lumen", app, [], display)
    client = McpClient(LUMEN_MCP_PORT)
    ts = lumen_wait_first_frame(client)
    if ts is None:
        client.close()
        err = proc.stderr.read().decode(errors="replace")[-400:]
        kill(proc)
        raise RuntimeError(f"lumen/{app}: no first frame via MCP: {err}")
    return proc, client, t_spawn, ts


def measure_startup_lumen(app, display, cold=False):
    """Lumen startup, measured identically to the native frameworks.

    `LUMEN_BOOT_TRACE=1` makes lumenc's windowed backend print, on the
    first on-screen present, a bare `first_frame` stdout line (the same
    spawn->marker signal every native bench app prints) followed by
    `startup_ms:<exec->first-frame ms>` (the in-app clock, parity with the
    native apps' `startup_ms:` line). No MCP connect/poll is involved, so
    the old ~108 ms socket-overhead inflation is gone; the scroll/interact
    passes still drive Lumen over MCP separately."""
    external, internal = [], []
    warm_external, warm_internal = [], []
    spawn_deltas = []
    boot_env = {"LUMEN_BOOT_TRACE": "1"}
    for i in range(STARTUP_WARMUP_RUNS + STARTUP_RUNS):
        warmup = i < STARTUP_WARMUP_RUNS
        if cold:
            evict_page_cache("lumen", app)
        # lumenc still starts its MCP server (unused for startup timing);
        # make sure the port from the previous run is released first so a
        # bind race can't abort the process before it paints.
        wait_port_free(LUMEN_MCP_PORT)
        t_spawn = time.monotonic()
        proc = spawn("lumen", app, [], display, extra_env=boot_env)
        kstart = proc_start_monotonic(proc.pid)
        reader = LineReader(proc.stdout)
        ts, _ = reader.wait_for(is_marker, timeout=120)
        if ts is None:
            err = proc.stderr.read().decode(errors="replace")[-400:]
            kill(proc)
            raise RuntimeError(f"lumen/{app}: no first-frame marker (run {i}): {err}")
        ts2, line2 = reader.wait_for(lambda l: l.startswith("startup_ms:"),
                                     timeout=10)
        kill(proc)
        ext_ms = (ts - t_spawn) * 1000.0
        self_ms = float(line2.split(":")[1]) if line2 else None
        if warmup:
            warm_external.append(ext_ms)
            if self_ms is not None:
                warm_internal.append(self_ms)
            time.sleep(0.3)
            continue
        external.append(ext_ms)
        if self_ms is not None:
            internal.append(self_ms)
        if kstart is not None:
            spawn_deltas.append((t_spawn - kstart) * 1000.0)
        time.sleep(0.3)
    out = {
        "external_ms": run_stats(external, ci=True, warmup=warm_external),
        "self_ms": (run_stats(internal, ci=True, warmup=warm_internal)
                    if internal else None),
        "clock_note": "external: harness CLOCK_MONOTONIC spawn->marker "
                      "(stdout `first_frame` on first on-screen present, "
                      "same method as the native frameworks); "
                      "self: app CLOCK_MONOTONIC exec->first-frame "
                      "(lumenc LUMEN_BOOT_TRACE startup_ms:)",
    }
    if spawn_deltas:
        out["harness_vs_kernel_spawn_ms"] = run_stats(spawn_deltas)
    if cold:
        out["cold"] = ("partial cold: file-backed pages of lumenc + libs + "
                       ".lmn/.css/.rhai sources evicted before each run")
    return out


def measure_scroll_pass_lumen(app, display):
    """Drive wheel events at ~60 Hz; sample the frame counter at 0.5 ms."""
    proc, client, _, _ = lumen_spawn_and_wait(app, display)
    time.sleep(1.0)  # settle startup work

    sampler = LumenTickSampler(LUMEN_MCP_PORT)
    sampler.start()

    dy = -(SCROLL_PX_PER_S * LUMEN_SCROLL_INTERVAL_S)  # negative = down
    errors = 0
    t_start = time.monotonic()
    next_send = t_start
    while True:
        now = time.monotonic()
        if now - t_start >= SCROLL_SECONDS:
            break
        if now >= next_send:
            try:
                client.call("lumen.simulate",
                            {"kind": "scroll", "x": 400.0, "y": 300.0,
                             "dx": 0.0, "dy": dy})
            except (OSError, ValueError):
                errors += 1
            next_send += LUMEN_SCROLL_INTERVAL_S
        time.sleep(0.0005)
    sampler.stop()
    post = sample_mem(proc.pid)
    client.close()
    kill(proc)
    if errors:
        log(f"lumen/{app}: {errors} simulate calls failed during scroll")

    stats = frame_stats(sampler.frame_intervals_ms())
    ticks = sampler.tick_micros()
    if ticks:
        stats["tick_cpu_us_p50"] = round(statistics.median(ticks), 1)
    stats["metric"] = ("wall frame intervals reconstructed from the MCP frame "
                       "counter sampled every 0.5 ms (persistent connection)")
    return stats, post


def lumen_forms_targets(client):
    """Toggleable controls of the forms app in document order.

    Lumen's MCP roles are coarse: checkboxes and switches report role
    'toggle' (12 of them); radios report 'interactive' (8; buttons and
    inputs classify as 'text'). Rects are scroll-corrected and queried
    at scroll=0, so sorting by (y, x) is document order; the forms
    markup fixes the mapping below."""
    def fetch(role, want):
        resp = client.call("lumen.find", {"by_role": role, "limit": 100})
        rows = resp.get("result", {}).get("results", [])
        rows.sort(key=lambda r: (r["y"], r["x"]))
        if len(rows) != want:
            raise RuntimeError(
                f"lumen/forms: expected {want} '{role}' controls, found "
                f"{len(rows)}")
        return [r["id"] for r in rows]

    tg = fetch("toggle", 12)       # 8 checkboxes + 4 switches, doc order
    ra = fetch("interactive", 8)   # 2 radio groups x 4, doc order
    checks = [tg[i] for i in (0, 1, 3, 4, 5, 6, 8, 9)]
    toggles = [tg[i] for i in (2, 7, 10, 11)]  # animations/autosave/dnt/experimental
    radio_a, radio_b = ra[:4], ra[4:]
    return checks, toggles, radio_a, radio_b


def lumen_click_target(client, eid):
    """Scroll the control into view if needed, then click its center.

    Lumen has no programmatic state setter reachable from outside, so
    toggle steps go through the real input pipeline: MCP rects are
    scroll-corrected window coordinates; a wheel event brings offscreen
    controls into the viewport first (extra work the other frameworks'
    direct state writes don't do; see caveats)."""
    for _ in range(6):
        resp = client.call("lumen.find", {"by_id": eid})
        rows = resp.get("result", {}).get("results", [])
        if not rows:
            return False
        r = rows[0]
        cy = r["y"] + r["h"] / 2.0
        cx = r["x"] + r["w"] / 2.0
        # Scroll viewport spans y 48..568 (header 48, footer 32).
        if 52.0 <= cy <= 564.0:
            client.call("lumen.simulate", {"kind": "click", "x": cx, "y": cy})
            return True
        client.call("lumen.simulate",
                    {"kind": "scroll", "x": 400.0, "y": 300.0,
                     "dx": 0.0, "dy": -(cy - 300.0)})
    return False


def measure_interact_pass_lumen(display):
    proc, client, _, _ = lumen_spawn_and_wait("forms", display)
    time.sleep(1.0)
    try:
        checks, toggles, radio_a, radio_b = lumen_forms_targets(client)
    except Exception:
        client.close()
        kill(proc)
        raise
    ra_idx, rb_idx = [0], [0]

    def toggle_step(t):
        if t <= 7:
            return lumen_click_target(client, checks[t])
        if t <= 11:
            return lumen_click_target(client, toggles[t - 8])
        if t <= 15:
            ra_idx[0] = (ra_idx[0] + 1) % 4
            return lumen_click_target(client, radio_a[ra_idx[0]])
        rb_idx[0] = (rb_idx[0] + 1) % 4
        return lumen_click_target(client, radio_b[rb_idx[0]])

    sampler = LumenTickSampler(LUMEN_MCP_PORT)
    sampler.start()

    total = 60 * INTERACT_CYCLES
    errors = 0
    step_done = 0
    t_start = time.monotonic()
    while step_done < total:
        due = min(total, int((time.monotonic() - t_start) / INTERACT_STEP_S))
        while step_done < due:
            in_cycle = step_done % 60
            try:
                if in_cycle < 40:
                    client.call("lumen.simulate", {"kind": "key", "key": "Tab"})
                else:
                    if not toggle_step(in_cycle - 40):
                        errors += 1
            except (OSError, ValueError):
                errors += 1
            step_done += 1
        time.sleep(0.001)
    sampler.stop()
    post = sample_mem(proc.pid)
    client.close()
    kill(proc)
    if errors:
        log(f"lumen/forms: {errors} interact steps failed")

    stats = frame_stats(sampler.frame_intervals_ms())
    ticks = sampler.tick_micros()
    if ticks:
        stats["tick_cpu_us_p50"] = round(statistics.median(ticks), 1)
    stats["metric"] = ("wall frame intervals reconstructed from the MCP frame "
                       "counter sampled every 0.5 ms; steps injected as real "
                       "input (Tab keys; scroll-into-view + click for toggles)")
    stats["step_errors"] = errors
    return stats, post


def measure_idle_mem_lumen(app, display):
    proc, client, _, _ = lumen_spawn_and_wait(app, display)
    time.sleep(2.0)
    idle = sample_mem(proc.pid)
    late = None
    if app == "hello":
        time.sleep(3.0)
        late = sample_mem(proc.pid)
    client.close()
    kill(proc)
    return idle, late


# --------------------------------------------------------------------------
# Per-cell measurement
# --------------------------------------------------------------------------

def measure_idle_mem(fw, app, display):
    """Idle (and, for hello, 5 s) memory over MEM_RUNS separate launches.

    One launch gives a point with no spread; repeating it exposes how much
    of the footprint is allocator/compositor luck. Returns
    (idle_point, idle_stats, late_point, late_stats)."""
    idles, lates = [], []
    for i in range(MEM_WARMUP_RUNS + MEM_RUNS):
        if fw == "lumen":
            idle, late = measure_idle_mem_lumen(app, display)
        else:
            idle, late = measure_idle_mem_native(fw, app, display)
        if i < MEM_WARMUP_RUNS:
            continue
        idles.append(idle)
        if late:
            lates.append(late)
        time.sleep(0.3)
    return (median_mem(idles), mem_stats(idles),
            median_mem(lates) if lates else None,
            mem_stats(lates) if lates else None)


def measure_cell(fw, app, display, cold=False):
    cell = {}
    log(f"=== {fw}/{app}: startup x{STARTUP_RUNS} "
        f"(+{STARTUP_WARMUP_RUNS} warmup) ===")
    if fw == "lumen":
        cell["startup"] = measure_startup_lumen(app, display, cold=cold)
    else:
        cell["startup"] = measure_startup_native(fw, app, display, cold=cold)

    log(f"=== {fw}/{app}: idle memory x{MEM_RUNS} ===")
    idle, idle_stats, late, late_stats = measure_idle_mem(fw, app, display)
    cell["mem_idle"] = idle
    cell["mem_idle_stats"] = idle_stats
    if late:
        cell["mem_5s"] = late
        cell["mem_5s_stats"] = late_stats

    workload = {"list": "scroll", "textview": "scroll", "forms": "interact"}.get(app)
    if workload == "scroll":
        passes, post_mems = [], []
        for p in range(SCROLL_PASSES):
            log(f"=== {fw}/{app}: scroll pass {p + 1}/{SCROLL_PASSES} ===")
            if fw == "lumen":
                pass_stats, post = measure_scroll_pass_lumen(app, display)
            else:
                pass_stats, post = measure_pass_native_retry(
                    fw, app, "--scroll-bench", display)
            passes.append(pass_stats)
            post_mems.append(post)
            time.sleep(0.5)
        cell["scroll"] = combine_passes(passes)
        cell["mem_post"] = median_mem(post_mems)
        cell["mem_post_stats"] = mem_stats(post_mems)
    elif workload == "interact":
        passes, post_mems = [], []
        for p in range(INTERACT_PASSES):
            log(f"=== {fw}/{app}: interact pass {p + 1}/{INTERACT_PASSES} ===")
            if fw == "lumen":
                pass_stats, post = measure_interact_pass_lumen(display)
            else:
                pass_stats, post = measure_pass_native_retry(
                    fw, app, "--interact", display)
            passes.append(pass_stats)
            post_mems.append(post)
            time.sleep(0.5)
        cell["interact"] = combine_passes(passes)
        cell["mem_post"] = median_mem(post_mems)
        cell["mem_post_stats"] = mem_stats(post_mems)
    return cell


def median_mem(mems):
    out = {}
    for key in ("pss_kb", "rss_kb"):
        vals = [m[key] for m in mems if m.get(key) is not None]
        out[key] = int(statistics.median(vals)) if vals else None
    return out


def mem_stats(mems):
    """Median, spread, min and samples for each memory series."""
    out = {}
    for key in ("pss_kb", "rss_kb"):
        vals = [m[key] for m in mems if m.get(key) is not None]
        if vals:
            out[key] = run_stats(vals)
    return out


# --------------------------------------------------------------------------
# Calibration
# --------------------------------------------------------------------------

def calibrate(display):
    """Bound the harness's systematic measurement error with independent
    anchors:

    1. spawn->marker floor: a trivial C binary printing the marker
       immediately. Its external time is pure harness+fork/exec+libc
       overhead; the floor baked into every external startup number.
    2. harness-vs-kernel spawn timestamps: the kernel's own record of
       process creation (/proc/pid/stat starttime) versus the harness's
       pre-Popen monotonic stamp. Bounds the external clock anchor error.
    3. app-clock cross-check: the calib binary also prints its own
       CLOCK_MONOTONIC, letting the harness compare marker arrival time
       against the app-side stamp (pipe+scheduling latency)."""
    ext, kdelta, pipe_lat, warm = [], [], [], []
    calib = BIN_OUT / "calib"
    for i in range(CALIB_WARMUP_RUNS + CALIB_RUNS):
        t_spawn = time.monotonic()
        proc = subprocess.Popen(_taskset_prefix() + [str(calib)],
                                stdout=subprocess.PIPE, start_new_session=True)
        kstart = proc_start_monotonic(proc.pid)
        reader = LineReader(proc.stdout)
        ts, _ = reader.wait_for(is_marker, timeout=10)
        ts2, line2 = reader.wait_for(lambda l: l.startswith("mono_ns:"), timeout=5)
        proc.wait(timeout=5)
        for s in (proc.stdout,):
            s.close()
        if ts is None:
            continue
        if i < CALIB_WARMUP_RUNS:
            warm.append((ts - t_spawn) * 1000.0)
            time.sleep(0.05)
            continue
        ext.append((ts - t_spawn) * 1000.0)
        if kstart is not None:
            kdelta.append((t_spawn - kstart) * 1000.0)
        if line2:
            app_mono = int(line2.split(":")[1]) / 1e9
            pipe_lat.append((ts - app_mono) * 1000.0)
        time.sleep(0.05)
    return {
        "note": (f"all values ms; median with IQR, MAD, min and a "
                 f"{CI_CONFIDENCE:.0%} bootstrap interval over "
                 f"{CALIB_RUNS} runs (+{CALIB_WARMUP_RUNS} warmup)"),
        "n": len(ext),
        "warmup_runs": CALIB_WARMUP_RUNS,
        "spawn_to_marker_floor_ms": run_stats(ext, ci=True, warmup=warm),
        "harness_vs_kernel_spawn_ms": run_stats(kdelta),
        "marker_pipe_latency_ms": run_stats(pipe_lat, ci=True),
        "interpretation": (
            "external startup numbers carry ~floor overhead identically for "
            "every framework; the kernel cross-check bounds the harness "
            "spawn-timestamp error; pipe latency bounds marker-arrival skew. "
            "Cross-framework startup deltas smaller than the floor's IQR + "
            "pipe latency are not meaningful."),
    }


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

CLOCK_TABLE = """\
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
"""

CAVEATS = """\
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
"""


def report_config(results):
    """Statistics settings behind a report: what the run recorded, or the
    current defaults when rendering a results.json that predates them."""
    cfg = results.get("config") or {}
    return {
        "confidence": cfg.get("ci_confidence", CI_CONFIDENCE),
        "resamples": cfg.get("ci_resamples", CI_RESAMPLES),
        "seed": cfg.get("ci_seed", CI_SEED),
        "tolerance": cfg.get("agreement_tolerance", AGREEMENT_TOLERANCE),
        "unstable": cfg.get("unstable_iqr_fraction", UNSTABLE_IQR_FRACTION),
        "startup_runs": cfg.get("startup_runs"),
        "startup_warmup": cfg.get("startup_warmup_runs"),
        "frame_warmup": cfg.get("frame_warmup_frames"),
        "mem_runs": cfg.get("mem_runs"),
        "scroll_passes": cfg.get("scroll_passes"),
        "interact_passes": cfg.get("interact_passes"),
        "calibration_runs": cfg.get("calibration_runs"),
        "schema": results.get("schema_version",
                              cfg.get("schema_version", 1)),
    }


def enrich(summary, rcfg):
    """A summary with min/MAD/CI filled in from its stored samples.

    Schema-1 results kept every startup sample but no interval, so the
    same report can be rendered from them."""
    if not summary:
        return summary
    return st.ensure_ci(summary, confidence=rcfg["confidence"],
                        resamples=rcfg["resamples"], seed=rcfg["seed"])


FRAME_CELL_LEGEND = (
    "Each frame cell reads `median (spread, min)`: the median across "
    "passes, the gap between the best and worst pass, and the best pass "
    "itself as the floor.")


def ascii_only(v):
    """Report text is ASCII. Version strings come from other people's
    tools (`flutter --version` ships a bullet character), so anything
    outside ASCII is replaced rather than passed through."""
    if v is None:
        return "-"
    return "".join(c if c.isascii() else "-" for c in str(v))


def fmt_ms(v, spec=".1f"):
    return f"{format(v, spec)}" if isinstance(v, (int, float)) else "-"


def fmt_flags(summary):
    """Trailing markers: instability and outlier count."""
    s = ""
    if summary.get("unstable"):
        s += " (!)"
    n_out = summary.get("n_outliers")
    if n_out is None:
        n_out = len(summary.get("outliers") or [])
    if n_out:
        s += f" ({n_out}o)"
    return s


def fmt_stat(summary, spec=".1f"):
    """median +/- IQR/2, with the instability and outlier markers."""
    if not summary or summary.get("median") is None:
        return "-"
    return (f"{format(summary['median'], spec)} "
            f"+/-{format(summary['iqr'] / 2, spec)}" + fmt_flags(summary))


def fmt_median(summary, spec=".1f"):
    if not summary or summary.get("median") is None:
        return "-"
    return format(summary["median"], spec) + fmt_flags(summary)


def fmt_spread(summary, spec=".1f"):
    """IQR with MAD in parentheses: two views of the same spread."""
    if not summary or summary.get("iqr") is None:
        return "-"
    s = format(summary["iqr"], spec)
    if summary.get("mad") is not None:
        s += f" ({format(summary['mad'], spec)})"
    return s


def fmt_ci(summary, spec=".1f"):
    bounds = st.ci_bounds(summary)
    if bounds is None:
        return "-"
    return f"{format(bounds[0], spec)}-{format(bounds[1], spec)}"


def fmt_pct(cell_metric, key):
    """One frame percentile: cross-pass median, then the pass-to-pass
    spread and the best pass in parentheses."""
    if not cell_metric:
        return "-"
    med = cell_metric.get(key + "_median")
    if med is None:
        return "-"
    spread = cell_metric.get(key + "_spread") or 0.0
    lo = cell_metric.get(key + "_min")
    if lo is None:
        passes = cell_metric.get("passes") or []
        vals = [pss[key] for pss in passes if key in pss]
        lo = min(vals) if vals else None
    tail = f", min {lo:.2f}" if lo is not None else ""
    return f"{med:.2f} ({spread:.2f}{tail})"


def fmt_mem(mem, mem_stats_dict=None):
    """PSS MiB with RSS in parentheses; PSS spread when several launches
    were sampled."""
    if not mem:
        return "-"
    pss = mem.get("pss_kb")
    rss = mem.get("rss_kb")
    if pss is None and rss is None:
        return "-"
    p = f"{pss / 1024:.1f}" if pss else "?"
    r = f"{rss / 1024:.1f}" if rss else "?"
    spread = ""
    pss_stat = (mem_stats_dict or {}).get("pss_kb") or {}
    if pss_stat.get("iqr") is not None and pss_stat.get("n", 0) > 1:
        spread = f" +/-{pss_stat['iqr'] / 2 / 1024:.1f}"
    return f"{p}{spread} ({r})"


def size_str(sizes, fw, app):
    s = sizes.get(fw, {})
    if fw == "lumen":
        rt = s.get("runtime_stripped_bytes")
        pl = s.get(app, {}).get("app_payload_bytes")
        if rt is None:
            return "-"
        return f"{rt / 1048576:.1f} MiB rt +{(pl or 0) / 1024:.1f} KiB app"
    b = s.get(app, {}).get("stripped_bytes")
    return f"{b / 1048576:.1f} MiB" if b else "-"


def startup_summary(cell, which="external_ms"):
    return (cell.get("startup") or {}).get(which) or {}


def overlapping_pairs(entries):
    """Pairs of (name, summary) whose confidence intervals overlap.

    An overlap means the two medians are not separated by the data: the
    difference between them is inside the run-to-run noise."""
    pairs = []
    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            a_name, a = entries[i]
            b_name, b = entries[j]
            if st.intervals_overlap(st.ci_bounds(a), st.ci_bounds(b)):
                pairs.append((a_name, b_name))
    return pairs


def agreement_rows(results, tolerance=None):
    """Run-1 vs run-2 medians for every headline metric.

    Agreement is the relative difference of the two medians: the gap
    between them divided by their average. A metric agrees when that
    difference is at or below `tolerance`."""
    if tolerance is None:
        tolerance = report_config(results)["tolerance"]
    rounds = results.get("rounds", [])
    if len(rounds) < 2:
        return []
    r0, r1 = rounds[0].get("cells", {}), rounds[1].get("cells", {})
    rows = []

    def add(fw, app, metric, m0, m1):
        if m0 is None or m1 is None:
            return
        diff = st.rel_diff(m0, m1)
        rows.append({
            "fw": fw, "app": app, "metric": metric,
            "run1": m0, "run2": m1,
            "abs_delta": round(abs(m1 - m0), 3),
            "rel_diff": round(diff, 4) if diff is not None else None,
            "tolerance": tolerance,
            "agree": diff is None or diff <= tolerance,
        })

    for fw in FRAMEWORKS:
        for app in APPS:
            c0 = r0.get(fw, {}).get(app)
            c1 = r1.get(fw, {}).get(app)
            if not c0 or not c1:
                continue
            s0 = startup_summary(c0)
            s1 = startup_summary(c1)
            add(fw, app, "startup ext ms", s0.get("median"), s1.get("median"))
            for wk in ("scroll", "interact"):
                w0, w1 = c0.get(wk), c1.get(wk)
                if not w0 or not w1:
                    continue
                for key in ("p50_ms", "p95_ms", "p99_ms"):
                    add(fw, app, f"{wk} {key}", w0.get(key + "_median"),
                        w1.get(key + "_median"))
            add(fw, app, "idle PSS kB",
                (c0.get("mem_idle") or {}).get("pss_kb"),
                (c1.get("mem_idle") or {}).get("pss_kb"))
    return rows


def env_block(results):
    """Compact block of the machine facts that move the numbers."""
    env = results.get("env", {})
    cpu = env.get("cpu", {})
    disp = env.get("display", {})
    versions = results.get("versions") or env.get("toolchains") or {}

    def cpu_fact(key, flat):
        return cpu.get(key, env.get(flat))

    app_cpus = cpu_fact("app_cpus", "app_cpus")
    govs = cpu.get("app_cpu_governors") or env.get("governors") or []
    backend = disp.get("backend") or results.get("display_backend", "?")
    disp_cmd = disp.get("command")
    if not disp_cmd and backend == "weston":
        disp_cmd = ("weston --backend=headless --renderer=gl "
                    "--socket=wayland-bench --width=1280 --height=1024")
    refresh = disp.get("refresh_hz")

    pin_note = cpu.get("pin_note") or env.get("cpu_pin_note")
    boost = cpu.get("cpufreq_boost") or env.get("cpufreq_boost")
    rows = [
        ("host / kernel", f"{env.get('hostname', '?')} / "
                          f"{env.get('kernel', '?')}"),
        ("CPU", f"{cpu_fact('model', 'cpu_model') or '?'} "
                f"({cpu_fact('count', 'cpu_count') or '?'} logical cpus)"),
        ("app cpus", f"{app_cpus}" + (f" ({pin_note})" if pin_note else "")),
        ("cpu governor", f"{'/'.join(govs) if govs else '?'} on the app cpus; "
                         f"pin attempt: {results.get('governor_note', '?')}"
                         + (f"; boost: {boost}" if boost else "")),
        ("memory", env.get("mem", {}).get("MemTotal", "?")),
        ("display", f"{backend}, nested headless"
                    + (f", {disp.get('size')}" if disp.get("size") else "")
                    + (f", {refresh} Hz nominal" if refresh else "")),
        ("display command", f"`{disp_cmd}`" if disp_cmd else "-"),
        ("GPU stack", env.get("mesa", "?")),
        ("load at start", env.get("loadavg_start", "?")),
        ("rustc / python", f"{env.get('rustc', '?')} / "
                           f"python {env.get('python', '?')}"),
    ]
    if cpu.get("scaling_driver"):
        rows.insert(4, ("cpufreq driver", cpu["scaling_driver"]))
    lumen_git = env.get("lumen_git") or {}
    if lumen_git.get("sha"):
        rows.append(("lumen checkout", (lumen_git["sha"][:12]
                     + (" (dirty)" if lumen_git.get("dirty") else ""))))

    L = ["## Environment", "",
         "Machine facts that move the numbers. A result is only comparable "
         "with another run on the same block.", "",
         "| item | value |", "|---|---|"]
    for k, v in rows:
        L.append(f"| {k} | {ascii_only(v)} |")
    L.append("")
    if versions:
        L.append("Toolkit version per framework: "
                 + "; ".join(f"{k} {ascii_only(v)}"
                             for k, v in versions.items()) + ".")
        L.append("")
    return L


def methodology_block(results):
    """Plain-language guide to every column and term in this report."""
    rcfg = report_config(results)
    cfg = results.get("config") or {}
    n_start = rcfg["startup_runs"]
    L = ["## How to read these tables", ""]
    L.append(
        "Every number is a **median**: the middle value of the repeated "
        "measurements, so one slow launch cannot drag it around. Next to it "
        "is a **spread**, showing how much the repeats disagreed. Small "
        "spread means the number is solid; large spread means the machine, "
        "not the framework, is doing the talking.")
    L.append("")
    L.append("Terms used in the columns:")
    L.append("")
    L.append("* **median**: the middle measurement. Half were faster, half "
             "slower.")
    L.append("* **IQR** (interquartile range): the width of the middle half "
             "of the measurements. A spread that ignores the extremes.")
    L.append("* **MAD** (median absolute deviation): the typical distance "
             "of a measurement from the median. A second spread, even less "
             "sensitive to extremes than the IQR. Shown in parentheses "
             "after the IQR.")
    L.append("* **min**: the fastest measurement seen. Treated as the noise "
             "floor: work cannot go faster than itself, so anything above "
             "min is interference or variance.")
    L.append(f"* **{int(rcfg['confidence'] * 100)}% CI** (confidence "
             "interval) on startup: the range where the median would "
             "plausibly land if the same cell were measured again. It is "
             "computed by resampling the recorded launches "
             f"({rcfg['resamples']} times, a percentile bootstrap). **If two "
             "frameworks' intervals overlap, the data does not separate "
             "them**; do not read the gap between their medians as real. "
             "Overlapping pairs are listed under the startup table.")
    L.append("* **(!)**: unstable cell, meaning IQR divided by median is "
             f"above {rcfg['unstable']:.0%}. Treat that number as "
             "indicative, not precise.")
    L.append("* **(2o)**: two measurements fell outside the outlier fences "
             "and were kept in the sample. See the outlier policy below.")
    L.append("* **frame percentile columns** (p50/p95/p99): p50 is the "
             "typical frame interval, p95 and p99 are the slow tail; a "
             "16.7 ms p50 with a 40 ms p99 means smooth scrolling with "
             "visible hitches. " + FRAME_CELL_LEGEND)
    L.append("* **`+/-`**: half the IQR, the form used where a table has "
             "no room for its own spread column (the startup column of the "
             "forms/list/textview tables, and the calibration figures).")
    L.append("* **memory columns**: PSS (proportional set size, the "
             "process's share of physical memory, counting shared pages "
             "only in proportion) in MiB, with RSS (resident set size, all "
             "resident pages) in parentheses. `+/-` on PSS is half the IQR "
             "across the repeated launches.")
    L.append("")
    counts = []
    if n_start:
        counts.append(f"startup: {n_start} launches per cell"
                      + (f" (+{rcfg['startup_warmup']} warmup)"
                         if rcfg["startup_warmup"] else ""))
    if rcfg["scroll_passes"]:
        counts.append(f"scroll: {rcfg['scroll_passes']} passes x "
                      f"{cfg.get('scroll_seconds', '?')} s")
    if rcfg["interact_passes"]:
        counts.append(f"interact: {rcfg['interact_passes']} passes x "
                      f"{cfg.get('interact_cycles', '?')} cycles")
    if rcfg["mem_runs"]:
        counts.append(f"idle memory: {rcfg['mem_runs']} launches per cell")
    if rcfg["calibration_runs"]:
        counts.append(f"calibration: {rcfg['calibration_runs']} launches")
    if counts:
        L.append("**Sample counts.** " + "; ".join(counts)
                 + ". Every count is an environment knob (see README.md) and "
                   "is recorded in `results.json` next to the numbers it "
                   "produced, together with each metric's raw per-iteration "
                   "samples, so any other statistic can be recomputed "
                   "without measuring again.")
        L.append("")
    L.append("**Warmup.** Measurements thrown away before recording starts, "
             "and why:")
    L.append("")
    L.append(WARMUP_POLICY)
    L.append("")
    L.append("**Outliers.** " + OUTLIER_POLICY.replace("\n", " "))
    L.append("")
    if rcfg["schema"] < SCHEMA_VERSION:
        L.append(f"This report renders a schema-{rcfg['schema']} "
                 f"`results.json` (the current harness writes schema "
                 f"{SCHEMA_VERSION}). That run recorded every startup "
                 "sample but no interval, minimum or MAD, so those are "
                 "recomputed here from the stored samples. Columns the run "
                 "never recorded, such as per-frame samples, read `-`.")
        L.append("")
    return L


def startup_block(results, rcfg, cells):
    """Startup detail: median, spread, floor, interval, and which pairs of
    frameworks the data does not separate."""
    L = ["## Startup detail (external, ms)", "",
         "External startup is process spawn to the first presented frame, "
         "measured identically for all eight frameworks. This is the one "
         "metric where the report carries confidence intervals, because it "
         "is the one most often quoted as a single number.", ""]
    for app in APPS:
        entries = []
        for fw in FRAMEWORKS:
            s = enrich(startup_summary(cells.get(fw, {}).get(app, {})), rcfg)
            if s and s.get("median") is not None:
                entries.append((fw, s))
        if not entries:
            continue
        entries.sort(key=lambda e: e[1]["median"])
        L.append(f"### {app}")
        L.append("")
        L.append(f"| framework | median ms | IQR (MAD) | min | "
                 f"{int(rcfg['confidence'] * 100)}% CI | outliers | n |")
        L.append("|---|---|---|---|---|---|---|")
        for fw, s in entries:
            n_out = s.get("n_outliers", len(s.get("outliers") or []))
            L.append(f"| {fw} | {fmt_median(s)} | {fmt_spread(s)} "
                     f"| {fmt_ms(s.get('min'))} | {fmt_ci(s)} "
                     f"| {n_out} | {s.get('n', '-')} |")
        L.append("")
        pairs = overlapping_pairs(entries)
        if pairs:
            L.append("Intervals overlap for "
                     + ", ".join(f"{a}/{b}" for a, b in pairs)
                     + ". The data does not separate those pairs; read them "
                       "as the same startup time.")
        elif any(st.ci_bounds(s) for _, s in entries):
            L.append("No intervals overlap: every framework's startup time "
                     "is separated from the others by more than the "
                     "measurement noise.")
        L.append("")
    return L


def write_results_json(results):
    RESULTS_JSON.write_text(json.dumps(results, indent=2) + "\n")
    log(f"wrote {RESULTS_JSON}")


def write_report(results, write_json=True):
    """Render results.md (and, unless told otherwise, results.json)."""
    if write_json:
        write_results_json(results)
    rcfg = report_config(results)
    env = results.get("env", {})
    sizes = results.get("sizes", {})
    versions = results.get("versions", {}) or env.get("toolchains", {})
    rounds = results.get("rounds", [])
    cells = rounds[0].get("cells", {}) if rounds else {}

    L = []
    L.append("# Cross-framework benchmark results")
    L.append("")
    L.append(f"Generated: {results.get('generated', '?')}  ")
    L.append(f"Host: {env.get('hostname', '?')} | "
             f"{env.get('cpu_model', '?')} | "
             f"display: {results.get('display_backend', '?')} "
             f"(nested headless) | schema {rcfg['schema']}")
    L.append("")
    n_rounds = len(rounds)
    L.append(f"The whole matrix is measured {'twice' if n_rounds > 1 else 'once'}; "
             "each full pass over it is a run. The tables below report run 1."
             + (" The run-to-run agreement section near the end compares run 1 "
                "with run 2 metric by metric and names anything that moved "
                "more than the stated threshold." if n_rounds > 1 else ""))
    L.append("")
    L.append("Startup is measured the same way across all eight frameworks: "
             "external = harness CLOCK_MONOTONIC spawn -> first `first_frame` "
             "stdout marker; self = the app's own CLOCK_MONOTONIC "
             "exec/main -> first-frame (`startup_ms:`). This includes Lumen, "
             "whose windowed backend emits both markers under "
             "`LUMEN_BOOT_TRACE`; there is no MCP (the harness control channel "
             "to Lumen) connect/poll in the startup path (MCP drives only the "
             "scroll/interact passes). See the clock-sources table and caveats "
             "below.")
    L.append("")
    L.extend(env_block(results))
    L.extend(methodology_block(results))

    def cell(fw, app):
        return cells.get(fw, {}).get(app, {})

    # hello ---------------------------------------------------------------
    L.append("## hello - startup floor, baseline memory, binary size")
    L.append("")
    L.append("| framework | version | binary (stripped) | startup ext ms | "
             "ext IQR (MAD) | ext min | startup self ms | PSS idle MiB (RSS) "
             "| PSS @5 s |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for fw in FRAMEWORKS:
        c = cell(fw, "hello")
        ext = enrich(startup_summary(c), rcfg)
        selfms = enrich(startup_summary(c, "self_ms"), rcfg)
        L.append(
            f"| {fw} | {ascii_only(versions.get(fw))} "
            f"| {size_str(sizes, fw, 'hello')} "
            f"| {fmt_median(ext)} | {fmt_spread(ext)} "
            f"| {fmt_ms(ext.get('min'))} | {fmt_median(selfms)} "
            f"| {fmt_mem(c.get('mem_idle'), c.get('mem_idle_stats'))} "
            f"| {fmt_mem(c.get('mem_5s'), c.get('mem_5s_stats'))} |")
    L.append("")

    # forms ---------------------------------------------------------------
    L.append("## forms - ~40-widget settings page")
    L.append("")
    L.append("Interact pass = 4 cycles x (40-step focus walk + 20-step "
             "toggle-all), one step per 16 ms; frame-interval percentiles "
             "over the pass. " + FRAME_CELL_LEGEND)
    L.append("")
    L.append("| framework | binary | startup ext ms | interact p50 ms | "
             "interact p95 ms | interact p99 ms | PSS idle (RSS) | PSS post |")
    L.append("|---|---|---|---|---|---|---|---|")
    for fw in FRAMEWORKS:
        c = cell(fw, "forms")
        ext = enrich(startup_summary(c), rcfg)
        w = c.get("interact")
        L.append(
            f"| {fw} | {size_str(sizes, fw, 'forms')} "
            f"| {fmt_stat(ext)} "
            f"| {fmt_pct(w, 'p50_ms')} | {fmt_pct(w, 'p95_ms')} "
            f"| {fmt_pct(w, 'p99_ms')} "
            f"| {fmt_mem(c.get('mem_idle'), c.get('mem_idle_stats'))} "
            f"| {fmt_mem(c.get('mem_post'), c.get('mem_post_stats'))} |")
    L.append("")

    # list / textview -----------------------------------------------------
    for app, blurb in (
        ("list", "10,000-row list scrolled at 1000 px/s"),
        ("textview", "5,000 wrapped paragraphs (~1.1 MiB) scrolled at 1000 px/s"),
    ):
        L.append(f"## {app} - {blurb}")
        L.append("")
        L.append(FRAME_CELL_LEGEND)
        L.append("")
        L.append("| framework | binary | startup ext ms | scroll p50 ms | "
                 "scroll p95 ms | scroll p99 ms | PSS idle (RSS) | PSS post |")
        L.append("|---|---|---|---|---|---|---|---|")
        for fw in FRAMEWORKS:
            c = cell(fw, app)
            ext = enrich(startup_summary(c), rcfg)
            w = c.get("scroll")
            L.append(
                f"| {fw} | {size_str(sizes, fw, app)} "
                f"| {fmt_stat(ext)} "
                f"| {fmt_pct(w, 'p50_ms')} | {fmt_pct(w, 'p95_ms')} "
                f"| {fmt_pct(w, 'p99_ms')} "
                f"| {fmt_mem(c.get('mem_idle'), c.get('mem_idle_stats'))} "
                f"| {fmt_mem(c.get('mem_post'), c.get('mem_post_stats'))} |")
        L.append("")

    L.extend(startup_block(results, rcfg, cells))

    # calibration ---------------------------------------------------------
    cal = results.get("calibration")
    if cal:
        L.append("## Calibration - bounding systematic error")
        L.append("")
        f = enrich(cal.get("spawn_to_marker_floor_ms", {}), rcfg)
        k = cal.get("harness_vs_kernel_spawn_ms", {})
        p = enrich(cal.get("marker_pipe_latency_ms", {}), rcfg)
        n_cal = f.get("n", rcfg["calibration_runs"] or "?")
        L.append("Each line is median ms, then half the IQR as the spread, "
                 "the minimum, and the confidence interval where one is "
                 "available.")
        L.append("")
        L.append(f"* spawn->marker floor (trivial C binary, n={n_cal}): "
                 f"**{fmt_median(f, '.2f')} ms** "
                 f"+/-{fmt_ms((f.get('iqr') or 0) / 2, '.2f')}, "
                 f"min {fmt_ms(f.get('min'), '.2f')}, "
                 f"CI {fmt_ci(f, '.2f')}. Harness plus fork/exec overhead, "
                 "baked identically into every external startup number.")
        L.append(f"* harness-vs-kernel spawn timestamp (independent, "
                 f"/proc starttime): **{fmt_median(k, '.2f')} ms** "
                 f"+/-{fmt_ms((k.get('iqr') or 0) / 2, '.2f')}. Bounds the "
                 "harness's spawn-anchor error.")
        L.append(f"* marker pipe latency (app clock vs harness clock): "
                 f"**{fmt_median(p, '.2f')} ms** "
                 f"+/-{fmt_ms((p.get('iqr') or 0) / 2, '.2f')}, "
                 f"CI {fmt_ci(p, '.2f')}. Bounds marker-arrival skew.")
        L.append("* Consequence: cross-framework startup deltas below "
                 "~1 ms are inside the systematic error band and not "
                 "meaningful, whatever the medians say.")
        L.append("")

    # agreement -----------------------------------------------------------
    rows = agreement_rows(results, rcfg["tolerance"])
    if rows:
        tol = rcfg["tolerance"]
        bad = [r for r in rows if not r["agree"]]
        n_ok = len(rows) - len(bad)
        L.append("## Run-to-run agreement (run 1 vs run 2)")
        L.append("")
        L.append(f"The same matrix was measured twice. For each headline "
                 f"number, agreement is the **relative difference** of the "
                 f"two runs' medians: the gap between them divided by their "
                 f"average. A metric agrees when that difference is at or "
                 f"below **{tol:.0%}**. A metric that disagrees is not "
                 f"necessarily wrong, but its single-run number should not "
                 f"be quoted to better than the difference shown.")
        L.append("")
        L.append(f"{n_ok}/{len(rows)} metrics agree within {tol:.0%}.")
        L.append("")
        if bad:
            worst = sorted(bad, key=lambda r: -(r["rel_diff"] or 0))
            shown = worst[:15]
            L.append(f"Over threshold ({len(bad)}), largest first"
                     + (f" (top {len(shown)}; the rest are in the table "
                        "below)" if len(worst) > len(shown) else "") + ":")
            L.append("")
            for r in shown:
                L.append(f"* **{r['fw']}/{r['app']} {r['metric']}**: "
                         f"{r['run1']} vs {r['run2']} "
                         f"({r['rel_diff']:.1%} apart)")
            L.append("")
        else:
            L.append("Nothing exceeds the threshold.")
            L.append("")
        L.append("| framework | app | metric | run 1 | run 2 | abs delta | "
                 "rel diff | within threshold |")
        L.append("|---|---|---|---|---|---|---|---|")
        for r in rows:
            rel = f"{r['rel_diff']:.1%}" if r["rel_diff"] is not None else "-"
            L.append(f"| {r['fw']} | {r['app']} | {r['metric']} "
                     f"| {r['run1']} | {r['run2']} | {r['abs_delta']} "
                     f"| {rel} | {'yes' if r['agree'] else 'no'} |")
        L.append("")

    L.append(CLOCK_TABLE)
    L.append(CAVEATS)
    RESULTS_MD.write_text("\n".join(L) + "\n")
    log(f"wrote {RESULTS_MD}")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def load_results():
    if RESULTS_JSON.exists():
        try:
            r = json.loads(RESULTS_JSON.read_text())
            if "rounds" in r:
                return r
        except ValueError:
            pass
    return {"rounds": []}


def ensure_round(results, idx):
    while len(results["rounds"]) <= idx:
        results["rounds"].append({"cells": {}})
    return results["rounds"][idx]


def measure_round(results, rnd_idx, fws, apps, display, cold=False):
    rnd = ensure_round(results, rnd_idx)
    rnd["started"] = time.strftime("%Y-%m-%d %H:%M:%S %z")
    rnd["loadavg"] = _read("/proc/loadavg")
    t0 = time.monotonic()
    for fw_idx, fw in enumerate(fws):
        if fw == "lumen" and not lumen_available():
            log(f"skip lumen: framework checkout not found at {LUMEN_REPO}")
            continue
        # Refresh the compositor at each framework boundary so GL-renderer
        # GPU state doesn't accumulate across a full round into the
        # transient failures that only appear late (see `Display.restart`).
        # Skipped before the first framework; `display` is already fresh.
        if fw_idx > 0 and display.backend == "weston":
            log(f"--- restarting compositor before {fw} ---")
            display.restart()
        for app in apps:
            try:
                cell = measure_cell(fw, app, display, cold=cold)
            except Exception as e:
                # One framework/app must never sink the whole round. Record
                # the failure on the cell (renders as "-") and press on.
                log(f"!!! {fw}/{app}: cell failed, recording N/A and "
                    f"continuing: {e}")
                cell = {"error": str(e)}
            rnd["cells"].setdefault(fw, {})[app] = cell
            write_report(results)
    rnd["wall_s"] = round(time.monotonic() - t0, 1)
    log(f"round {rnd_idx} wall time: {rnd['wall_s']} s")


def main():
    args = [a for a in sys.argv[1:]]
    cold = "--cold" in args
    if cold:
        args.remove("--cold")
    rnd_idx = 0
    if "--round" in args:
        i = args.index("--round")
        rnd_idx = int(args[i + 1])
        del args[i:i + 2]
    cmd = args[0] if args else "all"
    sel = args[1:]

    fws = [f for f in sel if f in FRAMEWORKS] or list(FRAMEWORKS)
    apps = [a for a in sel if a in APPS] or list(APPS)
    unknown = [s for s in sel if s not in FRAMEWORKS and s not in APPS]
    if unknown:
        print(f"unknown framework/app: {unknown}\n{__doc__}")
        return 2

    log(f"cpu pinning: {CPU_PIN_NOTE}")
    try:
        os.sched_setaffinity(0, HARNESS_CPUS)
    except OSError:
        pass

    results = load_results()
    if cmd != "report":
        # `report` re-renders an existing results.json and must not stamp
        # this invocation's settings onto someone else's data.
        results["generated"] = time.strftime("%Y-%m-%d %H:%M:%S %z")
        results["schema_version"] = SCHEMA_VERSION
        results["config"] = config_block()

    if cmd in ("build", "all"):
        sizes, versions = build_all()
        results["sizes"] = sizes
        results["versions"] = versions
        write_report(results)

    if cmd in ("calibrate", "measure", "all", "validate"):
        results["env"] = capture_env()
        results["governor_note"] = try_set_governor()
        display = Display()
        display.start()
        results["display_backend"] = display.backend
        results["env"]["display"] = display.describe()
        try:
            if cmd in ("calibrate", "all", "validate"):
                log("=== calibration ===")
                results["calibration"] = calibrate(display)
                write_report(results)
            if cmd == "measure":
                measure_round(results, rnd_idx, fws, apps, display, cold=cold)
            elif cmd == "all":
                measure_round(results, 0, fws, apps, display)
            elif cmd == "validate":
                measure_round(results, 0, fws, apps, display)
                measure_round(results, 1, fws, apps, display)
        finally:
            display.stop()
        write_report(results)

    if cmd == "report":
        # Render only: results.json is the input here, and a re-render must
        # never rewrite recorded data.
        write_report(results, write_json=False)

    if cmd not in ("build", "calibrate", "measure", "all", "validate", "report"):
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
