//! Bench list app - Slint variant (winit backend). See repo README for
//! the shared spec (header + 10k-row virtualized ListView + footer).
//!
//! First-presented-frame: the window's rendering notifier at
//! `RenderingState::AfterRendering` (the frame has been submitted).
//! The scroll animation is driven by a repeating 8 ms `slint::Timer`
//! that moves `ListView.viewport-y`; per-frame timestamps still come
//! from the rendering notifier, so timer granularity does not affect
//! the frame-delta measurement.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use bench_slint_common::{bounce, parse_mode, print_deltas_done, print_first_frame,
                         print_startup_and_exit, scroll_seconds, Mode};
use slint::{ComponentHandle, VecModel};

slint::include_modules!();

const ROWS: i32 = 10_000;
const SPEED: f32 = 1000.0; // px/s

fn main() {
    let t0 = Instant::now();
    let mode = parse_mode();
    let duration_s = scroll_seconds();

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
    let reported = Arc::new(AtomicBool::new(false));

    {
        let frames = frames.clone();
        let first_seen = first_seen.clone();
        let first_at = first_at.clone();
        let reported = reported.clone();
        let notifier_result = ui.window().set_rendering_notifier(move |state, _| {
            if matches!(state, slint::RenderingState::AfterRendering) {
                let now = Instant::now();
                if !first_seen.swap(true, Ordering::SeqCst) {
                    *first_at.lock().unwrap() = Some(now);
                    print_first_frame();
                    if mode == Mode::Startup {
                        print_startup_and_exit(t0, now);
                    }
                } else if mode == Mode::ScrollBench && !reported.load(Ordering::SeqCst) {
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
        let reported = reported.clone();
        timer.start(
            slint::TimerMode::Repeated,
            Duration::from_millis(8),
            move || {
                if reported.load(Ordering::SeqCst) {
                    return;
                }
                let Some(start) = *first_at.lock().unwrap() else {
                    return;
                };
                let ui = weak.unwrap();
                let elapsed = start.elapsed().as_secs_f32();
                if elapsed >= duration_s {
                    print_deltas_done(&frames.lock().unwrap());
                    reported.store(true, Ordering::SeqCst);
                    return; // stay alive for post-run memory sample
                }
                let max = (ui.get_content_h() - ui.get_visible_h()).max(0.0);
                let pos = bounce(SPEED * elapsed, max);
                ui.set_vy(-pos);
            },
        );
    }

    ui.run().unwrap();
}
