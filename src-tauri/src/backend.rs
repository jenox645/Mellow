//! The Python backend: which one to start, starting it, and ending it with
//! everything it started.
//!
//! Packaged (the installed app): the PyInstaller one-folder build ships in the
//! bundle's resources as `backend/` (build_setup.py --tauri) and its exe is
//! started with `--shell`. From source: `python main.py --shell` in a checkout.
//! Either way the backend serves on 127.0.0.1 and prints one line on stdout,
//! `MELLOW_READY <launch-url> [attached]` (main.py), and quits when its stdin
//! closes.
//!
//! Which one (Launch::resolve):
//! 1. MELLOW_BACKEND=<exe>: that backend exe (e.g. a dist/ build, with the debug shell);
//! 2. MELLOW_ROOT and/or MELLOW_PYTHON set: from source (checkout, interpreter);
//! 3. the bundle has `backend/<BACKEND_EXE>`: that one;
//! 4. else from source: the checkout this shell was built from, `python` / `python3`.
//!
//! The backend gets MELLOW_SHELL=tauri, so it knows a Tauri window is its
//! window (app_update: the bundle can't be replaced by the old updater).

use std::ffi::OsString;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

/// The folder of the bundle's resources the backend is in.
pub const BACKEND_DIR: &str = "backend";
/// The backend's exe in BACKEND_DIR (build_setup.py names the one-folder build's exe so).
pub const BACKEND_EXE: &str = if cfg!(windows) { "mellowdlp-backend.exe" } else { "mellowdlp-backend" };
/// What the backend reads to know which window it serves.
pub const SHELL_ENV: (&str, &str) = ("MELLOW_SHELL", "tauri");
/// Windows: a frameless window whose page draws the title bar (gui/components/titlebar.jsx);
/// elsewhere the system's own frame (not checked frameless on Linux or macOS)
pub const CUSTOM_FRAME: bool = cfg!(windows);

const SHUTDOWN_GRACE: Duration = Duration::from_secs(3);
const SHUTDOWN_POLL: Duration = Duration::from_millis(50);

/// How the backend is started.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Launch {
    /// A built backend (the bundle's, or MELLOW_BACKEND): its exe, with `--shell`.
    Packaged { exe: PathBuf },
    /// A source checkout: `<python> <root>/main.py --shell`.
    Source { python: String, root: PathBuf },
}

impl Launch {
    /// The backend for this run (see the module doc). `var` reads the
    /// environment, `resources` is the bundle's resource folder, `checkout`
    /// the source checkout to fall back to.
    pub fn resolve(var: impl Fn(&str) -> Option<OsString>, resources: Option<&Path>, checkout: &Path) -> Launch {
        let set = |name: &str| var(name).filter(|v| !v.is_empty());
        if let Some(exe) = set("MELLOW_BACKEND") {
            return Launch::Packaged { exe: PathBuf::from(exe) };
        }
        let source_asked = set("MELLOW_ROOT").is_some() || set("MELLOW_PYTHON").is_some();
        if !source_asked {
            if let Some(exe) = resources.map(bundled_exe).filter(|exe| exe.is_file()) {
                return Launch::Packaged { exe };
            }
        }
        Launch::Source {
            python: set("MELLOW_PYTHON")
                .map(|p| p.to_string_lossy().into_owned())
                .unwrap_or_else(|| if cfg!(windows) { "python".into() } else { "python3".into() }),
            root: set("MELLOW_ROOT").map(PathBuf::from).unwrap_or_else(|| checkout.to_path_buf()),
        }
    }

    /// The command that starts it (stdio still to be set).
    pub fn command(&self) -> Command {
        let mut cmd = match self {
            Launch::Packaged { exe } => {
                let mut cmd = Command::new(exe);
                if let Some(dir) = exe.parent() {
                    cmd.current_dir(dir);
                }
                cmd
            }
            Launch::Source { python, root } => {
                let mut cmd = Command::new(python);
                cmd.arg(root.join("main.py")).current_dir(root);
                cmd
            }
        };
        cmd.arg("--shell").env(SHELL_ENV.0, SHELL_ENV.1);
        if CUSTOM_FRAME {
            cmd.env("MELLOW_SHELL_FRAME", "custom");
        }
        cmd
    }

    /// For messages: what was started.
    pub fn describe(&self) -> String {
        match self {
            Launch::Packaged { exe } => exe.display().to_string(),
            Launch::Source { python, root } => format!("{python} {}", root.join("main.py").display()),
        }
    }
}

