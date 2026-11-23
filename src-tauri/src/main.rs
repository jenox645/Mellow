//! MellowDLP's Tauri shell: the window around the Flask backend, and the tray.
//!
//! The shell starts the backend (backend.rs: the bundle's PyInstaller build,
//! or `python main.py` in a checkout) with `--shell`. The backend serves on
//! 127.0.0.1 and prints `MELLOW_READY <launch-url> [attached]`, where
//! <launch-url> is the server's `/launch?t=<one-time token>` (mellow/session.py).
//! The window, which shows ui/index.html meanwhile, then goes there and is
//! signed in like FlaskWebGUI's window. `attached`: another MellowDLP already
//! served this account, the backend we started has exited, and the window
//! uses that one.
//!
//! After the ready line the backend and the shell keep talking over the same
//! pipes (channel.rs, mellow/shell.py), never through the page: the backend
//! sends what the tray and the taskbar button show and whether closing the
//! window keeps MellowDLP running, notifications for when no window is open,
//! and fresh sign-in links; the tray sends its commands (pause, the copied
//! link, sync, the download folder).
//!
//! Closing the window: with something to do (a download running or waiting,
//! a sync that runs by itself) and Config's "Run in the background" on, the
//! window hides and MellowDLP stays in the tray (a notice says so the first
//! time); after TRAY_RELEASE_AFTER hidden it is closed for real, freeing
//! WebView2, and "Show" opens a new one. Otherwise, and with the tray's Quit,
//! the app exits: the backend's stdin closes (main.py quits on EOF) and after
//! a grace period the rest is killed (Windows: a job object, which the OS also
//! closes if this process dies; Unix: the backend's process group).
//!
//! Started with --background (the system starting it at login,
//! tauri-plugin-autostart): no window, only the tray.
//!
//! Links and permissions: links.rs. MELLOW_TIMING_LOG=<file> appends
//! `<event> <epoch ms>` lines (shell_start, backend_spawned, ready, navigated).
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod backend;
mod channel;
mod links;
mod system;
mod tray;

use std::fs::OpenOptions;
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering::SeqCst};
use std::sync::Mutex;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use serde_json::{json, Value};
use tauri::webview::{NewWindowResponse, PageLoadEvent};
use tauri::window::ProgressBarState;
use tauri::{AppHandle, Manager, RunEvent, Url, WebviewUrl, WebviewWindow, WebviewWindowBuilder, WindowEvent};
use tauri_plugin_deep_link::DeepLinkExt;
use tauri_plugin_global_shortcut::{GlobalShortcutExt, ShortcutState};
use tauri_plugin_window_state::{AppHandleExt, StateFlags};

use backend::{Backend, Launch};
use channel::{Event, Line, State};
use links::{backend_origin, follow, is_backend_page, is_local, permission, route, route_new_window};

const WINDOW_LABEL: &str = "main";
const WINDOW_TITLE: &str = "MellowDLP";
// main.py's WINDOW_WIDTH / WINDOW_HEIGHT (FlaskWebGUI's --window-size)
const WINDOW_WIDTH: f64 = 1100.0;
const WINDOW_HEIGHT: f64 = 780.0;
/// The system started it at login: the tray only
const BACKGROUND_FLAG: &str = "--background";
/// A window hidden in the tray this long is closed for real
const TRAY_RELEASE_AFTER: Duration = Duration::from_secs(10 * 60);
const TRAY_NOTICE_TITLE: &str = "MellowDLP is still running";
const TRAY_NOTICE_BODY: &str =
    "Downloads and the daily sync go on from the tray. Right-click its icon to quit; Config → Run in the background changes this.";

/// What the shell knows and decides (Tauri state).
#[derive(Default)]
struct Shell {
    /// The backend's latest state (channel::State)
    state: Mutex<State>,
    got_state: AtomicBool,
    /// The tray's Quit: the next exit is for real
    quitting: AtomicBool,
    /// No window, on purpose: hidden to the tray, closed after a while there, or started at login
    in_tray: AtomicBool,
    /// Counts the times the window was shown: a release timer started before does nothing
    shown: AtomicU64,
    notice_shown: AtomicBool,
    /// What the tray's picture shows (whole percent, paused)
    tray_picture: Mutex<(Option<f64>, bool)>,
    menu: Mutex<Option<tray::TrayMenu>>,
    /// Where mellowdlp:// links go (deliver_link)
    links: Mutex<LinkRoute>,
}

