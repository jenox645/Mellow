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
//! MELLOW_TIMING_LOG=<file> appends `<event> <epoch ms>` lines (shell_start,
//! backend_spawned, ready, navigated) for the startup measurements.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::fs::OpenOptions;
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use tauri::webview::NewWindowResponse;
use tauri::{AppHandle, Manager, RunEvent, Url, WebviewUrl, WebviewWindowBuilder};

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
        || matches!(url.host_str(), Some("tauri.localhost" | "127.0.0.1" | "localhost"))
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
    /// Untested in this trial (Windows only).
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
                (Some(url), Some(window)) if is_local(&url) => {
                    ready = true;
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
        .manage(Backend { child: Mutex::new(None), stdin: Mutex::new(None), tree: Mutex::new(None) })
        .setup(|app| {
            WebviewWindowBuilder::new(app, WINDOW_LABEL, WebviewUrl::App("index.html".into()))
                .title(WINDOW_TITLE)
                .inner_size(WINDOW_WIDTH, WINDOW_HEIGHT)
                // The page's title (download progress) shows in the taskbar, like the --app window
                .on_document_title_changed(|window, title| {
                    let _ = window.set_title(if title.is_empty() { WINDOW_TITLE } else { &title });
                })
                .on_navigation(|url| {
                    let ok = is_local(url);
                    if !ok {
                        eprintln!("MellowDLP shell: blocked navigation to {url}");
                    }
                    ok
                })
                .on_new_window(|url, _features| {
                    eprintln!("MellowDLP shell: blocked a new window for {url}");
                    NewWindowResponse::Deny
                })
                .build()?;
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
