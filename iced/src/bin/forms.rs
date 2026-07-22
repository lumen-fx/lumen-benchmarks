//! Bench forms app - iced variant: widget-dense settings page
//! (~40 controls in 6 groups; shared spec in the repo README).
//!
//! --interact drives, per cycle: a 40-step focus walk
//! (`iced::widget::focus_next()`, iced's real focus chain operation),
//! then a 20-step toggle-all pass (flip 8 checkboxes + 4 togglers,
//! advance both radio groups through their 4 options - direct state
//! mutation, same as the other frameworks). One step per 16 ms of wall
//! time, paced by an `iced::time::every(4 ms)` timer subscription (a
//! frames()-driven pacer spins iced's update loop unthrottled); the
//! footer status label changes every step so every step produces
//! visible damage and hence a redraw. Frame timestamps: the first
//! `iced::window::frames()` delivery after each step's damage.
//! (`window::frames()` fires per update-loop iteration under the
//! headless compositor - ~26 us apart, no present gating - so raw
//! deliveries measure the message pump, not painting. Recording only
//! damaged iterations yields one timestamp per stepped frame, matching
//! what the Qt/GTK variants record. See caveats.)

use std::time::Instant;

use bench_iced::{interact_cycles, parse_mode, print_deltas_done,
                 print_first_frame, print_startup_and_exit, Mode};
use iced::widget::{button, checkbox, column, container, pick_list, radio, row,
                   scrollable, slider, text, text_input, toggler};
use iced::{Center, Color, Element, Fill, Font, Subscription, Task};

const STEP_S: f32 = 0.016;
const SETTLE_S: f32 = 0.5;
const STEPS_PER_CYCLE: i64 = 60; // 40 focus + 8 cb + 4 tg + 2x4 radio advances

const DENSITY: [&str; 5] = ["Compact", "Cozy", "Normal", "Comfortable", "Spacious"];
const PROTOCOL: [&str; 5] = ["Auto", "HTTP/1.1", "HTTP/2", "HTTP/3", "SOCKS5"];
const LINE_ENDINGS: [&str; 5] = ["Auto", "LF", "CRLF", "CR", "Keep mixed"];
const LOG_LEVEL: [&str; 5] = ["Error", "Warn", "Info", "Debug", "Trace"];
const RADIO_A: [&str; 4] = ["System", "Light", "Dark", "High contrast"];
const RADIO_B: [&str; 4] = ["Off", "Crash reports only", "Basic", "Full"];

#[derive(Debug, Clone)]
enum Message {
    Frame(Instant),
    Tick(Instant),
    Input(usize, String),
    Check(usize, bool),
    Toggle(usize, bool),
    RadioA(usize),
    RadioB(usize),
    Slider(usize, f32),
    Drop(usize, &'static str),
    Press,
}

struct Forms {
    t0: Instant,
    mode: Mode,
    cycles: i64,
    inputs: [String; 8],
    checks: [bool; 8],
    toggles: [bool; 4],
    radio_a: usize,
    radio_b: usize,
    sliders: [f32; 4],
    drops: [&'static str; 4],
    status: String,
    // interact driver
    reported: bool,
    first_frame: Option<Instant>,
    frames: Vec<Instant>,
    started: Option<Instant>,
    step_done: i64,
    damaged: bool,
}

impl Forms {
    fn apply_step(&mut self, step: i64) -> Task<Message> {
        let in_cycle = step % STEPS_PER_CYCLE;
        if in_cycle < 40 {
            return iced::widget::focus_next();
        }
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
        Task::none()
    }

