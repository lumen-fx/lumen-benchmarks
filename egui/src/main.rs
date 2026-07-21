//! Bench app - egui/eframe variant. See repo README for the shared spec.
//!
//! First-presented-frame proxy: end of the first `App::update` pass
//! (eframe paints immediately after update returns; there is no
//! present-complete callback). Frame timestamps for --scroll-bench are
//! taken at the top of every update pass.

use std::io::Write as _;
use std::time::Instant;

use eframe::egui;

const ROWS: usize = 10_000;
const ROW_H: f32 = 36.0;
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

struct Bench {
    t0: Instant,
    mode: Mode,
    count: u64,
    text: String,
    slider: f32,
    first_frame: Option<Instant>,
    frames: Vec<Instant>,
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
                if self.mode == Mode::ScrollBench {
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
                            ui.label(
                                egui::RichText::new(format!("Item {i}")).strong(),
                            );
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
            println!("first_frame");
            std::io::stdout().flush().ok();
            if self.mode == Mode::Startup {
                let ms = (now - self.t0).as_secs_f64() * 1000.0;
                println!("startup_ms: {ms:.3}");
                std::io::stdout().flush().ok();
                std::process::exit(0);
            }
        } else if self.mode == Mode::ScrollBench {
            self.frames.push(now);
            let elapsed = (now - self.first_frame.unwrap()).as_secs_f32();
            if elapsed >= DURATION_S {
                let mut out = String::new();
                for pair in self.frames.windows(2) {
                    let ms = (pair[1] - pair[0]).as_secs_f64() * 1000.0;
                    out.push_str(&format!("{ms:.3}\n"));
                }
                out.push_str("done\n");
                print!("{out}");
                std::io::stdout().flush().ok();
                std::process::exit(0);
            }
        }

        if self.mode == Mode::ScrollBench {
            root.ctx().request_repaint();
        }
    }
}

fn main() -> eframe::Result {
    let t0 = Instant::now();
    let mode = match std::env::args().nth(1).as_deref() {
        Some("--startup") => Mode::Startup,
        Some("--scroll-bench") => Mode::ScrollBench,
        _ => Mode::Default,
    };
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
                count: 0,
                text: String::new(),
                slider: 50.0,
                first_frame: None,
                frames: Vec::with_capacity(4096),
            }))
        }),
    )
}
