//! Bench app - Slint variant (winit backend). See repo README for the
//! shared spec.
//!
//! First-presented-frame: the window's rendering notifier at
//! `RenderingState::AfterRendering` (the frame has been submitted).
//! The scroll animation is driven by a repeating 8 ms `slint::Timer`
//! that moves `ListView.viewport-y`; per-frame timestamps still come
//! from the rendering notifier, so timer granularity does not affect
//! the frame-delta measurement.

use std::io::Write as _;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use slint::{ComponentHandle, VecModel};

slint::include_modules!();

const ROWS: i32 = 10_000;
const SPEED: f32 = 1000.0; // px/s
const DURATION_S: f32 = 10.0;

#[derive(Clone, Copy, PartialEq)]
enum Mode {
    Default,
    Startup,
    ScrollBench,
}

fn bounce(dist: f32, max: f32) -> f32 {
    if max <= 0.0 {
        return 0.0;
    }
    let period = 2.0 * max;
    let m = dist % period;
    if m < max { m } else { period - m }
}

fn main() {
    let t0 = Instant::now();
    let mode = match std::env::args().nth(1).as_deref() {
        Some("--startup") => Mode::Startup,
        Some("--scroll-bench") => Mode::ScrollBench,
        _ => Mode::Default,
    };

    let ui = BenchWindow::new().unwrap();

    let rows: Vec<RowData> = (0..ROWS).map(|i| RowData { i }).collect();
    let model = std::rc::Rc::new(VecModel::from(rows));
    ui.set_model(model.into());

    {
        let weak = ui.as_weak();
        ui.on_inc(move || {
            let ui = weak.unwrap();
            ui.set_count(ui.get_count() + 1);
        });
    }

    let frames: Arc<Mutex<Vec<Instant>>> = Arc::new(Mutex::new(Vec::with_capacity(4096)));
    let first_seen = Arc::new(AtomicBool::new(false));
    let first_at: Arc<Mutex<Option<Instant>>> = Arc::new(Mutex::new(None));

    {
        let frames = frames.clone();
        let first_seen = first_seen.clone();
        let first_at = first_at.clone();
        let notifier_result = ui.window().set_rendering_notifier(move |state, _| {
            if matches!(state, slint::RenderingState::AfterRendering) {
                let now = Instant::now();
                if !first_seen.swap(true, Ordering::SeqCst) {
                    *first_at.lock().unwrap() = Some(now);
                    println!("first_frame");
                    std::io::stdout().flush().ok();
                    if mode == Mode::Startup {
                        let ms = now.duration_since(t0).as_secs_f64() * 1000.0;
                        println!("startup_ms: {ms:.3}");
                        std::io::stdout().flush().ok();
                        std::process::exit(0);
                    }
                } else if mode == Mode::ScrollBench {
                    frames.lock().unwrap().push(now);
                }
            }
        });
        if let Err(e) = notifier_result {
            eprintln!("warning: rendering notifier unsupported ({e:?}); no frame timing");
        }
    }

    // Timer must stay alive for the duration of the event loop.
    let timer = slint::Timer::default();
    if mode == Mode::ScrollBench {
        let weak = ui.as_weak();
        let frames = frames.clone();
        let first_at = first_at.clone();
        timer.start(
            slint::TimerMode::Repeated,
            Duration::from_millis(8),
            move || {
                let Some(start) = *first_at.lock().unwrap() else {
                    return;
                };
                let ui = weak.unwrap();
                let elapsed = start.elapsed().as_secs_f32();
                if elapsed >= DURATION_S {
                    let frames = frames.lock().unwrap();
                    let mut out = String::new();
                    for pair in frames.windows(2) {
                        let ms = (pair[1] - pair[0]).as_secs_f64() * 1000.0;
                        out.push_str(&format!("{ms:.3}\n"));
                    }
                    out.push_str("done\n");
                    print!("{out}");
                    std::io::stdout().flush().ok();
                    std::process::exit(0);
                }
                let max = (ui.get_content_h() - ui.get_visible_h()).max(0.0);
                let pos = bounce(SPEED * elapsed, max);
                ui.set_vy(-pos);
            },
        );
    }

    ui.run().unwrap();
}
