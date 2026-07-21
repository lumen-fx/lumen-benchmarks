#!/usr/bin/env python3
"""Cross-framework GUI benchmark harness.

Builds six implementations of the same 800x600 "Bench" app (Lumen, Slint,
egui, iced, Qt6 Widgets, GTK4), then measures:

  * stripped binary size (Lumen: runtime binary + app payload separately)
  * startup: process spawn -> first presented frame, 10 runs, median
      - external_ms: measured by this harness (spawn -> marker line)
      - self_ms:     reported by the app itself (main entry -> first frame)
  * scroll: 10 s of programmatic scrolling at 1000 px/s over a 10k-row
    list; per-frame deltas -> p50/p95/p99
  * idle RSS: VmRSS 2 s after first frame

All measurement runs happen under a nested headless compositor
(weston --backend=headless, fallback Xvfb) so nothing ever appears on the
developer's desktop. Lumen runs `lumenc run --headless` (its own
offscreen pipeline; no compositor needed) - see FAIRNESS notes below.

Usage:
    harness/bench.py build          # build + size everything
    harness/bench.py measure        # run measurements (needs weston/Xvfb)
    harness/bench.py all            # build + measure + report
    harness/bench.py report         # rewrite results.md from results.json
"""

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
RESULTS_JSON = ROOT / "results.json"
RESULTS_MD = ROOT / "results.md"

# Deliberately NOT plain CARGO_TARGET_DIR: the developer shell exports a
# global CARGO_TARGET_DIR pointing at the Lumen repo's shared target dir,
# and building into that would poison its fingerprints.
CARGO_TARGET = os.environ.get("BENCH_CARGO_TARGET_DIR",
                              "/Storage/cargo-target-benchcomp")
LUMEN_REPO = Path(os.environ.get("LUMEN_REPO", "/home/artur/Lumen"))
LUMEN_APP = ROOT / "lumen" / "app"
# Must match lumen/app/lumen.toml [mcp].port. Deliberately not 7878 -
# other lumenc instances (dev tooling) commonly hold the default port.
LUMEN_MCP_PORT = 7941

STARTUP_RUNS = 10
SCROLL_SECONDS = 10.0
SCROLL_PX_PER_S = 1000.0
# Lumen scroll is driven externally over MCP wheel events (no in-app
# scroll setter): one event per interval, delta = speed * interval.
# ~60 Hz so the demand-driven headless loop renders at the same cadence
# the other frameworks present at.
LUMEN_SCROLL_INTERVAL_S = 1.0 / 60.0

WESTON_SOCKET = "wayland-bench"
XVFB_DISPLAY = ":97"


# --------------------------------------------------------------------------
# Framework table
# --------------------------------------------------------------------------

def cargo_env():
    env = os.environ.copy()
    env["CARGO_TARGET_DIR"] = CARGO_TARGET
    return env


FRAMEWORKS = {
    "lumen": {
        "kind": "lumen",
        "bin": Path(CARGO_TARGET) / "release" / "lumenc",
    },
    "slint": {
        "kind": "cargo",
        "dir": ROOT / "slint",
        "bin": Path(CARGO_TARGET) / "release" / "bench-slint",
    },
    "egui": {
        "kind": "cargo",
        "dir": ROOT / "egui",
        "bin": Path(CARGO_TARGET) / "release" / "bench-egui",
    },
    "iced": {
        "kind": "cargo",
        "dir": ROOT / "iced",
        "bin": Path(CARGO_TARGET) / "release" / "bench-iced",
    },
    "qt-widgets": {
        "kind": "cmake",
        "dir": ROOT / "qt-widgets",
        "bin": ROOT / "qt-widgets" / "build" / "bench_qt",
    },
    "gtk4": {
        "kind": "cmake",
        "dir": ROOT / "gtk4",
        "bin": ROOT / "gtk4" / "build" / "bench_gtk4",
    },
}


