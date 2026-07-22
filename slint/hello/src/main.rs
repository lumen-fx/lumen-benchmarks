//! Bench hello app - Slint variant: minimal static window, one "Hello"
//! label + one button. Isolates the startup floor and baseline memory.
//! First-presented-frame: rendering notifier AfterRendering (same as
//! the other Slint apps).

use std::sync::atomic::{AtomicBool, Ordering};
use std::time::Instant;

use bench_slint_common::{parse_mode, print_first_frame, print_startup_and_exit, Mode};
use slint::ComponentHandle;

slint::include_modules!();

fn main() {
    let t0 = Instant::now();
    let mode = parse_mode();
    let ui = HelloWindow::new().unwrap();

    let first_seen = AtomicBool::new(false);
    let notifier_result = ui.window().set_rendering_notifier(move |state, _| {
        if matches!(state, slint::RenderingState::AfterRendering)
            && !first_seen.swap(true, Ordering::SeqCst)
        {
            let now = Instant::now();
            print_first_frame();
            if mode == Mode::Startup {
                print_startup_and_exit(t0, now);
            }
        }
    });
    if let Err(e) = notifier_result {
        eprintln!("warning: rendering notifier unsupported ({e:?}); no frame timing");
    }

    ui.run().unwrap();
}