/// Until the backend we started is ready, links wait: it may find another MellowDLP
/// running (FlaskWebGUI's, or one started with --no-window) and leave the window to
/// that copy, which has no pipe of ours.
#[derive(Default)]
struct LinkRoute {
    ready: bool,
    attached: bool,
    waiting: Vec<String>,
}

fn timing(event: &str) {
    let Ok(path) = std::env::var("MELLOW_TIMING_LOG") else { return };
    let ms = SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_millis()).unwrap_or(0);
    if let Ok(mut f) = OpenOptions::new().create(true).append(true).open(path) {
        let _ = writeln!(f, "{event} {ms}");
    }
}

/// The source checkout this shell was built from (the folder above src-tauri)
fn checkout() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..")
}

fn state_flags() -> StateFlags {
    StateFlags::SIZE | StateFlags::POSITION | StateFlags::MAXIMIZED
}

/// A command for the backend (mellow/shell.py's handlers).
fn send(app: &AppHandle, cmd: &str, extra: Value) {
    app.state::<Backend>().send(&channel::command(cmd, extra));
}

fn show_error(app: &AppHandle, text: &str) {
    eprintln!("MellowDLP shell: {text}");
    match app.get_webview_window(WINDOW_LABEL) {
        Some(window) => {
            let text = format!("{text:?}"); // a JS string literal
            let _ = window.eval(format!(
                "(window.mellowShellError || function (t) {{ document.body.innerText = t; }})({text})"
            ));
        }
        None => system::notify(app, "MellowDLP stopped", text, show_main),
    }
}

// ── The window ──────────────────────────────────────────────────────────────

/// Whether window-state has a saved size and place for the window.
fn has_saved_state(app: &AppHandle) -> bool {
    let Ok(dir) = app.path().app_config_dir() else { return false };
    std::fs::read_to_string(dir.join(app.filename()))
        .ok()
        .and_then(|text| serde_json::from_str::<Value>(&text).ok())
        .is_some_and(|saved| saved.get(WINDOW_LABEL).is_some())
}

/// Chrome's --window-size (FlaskWebGUI) is the whole window, frame included;
/// Tauri sizes the page area. Shrink the page area by the frame so a first
/// window is as big as today's (later ones open as they were left).
fn fit_outer_size(window: &WebviewWindow) {
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

fn build_window(app: &AppHandle) -> tauri::Result<WebviewWindow> {
    let saved = has_saved_state(app);
    let window = WebviewWindowBuilder::new(app, WINDOW_LABEL, WebviewUrl::App("index.html".into()))
        .title(WINDOW_TITLE)
        .inner_size(WINDOW_WIDTH, WINDOW_HEIGHT)
        .visible(false) // shown once sized (window-state, or fit_outer_size)
        // Windows: no system frame; the page draws the title bar (backend::CUSTOM_FRAME).
        // Classic's background from the first frame: no white flash before a page paints
        .decorations(!backend::CUSTOM_FRAME)
        .background_color(tauri::window::Color(7, 9, 15, 255))
        // The page's own drag and drop (a link dropped anywhere, files dropped on
        // the Vault): with Tauri's handler on, Windows never gives the page drop events
        .disable_drag_drop_handler()
        // The page's title (download progress) shows in the taskbar, like the --app window
        .on_document_title_changed(|window, title| {
            let _ = window.set_title(if title.is_empty() { WINDOW_TITLE } else { &title });
        })
        .on_navigation({
            let app = app.clone();
            move |url| {
                if let Some(op) = links::splash_op(url) {
                    window_op(&app, op);
                    return false;
                }
                follow(&app, url, route(url), "a navigation")
            }
        })
        .on_new_window({
            let app = app.clone();
            move |url, _features| {
                follow(&app, &url, route_new_window(&url), "a new window");
                NewWindowResponse::Deny
            }
        })
        .on_page_load({
            let app = app.clone();
            move |webview, load| {
                let backend = app.state::<Backend>().origin();
                if matches!(load.event(), PageLoadEvent::Finished) && is_backend_page(load.url(), backend.as_deref()) {
                    let _ = webview.eval(links::ASK_NOTIFICATIONS);
                }
            }
        })
        .on_permission_request({
            let app = app.clone();
            move |webview, kind| {
                let page = webview.url().ok();
                let backend = app.state::<Backend>().origin();
                let answer = permission(page.as_ref(), backend.as_deref(), &kind);
                eprintln!("MellowDLP shell: permission {kind:?} for {page:?}: {answer:?}");
                answer
            }
        })
        .build()?;
    if !saved {
        fit_outer_size(&window);
    }
    window.on_window_event({
        let app = app.clone();
        move |event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                if close_to_tray(&app) {
                    api.prevent_close();
                }
            }
        }
    });
    let state = app.state::<Shell>().state.lock().unwrap().clone();
    show_progress(&window, &state);
    window.show()?;
    let _ = window.set_focus();
    Ok(window)
}

