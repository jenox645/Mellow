//! MellowDLP's Tauri shell (trial): one window around the Flask backend.
//!
//! The backend runs from Python source: this starts `python main.py --shell`
//! (the repo root is MELLOW_ROOT, else the folder above src-tauri; the
//! interpreter is MELLOW_PYTHON, else `python` / `python3`). The backend
//! serves on 127.0.0.1 and prints one line on stdout,
//! `MELLOW_READY <launch-url> [attached]`, where <launch-url> is the server's
//! `/launch?t=<one-time token>` (mellow/session.py). The window, which shows
//! ui/index.html meanwhile, then goes there and is signed in exactly like
//! FlaskWebGUI's window. `attached`: another MellowDLP already served this
//! account, the backend we started has exited, and the window uses that one.
//!
//! Closing the window ends the backend and everything it started: its stdin
//! closes (main.py's --shell watcher exits on EOF), and after SHUTDOWN_GRACE
//! the rest is killed (Windows: a job object, which the OS also closes if this
//! process dies; Unix: the backend's process group).
//!
//! Links: the window stays on the loading page and the local backend. Any
//! other http(s) or mailto link, followed or opened in a new window, goes to
//! the default browser (tauri-plugin-opener); other schemes are refused and
//! logged. Permissions: the backend's page (its exact origin, port included,
//! from the ready line) may show desktop notifications (the shell asks for that
//! permission each time the page loads; Config → Desktop Notifications still
//! decides whether the page notifies); every other page, another local port
//! too, and every other permission (camera, microphone, location…) is denied.
//!
//! MELLOW_TIMING_LOG=<file> appends `<event> <epoch ms>` lines (shell_start,
//! backend_spawned, ready, navigated) for the startup measurements.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::fs::OpenOptions;
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use tauri::webview::{NewWindowResponse, PageLoadEvent, PermissionKind, PermissionResponse};
use tauri::{AppHandle, Manager, RunEvent, Url, WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_opener::OpenerExt;

const WINDOW_LABEL: &str = "main";
const WINDOW_TITLE: &str = "MellowDLP";
// main.py's WINDOW_WIDTH / WINDOW_HEIGHT (FlaskWebGUI's --window-size)
const WINDOW_WIDTH: f64 = 1100.0;
const WINDOW_HEIGHT: f64 = 780.0;
const READY_PREFIX: &str = "MELLOW_READY ";
const SHUTDOWN_GRACE: Duration = Duration::from_secs(3);
const SHUTDOWN_POLL: Duration = Duration::from_millis(50);

fn timing(event: &str) {
    let Ok(path) = std::env::var("MELLOW_TIMING_LOG") else { return };
    let ms = SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_millis()).unwrap_or(0);
    if let Ok(mut f) = OpenOptions::new().create(true).append(true).open(path) {
        let _ = writeln!(f, "{event} {ms}");
    }
}

fn repo_root() -> PathBuf {
    std::env::var_os("MELLOW_ROOT")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join(".."))
}

fn python() -> String {
    std::env::var("MELLOW_PYTHON")
        .unwrap_or_else(|_| if cfg!(windows) { "python".into() } else { "python3".into() })
}

/// Where the window may go: the bundled loading page and the local backend.
fn is_local(url: &Url) -> bool {
    matches!(url.scheme(), "tauri" | "about" | "data")
        || (matches!(url.scheme(), "http" | "https")
            && matches!(url.host_str(), Some("tauri.localhost" | "127.0.0.1" | "localhost")))
}

/// What to do with a link the page follows or opens in a new window.
#[derive(Debug, PartialEq, Eq)]
enum Route {
    /// The loading page or the backend: the window goes there.
    Stay,
    /// Somewhere else on the web, or an e-mail address: the default browser / mail app.
    Browser,
    /// Anything else (file:, javascript:, a custom scheme…): nowhere, logged.
    Refuse,
}

