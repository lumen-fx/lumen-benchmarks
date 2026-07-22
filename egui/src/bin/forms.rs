//! Bench forms app - egui/eframe variant: widget-dense settings page
//! (40 controls in 6 groups; shared spec in the repo README).
//!
//! --interact drives, per cycle: a focus walk over all 40 controls
//! (egui: `Memory::request_focus` on each control's id - egui has no
//! synthetic-key path into a running context), then a toggle-all pass
//! (flip 8 checkboxes + 4 switches-as-checkboxes, advance both radio
//! groups through each of their 4 options). One action per 16 ms of
//! wall time; the footer status label changes every action so every
//! step produces visible damage. Frame timestamps: top of every update
//! pass (same proxy as the other egui apps); repaint is requested
//! continuously during the pass - egui is immediate-mode, so intervals
//! sit at the present cadence and jank shows as spikes.
//!
//! Equivalence caveats: egui has no switch widget (checkbox stands in),
//! and each radio is its own focus stop (no group-level Tab semantics).

use std::time::Instant;

use bench_egui::{interact_cycles, parse_mode, print_deltas_done,
                 print_first_frame, print_startup_and_exit, Mode};
use eframe::egui;

const STEP_S: f32 = 0.016;
const SETTLE_S: f32 = 0.5;

const DROPDOWNS: [(&str, [&str; 5]); 4] = [
    ("density", ["Compact", "Cozy", "Normal", "Comfortable", "Spacious"]),
    ("protocol", ["Auto", "HTTP/1.1", "HTTP/2", "HTTP/3", "SOCKS5"]),
    ("line-endings", ["Auto", "LF", "CRLF", "CR", "Keep mixed"]),
    ("log-level", ["Error", "Warn", "Info", "Debug", "Trace"]),
];
const RADIO_A: [&str; 4] = ["System", "Light", "Dark", "High contrast"];
const RADIO_B: [&str; 4] = ["Off", "Crash reports only", "Basic", "Full"];

struct Forms {
    t0: Instant,
    mode: Mode,
    cycles: u32,
    inputs: [String; 8],
    checks: [bool; 8],
    toggles: [bool; 4],
    radio_a: usize,
    radio_b: usize,
    sliders: [f32; 4],
    dropdowns: [usize; 4],
    // interact driver
    first_frame: Option<Instant>,
    frames: Vec<Instant>,
    reported: bool,
    started: Option<Instant>,
    step_done: i64,
    total_steps: i64,
    status: String,
    focus_ids: Vec<egui::Id>,
}

impl Forms {
    fn steps_per_cycle(&self) -> i64 {
        40 + 20 // focus walk + (8 cb + 4 tg + 2 groups x 4 radio advances)
    }

    fn apply_step(&mut self, step: i64, ctx: &egui::Context) {
        let per = self.steps_per_cycle();
        let in_cycle = step % per;
        self.status = format!("step {step}");
        if in_cycle < 40 {
            if let Some(id) = self.focus_ids.get(in_cycle as usize).copied() {
                ctx.memory_mut(|m| m.request_focus(id));
            }
        } else {
            let t = in_cycle - 40;
            match t {
                0..=7 => self.checks[t as usize] = !self.checks[t as usize],
                8..=11 => {
                    let i = (t - 8) as usize;
                    self.toggles[i] = !self.toggles[i];
                }
                12..=15 => self.radio_a = (self.radio_a + 1) % 4,
                _ => self.radio_b = (self.radio_b + 1) % 4,
            }
        }
    }
}