/// Bring the window up: the hidden one, or a new one (signed in with a fresh link).
fn show_main(app: &AppHandle) {
    let shell = app.state::<Shell>();
    shell.shown.fetch_add(1, SeqCst);
    shell.in_tray.store(false, SeqCst);
    // On screen again: the page shows its own toasts (mellow/shell.py)
    send(app, "window", json!({ "visible": true }));
    if let Some(window) = app.get_webview_window(WINDOW_LABEL) {
        let _ = window.unminimize();
        let _ = window.show();
        let _ = window.set_focus();
        return;
    }
    // Not here: show_main runs in event handlers (the tray, a second launch, a
    // notification's click), and building a webview there deadlocks on Windows
    // (wry #583); seen with --background → Show
    let app = app.clone();
    std::thread::spawn(move || match build_window(&app) {
        // The ready line's link has long expired (one use, a minute): ask for another
        Ok(_) if app.state::<Backend>().is_alive() => send(&app, "launch", Value::Null),
        // No backend of ours any more (it attached to another MellowDLP, or it stopped):
        // a new one prints a fresh link, to that copy or to itself
        Ok(_) => {
            if let Err(e) = start_backend(&app, false) {
                show_error(&app, &e);
            }
        }
        Err(e) => eprintln!("MellowDLP shell: couldn't open the window: {e}"),
    });
}

/// The window's close button: hide to the tray when the backend says there is
/// something to do and Config allows it; false = let it close (the app exits).
fn close_to_tray(app: &AppHandle) -> bool {
    let shell = app.state::<Shell>();
    if shell.quitting.load(SeqCst) {
        return false;
    }
    let state = shell.state.lock().unwrap().clone();
    if !state.keep_running {
        return false;
    }
    shell.in_tray.store(true, SeqCst);
    let _ = app.save_window_state(state_flags());
    if let Some(window) = app.get_webview_window(WINDOW_LABEL) {
        let _ = window.hide();
    }
    // Its page stays connected, but nobody sees it: the backend notifies through us
    send(app, "window", json!({ "visible": false }));
    if !state.tray_notice_seen && !shell.notice_shown.swap(true, SeqCst) {
        system::notify(app, TRAY_NOTICE_TITLE, TRAY_NOTICE_BODY, show_main);
        send(app, "tray_notice_seen", json!({ "value": true }));
    }
    // Still hidden after a while: close it for real, WebView2 frees its memory
    let generation = shell.shown.load(SeqCst);
    let app = app.clone();
    std::thread::spawn(move || {
        std::thread::sleep(TRAY_RELEASE_AFTER);
        let handle = app.clone();
        let _ = app.run_on_main_thread(move || {
            let shell = handle.state::<Shell>();
            if shell.shown.load(SeqCst) != generation || !shell.in_tray.load(SeqCst) {
                return;
            }
            if let Some(window) = handle.get_webview_window(WINDOW_LABEL) {
                if !window.is_visible().unwrap_or(true) {
                    let _ = window.destroy();
                }
            }
        });
    });
    true
}

