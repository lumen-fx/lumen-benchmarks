//! Bench hello app - iced variant: minimal static window, one "Hello"
//! label + one button. Isolates the startup floor and baseline memory.
//! First-presented-frame proxy: first delivery of the
//! `iced::window::frames()` subscription (fires on window redraw), the
//! same proxy as the other iced apps.

use std::time::Instant;

use bench_iced::{parse_mode, print_first_frame, print_startup_and_exit, Mode};
use iced::widget::{button, column, container, text};
use iced::{Center, Element, Fill, Font, Subscription, Task};

#[derive(Debug, Clone)]
enum Message {
    Frame(Instant),
    Press,
}

struct Hello {
    t0: Instant,
    mode: Mode,
    first_frame: Option<Instant>,
}

impl Hello {
    fn update(&mut self, message: Message) -> Task<Message> {
        match message {
            Message::Frame(now) => {
                if self.first_frame.is_none() {
                    self.first_frame = Some(now);
                    print_first_frame();
                    if self.mode == Mode::Startup {
                        print_startup_and_exit(self.t0, now);
                    }
                }
                Task::none()
            }
            Message::Press => Task::none(),
        }
    }

    fn view(&self) -> Element<'_, Message> {
        container(
            column![
                text("Hello").size(18).font(Font {
                    weight: iced::font::Weight::Bold,
                    ..Font::DEFAULT
                }),
                button(text("Press")).on_press(Message::Press),
            ]
            .spacing(12)
            .align_x(Center),
        )
        .center_x(Fill)
        .center_y(Fill)
        .into()
    }

    fn subscription(&self) -> Subscription<Message> {
        if self.first_frame.is_none() {
            iced::window::frames().map(Message::Frame)
        } else {
            Subscription::none()
        }
    }
}

fn main() -> iced::Result {
    let t0 = Instant::now();
    let mode = parse_mode();
    iced::application("Bench", Hello::update, Hello::view)
        .subscription(Hello::subscription)
        .window_size(iced::Size::new(800.0, 600.0))
        .run_with(move || {
            (
                Hello {
                    t0,
                    mode,
                    first_frame: None,
                },
                Task::none(),
            )
        })
}
