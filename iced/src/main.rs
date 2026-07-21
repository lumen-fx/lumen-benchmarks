//! Bench app - iced 0.13 variant. See repo README for the shared spec.
//!
//! First-presented-frame proxy: first delivery of the
//! `iced::window::frames()` subscription (fires on window redraw).
//! Equivalence caveat: iced has no built-in virtualized list widget, so
//! the 10,000-row list is a plain `Column` inside a `scrollable` - all
//! rows are built each view pass. That is the idiomatic iced approach
//! and is reported as-is.

use std::io::Write as _;
use std::time::Instant;

use iced::widget::{button, column, container, row, scrollable, slider, text, text_input};
use iced::{Center, Color, Element, Fill, Font, Subscription, Task};

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

#[derive(Debug, Clone)]
enum Message {
    Frame(Instant),
    Increment,
    Input(String),
    Slider(u8),
    Scrolled(scrollable::Viewport),
}

struct Bench {
    t0: Instant,
    mode: Mode,
    count: u64,
    text: String,
    slider: u8,
    first_frame: Option<Instant>,
    frames: Vec<Instant>,
    list_id: scrollable::Id,
    max_scroll: f32,
}

impl Bench {
    fn new(t0: Instant, mode: Mode) -> Self {
        Self {
            t0,
            mode,
            count: 0,
            text: String::new(),
            slider: 50,
            first_frame: None,
            frames: Vec::with_capacity(4096),
            list_id: scrollable::Id::new("list"),
            // Fallback before the first Scrolled event reports real bounds:
            // content height minus the nominal viewport (600 - 48 - 56).
            max_scroll: ROWS as f32 * ROW_H - 496.0,
        }
    }

    fn update(&mut self, message: Message) -> Task<Message> {
        match message {
            Message::Frame(now) => {
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
                    return Task::none();
                }
                if self.mode == Mode::ScrollBench {
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
                    let pos = bounce(SPEED * elapsed, self.max_scroll);
                    return scrollable::scroll_to(
                        self.list_id.clone(),
                        scrollable::AbsoluteOffset { x: 0.0, y: pos },
                    );
                }
                Task::none()
            }
            Message::Increment => {
                self.count += 1;
                Task::none()
            }
            Message::Input(s) => {
                self.text = s;
                Task::none()
            }
            Message::Slider(v) => {
                self.slider = v;
                Task::none()
            }
            Message::Scrolled(viewport) => {
                let content = viewport.content_bounds();
                let bounds = viewport.bounds();
                self.max_scroll = (content.height - bounds.height).max(0.0);
                Task::none()
            }
        }
    }

    fn view(&self) -> Element<'_, Message> {
        let header = row![
            text("Bench").size(18).font(Font {
                weight: iced::font::Weight::Bold,
                ..Font::DEFAULT
            }),
            iced::widget::horizontal_space(),
            button(text(format!("Count: {}", self.count))).on_press(Message::Increment),
        ]
        .height(48)
        .padding(8)
        .align_y(Center);

        let rows = (0..ROWS).map(|i| {
            row![
                text(format!("Item {i}")).font(Font {
                    weight: iced::font::Weight::Bold,
                    ..Font::DEFAULT
                }),
                text(format!("subtitle {i}")).color(Color::from_rgb8(0x77, 0x77, 0x77)),
            ]
            .spacing(12)
            .padding(iced::Padding::ZERO.left(8))
            .height(ROW_H)
            .align_y(Center)
            .into()
        });
        let list = scrollable(iced::widget::Column::with_children(rows).width(Fill))
            .id(self.list_id.clone())
            .on_scroll(Message::Scrolled)
            .height(Fill);

        let footer = row![
            text_input("Type here...", &self.text)
                .on_input(Message::Input)
                .width(240),
            slider(0..=100u8, self.slider, Message::Slider).width(200),
            text(format!("{}", self.slider)),
        ]
        .height(56)
        .padding(8)
        .spacing(12)
        .align_y(Center);

        container(column![header, list, footer]).into()
    }

    fn subscription(&self) -> Subscription<Message> {
        if self.mode == Mode::ScrollBench || self.first_frame.is_none() {
            iced::window::frames().map(Message::Frame)
        } else {
            Subscription::none()
        }
    }
}

fn main() -> iced::Result {
    let t0 = Instant::now();
    let mode = match std::env::args().nth(1).as_deref() {
        Some("--startup") => Mode::Startup,
        Some("--scroll-bench") => Mode::ScrollBench,
        _ => Mode::Default,
    };
    iced::application("Bench", Bench::update, Bench::view)
        .subscription(Bench::subscription)
        .window_size(iced::Size::new(800.0, 600.0))
        .run_with(move || (Bench::new(t0, mode), Task::none()))
}
