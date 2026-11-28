//! The backend's side of the conversation (mellow/shell.py): the lines it
//! writes on stdout, and the commands this shell writes to its stdin.
//!
//! stdout: `MELLOW_READY <launch-url> [attached]` once the server listens, then
//! one `MELLOW_EVENT <json object>` per message ("type": state, notify,
//! launch, window_op, and the questions dialog and clipboard). stdin: one
//! JSON object per line, `{"cmd": ...}`.

use serde::Deserialize;
use serde_json::{json, Value};

pub const READY_PREFIX: &str = "MELLOW_READY ";
pub const EVENT_PREFIX: &str = "MELLOW_EVENT ";

/// One line from the backend.
#[derive(Debug, PartialEq)]
pub enum Line {
    Ready { url: String, attached: bool },
    Event(Event),
    /// Anything else (a library's output in development): passed through to our stdout
    Other,
}

/// A message from shell.py.
#[derive(Debug, Clone, PartialEq, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum Event {
    State(State),
    Notify {
        #[serde(default)]
        title: String,
        #[serde(default)]
        body: String,
    },
    Launch {
        url: String,
    },
    /// The page's title bar buttons (/api/window): minimize | maximize | close
    WindowOp {
        op: String,
    },
    /// A native file or folder dialog; the answer goes back as {"cmd": "answer", "id", "path"}
    Dialog {
        id: u64,
        kind: String,
        #[serde(default)]
        initial: Option<String>,
        #[serde(default)]
        extension: Option<String>,
    },
    /// The clipboard's text (the page's /api/clipboard: the backend has no Tk);
    /// the answer goes back as {"cmd": "answer", "id", "text"}
    Clipboard {
        id: u64,
    },
    /// A newer backend's message this shell doesn't know: ignored
    #[serde(other)]
    Unknown,
}

/// What the tray, the taskbar button and the close button show and do (shell.state()).
#[derive(Debug, Clone, Default, PartialEq, Deserialize)]
#[serde(default)]
pub struct State {
    /// idle | starting | downloading | processing | paused
    pub phase: String,
    pub pct: Option<f64>,
    pub title: Option<String>,
    pub active: u32,
    pub queued: u32,
    pub scheduled: u32,
    /// HH:MM of the next download scheduled for later
    pub next_start: Option<String>,
    pub daily_sync: Option<DailySync>,
    pub linked_folders: u32,
    pub run_in_background: bool,
    pub start_with_system: bool,
    pub tray_notice_seen: bool,
    /// Closing the window keeps MellowDLP in the tray
    pub keep_running: bool,
    /// Config's key combination for "download the copied link" ("" = none)
    pub global_shortcut: String,
}

#[derive(Debug, Clone, Default, PartialEq, Deserialize)]
#[serde(default)]
pub struct DailySync {
    pub time: String,
    pub folders: u32,
    pub other_folders: u32,
}

pub fn parse(line: &str) -> Line {
    if let Some(rest) = line.strip_prefix(READY_PREFIX) {
        let mut words = rest.split_whitespace();
        if let Some(url) = words.next() {
            return Line::Ready { url: url.to_string(), attached: words.next() == Some("attached") };
        }
        return Line::Other;
    }
    // Found anywhere in the line: what another writer left unfinished before it is dropped
    match line.find(EVENT_PREFIX) {
        Some(at) => serde_json::from_str(&line[at + EVENT_PREFIX.len()..]).map(Line::Event).unwrap_or(Line::Other),
        None => Line::Other,
    }
}