def log(msg):
    print(f"[bench] {msg}", flush=True)


def run_checked(cmd, **kw):
    log("$ " + " ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True, **kw)


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------

def build_all():
    BIN_OUT.mkdir(parents=True, exist_ok=True)
    sizes = {}

    # Lumen: build the lumenc runner from the framework repo.
    run_checked(
        ["cargo", "build", "--release", "-p", "lumenc",
         "--manifest-path", str(LUMEN_REPO / "Cargo.toml")],
        env=cargo_env(),
    )
    # Validate the .lmn app.
    run_checked([str(FRAMEWORKS["lumen"]["bin"]), "check", str(LUMEN_APP)])

    for name in ("slint", "egui", "iced"):
        run_checked(["cargo", "build", "--release"],
                    cwd=FRAMEWORKS[name]["dir"], env=cargo_env())

    for name in ("qt-widgets", "gtk4"):
        d = FRAMEWORKS[name]["dir"]
        run_checked(["cmake", "-S", str(d), "-B", str(d / "build"),
                     "-DCMAKE_BUILD_TYPE=Release"])
        run_checked(["cmake", "--build", str(d / "build"), "-j",
                     str(os.cpu_count() or 4)])

    # Stripped-copy sizes (never strip cargo outputs in place).
    for name, fw in FRAMEWORKS.items():
        src = fw["bin"]
        dst = BIN_OUT / src.name
        shutil.copy2(src, dst)
        subprocess.run(["strip", str(dst)], check=True)
        sizes[name] = {"stripped_bytes": dst.stat().st_size}

    # Record toolkit versions for the report.
    versions = {}
    try:
        versions["lumen"] = "git " + subprocess.run(
            ["git", "-C", str(LUMEN_REPO), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True).stdout.strip()
    except OSError:
        pass
    for name, pkg in (("slint", "slint"), ("egui", "eframe"), ("iced", "iced")):
        lock = FRAMEWORKS[name]["dir"] / "Cargo.lock"
        if lock.exists():
            block = [l for l in lock.read_text().splitlines()]
            for i, l in enumerate(block):
                if l == f'name = "{pkg}"' and i + 1 < len(block):
                    versions[name] = pkg + " " + \
                        block[i + 1].split('"')[1]
                    break
    for name, pkg in (("qt-widgets", "Qt6Widgets"), ("gtk4", "gtk4")):
        try:
            v = subprocess.run(["pkg-config", "--modversion", pkg],
                               capture_output=True, text=True).stdout.strip()
            if v:
                versions[name] = f"{pkg} {v}"
        except OSError:
            pass

    # Lumen app payload: the interpreted sources shipped alongside lumenc.
    payload = sum(f.stat().st_size for f in LUMEN_APP.iterdir() if f.is_file())
    sizes["lumen"]["app_payload_bytes"] = payload
    sizes["lumen"]["note"] = (
        "lumenc is a generic runtime/dev-runner binary; the app itself is "
        f"{payload} bytes of .lmn/.css/.rhai/.toml text"
    )
    return sizes, versions


# --------------------------------------------------------------------------
# Headless display
# --------------------------------------------------------------------------

class Display:
    """Nested headless compositor. Prefers weston, falls back to Xvfb.

    Xvfb is additionally started (when present) even under weston:
    `lumenc run --headless` opens no window but currently segfaults
    during GPU discovery when no display connection exists at all, so
    the Lumen process gets DISPLAY pointed at Xvfb.
    """

    def __init__(self):
        self.proc = None
        self.xvfb = None
        self.backend = None

    def _start_xvfb(self):
        if shutil.which("Xvfb"):
            self.xvfb = subprocess.Popen(
                ["Xvfb", XVFB_DISPLAY, "-screen", "0", "1280x1024x24"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True)
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
                start_new_session=True)
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
        if fw_name == "lumen":
            # lumenc --headless renders offscreen (no window), but its
            # GPU discovery needs *some* display connection or it
            # segfaults - give it the Xvfb display.
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

    def next_line(self, timeout):
        try:
            return self.q.get(timeout=timeout)
        except queue.Empty:
            return (time.monotonic(), None)

    def wait_for(self, predicate, timeout):
        """Return (ts, line) of the first line matching predicate."""
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


def spawn(fw_name, mode_args, display):
    fw = FRAMEWORKS[fw_name]
    if fw["kind"] == "lumen":
        cmd = [str(fw["bin"]), "run", str(LUMEN_APP), "--headless",
               "--size", "800x600"]
    else:
        cmd = [str(fw["bin"])] + mode_args
    env = display.app_env(fw_name)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env=env, start_new_session=True)
    return proc


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


def is_first_frame_marker(fw_name):
    return lambda line: line == "first_frame"


def marker_reader(fw_name, proc):
    return LineReader(proc.stdout)


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


# --------------------------------------------------------------------------
# Measurements
# --------------------------------------------------------------------------

def lumen_wait_first_frame(timeout=60.0):
    """Poll MCP `lumen.tick` until the frame counter reaches 1.

    Lumen has no scriptable per-frame hook, so "first presented frame"
    for Lumen means: first headless tick+render completed, as observed
    through the MCP frame counter (polled every 2 ms)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = mcp_call(LUMEN_MCP_PORT, "lumen.tick", {}, timeout=0.5)
            frame = resp.get("result", {}).get("frame", 0)
            if frame and frame >= 1:
                return time.monotonic()
        except (OSError, AttributeError, ValueError):
            pass
        time.sleep(0.002)
    return None


def measure_startup(fw_name, display):
    external, internal = [], []
    for i in range(STARTUP_RUNS):
        if fw_name == "lumen":
            wait_port_free(LUMEN_MCP_PORT)
        t_spawn = time.monotonic()
        proc = spawn(fw_name, ["--startup"], display)
        if fw_name == "lumen":
            ts = lumen_wait_first_frame()
            if ts is None:
                kill(proc)
                raise RuntimeError(f"lumen: no first frame via MCP (run {i})")
            external.append((ts - t_spawn) * 1000.0)
            kill(proc)
        else:
            reader = marker_reader(fw_name, proc)
            ts, line = reader.wait_for(is_first_frame_marker(fw_name),
                                       timeout=60)
            if ts is None:
                kill(proc)
                raise RuntimeError(f"{fw_name}: no first-frame marker (run {i})")
            external.append((ts - t_spawn) * 1000.0)
            ts2, line2 = reader.wait_for(lambda l: l.startswith("startup_ms:"),
                                         timeout=10)
            if line2:
                internal.append(float(line2.split(":")[1]))
            proc.wait(timeout=10)
            kill(proc)
        time.sleep(0.3)
    return {
        "external_ms_runs": external,
        "external_ms_median": statistics.median(external),
        "self_ms_runs": internal,
        "self_ms_median": statistics.median(internal) if internal else None,
    }


def mcp_call(port, method, params, timeout=2.0):
    with socket.create_connection(("127.0.0.1", port), timeout=timeout) as s:
        req = json.dumps({"jsonrpc": "2.0", "method": method, "id": 1,
                          "params": params}) + "\n"
        s.sendall(req.encode())
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
        return json.loads(buf) if buf else None


def measure_scroll(fw_name, display):
    if fw_name == "lumen":
        return measure_scroll_lumen(display)
    proc = spawn(fw_name, ["--scroll-bench"], display)
    reader = marker_reader(fw_name, proc)
    ts, _ = reader.wait_for(is_first_frame_marker(fw_name), timeout=60)
    if ts is None:
        kill(proc)
        raise RuntimeError(f"{fw_name}: scroll-bench never produced a frame")
    deltas = []
    deadline = time.monotonic() + SCROLL_SECONDS + 30
    while time.monotonic() < deadline:
        try:
            _, line = reader.q.get(timeout=1.0)
        except queue.Empty:
            continue  # app buffers output until the 10 s run ends
        if line is None or line == "done":
            break
        try:
            deltas.append(float(line))
        except ValueError:
            pass
    kill(proc)
    return frame_stats(deltas)


def measure_scroll_lumen(display):
    """Drive Lumen's scroller externally via MCP wheel events at ~60 Hz.

    Lumen's Rhai API has no scroll-offset setter and no per-frame
    callback, so the harness (a) injects `lumen.simulate` wheel events
    every LUMEN_SCROLL_INTERVAL_S with delta = speed * interval
    (sensitivity 1.0 / inertia 0 in the app makes one wheel px == one
    scroll px), and (b) after each event polls `lumen.tick` for the
    frame counter and the last tick's duration.

    Reported stats are wall-clock frame intervals reconstructed from the
    sampled frame counter: for consecutive samples where the counter
    advanced by df over dt, dt/df is recorded df times. When the app
    keeps pace this tracks the ~60 Hz drive cadence; when it falls
    behind, the merged intervals surface as larger deltas. Quantized by
    the sampling cadence - see the caveats section.
    """
    wait_port_free(LUMEN_MCP_PORT)
    proc = spawn("lumen", [], display)
    ts = lumen_wait_first_frame()
    if ts is None:
        kill(proc)
        raise RuntimeError("lumen: app never ticked")
    time.sleep(1.0)  # let startup work settle

    dy = -(SCROLL_PX_PER_S * LUMEN_SCROLL_INTERVAL_S)  # negative = down
    samples = []  # (t, frame, last_tick_micros)
    errors = 0
    t_start = time.monotonic()
    next_send = t_start
    while True:
        now = time.monotonic()
        if now - t_start >= SCROLL_SECONDS:
            break
        if now >= next_send:
            try:
                mcp_call(LUMEN_MCP_PORT, "lumen.simulate",
                         {"kind": "scroll", "x": 400.0, "y": 300.0,
                          "dx": 0.0, "dy": dy})
                resp = mcp_call(LUMEN_MCP_PORT, "lumen.tick", {})
                r = resp.get("result", {})
                samples.append((time.monotonic(), r.get("frame"),
                                r.get("last_tick_micros")))
            except (OSError, AttributeError, ValueError):
                errors += 1
            next_send += LUMEN_SCROLL_INTERVAL_S
        time.sleep(0.001)
    t_stop = time.monotonic()
    kill(proc)
    if errors:
        log(f"lumen: {errors} MCP calls failed during scroll")

    good = [s for s in samples if s[1] is not None]
    if len(good) < 2:
        return {"frames": 0}
    frames_rendered = good[-1][1] - good[0][1]
    # Reconstruct per-frame wall intervals from counter advances.
    intervals_ms = []
    for (t1, f1, _), (t2, f2, _) in zip(good, good[1:]):
        df = f2 - f1
        if df > 0:
            intervals_ms.extend([(t2 - t1) * 1000.0 / df] * df)
    stats = frame_stats(intervals_ms)
    stats["frames"] = frames_rendered
    stats["metric"] = ("wall frame intervals reconstructed from the MCP "
                       "frame counter sampled at the ~60 Hz drive cadence")
    return stats


def frame_stats(deltas):
    if not deltas:
        return {"frames": 0}
    ordered = sorted(deltas)

    def pct(p):
        idx = min(len(ordered) - 1, max(0, round(p / 100.0 * len(ordered)) - 1))
        return ordered[idx]

    return {
        "frames": len(deltas),
        "p50_ms": pct(50),
        "p95_ms": pct(95),
        "p99_ms": pct(99),
        "max_ms": ordered[-1],
        "mean_ms": statistics.fmean(deltas),
    }


def measure_rss(fw_name, display):
    if fw_name == "lumen":
        wait_port_free(LUMEN_MCP_PORT)
    proc = spawn(fw_name, [], display)
    if fw_name == "lumen":
        lumen_wait_first_frame()
    else:
        reader = marker_reader(fw_name, proc)
        reader.wait_for(is_first_frame_marker(fw_name), timeout=60)
    time.sleep(2.0)
    rss_kb = None
    try:
        with open(f"/proc/{proc.pid}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    rss_kb = int(line.split()[1])
                    break
    except FileNotFoundError:
        pass
    kill(proc)
    return {"rss_kb": rss_kb}


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

CAVEATS = """\
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
"""


def write_report(results):
    RESULTS_JSON.write_text(json.dumps(results, indent=2) + "\n")

    lines = [
        "# Cross-framework benchmark results",
        "",
        f"Generated: {results.get('generated', '?')}  ",
        f"Host: {results.get('host', '?')}  ",
        f"Display backend: {results.get('display_backend', 'not run')}",
        "",
        "| framework | version | binary (stripped) | "
        "startup median (external) | startup median (self) | scroll p50 | "
        "scroll p95 | scroll p99 | idle RSS |",
        "|---|---|---|---|---|---|---|---|---|",
    ]

    def ms(v, spec=".1f"):
        return f"{format(v, spec)} ms" if isinstance(v, (int, float)) else "-"

    for name in FRAMEWORKS:
        r = results.get("frameworks", {}).get(name, {})
        size = r.get("size", {})
        sz = size.get("stripped_bytes")
        sz_s = f"{sz / 1024:.0f} KiB" if sz else "-"
        if name == "lumen" and size.get("app_payload_bytes"):
            sz_s += f" (+{size['app_payload_bytes'] / 1024:.1f} KiB app)"
        st = r.get("startup", {})
        sc = r.get("scroll", {})
        rss = r.get("rss", {}).get("rss_kb")
        lines.append(
            f"| {name} | {r.get('version', '-')} | {sz_s} "
            f"| {ms(st.get('external_ms_median'))} "
            f"| {ms(st.get('self_ms_median'))} "
            f"| {ms(sc.get('p50_ms'), '.2f')} "
            f"| {ms(sc.get('p95_ms'), '.2f')} "
            f"| {ms(sc.get('p99_ms'), '.2f')} "
            f"| {f'{rss / 1024:.1f} MiB' if rss else '-'} |")
    lines += ["", CAVEATS]
    RESULTS_MD.write_text("\n".join(lines) + "\n")
    log(f"wrote {RESULTS_MD} and {RESULTS_JSON}")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def load_results():
    if RESULTS_JSON.exists():
        return json.loads(RESULTS_JSON.read_text())
    return {"frameworks": {}}


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    only = sys.argv[2:] or list(FRAMEWORKS)
    results = load_results()
    results.setdefault("frameworks", {})
    results["host"] = os.uname().nodename + " " + os.uname().release
    results["generated"] = time.strftime("%Y-%m-%d %H:%M:%S %z")

    if cmd in ("build", "all"):
        sizes, versions = build_all()
        for name, s in sizes.items():
            results["frameworks"].setdefault(name, {})["size"] = s
        for name, v in versions.items():
            results["frameworks"].setdefault(name, {})["version"] = v
        write_report(results)

    if cmd in ("measure", "all"):
        display = Display()
        display.start()
        results["display_backend"] = display.backend
        try:
            for name in only:
                log(f"=== {name}: startup x{STARTUP_RUNS} ===")
                results["frameworks"].setdefault(name, {})["startup"] = \
                    measure_startup(name, display)
                log(f"=== {name}: scroll bench ===")
                results["frameworks"][name]["scroll"] = \
                    measure_scroll(name, display)
                log(f"=== {name}: idle RSS ===")
                results["frameworks"][name]["rss"] = measure_rss(name, display)
                write_report(results)
        finally:
            display.stop()

    if cmd == "report":
        write_report(results)

    if cmd not in ("build", "measure", "all", "report"):
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