/// Where the bundle keeps its backend exe, given its resource folder.
pub fn bundled_exe(resources: &Path) -> PathBuf {
    resources.join(BACKEND_DIR).join(BACKEND_EXE)
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

/// The running backend (Tauri state).
pub struct Backend {
    child: Mutex<Option<Child>>,
    stdin: Mutex<Option<ChildStdin>>,
    tree: Mutex<Option<tree::Tree>>,
    /// links::backend_origin() of the ready line's URL: the one page that may notify
    pub origin: Mutex<Option<String>>,
}

impl Backend {
    pub fn new() -> Backend {
        Backend { child: Mutex::new(None), stdin: Mutex::new(None), tree: Mutex::new(None), origin: Mutex::new(None) }
    }

    pub fn origin(&self) -> Option<String> {
        self.origin.lock().unwrap().clone()
    }

    /// Start the backend; returns its stdout, where the ready line comes.
    /// background: the system started the app at login (main.py --background).
    pub fn spawn(&self, launch: &Launch, background: bool) -> Result<ChildStdout, String> {
        let mut cmd = launch.command();
        if background {
            cmd.arg("--background");
        }
        cmd.stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::inherit());
        tree::configure(&mut cmd);
        let mut child = cmd.spawn().map_err(|e| format!("couldn't start {}: {e}", launch.describe()))?;
        let tree = tree::Tree::adopt(&child);
        let stdout = child.stdout.take().expect("piped stdout");
        *self.stdin.lock().unwrap() = child.stdin.take();
        *self.tree.lock().unwrap() = tree;
        *self.child.lock().unwrap() = Some(child);
        Ok(stdout)
    }

    /// Whether the backend we started still runs (it exits at once when it
    /// attached to another MellowDLP).
    pub fn is_alive(&self) -> bool {
        self.child.lock().unwrap().as_mut().is_some_and(|child| matches!(child.try_wait(), Ok(None)))
    }

    /// One line to the backend's stdin (a command, channel::command).
    pub fn send(&self, line: &str) {
        let mut stdin = self.stdin.lock().unwrap();
        if let Some(pipe) = stdin.as_mut() {
            if let Err(e) = pipe.write_all(format!("{line}\n").as_bytes()).and_then(|_| pipe.flush()) {
                eprintln!("MellowDLP shell: couldn't reach the backend: {e}");
            }
        }
    }

    /// Ask the backend to exit (stdin EOF), then kill whatever is left.
    pub fn shut_down(&self) {
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

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    /// A resource folder with (or without) a backend exe in it (one per call:
    /// the tests run in parallel)
    fn resources(with_backend: bool) -> PathBuf {
        static N: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);
        let dir = std::env::temp_dir().join(format!(
            "mellow-shell-test-{}-{}",
            std::process::id(),
            N.fetch_add(1, std::sync::atomic::Ordering::SeqCst)
        ));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(dir.join(BACKEND_DIR)).unwrap();
        if with_backend {
            std::fs::write(bundled_exe(&dir), b"").unwrap();
        }
        dir
    }

    fn env(pairs: &[(&str, &str)]) -> impl Fn(&str) -> Option<OsString> {
        let map: HashMap<String, OsString> = pairs.iter().map(|(k, v)| (k.to_string(), OsString::from(v))).collect();
        move |name| map.get(name).cloned()
    }

    fn checkout() -> PathBuf {
        PathBuf::from("/src/mellow")
    }

    #[test]
    fn the_installed_app_runs_the_bundled_backend() {
        let res = resources(true);
        assert_eq!(Launch::resolve(env(&[]), Some(&res), &checkout()), Launch::Packaged { exe: bundled_exe(&res) });
    }

    #[test]
    fn without_a_bundled_backend_it_runs_from_source() {
        let res = resources(false);
        let python = if cfg!(windows) { "python" } else { "python3" };
        for resources in [Some(res.as_path()), None] {
            assert_eq!(
                Launch::resolve(env(&[]), resources, &checkout()),
                Launch::Source { python: python.into(), root: checkout() }
            );
        }
    }

    #[test]
    fn mellow_backend_names_the_exe() {
        let res = resources(true);
        let wanted = Launch::Packaged { exe: PathBuf::from("/builds/dist/MellowDLP-backend/mellowdlp-backend") };
        for vars in [
            &[("MELLOW_BACKEND", "/builds/dist/MellowDLP-backend/mellowdlp-backend")][..],
            // it wins over the source variables too
            &[("MELLOW_BACKEND", "/builds/dist/MellowDLP-backend/mellowdlp-backend"), ("MELLOW_ROOT", "/x")][..],
        ] {
            assert_eq!(Launch::resolve(env(vars), Some(&res), &checkout()), wanted);
        }
    }

    #[test]
    fn the_source_variables_win_over_the_bundle() {
        let res = resources(true);
        assert_eq!(
            Launch::resolve(env(&[("MELLOW_ROOT", "/work/mellow")]), Some(&res), &checkout()),
            Launch::Source {
                python: if cfg!(windows) { "python" } else { "python3" }.into(),
                root: PathBuf::from("/work/mellow")
            }
        );
        assert_eq!(
            Launch::resolve(env(&[("MELLOW_PYTHON", "/venv/bin/python")]), Some(&res), &checkout()),
            Launch::Source { python: "/venv/bin/python".into(), root: checkout() }
        );
    }

    #[test]
    fn empty_variables_count_as_unset() {
        let res = resources(true);
        let vars = [("MELLOW_BACKEND", ""), ("MELLOW_ROOT", ""), ("MELLOW_PYTHON", "")];
        assert_eq!(Launch::resolve(env(&vars), Some(&res), &checkout()), Launch::Packaged { exe: bundled_exe(&res) });
    }

    #[test]
    fn the_backend_is_told_it_serves_a_tauri_window() {
        for launch in [
            Launch::Packaged { exe: PathBuf::from("/opt/backend/mellowdlp-backend") },
            Launch::Source { python: "python3".into(), root: checkout() },
        ] {
            let cmd = launch.command();
            let args: Vec<_> = cmd.get_args().map(|a| a.to_string_lossy().into_owned()).collect();
            assert_eq!(args.last().map(String::as_str), Some("--shell"), "{launch:?}");
            let envs: Vec<_> = cmd.get_envs().collect();
            let wanted = (std::ffi::OsStr::new(SHELL_ENV.0), Some(std::ffi::OsStr::new(SHELL_ENV.1)));
            assert!(envs.contains(&wanted), "{launch:?}");
        }
    }

    #[test]
    fn a_packaged_backend_runs_in_its_own_folder() {
        let cmd = Launch::Packaged { exe: PathBuf::from("/opt/backend/mellowdlp-backend") }.command();
        assert_eq!(cmd.get_current_dir(), Some(Path::new("/opt/backend")));
        let cmd = Launch::Source { python: "python3".into(), root: checkout() }.command();
        assert_eq!(cmd.get_current_dir(), Some(checkout().as_path()));
    }
}