fn show_progress(window: &WebviewWindow, state: &State) {
    let (status, progress) = tray::taskbar(state);
    let _ = window.set_progress_bar(ProgressBarState { status: Some(status), progress });
}

/// The title bar's buttons (the page's, through the backend; the splash's).
fn window_op(app: &AppHandle, op: &str) {
    let Some(window) = app.get_webview_window(WINDOW_LABEL) else { return };
    let done = match op {
        "minimize" => window.minimize(),
        "maximize" if window.is_maximized().unwrap_or(false) => window.unmaximize(),
        "maximize" => window.maximize(),
        // As the system's close button: the tray decides (close_to_tray)
        "close" => window.close(),
        _ => Ok(()),
    };
    if let Err(e) = done {
        eprintln!("MellowDLP shell: window {op}: {e}");
    }
}

/// A native file or folder dialog owned by the window (rfd), on its own thread;
/// the answer (the path, "" when cancelled) goes back to the backend.
fn dialog(app: &AppHandle, id: u64, kind: String, initial: Option<String>, extension: Option<String>) {
    let app = app.clone();
    std::thread::spawn(move || {
        let mut picker = rfd::FileDialog::new();
        if let Some(window) = app.get_webview_window(WINDOW_LABEL) {
            picker = picker.set_parent(&window);
        }
        if let Some(dir) = initial.filter(|d| !d.is_empty()) {
            picker = picker.set_directory(dir);
        }
        let path = if kind == "folder" {
            picker.pick_folder()
        } else {
            if let Some(ext) = extension.as_deref().map(|e| e.trim_start_matches('.')).filter(|e| !e.is_empty()) {
                picker = picker.add_filter(format!("{} files", ext.to_uppercase()), &[ext]).add_filter("All files", &["*"]);
            }
            picker.pick_file()
        };
        let path = path.map(|p| p.to_string_lossy().into_owned()).unwrap_or_default();
        send(&app, "answer", json!({ "id": id, "path": path }));
    });
}

// ── The tray ────────────────────────────────────────────────────────────────

fn on_menu(app: &AppHandle, id: &str) {
    match id {
        "show" => show_main(app),
        "pause" => {
            let paused = app.state::<Shell>().state.lock().unwrap().phase == "paused";
            send(app, if paused { "resume" } else { "pause" }, Value::Null);
        }
        // The backend checks it is a link (and says so when it isn't)
        "paste" => send(app, "download", json!({ "url": system::clipboard_text().unwrap_or_default() })),
        "sync" => send(app, "sync_all", Value::Null),
        "folder" => send(app, "open_vault", Value::Null),
        "quit" => {
            app.state::<Shell>().quitting.store(true, SeqCst);
            app.exit(0);
        }
        _ => {}
    }
}

/// The backend's new state: the tray, the taskbar button, starting with the system.
fn apply_state(app: &AppHandle, new: State) {
    let shell = app.state::<Shell>();
    let first = !shell.got_state.swap(true, SeqCst);
    let old = std::mem::replace(&mut *shell.state.lock().unwrap(), new.clone());
    if let Some(icon) = app.tray_by_id(tray::TRAY_ID) {
        let _ = icon.set_tooltip(Some(tray::tooltip(&new)));
        let picture = (tray::shown_pct(&new), new.phase == "paused");
        let mut shown = shell.tray_picture.lock().unwrap();
        if *shown != picture {
            *shown = picture;
            let _ = icon.set_icon(Some(tray::glyph(picture.0, picture.1)));
        }
    }
    if let Some(menu) = shell.menu.lock().unwrap().as_ref() {
        let (text, enabled) = tray::pause_item(&new);
        let _ = menu.pause.set_text(text);
        let _ = menu.pause.set_enabled(enabled);
        let _ = menu.sync.set_enabled(new.linked_folders > 0);
    }
    if let Some(window) = app.get_webview_window(WINDOW_LABEL) {
        show_progress(&window, &new);
    }
    if first || old.global_shortcut != new.global_shortcut {
        set_global_shortcut(app, &old.global_shortcut, &new.global_shortcut);
    }
    if first || old.start_with_system != new.start_with_system {
        let now = system::start_with_system(app, new.start_with_system);
        if now != new.start_with_system {
            send(app, "start_with_system", json!({ "value": now }));
        }
    }
}

