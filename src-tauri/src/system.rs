//! The system's services the tray needs: notifications, the clipboard and
//! starting with the system.
//!
//! Notifications go straight to the system (WinRT toasts on Windows,
//! notify-rust elsewhere), not through tauri-plugin-notification: that plugin
//! puts a script into every page, the backend's included, which replaces the
//! page's own `window.Notification` with calls to its IPC command, and the
//! page has no IPC, so the app's notifications (#95) would silently stop.

use tauri::AppHandle;
use tauri_plugin_autostart::ManagerExt;

/// The longest clipboard text sent to the backend as a link.
const CLIPBOARD_MAX_CHARS: usize = 4096;

/// A system notification. On Windows it shows on the main thread (WinRT wants
/// an initialized apartment) and a click on it brings the window up.
pub fn notify(app: &AppHandle, title: &str, body: &str, on_click: fn(&AppHandle)) {
    #[cfg(windows)]
    {
        let (title, body) = (title.to_string(), body.to_string());
        let handle = app.clone();
        let _ = app.run_on_main_thread(move || {
            use tauri_winrt_notification::Toast;
            let id = handle.config().identifier.clone();
            // The installed app's shortcut carries its identifier as AppUserModelID;
            // a build run from target/ has none, so it borrows PowerShell's
            let app_id = if installed() { id.as_str() } else { Toast::POWERSHELL_APP_ID };
            let clicked = handle.clone();
            let toast = Toast::new(app_id).title(&title).text1(&body).on_activated(move |_| {
                let again = clicked.clone();
                let _ = clicked.run_on_main_thread(move || on_click(&again));
                Ok(())
            });
            if let Err(e) = toast.show() {
                eprintln!("MellowDLP shell: notification not shown: {e}");
            }
        });
    }
    #[cfg(not(windows))]
    {
        let _ = on_click;
        let shown = notify_rust::Notification::new()
            .appname("MellowDLP")
            .summary(title)
            .body(body)
            .auto_icon()
            .show();
        if let Err(e) = shown {
            eprintln!("MellowDLP shell: notification not shown ({app:?}): {e}", app = app.config().identifier);
        }
    }
}

#[cfg(windows)]
fn installed() -> bool {
    let Ok(exe) = std::env::current_exe() else { return false };
    let dir = exe.parent().map(|d| d.to_string_lossy().to_lowercase()).unwrap_or_default();
    !(dir.ends_with("\\target\\debug") || dir.ends_with("\\target\\release"))
}

/// The clipboard's text, cut to a length a link can have.
pub fn clipboard_text() -> Option<String> {
    let text = arboard::Clipboard::new().ok()?.get_text().ok()?;
    Some(text.trim().chars().take(CLIPBOARD_MAX_CHARS).collect())
}

/// Make "start with the system" what Config says; returns what it now is.
pub fn start_with_system(app: &AppHandle, wanted: bool) -> bool {
    let launcher = app.autolaunch();
    let now = launcher.is_enabled().unwrap_or(false);
    if now == wanted {
        return now;
    }
    let done = if wanted { launcher.enable() } else { launcher.disable() };
    if let Err(e) = done {
        eprintln!("MellowDLP shell: couldn't turn starting with the system {}: {e}", if wanted { "on" } else { "off" });
    }
    launcher.is_enabled().unwrap_or(now)
}
