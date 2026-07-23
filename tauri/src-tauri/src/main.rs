// Cross-framework GUI benchmark - Tauri (system webkit2gtk) variant.
//
// One binary implements all four bench apps (hello / list / forms /
// textview). The app VARIANT is chosen from the executable's basename
// (the harness invokes hardlinks bench-tauri-<app> that all point at the
// single built binary), and the MODE from the first CLI argument. The
// frontend (plain HTML/JS/CSS in ../dist, no bundler) fetches both via
// the `bench_config` command. See the repo README for the shared spec
// and results.md for the fairness caveats.
//
// CLI contract (identical semantics to the native variants):
//   --startup       print `first_frame`, then `startup_ms: <float>`
//                   (process start -> first webview paint), then exit
//   --scroll-bench  (list/textview) the webview animates a windowed
//                   (virtualized) scroll at 1000 px/s, records one
//                   timestamp per rAF, and after BENCH_SCROLL_SECONDS
//                   posts the deltas back -> printed one per line + `done`
//   --interact      (forms) 4 cycles x (40-step focus walk + 20-step
//                   toggle-all), one step / 16 ms; per-frame deltas + `done`
//   (no arg)        run normally (idle-RSS sampling)
//
// First-paint proxy: the webview's first `requestAnimationFrame` after
// the initial content is in the DOM invokes `first_frame`; Rust stamps it
// against a process-start Instant (CLOCK_MONOTONIC family). Frame
// timestamps for the passes are `performance.now()` deltas captured in
// the rAF loop inside the webview and posted back in one batch.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::Write;
use std::time::Instant;

use serde::Serialize;
use tauri::Manager;

/// Process-start instant (first line of main) and resolved variant/mode.
struct BenchState {
    t0: Instant,
    app: String,
    mode: String,
    scroll_seconds: f64,
    interact_cycles: u32,
    corpus: String,
}

#[derive(Serialize)]
struct BenchConfig {
    app: String,
    mode: String,
    scroll_seconds: f64,
    interact_cycles: u32,
    corpus: String,
}

fn variant_from_exe() -> String {
    let name = std::env::current_exe()
        .ok()
        .and_then(|p| p.file_name().map(|s| s.to_string_lossy().into_owned()))
        .unwrap_or_default();
    for v in ["hello", "list", "forms", "textview"] {
        if name.contains(v) {
            return v.to_string();
        }
    }
    "hello".to_string()
}

fn mode_from_args() -> String {
    match std::env::args().nth(1).as_deref() {
        Some("--startup") => "startup",
        Some("--scroll-bench") => "scroll",
        Some("--interact") => "interact",
        _ => "normal",
    }
    .to_string()
}

fn env_f64(name: &str, dflt: f64) -> f64 {
    std::env::var(name).ok().and_then(|s| s.parse().ok()).unwrap_or(dflt)
}

fn env_u32(name: &str, dflt: u32) -> u32 {
    std::env::var(name).ok().and_then(|s| s.parse().ok()).unwrap_or(dflt)
}

fn load_corpus(app: &str) -> String {
    if app != "textview" {
        return String::new();
    }
    let path = std::env::var("BENCH_CORPUS")
        .unwrap_or_else(|_| "harness/out/corpus.txt".to_string());
    std::fs::read_to_string(&path).unwrap_or_default()
}

#[tauri::command]
fn bench_config(state: tauri::State<BenchState>) -> BenchConfig {
    BenchConfig {
        app: state.app.clone(),
        mode: state.mode.clone(),
        scroll_seconds: state.scroll_seconds,
        interact_cycles: state.interact_cycles,
        corpus: state.corpus.clone(),
    }
}

/// The webview has painted its first frame. Emit the marker; in --startup
/// mode also emit the self time (process start -> first paint) and exit.
#[tauri::command]
fn first_frame(state: tauri::State<BenchState>) {
    let stdout = std::io::stdout();
    let mut h = stdout.lock();
    if state.mode == "startup" {
        let ms = state.t0.elapsed().as_secs_f64() * 1000.0;
        let _ = writeln!(h, "first_frame");
        let _ = writeln!(h, "startup_ms: {ms:.3}");
        let _ = h.flush();
        std::process::exit(0);
    }
    let _ = writeln!(h, "first_frame");
    let _ = h.flush();
}

/// One frame delta (ms) per line, then `done`. The process stays alive so
/// the harness can sample post-run memory before killing it.
#[tauri::command]
fn report_frames(deltas: Vec<f64>) {
    let stdout = std::io::stdout();
    let mut h = stdout.lock();
    let mut buf = String::new();
    for d in &deltas {
        buf.push_str(&format!("{d:.3}\n"));
    }
    buf.push_str("done\n");
    let _ = h.write_all(buf.as_bytes());
    let _ = h.flush();
}

fn main() {
    let t0 = Instant::now();
    // webkit2gtk under a nested headless compositor: the DMABUF renderer
    // path needs GPU buffer sharing the headless weston can't always
    // provide; force the in-process GL/SHM path so first paint is reliable.
    if std::env::var_os("WEBKIT_DISABLE_DMABUF_RENDERER").is_none() {
        std::env::set_var("WEBKIT_DISABLE_DMABUF_RENDERER", "1");
    }

    let app = variant_from_exe();
    let mode = mode_from_args();
    let corpus = load_corpus(&app);
    let state = BenchState {
        t0,
        app,
        mode,
        scroll_seconds: env_f64("BENCH_SCROLL_SECONDS", 6.0),
        interact_cycles: env_u32("BENCH_INTERACT_CYCLES", 4),
        corpus,
    };

    tauri::Builder::default()
        .manage(state)
        .invoke_handler(tauri::generate_handler![
            bench_config,
            first_frame,
            report_frames
        ])
        .setup(|app| {
            // Ensure the window is shown (config marks it visible, but be
            // explicit for the headless present path).
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.show();
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
