//! Bench textview app - iced variant: the shared ~1 MiB corpus
//! (5,000 wrapped paragraphs) as one `text` widget in a `scrollable`.
//!
//! Equivalence caveat: iced lays out the whole paragraph set every view
//! pass (no virtualization, no persistent galley cache across text
//! reuse) - this stresses its text layout path honestly.

use std::time::Instant;

use bench_iced::{bounce, load_corpus, parse_mode, print_deltas_done,
                 print_first_frame, print_startup_and_exit, scroll_seconds, Mode};
use iced::widget::{column, container, row, scrollable, text};
use iced::{Center, Element, Fill, Font, Subscription, Task};

const SPEED: f32 = 1000.0; // px/s

#[derive(Debug, Clone)]
enum Message {
    Frame(Instant),
    Scrolled(scrollable::Viewport),
}

struct TextView {
    t0: Instant,
    mode: Mode,
    duration_s: f32,
    corpus: String,
    reported: bool,
    first_frame: Option<Instant>,
    frames: Vec<Instant>,
    doc_id: scrollable::Id,
    max_scroll: f32,
}

impl TextView {
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
                if self.mode == Mode::ScrollBench && !self.reported {
                    self.frames.push(now);
                    let elapsed = (now - self.first_frame.unwrap()).as_secs_f32();
                    if elapsed >= self.duration_s {
                        print_deltas_done(&self.frames);
                        self.reported = true; // stay alive for post-run memory sample
                        return Task::none();
                    }
                    let pos = bounce(SPEED * elapsed, self.max_scroll);
                    return scrollable::scroll_to(
                        self.doc_id.clone(),
                        scrollable::AbsoluteOffset { x: 0.0, y: pos },
                    );
                }
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
        let header = row![text("Bench").size(18).font(Font {
            weight: iced::font::Weight::Bold,
            ..Font::DEFAULT
        })]
        .height(48)
        .padding(8)
        .align_y(Center);

        let doc = scrollable(
            container(text(self.corpus.as_str()))
                .padding(8)
                .width(Fill),
        )
        .id(self.doc_id.clone())
        .on_scroll(Message::Scrolled)
        .height(Fill);

        container(column![header, doc]).into()
    }

    fn subscription(&self) -> Subscription<Message> {
        if (self.mode == Mode::ScrollBench && !self.reported) || self.first_frame.is_none() {
            iced::window::frames().map(Message::Frame)
        } else {
            Subscription::none()
        }
    }
}

fn main() -> iced::Result {
    let t0 = Instant::now();
    let mode = parse_mode();
    let corpus = load_corpus();
    iced::application("Bench", TextView::update, TextView::view)
        .subscription(TextView::subscription)
        .window_size(iced::Size::new(800.0, 600.0))
        .run_with(move || {
            (
                TextView {
                    t0,
                    mode,
                    duration_s: scroll_seconds(),
                    corpus,
                    reported: false,
                    first_frame: None,
                    frames: Vec::with_capacity(4096),
                    doc_id: scrollable::Id::new("doc"),
                    max_scroll: 10_000.0, // replaced by the first Scrolled event
                },
                Task::none(),
            )
        })
}
