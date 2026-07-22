//! Shared plumbing for the four iced bench apps (hello / list / forms /
//! textview). See the repo README for the cross-framework spec.

use std::io::Write as _;
use std::time::Instant;

#[derive(Clone, Copy, PartialEq)]
pub enum Mode {
    Default,
    Startup,
    ScrollBench,
    Interact,
}

pub fn parse_mode() -> Mode {
    match std::env::args().nth(1).as_deref() {
        Some("--startup") => Mode::Startup,
        Some("--scroll-bench") => Mode::ScrollBench,
        Some("--interact") => Mode::Interact,
        _ => Mode::Default,
    }
}

/// Scroll-bench duration; overridable so the harness controls pass length.
pub fn scroll_seconds() -> f32 {
    std::env::var("BENCH_SCROLL_SECONDS")
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or(6.0)
}

pub fn interact_cycles() -> u32 {
    std::env::var("BENCH_INTERACT_CYCLES")
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or(4)
}

/// Load the shared textview corpus (one paragraph per line).
pub fn load_corpus() -> String {
    let path = std::env::var("BENCH_CORPUS")
        .unwrap_or_else(|_| "harness/out/corpus.txt".to_string());
    std::fs::read_to_string(&path)
        .unwrap_or_else(|e| panic!("cannot read corpus {path}: {e}"))
}

pub fn bounce(dist: f32, max: f32) -> f32 {
    if max <= 0.0 {
        return 0.0;
    }
    let period = 2.0 * max;
    let m = dist % period;
    if m < max { m } else { period - m }
}

pub fn print_first_frame() {
    println!("first_frame");
    std::io::stdout().flush().ok();
}

pub fn print_startup_and_exit(t0: Instant, now: Instant) -> ! {
    let ms = (now - t0).as_secs_f64() * 1000.0;
    println!("startup_ms: {ms:.3}");
    std::io::stdout().flush().ok();
    std::process::exit(0);
}

/// Dump per-frame deltas + `done`, then KEEP RUNNING (the harness samples
/// post-run memory from the still-live process, then kills it).
pub fn print_deltas_done(frames: &[Instant]) {
    let mut out = String::new();
    for pair in frames.windows(2) {
        let ms = (pair[1] - pair[0]).as_secs_f64() * 1000.0;
        out.push_str(&format!("{ms:.3}\n"));
    }
    out.push_str("done\n");
    print!("{out}");
    std::io::stdout().flush().ok();
}