impl eframe::App for Forms {
    fn ui(&mut self, root: &mut egui::Ui, _frame: &mut eframe::Frame) {
        let now = Instant::now();
        let mut ids: Vec<egui::Id> = Vec::with_capacity(40);

        egui::Panel::top("header")
            .exact_size(48.0)
            .show(root, |ui| {
                ui.horizontal_centered(|ui| {
                    ui.label(egui::RichText::new("Bench").strong().size(18.0));
                });
            });

        egui::Panel::bottom("footer")
            .exact_size(32.0)
            .show(root, |ui| {
                ui.horizontal_centered(|ui| {
                    ui.label(&self.status);
                    ui.label(format!("theme: {}", RADIO_A[self.radio_a]));
                    ui.label(format!("telemetry: {}", RADIO_B[self.radio_b]));
                });
            });

        egui::CentralPanel::default().show(root, |ui| {
            egui::ScrollArea::vertical()
                .auto_shrink([false, false])
                .show(ui, |ui| {
                    // Group 1: Account -----------------------------------
                    ui.group(|ui| {
                        ui.label(egui::RichText::new("Account").strong());
                        for (i, name) in ["Username:", "Email:"].iter().enumerate() {
                            ui.horizontal(|ui| {
                                ui.label(*name);
                                let r = ui.add(
                                    egui::TextEdit::singleline(&mut self.inputs[i])
                                        .desired_width(220.0),
                                );
                                ids.push(r.id);
                            });
                        }
                        ui.horizontal(|ui| {
                            ids.push(ui.checkbox(&mut self.checks[0], "Remember me").id);
                            ids.push(
                                ui.checkbox(&mut self.checks[1], "Subscribe to newsletter").id,
                            );
                        });
                        ids.push(ui.button("Sign out").id);
                    });
                    // Group 2: Appearance --------------------------------
                    ui.group(|ui| {
                        ui.label(egui::RichText::new("Appearance").strong());
                        ui.horizontal(|ui| {
                            ui.label("Theme:");
                            ui.vertical(|ui| {
                                for (i, name) in RADIO_A.iter().enumerate() {
                                    let r = ui.radio_value(&mut self.radio_a, i, *name);
                                    ids.push(r.id);
                                }
                            });
                        });
                        ui.horizontal(|ui| {
                            ui.label("Font size:");
                            ids.push(
                                ui.add(egui::Slider::new(&mut self.sliders[0], 0.0..=100.0)).id,
                            );
                        });
                        ui.horizontal(|ui| {
                            ui.label("Density:");
                            ids.push(combo(ui, 0, &mut self.dropdowns[0]));
                        });
                        ui.horizontal(|ui| {
                            ui.label("Animations:");
                            ids.push(ui.checkbox(&mut self.toggles[0], "").id);
                        });
                    });
                    // Group 3: Network -----------------------------------
                    ui.group(|ui| {
                        ui.label(egui::RichText::new("Network").strong());
                        for (i, name) in ["Proxy host:", "Proxy port:"].iter().enumerate() {
                            ui.horizontal(|ui| {
                                ui.label(*name);
                                let r = ui.add(
                                    egui::TextEdit::singleline(&mut self.inputs[2 + i])
                                        .desired_width(if i == 0 { 220.0 } else { 100.0 }),
                                );
                                ids.push(r.id);
                            });
                        }
                        ui.horizontal(|ui| {
                            ids.push(ui.checkbox(&mut self.checks[2], "Use proxy").id);
                            ids.push(
                                ui.checkbox(&mut self.checks[3], "Verify TLS certificates").id,
                            );
                        });
                        ui.horizontal(|ui| {
                            ui.label("Timeout:");
                            ids.push(
                                ui.add(egui::Slider::new(&mut self.sliders[1], 0.0..=100.0)).id,
                            );
                        });
                        ui.horizontal(|ui| {
                            ui.label("Protocol:");
                            ids.push(combo(ui, 1, &mut self.dropdowns[1]));
                        });
                        ids.push(ui.button("Test connection").id);
                    });
                    // Group 4: Editor ------------------------------------
                    ui.group(|ui| {
                        ui.label(egui::RichText::new("Editor").strong());
                        for (i, name) in ["Font family:", "Tab width:"].iter().enumerate() {
                            ui.horizontal(|ui| {
                                ui.label(*name);
                                let r = ui.add(
                                    egui::TextEdit::singleline(&mut self.inputs[4 + i])
                                        .desired_width(if i == 0 { 220.0 } else { 100.0 }),
                                );
                                ids.push(r.id);
                            });
                        }
                        ui.horizontal(|ui| {
                            ids.push(ui.checkbox(&mut self.checks[4], "Word wrap").id);
                            ids.push(ui.checkbox(&mut self.checks[5], "Line numbers").id);
                        });
                        ui.horizontal(|ui| {
                            ui.label("Line endings:");
                            ids.push(combo(ui, 2, &mut self.dropdowns[2]));
                        });
                        ui.horizontal(|ui| {
                            ui.label("Rulers:");
                            ids.push(
                                ui.add(egui::Slider::new(&mut self.sliders[2], 0.0..=100.0)).id,
                            );
                        });
                        ui.horizontal(|ui| {
                            ui.label("Autosave:");
                            ids.push(ui.checkbox(&mut self.toggles[1], "").id);
                        });
                    });
                    // Group 5: Privacy -----------------------------------
                    ui.group(|ui| {
                        ui.label(egui::RichText::new("Privacy").strong());
                        ui.horizontal(|ui| {
                            ui.label("Telemetry:");
                            ui.vertical(|ui| {
                                for (i, name) in RADIO_B.iter().enumerate() {
                                    let r = ui.radio_value(&mut self.radio_b, i, *name);
                                    ids.push(r.id);
                                }
                            });
                        });
                        ui.horizontal(|ui| {
                            ids.push(ui.checkbox(&mut self.checks[6], "Upload crash reports").id);
                            ids.push(
                                ui.checkbox(&mut self.checks[7], "Share usage statistics").id,
                            );
                        });
                        ui.horizontal(|ui| {
                            ui.label("Do not track:");
                            ids.push(ui.checkbox(&mut self.toggles[2], "").id);
                        });
                        ids.push(ui.button("Clear data").id);
                    });
                    // Group 6: Advanced ----------------------------------
                    ui.group(|ui| {
                        ui.label(egui::RichText::new("Advanced").strong());
                        for (i, name) in ["Config path:", "Log filter:"].iter().enumerate() {
                            ui.horizontal(|ui| {
                                ui.label(*name);
                                let r = ui.add(
                                    egui::TextEdit::singleline(&mut self.inputs[6 + i])
                                        .desired_width(220.0),
                                );
                                ids.push(r.id);
                            });
                        }
                        ui.horizontal(|ui| {
                            ui.label("Log level:");
                            ids.push(combo(ui, 3, &mut self.dropdowns[3]));
                        });
                        ui.horizontal(|ui| {
                            ui.label("Cache size:");
                            ids.push(
                                ui.add(egui::Slider::new(&mut self.sliders[3], 0.0..=100.0)).id,
                            );
                        });
                        ui.horizontal(|ui| {
                            ui.label("Experimental:");
                            ids.push(ui.checkbox(&mut self.toggles[3], "").id);
                        });
                        ids.push(ui.button("Reset all").id);
                    });
                });
        });

        self.focus_ids = ids;

        if self.first_frame.is_none() {
            self.first_frame = Some(now);
            print_first_frame();
            if self.mode == Mode::Startup {
                print_startup_and_exit(self.t0, now);
            }
        }

        if self.mode == Mode::Interact && !self.reported {
            let first = self.first_frame.unwrap();
            if (now - first).as_secs_f32() >= SETTLE_S && self.started.is_none() {
                self.started = Some(now);
                self.total_steps = self.steps_per_cycle() * self.cycles as i64;
            }
            if let Some(started) = self.started {
                self.frames.push(now);
                let due = ((now - started).as_secs_f32() / STEP_S) as i64;
                let due = due.min(self.total_steps);
                let ctx = root.ctx().clone();
                while self.step_done < due {
                    let s = self.step_done;
                    self.apply_step(s, &ctx);
                    self.step_done += 1;
                }
                if self.step_done >= self.total_steps {
                    print_deltas_done(&self.frames);
                    self.reported = true; // stay alive for memory sample
                }
            }
            if !self.reported {
                root.ctx().request_repaint();
            }
        }
    }
}

fn combo(ui: &mut egui::Ui, which: usize, sel: &mut usize) -> egui::Id {
    let (name, opts) = DROPDOWNS[which];
    let r = egui::ComboBox::from_id_salt(name)
        .selected_text(opts[*sel])
        .show_ui(ui, |ui| {
            for (i, o) in opts.iter().enumerate() {
                ui.selectable_value(sel, i, *o);
            }
        });
    r.response.id
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
            Ok(Box::new(Forms {
                t0,
                mode,
                cycles: interact_cycles(),
                inputs: Default::default(),
                checks: [false; 8],
                toggles: [false; 4],
                radio_a: 0,
                radio_b: 0,
                sliders: [50.0; 4],
                dropdowns: [0; 4],
                first_frame: None,
                frames: Vec::with_capacity(4096),
                reported: false,
                started: None,
                step_done: 0,
                total_steps: 0,
                status: "idle".into(),
                focus_ids: Vec::new(),
            }))
        }),
    )
}
