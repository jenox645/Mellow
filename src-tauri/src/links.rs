//! Where the window may go, what opens in the default browser, and which page
//! may ask for which permission.
//!
//! Links: the window stays on the loading page and the local backend. Any
//! other http(s) or mailto link, followed or opened in a new window, goes to
//! the default browser (tauri-plugin-opener); other schemes are refused and
//! logged. Permissions: the backend's page (its exact origin, port included,
//! from the ready line) may show desktop notifications (the shell asks for that
//! permission each time the page loads; Config → Desktop Notifications still
//! decides whether the page notifies); every other page, another local port
//! too, and every other permission (camera, microphone, location…) is denied.

use tauri::webview::{PermissionKind, PermissionResponse};
use tauri::{AppHandle, Url};
use tauri_plugin_opener::OpenerExt;

/// Where the window may go: the bundled loading page and the local backend.
pub fn is_local(url: &Url) -> bool {
    matches!(url.scheme(), "tauri" | "about" | "data")
        || (matches!(url.scheme(), "http" | "https")
            && matches!(url.host_str(), Some("tauri.localhost" | "127.0.0.1" | "localhost")))
}

/// The splash page's buttons (the window has no frame on Windows, and the
/// bundled page has no IPC either): links to `/__window/<op>` on the bundled
/// page, caught as navigations and done by the shell.
pub fn splash_op(url: &Url) -> Option<&str> {
    let bundled = url.scheme() == "tauri" || url.host_str() == Some("tauri.localhost");
    match url.path().strip_prefix("/__window/") {
        Some(op @ ("minimize" | "close")) if bundled => Some(op),
        _ => None,
    }
}

/// What to do with a link the page follows or opens in a new window.
#[derive(Debug, PartialEq, Eq)]
pub enum Route {
    /// The loading page or the backend: the window goes there.
    Stay,
    /// Somewhere else on the web, or an e-mail address: the default browser / mail app.
    Browser,
    /// Anything else (file:, javascript:, a custom scheme…): nowhere, logged.
    Refuse,
}

pub fn route(url: &Url) -> Route {
    if is_local(url) {
        Route::Stay
    } else if matches!(url.scheme(), "http" | "https" | "mailto") {
        Route::Browser
    } else {
        Route::Refuse
    }
}

/// A new window is never opened in the app: a local one would be a second,
/// signed-out copy of the page, so it's refused.
pub fn route_new_window(url: &Url) -> Route {
    match route(url) {
        Route::Stay => Route::Refuse,
        other => other,
    }
}

/// Hand a link to the default browser (or mail app) unless the route says no.
/// Returns whether the window itself may go there.
pub fn follow(app: &AppHandle, url: &Url, route: Route, what: &str) -> bool {
    match route {
        Route::Stay => true,
        Route::Browser => {
            match app.opener().open_url(url.as_str(), None::<&str>) {
                Ok(()) => eprintln!("MellowDLP shell: opened {url} in the default browser ({what})"),
                Err(e) => eprintln!("MellowDLP shell: couldn't open {url} in the default browser: {e}"),
            }
            false
        }
        Route::Refuse => {
            eprintln!("MellowDLP shell: refused {what} to {url}");
            false
        }
    }
}

/// Asked by the shell each time the backend's page has loaded. The page
/// notifies only while `Notification.permission` is "granted" (it asks once,
/// from Config's toggle), but the engine forgets a grant when the app exits, and
/// the origin changes with the backend's port at every launch. `permission()`
/// answers, without a prompt; Config's toggle still decides whether the page
/// notifies at all.
pub const ASK_NOTIFICATIONS: &str = "typeof Notification !== 'undefined' \
    && Notification.permission === 'default' && Notification.requestPermission()";

/// The origin (`http://127.0.0.1:<port>`) of the backend the window was sent
/// to by the ready line; None until then.
pub fn backend_origin(launch_url: &Url) -> Option<String> {
    let origin = launch_url.origin();
    (origin.is_tuple() && matches!(launch_url.scheme(), "http" | "https")).then(|| origin.ascii_serialization())
}

/// The backend's own page: its exact origin, port included (not the loading
/// page, not another site, not another service on this computer).
pub fn is_backend_page(url: &Url, backend: Option<&str>) -> bool {
    backend.is_some_and(|origin| backend_origin(url).as_deref() == Some(origin))
}

