//! Bench list app - egui/eframe variant. See repo README for the shared
//! spec (header + 10k-row virtualized list + footer).
//!
//! First-presented-frame proxy: end of the first `App::update` pass
//! (eframe paints immediately after update returns; there is no
//! present-complete callback). Frame timestamps for --scroll-bench are
//! taken at the top of every update pass.

use std::time::Instant;

use bench_egui::{bounce, parse_mode, print_deltas_done, print_first_frame,
                 print_startup_and_exit, scroll_seconds, Mode};
use eframe::egui;

const ROWS: usize = 10_000;
const ROW_H: f32 = 36.0;
const SPEED: f32 = 1000.0; // px/s

struct Bench {
    t0: Instant,
    mode: Mode,
    duration_s: f32,
    count: u64,
    text: String,
    slider: f32,
    first_frame: Option<Instant>,
    frames: Vec<Instant>,
    reported: bool,
}

impl eframe::App for Bench {
    fn ui(&mut self, root: &mut egui::Ui, _frame: &mut eframe::Frame) {
        let now = Instant::now();

        egui::Panel::top("header")
            .exact_size(48.0)
            .show(root, |ui| {
                ui.horizontal_centered(|ui| {
                    ui.label(egui::RichText::new("Bench").strong().size(18.0));
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        if ui.button(format!("Count: {}", self.count)).clicked() {
                            self.count += 1;
                        }
                    });
                });
            });

        egui::Panel::bottom("footer")
            .exact_size(56.0)
            .show(root, |ui| {
                ui.horizontal_centered(|ui| {
                    ui.add(
                        egui::TextEdit::singleline(&mut self.text)
                            .hint_text("Type here...")
                            .desired_width(240.0),
                    );
                    ui.add(
                        egui::Slider::new(&mut self.slider, 0.0..=100.0)
                            .show_value(false),
                    );
                    ui.label(format!("{}", self.slider.round() as i64));
                });
            });

        egui::CentralPanel::default().show(root, |ui| {
            ui.spacing_mut().item_spacing.y = 0.0;
            let mut area = egui::ScrollArea::vertical().auto_shrink([false, false]);
            if self.mode == Mode::ScrollBench && !self.reported {
                if let Some(first) = self.first_frame {
                    let elapsed = (now - first).as_secs_f32();
                    let max = ROWS as f32 * ROW_H - ui.available_height();
                    area = area.vertical_scroll_offset(bounce(SPEED * elapsed, max));
                }
            }
            area.show_rows(ui, ROW_H, ROWS, |ui, range| {
                for i in range {
                    ui.horizontal(|ui| {
                        ui.set_height(ROW_H);
                        ui.add_space(8.0);
                        ui.label(egui::RichText::new(format!("Item {i}")).strong());
                        ui.add_space(12.0);
                        ui.label(
                            egui::RichText::new(format!("subtitle {i}"))
                                .color(egui::Color32::from_rgb(0x77, 0x77, 0x77)),
                        );
                    });
                }
            });
        });

        if self.first_frame.is_none() {
            self.first_frame = Some(now);
            print_first_frame();
            if self.mode == Mode::Startup {
                print_startup_and_exit(self.t0, now);
            }
        } else if self.mode == Mode::ScrollBench && !self.reported {
            self.frames.push(now);
            let elapsed = (now - self.first_frame.unwrap()).as_secs_f32();
            if elapsed >= self.duration_s {
                print_deltas_done(&self.frames);
                self.reported = true; // stay alive for post-run memory sample
            }
        }

        if self.mode == Mode::ScrollBench && !self.reported {
            root.ctx().request_repaint();
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
            Ok(Box::new(Bench {
                t0,
                mode,
                duration_s: scroll_seconds(),
                count: 0,
                text: String::new(),
                slider: 50.0,
                first_frame: None,
                frames: Vec::with_capacity(4096),
                reported: false,
            }))
        }),
    )
}
