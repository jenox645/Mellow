//! The tray icon: its menu, its tooltip and its picture, from the backend's
//! state (channel::State). The menu's actions go to the backend as commands
//! (main.rs); nothing here talks to the page.

use tauri::image::Image;
use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIcon, TrayIconBuilder, TrayIconEvent};
use tauri::window::ProgressBarStatus;
use tauri::{AppHandle, Wry};

use crate::channel::State;

pub const TRAY_ID: &str = "main";
// Windows cuts a tray tooltip at 127 characters
const TOOLTIP_MAX_CHARS: usize = 120;

/// The tray glyph (src-tauri/icons/tray.png), 32 × 32
const GLYPH: &[u8] = include_bytes!("../icons/tray.png");
// The progress line drawn along the glyph's bottom edge while downloading
const BAR_ROWS: u32 = 3;
const BAR_DONE: [u8; 4] = [0x2f, 0xd8, 0xf5, 0xff]; // Classic's cyan
const BAR_PAUSED: [u8; 4] = [0xf5, 0xb0, 0x2f, 0xff]; // Classic's amber
const BAR_LEFT: [u8; 4] = [0x1c, 0x2a, 0x3a, 0xff];

/// The menu items whose text or state follows the backend's state.
pub struct TrayMenu {
    pub pause: MenuItem<Wry>,
    pub sync: MenuItem<Wry>,
}

pub fn build(
    app: &AppHandle,
    on_menu: impl Fn(&AppHandle, &str) + Send + Sync + 'static,
    on_click: impl Fn(&AppHandle) + Send + Sync + 'static,
) -> tauri::Result<(TrayIcon, TrayMenu)> {
    let show = MenuItem::with_id(app, "show", "Show MellowDLP", true, None::<&str>)?;
    let pause = MenuItem::with_id(app, "pause", "Pause all downloads", false, None::<&str>)?;
    let paste = MenuItem::with_id(app, "paste", "Download the copied link", true, None::<&str>)?;
    let sync = MenuItem::with_id(app, "sync", "Sync all folders now", false, None::<&str>)?;
    let folder = MenuItem::with_id(app, "folder", "Open the download folder", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "Quit MellowDLP", true, None::<&str>)?;
    let menu = Menu::with_items(
        app,
        &[
            &show,
            &PredefinedMenuItem::separator(app)?,
            &pause,
            &paste,
            &sync,
            &folder,
            &PredefinedMenuItem::separator(app)?,
            &quit,
        ],
    )?;
    let tray = TrayIconBuilder::with_id(TRAY_ID)
        .icon(glyph(None, false))
        .tooltip("MellowDLP")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(move |app, event| on_menu(app, event.id().as_ref()))
        .on_tray_icon_event(move |tray, event| {
            if let TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, .. } = event {
                on_click(tray.app_handle());
            }
        })
        .build(app)?;
    Ok((tray, TrayMenu { pause, sync }))
}

/// The tray picture: the glyph, with the first download's progress along its
/// bottom edge (amber while paused).
pub fn glyph(pct: Option<f64>, paused: bool) -> Image<'static> {
    let base = Image::from_bytes(GLYPH).expect("icons/tray.png is a PNG");
    let (width, height) = (base.width(), base.height());
    let mut rgba = base.rgba().to_vec();
    if let Some(pct) = pct {
        let done = ((pct.clamp(0.0, 100.0) / 100.0) * width as f64).round() as u32;
        for y in height.saturating_sub(BAR_ROWS)..height {
            for x in 0..width {
                let colour = if x < done { if paused { BAR_PAUSED } else { BAR_DONE } } else { BAR_LEFT };
                let at = ((y * width + x) * 4) as usize;
                rgba[at..at + 4].copy_from_slice(&colour);
            }
        }
    }
    Image::new_owned(rgba, width, height)
}

/// The progress the picture shows: whole percents, so it changes ≤ 100 times a download.
pub fn shown_pct(state: &State) -> Option<f64> {
    match state.phase.as_str() {
        "downloading" | "paused" => Some(state.pct.unwrap_or(0.0).floor()),
        _ => None,
    }
}

pub fn tooltip(state: &State) -> String {
    let mut parts: Vec<String> = Vec::new();
    let pct = state.pct.map(|p| format!("{p:.0}%")).unwrap_or_default();
    match state.phase.as_str() {
        "downloading" => parts.push(format!("▼ {pct} {}", state.title.as_deref().unwrap_or("")).trim_end().to_string()),
        "processing" => parts.push(format!("Processing {}", state.title.as_deref().unwrap_or("")).trim_end().to_string()),
        "starting" => parts.push("Starting a download".into()),
        "paused" => parts.push(format!("Paused at {pct}").trim_end().to_string()),
        _ => {}
    }
    if state.active > 1 {
        parts.push(format!("{} running", state.active));
    }
    if state.queued > 0 {
        parts.push(format!("{} waiting", state.queued));
    }
    if state.scheduled > 0 {
        let when = state.next_start.as_deref().unwrap_or("later");
        parts.push(if state.scheduled == 1 {
            format!("1 download at {when}")
        } else {
            format!("{} downloads, first at {when}", state.scheduled)
        });
    }
    if state.phase == "idle" || state.phase.is_empty() {
        if let Some(sync) = &state.daily_sync {
            if sync.folders > 0 {
                parts.push(format!("Daily sync at {}", sync.time));
            } else {
                parts.push("Auto-sync on".into());
            }
        }
    }
    let text = if parts.is_empty() { "MellowDLP".to_string() } else { format!("MellowDLP — {}", parts.join(" · ")) };
    if text.chars().count() <= TOOLTIP_MAX_CHARS {
        text
    } else {
        text.chars().take(TOOLTIP_MAX_CHARS - 1).collect::<String>() + "…"
    }
}