fn route(url: &Url) -> Route {
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
fn route_new_window(url: &Url) -> Route {
    match route(url) {
        Route::Stay => Route::Refuse,
        other => other,
    }
}

/// Hand a link to the default browser (or mail app) unless the route says no.
/// Returns whether the window itself may go there.
fn follow(app: &AppHandle, url: &Url, route: Route, what: &str) -> bool {
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
const ASK_NOTIFICATIONS: &str = "typeof Notification !== 'undefined' \
    && Notification.permission === 'default' && Notification.requestPermission()";

/// The origin (`http://127.0.0.1:<port>`) of the backend the window was sent
/// to by the ready line; None until then.
fn backend_origin(launch_url: &Url) -> Option<String> {
    let origin = launch_url.origin();
    (origin.is_tuple() && matches!(launch_url.scheme(), "http" | "https")).then(|| origin.ascii_serialization())
}

/// The backend's own page: its exact origin, port included (not the loading
/// page, not another site, not another service on this computer).
fn is_backend_page(url: &Url, backend: Option<&str>) -> bool {
    backend.is_some_and(|origin| backend_origin(url).as_deref() == Some(origin))
}

/// Permission requests from a page: only desktop notifications, and only for
/// the backend's own page (never the loading page, never anything else).
fn permission(page: Option<&Url>, backend: Option<&str>, kind: &PermissionKind) -> PermissionResponse {
    let backend_page = page.is_some_and(|url| is_backend_page(url, backend));
    if backend_page && matches!(kind, PermissionKind::Notifications) {
        PermissionResponse::Allow
    } else {
        PermissionResponse::Deny
    }
}

// ── The backend process and everything it starts ────────────────────────────

#[cfg(windows)]
mod tree {
    use std::os::windows::io::AsRawHandle;
    use std::process::Child;
    use windows_sys::Win32::Foundation::{CloseHandle, HANDLE};
    use windows_sys::Win32::System::JobObjects::{
        AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
        SetInformationJobObject, TerminateJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    };

    /// A job object holding the backend and its children (ffmpeg, deno…).
    /// KILL_ON_JOB_CLOSE: if this process dies, Windows kills them all.
    pub struct Tree(HANDLE);
    // The handle is only used through these methods; Windows handles are process-wide
    unsafe impl Send for Tree {}
    unsafe impl Sync for Tree {}

    impl Tree {
        pub fn adopt(child: &Child) -> Option<Tree> {
            unsafe {
                let job = CreateJobObjectW(std::ptr::null(), std::ptr::null());
                if job.is_null() {
                    return None;
                }
                let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
                info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
                let ok = SetInformationJobObject(
                    job,
                    JobObjectExtendedLimitInformation,
                    &info as *const _ as *const core::ffi::c_void,
                    std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
                ) != 0
                    && AssignProcessToJobObject(job, child.as_raw_handle() as HANDLE) != 0;
                if !ok {
                    CloseHandle(job);
                    return None;
                }
                Some(Tree(job))
            }
        }

        pub fn kill(&self) {
            unsafe {
                TerminateJobObject(self.0, 1);
            }
        }
    }

    impl Drop for Tree {
        fn drop(&mut self) {
            unsafe {
                CloseHandle(self.0);
            }
        }
    }

    pub fn configure(cmd: &mut std::process::Command) {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
}

#[cfg(unix)]
mod tree {
    use std::process::Child;

    /// The backend's process group (it leads its own: see configure()).
    /// Checked on Linux (Xvfb + openbox): closing the window or killing the shell ends
    /// the backend and its ffmpeg (main.py ends its own group when the shell dies).
    pub struct Tree(i32);

    impl Tree {
        pub fn adopt(child: &Child) -> Option<Tree> {
            Some(Tree(child.id() as i32))
        }

        pub fn kill(&self) {
            unsafe {
                libc::killpg(self.0, libc::SIGKILL);
            }
        }
    }

    pub fn configure(cmd: &mut std::process::Command) {
        use std::os::unix::process::CommandExt;
        cmd.process_group(0);
    }
}

struct Backend {
    child: Mutex<Option<Child>>,
    stdin: Mutex<Option<ChildStdin>>,
    tree: Mutex<Option<tree::Tree>>,
    /// backend_origin() of the ready line's URL: the one page that may notify
    origin: Mutex<Option<String>>,
}

impl Backend {
    fn origin(&self) -> Option<String> {
        self.origin.lock().unwrap().clone()
    }
}

impl Backend {
    /// Ask the backend to exit (stdin EOF), then kill whatever is left.
    fn shut_down(&self) {
        drop(self.stdin.lock().unwrap().take());
        if let Some(mut child) = self.child.lock().unwrap().take() {
            let deadline = Instant::now() + SHUTDOWN_GRACE;
            while Instant::now() < deadline {
                if !matches!(child.try_wait(), Ok(None)) {
                    break;
                }
                std::thread::sleep(SHUTDOWN_POLL);
            }
            let _ = child.kill();
            let _ = child.wait();
        }
        // Children the backend started (ffmpeg, deno…) die with it too
        if let Some(tree) = self.tree.lock().unwrap().take() {
            tree.kill();
        }
    }
}

fn show_error(app: &AppHandle, text: &str) {
    eprintln!("MellowDLP shell: {text}");
    if let Some(window) = app.get_webview_window(WINDOW_LABEL) {
        let text = format!("{text:?}"); // a JS string literal
        let _ = window.eval(format!(
            "(window.mellowShellError || function (t) {{ document.body.innerText = t; }})({text})"
        ));
    }
}

fn start_backend(app: &AppHandle) -> Result<(), String> {
    let root = repo_root();
    let mut cmd = Command::new(python());
    cmd.arg(root.join("main.py"))
        .arg("--shell")
        .current_dir(&root)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit());
    tree::configure(&mut cmd);
    let mut child = cmd
        .spawn()
        .map_err(|e| format!("couldn't start {} {}: {e}", python(), root.join("main.py").display()))?;
    timing("backend_spawned");
    let tree = tree::Tree::adopt(&child);
    let stdout = child.stdout.take().expect("piped stdout");
    let backend = app.state::<Backend>();
    *backend.stdin.lock().unwrap() = child.stdin.take();
    *backend.tree.lock().unwrap() = tree;
    *backend.child.lock().unwrap() = Some(child);

    let app = app.clone();
    std::thread::spawn(move || {
        let mut ready = false;
        let mut attached = false;
        for line in BufReader::new(stdout).lines() {
            let Ok(line) = line else { break };
            if ready {
                println!("{line}");
                continue;
            }
            let Some(rest) = line.strip_prefix(READY_PREFIX) else {
                println!("{line}");
                continue;
            };
            timing("ready");
            let mut words = rest.split_whitespace();
            let url = words.next().and_then(|u| Url::parse(u).ok());
            attached = words.next() == Some("attached");
            match (url, app.get_webview_window(WINDOW_LABEL)) {
                (Some(url), Some(window)) if is_local(&url) && backend_origin(&url).is_some() => {
                    ready = true;
                    *app.state::<Backend>().origin.lock().unwrap() = backend_origin(&url);
                    if window.navigate(url).is_ok() {
                        timing("navigated");
                    }
                }
                _ => show_error(&app, &format!("unexpected ready line: {line}")),
            }
        }
        // stdout closed: the backend exited
        if !ready {
            show_error(&app, "The MellowDLP backend stopped before it was ready: see ~/.mellow_dlp.log");
        } else if !attached {
            show_error(&app, "The MellowDLP backend stopped: see ~/.mellow_dlp.log");
        }
    });
    Ok(())
}

/// Chrome's --window-size (FlaskWebGUI) is the whole window, frame included;
/// Tauri sizes the page area. Shrink the page area by the frame so the window
/// is as big as today's.
fn fit_outer_size(window: &tauri::WebviewWindow) {
    let (Ok(scale), Ok(outer), Ok(inner)) = (window.scale_factor(), window.outer_size(), window.inner_size())
    else {
        return;
    };
    let frame_w = outer.width.saturating_sub(inner.width);
    let frame_h = outer.height.saturating_sub(inner.height);
    let width = ((WINDOW_WIDTH * scale) as u32).saturating_sub(frame_w);
    let height = ((WINDOW_HEIGHT * scale) as u32).saturating_sub(frame_h);
    let _ = window.set_size(tauri::PhysicalSize::new(width, height));
}

fn main() {
    timing("shell_start");
    let app = tauri::Builder::default()
        // First: a second launch focuses this window instead of starting another backend
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(window) = app.get_webview_window(WINDOW_LABEL) {
                let _ = window.unminimize();
                let _ = window.show();
                let _ = window.set_focus();
            }
        }))
        // Rust-side only: opens links in the browser for on_navigation / on_new_window.
        // Its click script stays out of the page: it sends target="_blank" links to the
        // plugin's IPC command, which this remote page can't call (no capability), so
        // those clicks did nothing at all
        .plugin(tauri_plugin_opener::Builder::new().open_js_links_on_click(false).build())
        .manage(Backend {
            child: Mutex::new(None),
            stdin: Mutex::new(None),
            tree: Mutex::new(None),
            origin: Mutex::new(None),
        })
        .setup(|app| {
            let window = WebviewWindowBuilder::new(app, WINDOW_LABEL, WebviewUrl::App("index.html".into()))
                .title(WINDOW_TITLE)
                .inner_size(WINDOW_WIDTH, WINDOW_HEIGHT)
                .visible(false) // shown once sized like the --app window (fit_outer_size)
                // The page's own drag and drop (a link dropped anywhere, files dropped on
                // the Vault): with Tauri's handler on, Windows never gives the page drop events
                .disable_drag_drop_handler()
                // The page's title (download progress) shows in the taskbar, like the --app window
                .on_document_title_changed(|window, title| {
                    let _ = window.set_title(if title.is_empty() { WINDOW_TITLE } else { &title });
                })
                .on_navigation({
                    let app = app.handle().clone();
                    move |url| follow(&app, url, route(url), "a navigation")
                })
                .on_new_window({
                    let app = app.handle().clone();
                    move |url, _features| {
                        follow(&app, &url, route_new_window(&url), "a new window");
                        NewWindowResponse::Deny
                    }
                })
                .on_page_load({
                    let app = app.handle().clone();
                    move |webview, load| {
                        let backend = app.state::<Backend>().origin();
                        if matches!(load.event(), PageLoadEvent::Finished)
                            && is_backend_page(load.url(), backend.as_deref())
                        {
                            let _ = webview.eval(ASK_NOTIFICATIONS);
                        }
                    }
                })
                .on_permission_request({
                    let app = app.handle().clone();
                    move |webview, kind| {
                        let page = webview.url().ok();
                        let backend = app.state::<Backend>().origin();
                        let answer = permission(page.as_ref(), backend.as_deref(), &kind);
                        eprintln!("MellowDLP shell: permission {kind:?} for {page:?}: {answer:?}");
                        answer
                    }
                })
                .build()?;
            fit_outer_size(&window);
            window.show()?;
            if let Err(e) = start_backend(app.handle()) {
                show_error(app.handle(), &e);
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building the MellowDLP shell");

    app.run(|app, event| {
        if let RunEvent::Exit = event {
            app.state::<Backend>().shut_down();
        }
    });
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