    fn update(&mut self, message: Message) -> Task<Message> {
        match message {
            Message::Frame(now) => {
                if self.first_frame.is_none() {
                    self.first_frame = Some(now);
                    print_first_frame();
                    if self.mode == Mode::Startup {
                        print_startup_and_exit(self.t0, now);
                    }
                    return Task::none();
                }
                if self.mode == Mode::Interact && !self.reported && self.started.is_some()
                    && self.damaged
                {
                    self.frames.push(now);
                    self.damaged = false;
                }
                Task::none()
            }
            Message::Tick(now) => {
                if self.mode != Mode::Interact || self.reported {
                    return Task::none();
                }
                let Some(first) = self.first_frame else {
                    return Task::none();
                };
                if (now - first).as_secs_f32() < SETTLE_S {
                    return Task::none();
                }
                let started = *self.started.get_or_insert(now);
                let total = STEPS_PER_CYCLE * self.cycles;
                let due = (((now - started).as_secs_f32() / STEP_S) as i64).min(total);
                let mut tasks = Vec::new();
                while self.step_done < due {
                    let s = self.step_done;
                    self.status = format!("step {s}");
                    tasks.push(self.apply_step(s));
                    self.step_done += 1;
                    self.damaged = true;
                }
                if self.step_done >= total {
                    print_deltas_done(&self.frames);
                    self.reported = true; // stay alive for post-run memory sample
                }
                Task::batch(tasks)
            }
            Message::Input(i, s) => {
                self.inputs[i] = s;
                Task::none()
            }
            Message::Check(i, v) => {
                self.checks[i] = v;
                Task::none()
            }
            Message::Toggle(i, v) => {
                self.toggles[i] = v;
                Task::none()
            }
            Message::RadioA(i) => {
                self.radio_a = i;
                Task::none()
            }
            Message::RadioB(i) => {
                self.radio_b = i;
                Task::none()
            }
            Message::Slider(i, v) => {
                self.sliders[i] = v;
                Task::none()
            }
            Message::Drop(i, v) => {
                self.drops[i] = v;
                Task::none()
            }
            Message::Press => Task::none(),
        }
    }

    fn labeled<'a>(
        &self,
        name: &'static str,
        w: impl Into<Element<'a, Message>>,
    ) -> Element<'a, Message> {
        row![text(name).width(110), w.into()]
            .spacing(12)
            .align_y(Center)
            .into()
    }

