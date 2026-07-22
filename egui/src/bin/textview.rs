//! Bench textview app - egui/eframe variant: 5,000 wrapped paragraphs
//! (~1.1 MiB shared corpus) as ONE wrapped label inside a scroll area.
//!
//! Equivalence caveat: egui shapes the whole document into a single
//! galley; the galley is cached across frames (keyed by text + wrap
//! width), so per-frame cost is the cache lookup + visible-region
//! tessellation, not a re-shape. No virtualization - deliberate for
//! this app type (it stresses shaping/wrapping, not row recycling).

use std::time::Instant;

use bench_egui::{bounce, load_corpus, parse_mode, print_deltas_done,
                 print_first_frame, print_startup_and_exit, scroll_seconds, Mode};
use eframe::egui;

const SPEED: f32 = 1000.0; // px/s

struct TextView {
    t0: Instant,
    mode: Mode,
    duration_s: f32,
    corpus: String,
    content_h: f32,
    first_frame: Option<Instant>,
    frames: Vec<Instant>,
    reported: bool,
}

impl eframe::App for TextView {
    fn ui(&mut self, root: &mut egui::Ui, _frame: &mut eframe::Frame) {
        let now = Instant::now();

        egui::Panel::top("header")
            .exact_size(48.0)
            .show(root, |ui| {
                ui.horizontal_centered(|ui| {
                    ui.label(egui::RichText::new("Bench").strong().size(18.0));
                });
            });

        egui::CentralPanel::default().show(root, |ui| {
            let avail_h = ui.available_height();
            let mut area = egui::ScrollArea::vertical().auto_shrink([false, false]);
            if self.mode == Mode::ScrollBench && !self.reported {
                if let Some(first) = self.first_frame {
                    let elapsed = (now - first).as_secs_f32();
                    let max = (self.content_h - avail_h).max(0.0);
                    area = area.vertical_scroll_offset(bounce(SPEED * elapsed, max));
                }
            }
            let out = area.show(ui, |ui| {
                ui.add(egui::Label::new(egui::RichText::new(self.corpus.as_str())).wrap());
            });
            self.content_h = out.content_size.y;
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
                self.reported = true;
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
    let corpus = load_corpus();
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
            Ok(Box::new(TextView {
                t0,
                mode,
                duration_s: scroll_seconds(),
                corpus,
                content_h: 0.0,
                first_frame: None,
                frames: Vec::with_capacity(4096),
                reported: false,
            }))
        }),
    )
}
