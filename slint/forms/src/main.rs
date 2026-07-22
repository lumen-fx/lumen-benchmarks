//! Bench forms app - Slint variant: widget-dense settings page
//! (~40 controls in 6 groups; shared spec in the repo README).
//!
//! --interact drives, per cycle: a 40-step focus walk (real Tab key
//! events dispatched through `Window::dispatch_event`, so the walk uses
//! Slint's actual focus chain), then a 20-step toggle-all pass (flip
//! 8 checkboxes + 4 switches from Rust through two-way property
//! bindings, advance both radio groups through their 4 options). One
//! step per 16 ms of wall time; the footer status label changes every
//! step so every step produces visible damage. Frame timestamps:
//! rendering notifier at `AfterRendering`, like the other Slint apps.
//!
//! Equivalence caveats: std-widgets has no RadioButton - the radio
//! groups are exclusive CheckBoxes; toggle steps mutate bound
//! properties rather than synthesizing pointer events (same as the
//! egui/iced/Qt/GTK variants).

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use bench_slint_common::{interact_cycles, parse_mode, print_deltas_done,
                         print_first_frame, print_startup_and_exit, Mode};
use slint::platform::{Key, WindowEvent};
use slint::ComponentHandle;

slint::include_modules!();

const STEP_S: f32 = 0.016;
const SETTLE_S: f32 = 0.5;
const STEPS_PER_CYCLE: i64 = 60; // 40 focus + 8 cb + 4 sw + 2x4 radio advances

fn apply_step(ui: &FormsWindow, step: i64) {
    ui.set_status(format!("step {step}").into());
    let in_cycle = step % STEPS_PER_CYCLE;
    if in_cycle < 40 {
        let tab: slint::SharedString = Key::Tab.into();
        ui.window().dispatch_event(WindowEvent::KeyPressed { text: tab.clone() });
        ui.window().dispatch_event(WindowEvent::KeyReleased { text: tab });
        return;
    }
    let t = in_cycle - 40;
    match t {
        0 => ui.set_c0(!ui.get_c0()),
        1 => ui.set_c1(!ui.get_c1()),
        2 => ui.set_c2(!ui.get_c2()),
        3 => ui.set_c3(!ui.get_c3()),
        4 => ui.set_c4(!ui.get_c4()),
        5 => ui.set_c5(!ui.get_c5()),
        6 => ui.set_c6(!ui.get_c6()),
        7 => ui.set_c7(!ui.get_c7()),
        8 => ui.set_t0(!ui.get_t0()),
        9 => ui.set_t1(!ui.get_t1()),
        10 => ui.set_t2(!ui.get_t2()),
        11 => ui.set_t3(!ui.get_t3()),
        12..=15 => ui.set_ra((ui.get_ra() + 1) % 4),
        _ => ui.set_rb((ui.get_rb() + 1) % 4),
    }
}

fn main() {
    let t0 = Instant::now();
    let mode = parse_mode();
    let cycles = interact_cycles() as i64;

    let ui = FormsWindow::new().unwrap();

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
                } else if mode == Mode::Interact && !reported.load(Ordering::SeqCst) {
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
    if mode == Mode::Interact {
        let weak = ui.as_weak();
        let frames = frames.clone();
        let first_at = first_at.clone();
        let reported = reported.clone();
        let total_steps = STEPS_PER_CYCLE * cycles;
        let mut step_done: i64 = 0;
        let mut started: Option<Instant> = None;
        timer.start(
            slint::TimerMode::Repeated,
            Duration::from_millis(4),
            move || {
                if reported.load(Ordering::SeqCst) {
                    return;
                }
                let Some(first) = *first_at.lock().unwrap() else {
                    return;
                };
                let now = Instant::now();
                if (now - first).as_secs_f32() < SETTLE_S {
                    return;
                }
                let started = *started.get_or_insert(now);
                let ui = weak.unwrap();
                let due = ((now - started).as_secs_f32() / STEP_S) as i64;
                let due = due.min(total_steps);
                while step_done < due {
                    apply_step(&ui, step_done);
                    step_done += 1;
                }
                if step_done >= total_steps {
                    print_deltas_done(&frames.lock().unwrap());
                    reported.store(true, Ordering::SeqCst); // stay alive for memory sample
                }
            },
        );
    }

    ui.run().unwrap();
}
