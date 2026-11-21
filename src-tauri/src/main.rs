//! MellowDLP's Tauri shell: one window around the Flask backend.
//!
//! The shell starts the backend (backend.rs: the bundle's PyInstaller build,
//! or `python main.py` in a checkout) with `--shell`. The backend serves on
//! 127.0.0.1 and prints one line on stdout, `MELLOW_READY <launch-url>
//! [attached]`, where <launch-url> is the server's `/launch?t=<one-time token>`
//! (mellow/session.py). The window, which shows ui/index.html meanwhile, then
//! goes there and is signed in exactly like FlaskWebGUI's window. `attached`:
//! another MellowDLP already served this account, the backend we started has
//! exited, and the window uses that one.
//!
//! Closing the window ends the backend and everything it started: its stdin
//! closes (main.py's --shell watcher exits on EOF), and after a grace period
//! the rest is killed (Windows: a job object, which the OS also closes if this
//! process dies; Unix: the backend's process group).
//!
//! Links and permissions: links.rs.
//!
//! MELLOW_TIMING_LOG=<file> appends `<event> <epoch ms>` lines (shell_start,
//! backend_spawned, ready, navigated) for the startup measurements.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod backend;
mod links;

use std::fs::OpenOptions;
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};

use tauri::webview::{NewWindowResponse, PageLoadEvent};
use tauri::{AppHandle, Manager, RunEvent, Url, WebviewUrl, WebviewWindowBuilder};

use backend::{Backend, Launch};
use links::{backend_origin, follow, is_backend_page, is_local, permission, route, route_new_window};

const WINDOW_LABEL: &str = "main";
const WINDOW_TITLE: &str = "MellowDLP";
// main.py's WINDOW_WIDTH / WINDOW_HEIGHT (FlaskWebGUI's --window-size)
const WINDOW_WIDTH: f64 = 1100.0;
const WINDOW_HEIGHT: f64 = 780.0;
const READY_PREFIX: &str = "MELLOW_READY ";

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
    let resources = app.path().resource_dir().ok();
    let launch = Launch::resolve(|name| std::env::var_os(name), resources.as_deref(), &checkout());
    eprintln!("MellowDLP shell: starting the backend: {}", launch.describe());
    let stdout = app.state::<Backend>().spawn(&launch)?;
    timing("backend_spawned");

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
        .manage(Backend::new())
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
                            let _ = webview.eval(links::ASK_NOTIFICATIONS);
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
