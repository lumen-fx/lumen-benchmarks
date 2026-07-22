//! Bench hello app - egui/eframe variant: minimal static window, one
//! "Hello" label + one button. Isolates the startup floor and baseline
//! memory. Same first-frame proxy as the other egui apps (end of the
//! first update pass).

use std::time::Instant;

use bench_egui::{parse_mode, print_first_frame, print_startup_and_exit, Mode};
use eframe::egui;

struct Hello {
    t0: Instant,
    mode: Mode,
    first_frame: Option<Instant>,
}

impl eframe::App for Hello {
    fn ui(&mut self, root: &mut egui::Ui, _frame: &mut eframe::Frame) {
        let now = Instant::now();
        egui::CentralPanel::default().show(root, |ui| {
            ui.vertical_centered(|ui| {
                ui.add_space(ui.available_height() / 2.0 - 30.0);
                ui.label(egui::RichText::new("Hello").strong().size(18.0));
                let _ = ui.button("Press");
            });
        });
        if self.first_frame.is_none() {
            self.first_frame = Some(now);
            print_first_frame();
            if self.mode == Mode::Startup {
                print_startup_and_exit(self.t0, now);
            }
        }
    }
}

fn main() -> eframe::Result {
    let t0 = Instant::now();
    let mode = parse_mode();
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([800.0, 600.0])
            .with_title("Bench"),
        ..Default::default()
    };
    eframe::run_native(
        "Bench",
        options,
        Box::new(move |_cc| {
            Ok(Box::new(Hello {
                t0,
                mode,
                first_frame: None,
            }))
        }),
    )
}