/// Config's key combination for "download the copied link", from anywhere.
fn set_global_shortcut(app: &AppHandle, old: &str, new: &str) {
    let shortcuts = app.global_shortcut();
    if !old.is_empty() {
        let _ = shortcuts.unregister(old);
    }
    if new.trim().is_empty() {
        return;
    }
    if let Err(e) = shortcuts.register(new.trim()) {
        eprintln!("MellowDLP shell: shortcut {new}: {e}");
        system::notify(app, "Shortcut not set", &format!("{new} can't be used ({e}). Config → In the background."), show_main);
    }
}

/// mellowdlp://download?url=<link>: the window comes up and the Feed analyzes the link.
fn open_deep_links(app: &AppHandle, links: &[Url]) {
    for link in links {
        match links::deep_link_target(link) {
            Some(target) => {
                show_main(app);
                deliver_link(app, target);
            }
            None => eprintln!("MellowDLP shell: ignored the link {link}"),
        }
    }
}

/// A link for the Feed: to our backend (its page analyzes it), held until it's ready,
/// or, when the window shows another MellowDLP, handed over through the clipboard.
fn deliver_link(app: &AppHandle, url: String) {
    let shell = app.state::<Shell>();
    let mut route = shell.links.lock().unwrap();
    if !route.ready {
        route.waiting.push(url);
    } else if route.attached {
        drop(route);
        hand_over_link(app, &url);
    } else {
        drop(route);
        send(app, "open_link", json!({ "url": url }));
    }
}

/// The other copy has no pipe of ours (and an older one no open_link): the link goes on the
/// clipboard, which its Feed offers when the window is focused, and a notification says so.
fn hand_over_link(app: &AppHandle, url: &str) {
    let copied = arboard::Clipboard::new().and_then(|mut clipboard| clipboard.set_text(url.to_owned())).is_ok();
    let body = if copied { "The link is on the clipboard: paste it in the Feed." } else { url };
    system::notify(app, "MellowDLP was already open", body, show_main);
}

// ── The backend ─────────────────────────────────────────────────────────────

fn go_to(app: &AppHandle, url: &str) {
    let Ok(url) = Url::parse(url) else { return };
    if !(is_local(&url) && backend_origin(&url).is_some()) {
        show_error(app, &format!("unexpected sign-in link: {url}"));
        return;
    }
    *app.state::<Backend>().origin.lock().unwrap() = backend_origin(&url);
    if let Some(window) = app.get_webview_window(WINDOW_LABEL) {
        if window.navigate(url).is_ok() {
            timing("navigated");
        }
    }
}

fn start_backend(app: &AppHandle, background: bool) -> Result<(), String> {
    let resources = app.path().resource_dir().ok();
    let launch = Launch::resolve(|name| std::env::var_os(name), resources.as_deref(), &checkout());
    eprintln!("MellowDLP shell: starting the backend: {}", launch.describe());
    app.state::<Shell>().links.lock().unwrap().ready = false;
    let stdout = app.state::<Backend>().spawn(&launch, background)?;
    timing("backend_spawned");

    let app = app.clone();
    std::thread::spawn(move || {
        let mut ready = false;
        let mut attached = false;
        for line in BufReader::new(stdout).lines() {
            let Ok(line) = line else { break };
            match channel::parse(&line) {
                Line::Ready { url, attached: other_copy } if !ready => {
                    timing("ready");
                    ready = true;
                    attached = other_copy;
                    // Started at login while another MellowDLP (the FlaskWebGUI app) runs:
                    // that copy does the work, and this tray would have no backend to talk to
                    if other_copy && app.get_webview_window(WINDOW_LABEL).is_none() {
                        eprintln!("MellowDLP shell: another MellowDLP is running: nothing to do in the tray");
                        app.exit(0);
                        return;
                    }
                    if let Some(window) = app.get_webview_window(WINDOW_LABEL) {
                        // That copy has no shell: its page draws no title bar and can't move or
                        // close this window, so the system's frame comes back
                        let _ = window.set_decorations(other_copy || !backend::CUSTOM_FRAME);
                    }
                    go_to(&app, &url);
                    let waiting = {
                        let shell = app.state::<Shell>();
                        let mut route = shell.links.lock().unwrap();
                        route.ready = true;
                        route.attached = other_copy;
                        std::mem::take(&mut route.waiting)
                    };
                    for link in waiting {
                        deliver_link(&app, link);
                    }
                }
                Line::Event(Event::State(state)) => apply_state(&app, state),
                Line::Event(Event::Notify { title, body }) => system::notify(&app, &title, &body, show_main),
                Line::Event(Event::Launch { url }) => go_to(&app, &url),
                Line::Event(Event::WindowOp { op }) => window_op(&app, &op),
                Line::Event(Event::Dialog { id, kind, initial, extension }) => {
                    dialog(&app, id, kind, initial, extension)
                }
                Line::Event(Event::Unknown) => {}
                _ => println!("{line}"),
            }
        }
        // stdout closed: the backend exited
        if !ready {
            show_error(&app, "The MellowDLP backend stopped before it was ready: see ~/.mellow_dlp.log");
        } else if !attached && !app.state::<Shell>().quitting.load(SeqCst) {
            show_error(&app, "The MellowDLP backend stopped: see ~/.mellow_dlp.log");
        }
    });
    Ok(())
}