/// The taskbar button's progress (Windows; elsewhere Tauri does what the system allows).
pub fn taskbar(state: &State) -> (ProgressBarStatus, Option<u64>) {
    let pct = state.pct.map(|p| p.clamp(0.0, 100.0).round() as u64);
    match state.phase.as_str() {
        "downloading" => (ProgressBarStatus::Normal, Some(pct.unwrap_or(0))),
        "paused" => (ProgressBarStatus::Paused, Some(pct.unwrap_or(0))),
        "processing" | "starting" => (ProgressBarStatus::Indeterminate, None),
        _ => (ProgressBarStatus::None, None),
    }
}

/// The pause item: what it says and whether it can be clicked.
pub fn pause_item(state: &State) -> (&'static str, bool) {
    if state.phase == "paused" {
        ("Resume all downloads", true)
    } else {
        ("Pause all downloads", state.active > 0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::channel::DailySync;

    fn state(phase: &str) -> State {
        State { phase: phase.into(), ..State::default() }
    }

    #[test]
    fn tooltips() {
        assert_eq!(tooltip(&state("idle")), "MellowDLP");
        let s = State { pct: Some(42.4), title: Some("A song".into()), active: 1, queued: 2, ..state("downloading") };
        assert_eq!(tooltip(&s), "MellowDLP — ▼ 42% A song · 2 waiting");
        let s = State { pct: Some(10.0), active: 1, ..state("paused") };
        assert_eq!(tooltip(&s), "MellowDLP — Paused at 10%");
        let s = State { scheduled: 1, next_start: Some("02:00".into()), ..state("idle") };
        assert_eq!(tooltip(&s), "MellowDLP — 1 download at 02:00");
        let sync = DailySync { time: "03:00".into(), folders: 2, other_folders: 0 };
        let s = State { daily_sync: Some(sync), ..state("idle") };
        assert_eq!(tooltip(&s), "MellowDLP — Daily sync at 03:00");
    }

    #[test]
    fn a_long_tooltip_is_cut() {
        let s = State { pct: Some(1.0), title: Some("x".repeat(300)), ..state("downloading") };
        let text = tooltip(&s);
        assert_eq!(text.chars().count(), TOOLTIP_MAX_CHARS);
        assert!(text.ends_with('…'));
    }

    #[test]
    fn the_taskbar_button() {
        assert!(matches!(taskbar(&State { pct: Some(42.6), ..state("downloading") }), (ProgressBarStatus::Normal, Some(43))));
        assert!(matches!(taskbar(&State { pct: Some(10.0), ..state("paused") }), (ProgressBarStatus::Paused, Some(10))));
        assert!(matches!(taskbar(&state("processing")), (ProgressBarStatus::Indeterminate, None)));
        assert!(matches!(taskbar(&state("idle")), (ProgressBarStatus::None, None)));
    }

    #[test]
    fn the_pause_item() {
        assert_eq!(pause_item(&state("idle")), ("Pause all downloads", false));
        assert_eq!(pause_item(&State { active: 1, ..state("downloading") }), ("Pause all downloads", true));
        assert_eq!(pause_item(&State { active: 1, ..state("paused") }), ("Resume all downloads", true));
    }

    #[test]
    fn the_picture_shows_the_progress_along_its_bottom() {
        let plain = glyph(None, false);
        let half = glyph(Some(50.0), false);
        let (w, h) = (half.width(), half.height());
        let px = |img: &Image, x: u32, y: u32| img.rgba()[((y * w + x) * 4) as usize..((y * w + x) * 4 + 4) as usize].to_vec();
        assert_eq!(px(&half, 0, h - 1), BAR_DONE.to_vec());
        assert_eq!(px(&half, w - 1, h - 1), BAR_LEFT.to_vec());
        assert_eq!(px(&glyph(Some(50.0), true), 0, h - 1), BAR_PAUSED.to_vec());
        assert_eq!(px(&half, w / 2, 0), px(&plain, w / 2, 0)); // the glyph itself untouched
        assert_eq!(shown_pct(&State { pct: Some(42.9), ..state("downloading") }), Some(42.0));
        assert_eq!(shown_pct(&state("idle")), None);
    }
}