/// Permission requests from a page: only desktop notifications, and only for
/// the backend's own page (never the loading page, never anything else).
pub fn permission(page: Option<&Url>, backend: Option<&str>, kind: &PermissionKind) -> PermissionResponse {
    let backend_page = page.is_some_and(|url| is_backend_page(url, backend));
    if backend_page && matches!(kind, PermissionKind::Notifications) {
        PermissionResponse::Allow
    } else {
        PermissionResponse::Deny
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn url(text: &str) -> Url {
        Url::parse(text).unwrap()
    }

    #[test]
    fn the_loading_page_and_the_backend_stay_in_the_window() {
        for u in [
            "tauri://localhost/index.html",
            "http://tauri.localhost/index.html", // the bundled page's address on Windows
            "http://127.0.0.1:5123/launch?t=abc",
            "http://localhost:5123/",
            "about:blank",
            "data:text/html,hi",
        ] {
            assert_eq!(route(&url(u)), Route::Stay, "{u}");
        }
    }

    #[test]
    fn web_and_mail_links_open_in_the_browser() {
        for u in [
            "https://github.com/jenox645/Mellow/releases/latest",
            "http://example.com/",
            "mailto:someone@example.com",
            // a look-alike of the backend is still another site
            "https://127.0.0.1.example.com/",
            "http://localhost.example.com:5123/",
        ] {
            assert_eq!(route(&url(u)), Route::Browser, "{u}");
            assert_eq!(route_new_window(&url(u)), Route::Browser, "{u}");
        }
    }

    #[test]
    fn other_schemes_are_refused() {
        for u in [
            "file:///etc/passwd",
            "javascript:alert(1)",
            "ftp://example.com/x",
            "ms-settings:privacy",
            "vscode://file/x",
            "smb://server/share",
            "ws://127.0.0.1:5123/", // the backend's host, but not a page
            "file://127.0.0.1/etc/passwd",
        ] {
            assert_eq!(route(&url(u)), Route::Refuse, "{u}");
            assert_eq!(route_new_window(&url(u)), Route::Refuse, "{u}");
        }
    }

    #[test]
    fn the_splash_buttons_and_nothing_else() {
        assert_eq!(splash_op(&url("http://tauri.localhost/__window/close")), Some("close"));
        assert_eq!(splash_op(&url("tauri://localhost/__window/minimize")), Some("minimize"));
        for u in ["http://127.0.0.1:5123/__window/close", "http://tauri.localhost/__window/maximize",
                  "https://example.com/__window/close", "http://tauri.localhost/index.html"] {
            assert_eq!(splash_op(&url(u)), None, "{u}");
        }
    }

    #[test]
    fn a_new_window_for_the_backend_is_refused() {
        assert_eq!(route_new_window(&url("http://127.0.0.1:5123/")), Route::Refuse);
        assert_eq!(route_new_window(&url("tauri://localhost/index.html")), Route::Refuse);
    }

    /// What the ready line gives: the backend's /launch URL
    fn ready_origin() -> Option<String> {
        backend_origin(&url("http://127.0.0.1:5123/launch?t=abc"))
    }

    #[test]
    fn the_backend_origin_comes_from_the_ready_line() {
        assert_eq!(ready_origin().as_deref(), Some("http://127.0.0.1:5123"));
        assert_eq!(backend_origin(&url("tauri://localhost/index.html")), None);
        assert_eq!(backend_origin(&url("data:text/html,hi")), None);
    }

    #[test]
    fn only_the_backend_page_may_notify() {
        let backend = ready_origin();
        for page in ["http://127.0.0.1:5123/", "http://127.0.0.1:5123/launch?t=abc", "http://127.0.0.1:5123/#vault"] {
            assert_eq!(
                permission(Some(&url(page)), backend.as_deref(), &PermissionKind::Notifications),
                PermissionResponse::Allow,
                "{page}"
            );
        }
        for page in [
            // another service on this computer: same host, another port
            Some(url("http://127.0.0.1:8080/")),
            Some(url("http://127.0.0.1/")),
            // the same port under another name or scheme is another origin too
            Some(url("http://localhost:5123/")),
            Some(url("https://127.0.0.1:5123/")),
            Some(url("tauri://localhost/index.html")),
            Some(url("http://tauri.localhost/index.html")),
            Some(url("https://example.com/")),
            None,
        ] {
            assert_eq!(
                permission(page.as_ref(), backend.as_deref(), &PermissionKind::Notifications),
                PermissionResponse::Deny,
                "{page:?}"
            );
        }
    }

    #[test]
    fn nothing_may_notify_before_the_backend_is_ready() {
        for page in ["http://127.0.0.1:5123/", "tauri://localhost/index.html"] {
            assert_eq!(permission(Some(&url(page)), None, &PermissionKind::Notifications), PermissionResponse::Deny);
            assert!(!is_backend_page(&url(page), None));
        }
    }

    #[test]
    fn no_other_permission_is_ever_granted() {
        let backend = url("http://127.0.0.1:5123/");
        let origin = ready_origin();
        for kind in [
            PermissionKind::Microphone,
            PermissionKind::Camera,
            PermissionKind::Geolocation,
            PermissionKind::ClipboardRead,
            PermissionKind::DisplayCapture,
            PermissionKind::PointerLock,
            PermissionKind::Other,
        ] {
            assert_eq!(permission(Some(&backend), origin.as_deref(), &kind), PermissionResponse::Deny, "{kind:?}");
        }
    }
}
