//! The system's services the tray needs: notifications, the clipboard and
//! starting with the system; and on Linux, the window's app ID.
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

/// Linux: the app ID GTK gives the window (Wayland's `app_id`, X11's `WM_CLASS`) is the
/// product name, `MellowDLP`. That is also the name of the .desktop file tauri's bundler
/// installs (`<productName>.desktop`) and its `StartupWMClass` (linux/mellowdlp.desktop):
/// GNOME and KDE find the window's .desktop file through it, and show MellowDLP with Mellow's
/// badge in Alt-Tab and the dock. GTK's own default is the executable's name
/// (`mellowdlp-shell`), which matched no .desktop file's name, and is what GNOME showed (with a
/// gear) for an AppImage, which installs none. Runs before GTK starts (`Builder::build`).
/// X11's class half is GDK's program class, by default the same name with its first letter
/// capitalized (so the same here). Not tauri's `app.enableGTKAppId`: that also registers a
/// GApplication on the session bus.
#[cfg(target_os = "linux")]
pub fn set_app_id(product_name: &str) {
    gtk::glib::set_prgname(Some(product_name));
}

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

/// Hidden in the tray, WebView2 may give memory back: its renderer trims caches and
/// the JavaScript heap (ICoreWebView2_19's memory usage target, "Low"); back on
/// screen, "Normal". Windows only; an older WebView2 runtime without it is left as is.
pub fn webview_memory_low(window: &tauri::WebviewWindow, low: bool) {
    #[cfg(windows)]
    {
        let _ = window.with_webview(move |webview| {
            use webview2_com::Microsoft::Web::WebView2::Win32::{
                ICoreWebView2_19, COREWEBVIEW2_MEMORY_USAGE_TARGET_LEVEL,
            };
            use windows_core::Interface;
            // 0: normal, 1: low (COREWEBVIEW2_MEMORY_USAGE_TARGET_LEVEL_*)
            let level = COREWEBVIEW2_MEMORY_USAGE_TARGET_LEVEL(if low { 1 } else { 0 });
            unsafe {
                if let Ok(core) = webview.controller().CoreWebView2() {
                    if let Ok(core) = core.cast::<ICoreWebView2_19>() {
                        if let Err(e) = core.SetMemoryUsageTargetLevel(level) {
                            eprintln!("MellowDLP shell: WebView2 memory target: {e}");
                        }
                    }
                }
            }
        });
    }
    #[cfg(not(windows))]
    let _ = (window, low);
}

#[cfg(test)]
mod tests {
    use serde_json::Value;

    fn config(text: &str) -> Value {
        serde_json::from_str(text).expect("valid JSON")
    }

    /// The .desktop file every Linux bundle installs (#117) names the window by the app ID
    /// set_app_id gives it, the product name: without that GNOME showed `mellowdlp-shell`
    /// with a gear. Its links (mellowdlp://, MimeType) reach the app as the argument.
    #[test]
    fn the_desktop_file_finds_the_window_by_its_app_id() {
        let desktop = include_str!("../linux/mellowdlp.desktop");
        let has = |line: &str| desktop.lines().any(|l| l == line);
        assert!(has("Name={{name}}") && has("StartupWMClass={{name}}"), "{desktop}");
        assert!(has("Icon={{icon}}") && has("Exec={{exec}} %u"), "{desktop}");
        assert!(desktop.contains("MimeType={{mime_type}}"), "the deep link's scheme");
        let bundle = config(include_str!("../tauri.bundle.conf.json"));
        for kind in ["deb", "rpm"] {
            // the AppImage is made from the deb's files
            assert_eq!(bundle["bundle"]["linux"][kind]["desktopTemplate"], "linux/mellowdlp.desktop");
        }
        let app = config(include_str!("../tauri.conf.json"));
        assert_eq!(app["productName"], "MellowDLP");
    }

    /// Linux installs every PNG of `bundle.icon` into the hicolor theme, by its size: GNOME's
    /// dock, Alt-Tab and app grid ask for 64 to 256 px and more. Each is Mellow's badge
    /// (scripts/make_icons.py), at the size its name says.
    #[test]
    fn linux_gets_the_badge_at_every_size_gnome_asks_for() {
        let app = config(include_str!("../tauri.conf.json"));
        let icons: Vec<&str> = app["bundle"]["icon"].as_array().unwrap().iter().map(|v| v.as_str().unwrap()).collect();
        let dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR"));
        let mut sizes = Vec::new();
        for icon in icons.iter().filter(|i| i.ends_with(".png")) {
            let png = std::fs::read(dir.join(icon)).unwrap_or_else(|e| panic!("{icon}: {e}"));
            let width = u32::from_be_bytes(png[16..20].try_into().unwrap());
            let height = u32::from_be_bytes(png[20..24].try_into().unwrap());
            assert_eq!(width, height, "{icon}");
            assert!(icon.ends_with(&format!("/{width}x{height}.png")), "{icon} is {width}x{height}");
            sizes.push(width);
        }
        sizes.sort();
        assert_eq!(sizes, [32, 64, 128, 256, 512]);
        // The window's own icon is the first PNG: the badge at 64 px
        assert_eq!(icons.iter().find(|i| i.ends_with(".png")), Some(&"icons/64x64.png"));
    }
}