fn main() {
    timing("shell_start");
    let background = std::env::args().any(|arg| arg == BACKGROUND_FLAG);
    let app = tauri::Builder::default()
        // First: a second launch shows this window instead of starting another backend;
        // the system starting it at login while it already runs shows nothing
        .plugin(tauri_plugin_single_instance::init(|app, args, _cwd| {
            if !args.iter().any(|arg| arg == BACKGROUND_FLAG) {
                show_main(app);
            }
        }))
        // Rust-side only: opens links in the browser for on_navigation / on_new_window.
        // Its click script stays out of the page: it sends target="_blank" links to the
        // plugin's IPC command, which this remote page can't call (no capability), so
        // those clicks did nothing at all
        .plugin(tauri_plugin_opener::Builder::new().open_js_links_on_click(false).build())
        // The window opens where and as big as it was left (not hidden or shown: we decide)
        .plugin(tauri_plugin_window_state::Builder::default().with_state_flags(state_flags()).build())
        // Config's key combination: the tray's "download the copied link", from any app
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(|app, _shortcut, event| {
                    if event.state() == ShortcutState::Pressed {
                        on_menu(app, "paste");
                    }
                })
                .build(),
        )
        // mellowdlp:// links (the installer registers the scheme; a second launch
        // with one hands it over through the single-instance plugin)
        .plugin(tauri_plugin_deep_link::init())
        // Config's "Start with Windows": the system starts it with --background
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            Some(vec![BACKGROUND_FLAG]),
        ))
        .manage(Backend::new())
        .manage(Shell::default())
        .setup(move |app| {
            let handle = app.handle().clone();
            let (_icon, menu) = tray::build(&handle, on_menu, show_main)?;
            {
                let links = handle.clone();
                app.deep_link().on_open_url(move |event| open_deep_links(&links, &event.urls()));
            }
            *app.state::<Shell>().menu.lock().unwrap() = Some(menu);
            if background {
                app.state::<Shell>().in_tray.store(true, SeqCst);
            } else {
                build_window(&handle)?;
            }
            if let Err(e) = start_backend(&handle, background) {
                show_error(&handle, &e);
            }
            // Started by a mellowdlp:// link: once the backend listens (the command waits in its pipe)
            if let Ok(Some(links)) = app.deep_link().get_current() {
                open_deep_links(&handle, &links);
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building the MellowDLP shell");

    app.run(|app, event| match event {
        // The last window closed while MellowDLP lives in the tray: keep running
        RunEvent::ExitRequested { code: None, api, .. } => {
            let shell = app.state::<Shell>();
            if shell.in_tray.load(SeqCst) && !shell.quitting.load(SeqCst) {
                api.prevent_exit();
            }
        }
        RunEvent::Exit => app.state::<Backend>().shut_down(),
        _ => {}
    });
}
