#!/usr/bin/env python3
"""Cross-framework GUI benchmark harness.

Four apps (hello / list / forms / textview), each implemented in six
frameworks (Lumen, Slint, egui, iced, Qt6 Widgets, GTK4 C), measured the
same way:

  * startup: process spawn -> first presented frame, n=15 (+1 discarded
    warmup), median + IQR, Tukey-fence outlier count, unstable flag
  * scroll (list, textview): 3 passes x 6 s of programmatic scrolling at
    1000 px/s; per-frame deltas -> p50/p95/p99 per pass, cross-pass median
    + spread
  * interact (forms): 3 passes x 4 cycles of (40-step focus walk + 20-step
    toggle-all), one step / 16 ms; same frame-delta stats
  * memory: PSS primary (smaps_rollup) + RSS secondary, at two fixed
    points: idle (2 s after first frame) and post-workload (right after a
    pass ends; for hello, 5 s after first frame)
  * stripped binary size per app

All measurement runs happen under a nested headless compositor
(weston --backend=headless, fallback Xvfb); nothing appears on the
developer's desktop. Lumen runs `lumenc run --headless` and is measured
externally over its MCP server (persistent connection, `lumen.tick`
sampled every 0.5 ms) - see the caveats section of results.md.

Usage:
    harness/bench.py build                    # build + size everything
    harness/bench.py calibrate                # measurement-error anchors
    harness/bench.py measure [fw] [app] [--round N] [--cold]
    harness/bench.py all                      # build + calibrate + round 0 + report
    harness/bench.py validate                 # calibrate + rounds 0 and 1 + agreement
    harness/bench.py report                   # rewrite results.md from results.json
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

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "harness" / "out"
BIN_OUT = OUT / "bin"
CORPUS = OUT / "corpus.txt"
RESULTS_JSON = ROOT / "results.json"
RESULTS_MD = ROOT / "results.md"

# Deliberately NOT plain CARGO_TARGET_DIR: the developer shell exports a
# global CARGO_TARGET_DIR pointing at the Lumen repo's shared target dir,
# and building into that would poison its fingerprints.
CARGO_TARGET = os.environ.get("BENCH_CARGO_TARGET_DIR",
                              "/Storage/cargo-target-benchcomp")
LUMEN_REPO = Path(os.environ.get("LUMEN_REPO", "/home/artur/Lumen"))
# Must match lumen/*/lumen.toml [mcp].port. Deliberately not 7878 -
# other lumenc instances (dev tooling) commonly hold the default port.
LUMEN_MCP_PORT = 7941

APPS = ("hello", "list", "forms", "textview")
STARTUP_RUNS = 15          # recorded runs; +1 warmup discarded
SCROLL_PASSES = 3
SCROLL_SECONDS = 6.0
SCROLL_PX_PER_S = 1000.0
INTERACT_PASSES = 3
INTERACT_CYCLES = 4
INTERACT_STEP_S = 0.016
LUMEN_SCROLL_INTERVAL_S = 1.0 / 60.0
LUMEN_TICK_SAMPLE_S = 0.0005   # 0.5 ms monotonic lumen.tick sampling

# CPU pinning: measured apps and the compositor get disjoint fixed CPU
# sets; the harness keeps itself off both. Recorded in env capture.
N_CPUS = os.cpu_count() or 4
if N_CPUS >= 16:
    APP_CPUS = set(range(4, 12))
    DISPLAY_CPUS = {2, 3}
    HARNESS_CPUS = set(range(12, 16))
else:
    APP_CPUS = set(range(N_CPUS))
    DISPLAY_CPUS = set(range(N_CPUS))
    HARNESS_CPUS = set(range(N_CPUS))

WESTON_SOCKET = "wayland-bench"
XVFB_DISPLAY = ":97"

UNSTABLE_IQR_FRACTION = 0.05   # IQR/median above this flags the cell


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
    }
    return rel[fw]


FRAMEWORKS = ("lumen", "slint", "egui", "iced", "qt-widgets", "gtk4")


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


def capture_env():
    u = os.uname()
    model = None
    for line in (_read("/proc/cpuinfo") or "").splitlines():
        if line.startswith("model name"):
            model = line.split(":", 1)[1].strip()
            break
    governors = sorted({
        _read(f"/sys/devices/system/cpu/cpu{c}/cpufreq/scaling_governor") or "?"
        for c in range(N_CPUS)})
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
        "cpu_model": model,
        "cpu_count": N_CPUS,
        "governors": governors,
        "cpufreq_boost": _read("/sys/devices/system/cpu/cpufreq/boost"),
        "app_cpus": sorted(APP_CPUS),
        "display_cpus": sorted(DISPLAY_CPUS),
        "harness_cpus": sorted(HARNESS_CPUS),
        "mem": meminfo,
        "loadavg_start": _read("/proc/loadavg"),
        "mesa": _cmd_out(["pacman", "-Q", "mesa"]),
        "host_compositor": os.environ.get("XDG_CURRENT_DESKTOP"),
        "weston": (_cmd_out(["weston", "--version"]) or "").splitlines()[:1],
        "qt": _cmd_out(["pkg-config", "--modversion", "Qt6Widgets"]),
        "gtk4": _cmd_out(["pkg-config", "--modversion", "gtk4"]),
        "rustc": _cmd_out(["rustc", "-V"]),
        "python": sys.version.split()[0],
        "lumen_git": {"sha": lumen_sha, "dirty": lumen_dirty},
        "lockfile_sha256_16": {
            "egui": _sha256(ROOT / "egui" / "Cargo.lock"),
            "iced": _sha256(ROOT / "iced" / "Cargo.lock"),
            "slint": _sha256(ROOT / "slint" / "Cargo.lock"),
            "lumen": _sha256(LUMEN_REPO / "Cargo.lock"),
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


def build_all():
    BIN_OUT.mkdir(parents=True, exist_ok=True)

    # Deterministic corpus + generated Lumen textview markup.
    run_checked([sys.executable, str(ROOT / "harness" / "gen_corpus.py")])

    # Calibration probe.
    calib_src = OUT / "calib.c"
    calib_src.write_text(CALIB_C)
    run_checked(["cc", "-O2", "-o", str(BIN_OUT / "calib"), str(calib_src)])

    # Lumen: build the lumenc runner from the framework repo, validate apps.
    run_checked(
        ["cargo", "build", "--release", "-p", "lumenc",
         "--manifest-path", str(LUMEN_REPO / "Cargo.toml")],
        env=cargo_env(),
    )
    for app in APPS:
        run_checked([str(fw_bin("lumen", "x")), "check",
                     str(ROOT / "lumen" / app)])

    for name in ("slint", "egui", "iced"):
        run_checked(["cargo", "build", "--release"],
                    cwd=ROOT / name, env=cargo_env())

    for name in ("qt-widgets", "gtk4"):
        d = ROOT / name
        run_checked(["cmake", "-S", str(d), "-B", str(d / "build"),
                     "-DCMAKE_BUILD_TYPE=Release"])
        run_checked(["cmake", "--build", str(d / "build"), "-j",
                     str(os.cpu_count() or 4)])

    # Stripped-copy sizes (never strip cargo outputs in place).
    sizes = {}
    for fw in FRAMEWORKS:
        sizes[fw] = {}
        if fw == "lumen":
            src = fw_bin("lumen", "x")
            dst = BIN_OUT / src.name
            shutil.copy2(src, dst)
            subprocess.run(["strip", str(dst)], check=True)
            sizes[fw]["runtime_stripped_bytes"] = dst.stat().st_size
            for app in APPS:
                d = ROOT / "lumen" / app
                sizes[fw][app] = {"app_payload_bytes": sum(
                    f.stat().st_size for f in d.iterdir() if f.is_file())}
            continue
        for app in APPS:
            src = fw_bin(fw, app)
            dst = BIN_OUT / src.name
            shutil.copy2(src, dst)
            subprocess.run(["strip", str(dst)], check=True)
            sizes[fw][app] = {"stripped_bytes": dst.stat().st_size}

    # Toolkit versions for the report.
    versions = {}
    sha = _cmd_out(["git", "-C", str(LUMEN_REPO), "rev-parse", "--short", "HEAD"])
    if sha:
        versions["lumen"] = f"git {sha}"
    for name, pkg in (("slint", "slint"), ("egui", "eframe"), ("iced", "iced")):
        lock = ROOT / name / "Cargo.lock"
        if lock.exists():
            lines = lock.read_text().splitlines()
            for i, l in enumerate(lines):
                if l == f'name = "{pkg}"' and i + 1 < len(lines):
                    versions[name] = pkg + " " + lines[i + 1].split('"')[1]
                    break
    for name, pkg in (("qt-widgets", "Qt6Widgets"), ("gtk4", "gtk4")):
        v = _cmd_out(["pkg-config", "--modversion", pkg])
        if v:
            versions[name] = f"{pkg} {v}"
    return sizes, versions


# --------------------------------------------------------------------------
# Headless display
# --------------------------------------------------------------------------

class Display:
    """Nested headless compositor. Prefers weston, falls back to Xvfb."""

    def __init__(self):
        self.proc = None
        self.xvfb = None
        self.backend = None

    def _preexec(self):
        os.setsid()
        try:
            os.sched_setaffinity(0, DISPLAY_CPUS)
        except OSError:
            pass

    def _start_xvfb(self):
        if shutil.which("Xvfb"):
            self.xvfb = subprocess.Popen(
                ["Xvfb", XVFB_DISPLAY, "-screen", "0", "1280x1024x24"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                preexec_fn=self._preexec)
            time.sleep(1.0)
            if self.xvfb.poll() is not None:
                self.xvfb = None

    def start(self):
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        self._start_xvfb()
        if shutil.which("weston"):
            env = os.environ.copy()
            env["XDG_RUNTIME_DIR"] = runtime_dir
            env.pop("WAYLAND_DISPLAY", None)
            self.proc = subprocess.Popen(
                ["weston", "--backend=headless", f"--socket={WESTON_SOCKET}",
                 "--width=1280", "--height=1024"],
                env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                preexec_fn=self._preexec)
            sock = Path(runtime_dir) / WESTON_SOCKET
            for _ in range(100):
                if sock.exists():
                    self.backend = "weston"
                    log(f"weston headless up on {WESTON_SOCKET}")
                    return
                if self.proc.poll() is not None:
                    break
                time.sleep(0.1)
            raise RuntimeError("weston failed to create its socket")
        if self.xvfb is not None:
            self.backend = "xvfb"
            log(f"Xvfb up on {XVFB_DISPLAY}")
            return
        raise RuntimeError(
            "neither weston nor Xvfb is installed; cannot run measurements "
            "headlessly. Install weston (preferred) and re-run.")

    def app_env(self, fw_name):
        env = os.environ.copy()
        # Never let an app reach the real session.
        env.pop("WAYLAND_DISPLAY", None)
        env.pop("DISPLAY", None)
        env["BENCH_SCROLL_SECONDS"] = str(SCROLL_SECONDS)
        env["BENCH_INTERACT_CYCLES"] = str(INTERACT_CYCLES)
        env["BENCH_CORPUS"] = str(CORPUS)
        if fw_name == "lumen":
            # lumenc --headless renders offscreen (no window); DISPLAY
            # points at the harness Xvfb for GPU-discovery parity.
            if self.xvfb is not None:
                env["DISPLAY"] = XVFB_DISPLAY
            return env
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


def spawn(fw_name, app, mode_args, display):
    if fw_name == "lumen":
        cmd = [str(fw_bin("lumen", app)), "run", str(ROOT / "lumen" / app),
               "--headless", "--size", "800x600"]
    else:
        cmd = [str(fw_bin(fw_name, app))] + mode_args
    return app_popen(cmd, display.app_env(fw_name))


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
    the app sources. Unprivileged - anonymous pages and already-mapped
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

def quartiles(vals):
    if not vals:
        return (None, None, None)
    q = statistics.quantiles(vals, n=4, method="inclusive") if len(vals) > 1 \
        else [vals[0]] * 3
    return (q[0], statistics.median(vals), q[2])


def run_stats(vals):
    """median + IQR + Tukey outliers + unstable flag over repeated runs."""
    if not vals:
        return {"n": 0}
    q1, med, q3 = quartiles(vals)
    iqr = q3 - q1
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    outliers = [v for v in vals if v < lo or v > hi]
    unstable = bool(med) and (iqr / med > UNSTABLE_IQR_FRACTION)
    return {
        "n": len(vals),
        "runs": [round(v, 3) for v in vals],
        "median": round(med, 3),
        "q1": round(q1, 3),
        "q3": round(q3, 3),
        "iqr": round(iqr, 3),
        "outliers": [round(v, 3) for v in outliers],
        "unstable": unstable,
    }


def frame_stats(deltas):
    if not deltas:
        return {"frames": 0}
    ordered = sorted(deltas)

    def pct(p):
        idx = min(len(ordered) - 1, max(0, round(p / 100.0 * len(ordered)) - 1))
        return ordered[idx]

    return {
        "frames": len(deltas),
        "p50_ms": round(pct(50), 3),
        "p95_ms": round(pct(95), 3),
        "p99_ms": round(pct(99), 3),
        "max_ms": round(ordered[-1], 3),
        "mean_ms": round(statistics.fmean(deltas), 3),
    }


def combine_passes(passes):
    """Cross-pass median + spread for each percentile metric."""
    out = {"passes": passes}
    for key in ("p50_ms", "p95_ms", "p99_ms"):
        vals = [p[key] for p in passes if key in p]
        if vals:
            out[key + "_median"] = round(statistics.median(vals), 3)
            out[key + "_spread"] = round(max(vals) - min(vals), 3)
    out["frames_total"] = sum(p.get("frames", 0) for p in passes)
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
    'First presented frame' for Lumen = first headless tick+render
    completed, observed through the MCP frame counter."""
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
    spawn_deltas = []  # harness-vs-kernel spawn timestamp deltas
    for i in range(STARTUP_RUNS + 1):  # +1 warmup, discarded
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
        if i == 0:
            time.sleep(0.3)
            continue  # warmup
        external.append((ts - t_spawn) * 1000.0)
        if line2:
            internal.append(float(line2.split(":")[1]))
        if kstart is not None:
            spawn_deltas.append((t_spawn - kstart) * 1000.0)
        time.sleep(0.3)
    out = {
        "external_ms": run_stats(external),
        "self_ms": run_stats(internal) if internal else None,
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
    external = []
    spawn_deltas = []
    for i in range(STARTUP_RUNS + 1):
        if cold:
            evict_page_cache("lumen", app)
        proc, client, t_spawn, ts = lumen_spawn_and_wait(app, display)
        kstart = proc_start_monotonic(proc.pid)
        client.close()
        kill(proc)
        if i == 0:
            time.sleep(0.3)
            continue
        external.append((ts - t_spawn) * 1000.0)
        if kstart is not None:
            spawn_deltas.append((t_spawn - kstart) * 1000.0)
        time.sleep(0.3)
    out = {
        "external_ms": run_stats(external),
        "self_ms": None,
        "clock_note": "external: harness CLOCK_MONOTONIC spawn -> MCP frame "
                      "counter >= 1, sampled every 0.5 ms over a persistent "
                      "connection; no in-app clock exists (no per-frame hook)",
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
    'toggle' (12 of them); radios report 'interactive' (8 - buttons and
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
    direct state writes don't do - see caveats)."""
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

def measure_cell(fw, app, display, cold=False):
    cell = {}
    log(f"=== {fw}/{app}: startup x{STARTUP_RUNS} ===")
    if fw == "lumen":
        cell["startup"] = measure_startup_lumen(app, display, cold=cold)
    else:
        cell["startup"] = measure_startup_native(fw, app, display, cold=cold)

    log(f"=== {fw}/{app}: idle memory ===")
    if fw == "lumen":
        idle, late = measure_idle_mem_lumen(app, display)
    else:
        idle, late = measure_idle_mem_native(fw, app, display)
    cell["mem_idle"] = idle
    if late:
        cell["mem_5s"] = late

    workload = {"list": "scroll", "textview": "scroll", "forms": "interact"}.get(app)
    if workload == "scroll":
        passes, post_mems = [], []
        for p in range(SCROLL_PASSES):
            log(f"=== {fw}/{app}: scroll pass {p + 1}/{SCROLL_PASSES} ===")
            if fw == "lumen":
                st, post = measure_scroll_pass_lumen(app, display)
            else:
                st, post = measure_pass_native(fw, app, "--scroll-bench", display)
            passes.append(st)
            post_mems.append(post)
            time.sleep(0.5)
        cell["scroll"] = combine_passes(passes)
        cell["mem_post"] = median_mem(post_mems)
    elif workload == "interact":
        passes, post_mems = [], []
        for p in range(INTERACT_PASSES):
            log(f"=== {fw}/{app}: interact pass {p + 1}/{INTERACT_PASSES} ===")
            if fw == "lumen":
                st, post = measure_interact_pass_lumen(display)
            else:
                st, post = measure_pass_native(fw, app, "--interact", display)
            passes.append(st)
            post_mems.append(post)
            time.sleep(0.5)
        cell["interact"] = combine_passes(passes)
        cell["mem_post"] = median_mem(post_mems)
    return cell


def median_mem(mems):
    out = {}
    for key in ("pss_kb", "rss_kb"):
        vals = [m[key] for m in mems if m.get(key) is not None]
        out[key] = int(statistics.median(vals)) if vals else None
    return out


# --------------------------------------------------------------------------
# Calibration
# --------------------------------------------------------------------------

def calibrate(display):
    """Bound the harness's systematic measurement error with independent
    anchors:

    1. spawn->marker floor: a trivial C binary printing the marker
       immediately. Its external time is pure harness+fork/exec+libc
       overhead - the floor baked into every external startup number.
    2. harness-vs-kernel spawn timestamps: the kernel's own record of
       process creation (/proc/pid/stat starttime) versus the harness's
       pre-Popen monotonic stamp. Bounds the external clock anchor error.
    3. app-clock cross-check: the calib binary also prints its own
       CLOCK_MONOTONIC, letting the harness compare marker arrival time
       against the app-side stamp (pipe+scheduling latency)."""
    ext, kdelta, pipe_lat = [], [], []
    calib = BIN_OUT / "calib"
    for _ in range(30):
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
        ext.append((ts - t_spawn) * 1000.0)
        if kstart is not None:
            kdelta.append((t_spawn - kstart) * 1000.0)
        if line2:
            app_mono = int(line2.split(":")[1]) / 1e9
            pipe_lat.append((ts - app_mono) * 1000.0)
        time.sleep(0.05)
    return {
        "note": "all values ms; medians with IQR over 30 runs",
        "spawn_to_marker_floor_ms": run_stats(ext),
        "harness_vs_kernel_spawn_ms": run_stats(kdelta),
        "marker_pipe_latency_ms": run_stats(pipe_lat),
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
"""

CAVEATS = """\
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

* **Lumen** runs via `lumenc run --headless` (its own offscreen wgpu
  pipeline, demand-driven, no compositor and no vsync), while the other
  five run windowed under a nested headless compositor with their normal
  present paths. Lumen startup includes compiling the `.lmn/.css/.rhai`
  sources (that is how Lumen apps launch today). Lumen's size row is the
  generic `lumenc` runtime plus a few KB of app text. Lumen has no
  in-app per-frame callback by design, so all Lumen numbers are external:
  the MCP frame counter is sampled every 0.5 ms over a persistent
  connection (reading it does not wake the parked loop; only injected
  events do). Frame intervals are therefore quantized at ~0.5 ms, and
  Lumen's demand-driven loop has no compositor vsync: frames land
  against a 16.7 ms deadline anchor, so sub-16.7 p50 readings mean early
  frames, not faster rendering - p95/p99 are the honest cross-framework
  comparison. Scroll is driven by injected wheel events at ~60 Hz x
  16.7 px (sensitivity 1.0, inertia 0 -> 1 wheel px = 1 scroll px).
  The interact pass differs structurally: Tab focus-walk uses real key
  events (like Qt/Slint), but Lumen has no externally reachable state
  setter, so toggle steps scroll the control into view and click it -
  real input-pipeline work (hit-testing, scrolling) that the other
  frameworks' direct state writes do not perform. Lumen's interact
  numbers are therefore an upper bound.
* **iced** has no virtualized list widget: the 10k rows are a plain
  `Column` in a `scrollable`, rebuilt every view pass - idiomatic iced,
  inherently disadvantaged on the list workload and honestly so. Under
  the headless compositor iced's redraw loop is not vsync-throttled
  (~7 ms deltas): its scroll numbers measure raw redraw throughput, not
  presentation cadence. Its textview lays out the full corpus each pass.
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
"""


def fmt_ms(v, spec=".1f"):
    return f"{format(v, spec)}" if isinstance(v, (int, float)) else "-"


def fmt_stat(st, spec=".1f"):
    """median ± IQR/2 rendering with instability flag."""
    if not st or st.get("median") is None:
        return "-"
    s = f"{format(st['median'], spec)} ±{format(st['iqr'] / 2, spec)}"
    if st.get("unstable"):
        s += " ⚠"
    if st.get("outliers"):
        s += f" ({len(st['outliers'])}o)"
    return s


def fmt_pct(cell_metric, key):
    if not cell_metric:
        return "-"
    med = cell_metric.get(key + "_median")
    spread = cell_metric.get(key + "_spread")
    if med is None:
        return "-"
    return f"{med:.2f} ±{(spread or 0) / 2:.2f}"


def fmt_mem(mem):
    if not mem:
        return "-"
    pss = mem.get("pss_kb")
    rss = mem.get("rss_kb")
    if pss is None and rss is None:
        return "-"
    p = f"{pss / 1024:.1f}" if pss else "?"
    r = f"{rss / 1024:.1f}" if rss else "?"
    return f"{p} ({r})"


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


def agreement_rows(results):
    """Round-0 vs round-1 medians for every headline metric.

    Error bars: startup -> max of the two rounds' IQRs; frame
    percentiles -> max of the two rounds' cross-pass spreads (floored at
    5% of the metric); memory -> max(3%, 1 MiB)."""
    rounds = results.get("rounds", [])
    if len(rounds) < 2:
        return []
    r0, r1 = rounds[0].get("cells", {}), rounds[1].get("cells", {})
    rows = []

    def add(fw, app, metric, m0, m1, bar):
        if m0 is None or m1 is None:
            return
        delta = abs(m1 - m0)
        rows.append({
            "fw": fw, "app": app, "metric": metric,
            "round0": m0, "round1": m1, "delta": round(delta, 3),
            "error_bar": round(bar, 3),
            "agree": delta <= bar,
        })

    for fw in FRAMEWORKS:
        for app in APPS:
            c0 = r0.get(fw, {}).get(app)
            c1 = r1.get(fw, {}).get(app)
            if not c0 or not c1:
                continue
            s0 = c0.get("startup", {}).get("external_ms", {})
            s1 = c1.get("startup", {}).get("external_ms", {})
            if s0.get("median") is not None and s1.get("median") is not None:
                bar = max(s0.get("iqr", 0), s1.get("iqr", 0),
                          0.02 * s0["median"])
                add(fw, app, "startup ext ms", s0["median"], s1["median"], bar)
            for wk in ("scroll", "interact"):
                w0, w1 = c0.get(wk), c1.get(wk)
                if not w0 or not w1:
                    continue
                for key in ("p50_ms", "p95_ms", "p99_ms"):
                    m0 = w0.get(key + "_median")
                    m1 = w1.get(key + "_median")
                    if m0 is None or m1 is None:
                        continue
                    bar = max(w0.get(key + "_spread", 0),
                              w1.get(key + "_spread", 0), 0.05 * m0)
                    add(fw, app, f"{wk} {key}", m0, m1, bar)
            p0 = c0.get("mem_idle", {}).get("pss_kb")
            p1 = c1.get("mem_idle", {}).get("pss_kb")
            if p0 and p1:
                bar = max(0.03 * p0, 1024)
                add(fw, app, "idle PSS kB", p0, p1, bar)
    return rows


def write_report(results):
    RESULTS_JSON.write_text(json.dumps(results, indent=2) + "\n")
    env = results.get("env", {})
    sizes = results.get("sizes", {})
    versions = results.get("versions", {})
    rounds = results.get("rounds", [])
    cells = rounds[0].get("cells", {}) if rounds else {}

    L = []
    L.append("# Cross-framework benchmark results")
    L.append("")
    L.append(f"Generated: {results.get('generated', '?')}  ")
    L.append(f"Host: {env.get('hostname', '?')} · kernel {env.get('kernel', '?')} · "
             f"{env.get('cpu_model', '?')} ({env.get('cpu_count', '?')} cpus)  ")
    L.append(f"Governors: {'/'.join(env.get('governors', []))} · "
             f"governor pin: {results.get('governor_note', '?')} · "
             f"app cpus {env.get('app_cpus')}  ")
    L.append(f"Mesa: {env.get('mesa', '?')} · display: "
             f"{results.get('display_backend', '?')} (nested headless) · "
             f"Lumen: {env.get('lumen_git', {}).get('sha', '?')[:12]}"
             f"{' (dirty)' if env.get('lumen_git', {}).get('dirty') else ''}")
    L.append("")
    L.append("Primary numbers below are **round 0**; the run-to-run agreement "
             "table compares round 0 vs round 1. Values are medians; ± is "
             "half the IQR (startup, n=15) or half the cross-pass spread "
             "(frame percentiles, 3 passes). ⚠ = unstable "
             f"(IQR/median > {UNSTABLE_IQR_FRACTION:.0%}); (No) = N Tukey "
             "outliers retained. Memory is PSS in MiB with RSS in "
             "parentheses (both from /proc, idle = first frame + 2 s).")
    L.append("")

    def cell(fw, app):
        return cells.get(fw, {}).get(app, {})

    # hello ---------------------------------------------------------------
    L.append("## hello - startup floor, baseline memory, binary size")
    L.append("")
    L.append("| framework | version | binary (stripped) | startup ext ms | "
             "startup self ms | PSS idle MiB (RSS) | PSS @5 s |")
    L.append("|---|---|---|---|---|---|---|")
    for fw in FRAMEWORKS:
        c = cell(fw, "hello")
        st = c.get("startup", {})
        L.append(
            f"| {fw} | {versions.get(fw, '-')} | {size_str(sizes, fw, 'hello')} "
            f"| {fmt_stat(st.get('external_ms'))} "
            f"| {fmt_stat(st.get('self_ms'))} "
            f"| {fmt_mem(c.get('mem_idle'))} "
            f"| {fmt_mem(c.get('mem_5s'))} |")
    L.append("")

    # forms ---------------------------------------------------------------
    L.append("## forms - ~40-widget settings page")
    L.append("")
    L.append("Interact pass = 4 cycles x (40-step focus walk + 20-step "
             "toggle-all), one step per 16 ms; frame-interval percentiles "
             "over the pass.")
    L.append("")
    L.append("| framework | binary | startup ext ms | interact p50 ms | "
             "interact p95 ms | interact p99 ms | PSS idle (RSS) | PSS post |")
    L.append("|---|---|---|---|---|---|---|---|")
    for fw in FRAMEWORKS:
        c = cell(fw, "forms")
        st = c.get("startup", {})
        w = c.get("interact")
        L.append(
            f"| {fw} | {size_str(sizes, fw, 'forms')} "
            f"| {fmt_stat(st.get('external_ms'))} "
            f"| {fmt_pct(w, 'p50_ms')} | {fmt_pct(w, 'p95_ms')} "
            f"| {fmt_pct(w, 'p99_ms')} "
            f"| {fmt_mem(c.get('mem_idle'))} | {fmt_mem(c.get('mem_post'))} |")
    L.append("")

    # list / textview -----------------------------------------------------
    for app, blurb in (
        ("list", "10,000-row list scrolled at 1000 px/s"),
        ("textview", "5,000 wrapped paragraphs (~1.1 MiB) scrolled at 1000 px/s"),
    ):
        L.append(f"## {app} - {blurb}")
        L.append("")
        L.append("| framework | binary | startup ext ms | scroll p50 ms | "
                 "scroll p95 ms | scroll p99 ms | PSS idle (RSS) | PSS post |")
        L.append("|---|---|---|---|---|---|---|---|")
        for fw in FRAMEWORKS:
            c = cell(fw, app)
            st = c.get("startup", {})
            w = c.get("scroll")
            L.append(
                f"| {fw} | {size_str(sizes, fw, app)} "
                f"| {fmt_stat(st.get('external_ms'))} "
                f"| {fmt_pct(w, 'p50_ms')} | {fmt_pct(w, 'p95_ms')} "
                f"| {fmt_pct(w, 'p99_ms')} "
                f"| {fmt_mem(c.get('mem_idle'))} | {fmt_mem(c.get('mem_post'))} |")
        L.append("")

    # calibration ---------------------------------------------------------
    cal = results.get("calibration")
    if cal:
        L.append("## Calibration - bounding systematic error")
        L.append("")
        f = cal.get("spawn_to_marker_floor_ms", {})
        k = cal.get("harness_vs_kernel_spawn_ms", {})
        p = cal.get("marker_pipe_latency_ms", {})
        L.append(f"* spawn->marker floor (trivial C binary, n=30): "
                 f"**{fmt_stat(f, '.2f')} ms** - harness+fork/exec overhead "
                 "baked identically into every external startup number.")
        L.append(f"* harness-vs-kernel spawn timestamp (independent, "
                 f"/proc starttime): **{fmt_stat(k, '.2f')} ms** - bounds the "
                 "harness's spawn-anchor error.")
        L.append(f"* marker pipe latency (app clock vs harness clock): "
                 f"**{fmt_stat(p, '.2f')} ms** - bounds marker-arrival skew.")
        L.append("* Consequence: cross-framework startup deltas below "
                 "~1 ms are inside the systematic error band and not "
                 "meaningful.")
        L.append("")

    # agreement -----------------------------------------------------------
    rows = agreement_rows(results)
    if rows:
        n_ok = sum(1 for r in rows if r["agree"])
        L.append("## Run-to-run agreement (round 0 vs round 1)")
        L.append("")
        L.append(f"{n_ok}/{len(rows)} headline medians agree within their "
                 "stated error bars (startup: IQR; frame percentiles: "
                 "cross-pass spread, floored at 5%; idle PSS: max(3%, 1 MiB)).")
        L.append("")
        L.append("| framework | app | metric | round 0 | round 1 | |Δ| | "
                 "error bar | agree |")
        L.append("|---|---|---|---|---|---|---|---|")
        for r in rows:
            L.append(f"| {r['fw']} | {r['app']} | {r['metric']} "
                     f"| {r['round0']} | {r['round1']} | {r['delta']} "
                     f"| {r['error_bar']} | {'✓' if r['agree'] else '✗ MISMATCH'} |")
        L.append("")

    L.append(CLOCK_TABLE)
    L.append(CAVEATS)
    RESULTS_MD.write_text("\n".join(L) + "\n")
    log(f"wrote {RESULTS_MD} and {RESULTS_JSON}")


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
    for fw in fws:
        for app in apps:
            rnd["cells"].setdefault(fw, {})[app] = \
                measure_cell(fw, app, display, cold=cold)
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

    try:
        os.sched_setaffinity(0, HARNESS_CPUS)
    except OSError:
        pass

    results = load_results()
    results["generated"] = time.strftime("%Y-%m-%d %H:%M:%S %z")
    results["config"] = {
        "startup_runs": STARTUP_RUNS, "scroll_passes": SCROLL_PASSES,
        "scroll_seconds": SCROLL_SECONDS, "interact_passes": INTERACT_PASSES,
        "interact_cycles": INTERACT_CYCLES,
        "lumen_tick_sample_ms": LUMEN_TICK_SAMPLE_S * 1000,
    }

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
        write_report(results)

    if cmd not in ("build", "calibrate", "measure", "all", "validate", "report"):
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