/// One command for the backend's stdin (without the newline).
pub fn command(cmd: &str, extra: Value) -> String {
    let mut message = json!({ "cmd": cmd });
    if let (Some(map), Value::Object(more)) = (message.as_object_mut(), extra) {
        map.extend(more);
    }
    message.to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_ready_line() {
        assert_eq!(
            parse("MELLOW_READY http://127.0.0.1:5123/launch?t=abc"),
            Line::Ready { url: "http://127.0.0.1:5123/launch?t=abc".into(), attached: false }
        );
        assert_eq!(
            parse("MELLOW_READY http://127.0.0.1:6001/launch?t=x attached"),
            Line::Ready { url: "http://127.0.0.1:6001/launch?t=x".into(), attached: true }
        );
        assert_eq!(parse("MELLOW_READY "), Line::Other);
    }

    #[test]
    fn a_state_message() {
        let line = r#"MELLOW_EVENT {"type":"state","phase":"downloading","pct":42.4,"title":"A song","active":1,"queued":2,"scheduled":0,"next_start":null,"daily_sync":{"time":"03:00","folders":2,"other_folders":0},"linked_folders":2,"run_in_background":true,"start_with_system":false,"tray_notice_seen":false,"keep_running":true}"#;
        let Line::Event(Event::State(s)) = parse(line) else { panic!("not a state") };
        assert_eq!((s.phase.as_str(), s.pct, s.active, s.queued), ("downloading", Some(42.4), 1, 2));
        assert_eq!(s.daily_sync.unwrap().time, "03:00");
        assert!(s.keep_running && s.run_in_background && !s.start_with_system);
    }

    #[test]
    fn fields_a_backend_leaves_out_take_defaults() {
        let Line::Event(Event::State(s)) = parse(r#"MELLOW_EVENT {"type":"state","phase":"idle"}"#) else {
            panic!("not a state")
        };
        assert_eq!(s, State { phase: "idle".into(), ..State::default() });
    }

    #[test]
    fn notify_and_launch() {
        assert_eq!(
            parse(r#"MELLOW_EVENT {"type":"notify","title":"3 new items in Lo-fi","body":"Synced in the background."}"#),
            Line::Event(Event::Notify { title: "3 new items in Lo-fi".into(), body: "Synced in the background.".into() })
        );
        assert_eq!(
            parse(r#"MELLOW_EVENT {"type":"launch","url":"http://127.0.0.1:5123/launch?t=new"}"#),
            Line::Event(Event::Launch { url: "http://127.0.0.1:5123/launch?t=new".into() })
        );
    }

    #[test]
    fn window_ops_and_dialogs() {
        assert_eq!(
            parse(r#"MELLOW_EVENT {"type":"window_op","op":"maximize"}"#),
            Line::Event(Event::WindowOp { op: "maximize".into() })
        );
        assert_eq!(
            parse(r#"MELLOW_EVENT {"type":"dialog","id":7,"kind":"folder","initial":"C:\\Music"}"#),
            Line::Event(Event::Dialog { id: 7, kind: "folder".into(), initial: Some("C:\\Music".into()), extension: None })
        );
        assert_eq!(parse(r#"MELLOW_EVENT {"type":"clipboard","id":8}"#), Line::Event(Event::Clipboard { id: 8 }));
    }

    #[test]
    fn unknown_messages_and_other_output() {
        assert_eq!(parse(r#"MELLOW_EVENT {"type":"from_the_future","x":1}"#), Line::Event(Event::Unknown));
        for line in ["", "[download] 42%", "MELLOW_EVENT not json", "MELLOW_EVENT {\"no\":\"type\"}"] {
            assert_eq!(parse(line), Line::Other, "{line}");
        }
    }

    #[test]
    fn a_message_after_unfinished_output_is_still_read() {
        assert_eq!(
            parse(r#"some print without its newline MELLOW_EVENT {"type":"launch","url":"http://127.0.0.1:1/launch?t=a"}"#),
            Line::Event(Event::Launch { url: "http://127.0.0.1:1/launch?t=a".into() })
        );
    }

    #[test]
    fn commands_are_one_json_line() {
        assert_eq!(command("pause", Value::Null), r#"{"cmd":"pause"}"#);
        let line = command("download", json!({"url": "https://x/v?a=1\nb"}));
        assert!(!line.contains('\n'));
        let back: Value = serde_json::from_str(&line).unwrap();
        assert_eq!(back, json!({"cmd": "download", "url": "https://x/v?a=1\nb"}));
        // Links go as they are, in UTF-8 (main.py reads the pipe as UTF-8)
        let line = command("download", json!({"url": "https://x/caf\u{e9}/\u{6771}\u{4eac}"}));
        assert!(line.contains("caf\u{e9}/\u{6771}\u{4eac}"));
    }
}