    fn group<'a>(
        &self,
        title: &'static str,
        items: Vec<Element<'a, Message>>,
    ) -> Element<'a, Message> {
        let mut col = column![text(title).font(Font {
            weight: iced::font::Weight::Bold,
            ..Font::DEFAULT
        })]
        .spacing(8);
        for item in items {
            col = col.push(item);
        }
        container(col)
            .padding(8)
            .width(Fill)
            .style(container::bordered_box)
            .into()
    }

    fn view(&self) -> Element<'_, Message> {
        let header = row![text("Bench").size(18).font(Font {
            weight: iced::font::Weight::Bold,
            ..Font::DEFAULT
        })]
        .height(48)
        .padding(8)
        .align_y(Center);

        let input = |i: usize, ph: &'static str, w: f32| {
            text_input(ph, &self.inputs[i])
                .on_input(move |s| Message::Input(i, s))
                .width(w)
        };
        let check = |i: usize, label: &'static str| {
            checkbox(label, self.checks[i]).on_toggle(move |v| Message::Check(i, v))
        };
        let tog = |i: usize| toggler(self.toggles[i]).on_toggle(move |v| Message::Toggle(i, v));
        let slide = |i: usize| {
            slider(0.0..=100.0, self.sliders[i], move |v| Message::Slider(i, v)).width(200)
        };
        let radio_col = |names: &'static [&'static str; 4],
                         sel: usize,
                         msg: fn(usize) -> Message| {
            let mut col = column![].spacing(4);
            for (i, n) in names.iter().enumerate() {
                col = col.push(radio(*n, i, Some(sel), move |v| msg(v)));
            }
            col
        };

        let account = self.group(
            "Account",
            vec![
                self.labeled("Username:", input(0, "Username", 220.0)),
                self.labeled("Email:", input(1, "Email", 220.0)),
                row![check(0, "Remember me"), check(1, "Subscribe to newsletter")]
                    .spacing(12)
                    .into(),
                button(text("Sign out")).on_press(Message::Press).into(),
            ],
        );
        let appearance = self.group(
            "Appearance",
            vec![
                self.labeled("Theme:", radio_col(&RADIO_A, self.radio_a, Message::RadioA)),
                self.labeled("Font size:", slide(0)),
                self.labeled(
                    "Density:",
                    pick_list(DENSITY, Some(self.drops[0]), |v| Message::Drop(0, v)),
                ),
                self.labeled("Animations:", tog(0)),
            ],
        );
        let network = self.group(
            "Network",
            vec![
                self.labeled("Proxy host:", input(2, "proxy.example.com", 220.0)),
                self.labeled("Proxy port:", input(3, "8080", 100.0)),
                row![check(2, "Use proxy"), check(3, "Verify TLS certificates")]
                    .spacing(12)
                    .into(),
                self.labeled("Timeout:", slide(1)),
                self.labeled(
                    "Protocol:",
                    pick_list(PROTOCOL, Some(self.drops[1]), |v| Message::Drop(1, v)),
                ),
                button(text("Test connection")).on_press(Message::Press).into(),
            ],
        );
        let editor = self.group(
            "Editor",
            vec![
                self.labeled("Font family:", input(4, "monospace", 220.0)),
                self.labeled("Tab width:", input(5, "4", 100.0)),
                row![check(4, "Word wrap"), check(5, "Line numbers")]
                    .spacing(12)
                    .into(),
                self.labeled(
                    "Line endings:",
                    pick_list(LINE_ENDINGS, Some(self.drops[2]), |v| Message::Drop(2, v)),
                ),
                self.labeled("Rulers:", slide(2)),
                self.labeled("Autosave:", tog(1)),
            ],
        );
        let privacy = self.group(
            "Privacy",
            vec![
                self.labeled("Telemetry:", radio_col(&RADIO_B, self.radio_b, Message::RadioB)),
                row![check(6, "Upload crash reports"), check(7, "Share usage statistics")]
                    .spacing(12)
                    .into(),
                self.labeled("Do not track:", tog(2)),
                button(text("Clear data")).on_press(Message::Press).into(),
            ],
        );
        let advanced = self.group(
            "Advanced",
            vec![
                self.labeled("Config path:", input(6, "~/.config/bench", 220.0)),
                self.labeled("Log filter:", input(7, "info", 220.0)),
                self.labeled(
                    "Log level:",
                    pick_list(LOG_LEVEL, Some(self.drops[3]), |v| Message::Drop(3, v)),
                ),
                self.labeled("Cache size:", slide(3)),
                self.labeled("Experimental:", tog(3)),
                button(text("Reset all")).on_press(Message::Press).into(),
            ],
        );

        let body = scrollable(
            column![account, appearance, network, editor, privacy, advanced]
                .spacing(12)
                .padding(8)
                .width(Fill),
        )
        .height(Fill);

        let grey = Color::from_rgb8(0x77, 0x77, 0x77);
        let footer = row![
            text(&self.status).color(grey),
            text(format!("theme: {}", RADIO_A[self.radio_a])).color(grey),
            text(format!("telemetry: {}", RADIO_B[self.radio_b])).color(grey),
        ]
        .height(32)
        .padding([4, 8])
        .spacing(8)
        .align_y(Center);

        container(column![header, body, footer]).into()
    }

    fn subscription(&self) -> Subscription<Message> {
        if (self.mode == Mode::Interact && !self.reported) || self.first_frame.is_none() {
            let mut subs = vec![iced::window::frames().map(Message::Frame)];
            if self.mode == Mode::Interact {
                subs.push(
                    iced::time::every(std::time::Duration::from_millis(4))
                        .map(|t| Message::Tick(t.into())),
                );
            }
            Subscription::batch(subs)
        } else {
            Subscription::none()
        }
    }
}

fn main() -> iced::Result {
    let t0 = Instant::now();
    let mode = parse_mode();
    iced::application("Bench", Forms::update, Forms::view)
        .subscription(Forms::subscription)
        .window_size(iced::Size::new(800.0, 600.0))
        .run_with(move || {
            (
                Forms {
                    t0,
                    mode,
                    cycles: interact_cycles() as i64,
                    inputs: Default::default(),
                    checks: [false; 8],
                    toggles: [false; 4],
                    radio_a: 0,
                    radio_b: 0,
                    sliders: [50.0; 4],
                    drops: [DENSITY[0], PROTOCOL[0], LINE_ENDINGS[0], LOG_LEVEL[0]],
                    status: "idle".into(),
                    reported: false,
                    first_frame: None,
                    frames: Vec::with_capacity(4096),
                    started: None,
                    step_done: 0,
                    damaged: false,
                },
                Task::none(),
            )
        })
}
