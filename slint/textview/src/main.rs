//! Bench textview app - Slint variant: the shared ~1 MiB corpus
//! (5,000 paragraphs) as one word-wrapped `Text` inside a `Flickable`.
//!
//! First-presented-frame: rendering notifier at `AfterRendering`, like
//! the other Slint apps. The scroll animation is driven by a repeating
//! 8 ms `slint::Timer` that moves the Flickable's `viewport-y`;
//! per-frame timestamps still come from the rendering notifier.
//!
//! Equivalence caveat: Slint lays out the whole document as a single
//! Text item (no virtualization) - startup includes shaping/wrapping
//! the full corpus to compute `preferred-height`.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use bench_slint_common::{bounce, load_corpus, parse_mode, print_deltas_done,
                         print_first_frame, print_startup_and_exit, scroll_seconds, Mode};
use slint::ComponentHandle;

slint::include_modules!();

const SPEED: f32 = 1000.0; // px/s

fn main() {
    let t0 = Instant::now();
    let mode = parse_mode();
    let duration_s = scroll_seconds();

    let ui = TextViewWindow::new().unwrap();
    ui.set_corpus(load_corpus().into());

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
