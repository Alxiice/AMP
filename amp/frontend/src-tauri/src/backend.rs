//! Owns the Python backend (Phase 6): spawned in `setup`, stopped on `RunEvent::Exit`.
//!
//! Dev builds run `python -m backend.main` from the venv (or `AMP_PYTHON`); release builds
//! run the PyInstaller sidecar `amp-backend`. The backend gets a free port (or `AMP_PORT`),
//! the app data dir and `--parent-watch`: it exits when our end of its stdin pipe closes,
//! which also covers the app being killed. The frontend asks `backend_info` for the port
//! and never spawns anything itself (no `shell:*` permission in JS).

use std::collections::VecDeque;
use std::ffi::OsString;
use std::net::TcpListener;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager, Runtime, State};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

const MAX_LOG_LINES: usize = 1000;
// How long a backend gets to exit on its own after "exit" before it is killed.
const EXIT_GRACE: Duration = Duration::from_secs(2);

#[derive(Clone, Serialize)]
pub struct BackendInfo {
    port: u16,
    // Per-launch token (plan 5.6) is not generated yet: the backend runs in open mode.
    token: Option<String>,
}

#[derive(Clone, Serialize)]
struct StatusEvent {
    state: &'static str,
    code: Option<i32>,
}

struct Running {
    child: CommandChild,
    exited: Arc<AtomicBool>,
}

#[derive(Default)]
pub struct BackendState {
    running: Option<Running>,
    generation: u64, // events of a replaced backend must not change the status of the new one
    info: Option<BackendInfo>,
    error: Option<String>,
    logs: VecDeque<String>,
}

pub type Backend = Mutex<BackendState>;

/// Spawn the backend; failures are stored for `backend_info` and shown on the Logs page.
pub fn start<R: Runtime>(app: &AppHandle<R>) {
    if let Err(e) = spawn(app) {
        push_log(app, format!("Failed to start backend: {e}"));
        let state = app.state::<Backend>();
        let mut s = state.lock().unwrap();
        s.info = None;
        s.error = Some(e);
    }
}

/// Ask the backend to exit, then kill it (and its process tree) if it is still alive.
pub fn stop<R: Runtime>(app: &AppHandle<R>) {
    let running = {
        let state = app.state::<Backend>();
        let mut s = state.lock().unwrap();
        s.generation += 1;
        s.info = None;
        s.running.take()
    };
    let Some(Running { mut child, exited }) = running else { return };

    let _ = child.write(b"exit\n");
    let deadline = Instant::now() + EXIT_GRACE;
    while !exited.load(Ordering::SeqCst) && Instant::now() < deadline {
        std::thread::sleep(Duration::from_millis(50));
    }
    if !exited.load(Ordering::SeqCst) {
        push_log(app, "Backend did not exit in time; killing it".into());
    }
    // Also needed after a clean exit: the job object may still hold a PyInstaller/venv child.
    let _ = child.kill();
}

fn spawn<R: Runtime>(app: &AppHandle<R>) -> Result<BackendInfo, String> {
    let port = pick_port()?;
    let data_dir = app.path().app_data_dir().map_err(|e| format!("no app data dir: {e}"))?;
    std::fs::create_dir_all(&data_dir).map_err(|e| format!("cannot create {}: {e}", data_dir.display()))?;

    let args: Vec<OsString> = vec![
        "--host".into(),
        "127.0.0.1".into(),
        "--port".into(),
        port.to_string().into(),
        "--data-dir".into(),
        data_dir.clone().into_os_string(),
        "--parent-watch".into(),
    ];
    let command = backend_command(app)?
        .args(args)
        // P7: the backend writes UTF-8 whatever the console code page; lines are decoded lossily below
        .env("PYTHONIOENCODING", "utf-8")
        .env("PYTHONUNBUFFERED", "1")
        // Job object / process group: the venv launcher and the PyInstaller bootloader both
        // start a second process, which kill() must take down too.
        .set_process_group(true);
    let (mut rx, child) = command.spawn().map_err(|e| format!("spawn failed: {e}"))?;

    let info = BackendInfo { port, token: None };
    let exited = Arc::new(AtomicBool::new(false));
    let generation = {
        let state = app.state::<Backend>();
        let mut s = state.lock().unwrap();
        s.generation += 1;
        s.running = Some(Running { child, exited: exited.clone() });
        s.info = Some(info.clone());
        s.error = None;
        s.generation
    };
    push_log(app, format!("Backend spawned on port {port}, data dir {}", data_dir.display()));

    let app = app.clone();
    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(bytes) | CommandEvent::Stderr(bytes) => {
                    push_log(&app, String::from_utf8_lossy(&bytes).trim_end().to_string());
                }
                CommandEvent::Error(e) => push_log(&app, format!("Backend error: {e}")),
                CommandEvent::Terminated(payload) => {
                    exited.store(true, Ordering::SeqCst);
                    push_log(&app, format!("Backend exited with code {:?}", payload.code));
                    let current = {
                        let state = app.state::<Backend>();
                        let mut s = state.lock().unwrap();
                        let current = s.generation == generation;
                        if current {
                            s.running = None;
                            s.info = None;
                            s.error = Some(format!("backend exited with code {:?}", payload.code));
                        }
                        current
                    };
                    if current {
                        let _ = app.emit("backend-status", StatusEvent { state: "stopped", code: payload.code });
                    }
                }
                _ => {}
            }
        }
    });
    Ok(info)
}

#[cfg(debug_assertions)]
fn backend_command<R: Runtime>(app: &AppHandle<R>) -> Result<tauri_plugin_shell::process::Command, String> {
    use std::path::PathBuf;
    // src-tauri/ -> frontend/ -> amp/
    let amp_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("..");
    let python = match std::env::var_os("AMP_PYTHON") {
        Some(p) => PathBuf::from(p),
        None if cfg!(windows) => amp_dir.join("venv").join("Scripts").join("python.exe"),
        None => amp_dir.join("venv").join("bin").join("python"),
    };
    if !python.exists() {
        return Err(format!(
            "Python not found at {}: create amp/venv (see README) or set AMP_PYTHON",
            python.display()
        ));
    }
    Ok(app.shell().command(python).args(["-m", "backend.main"]).current_dir(amp_dir))
}

#[cfg(not(debug_assertions))]
fn backend_command<R: Runtime>(app: &AppHandle<R>) -> Result<tauri_plugin_shell::process::Command, String> {
    app.shell().sidecar("amp-backend").map_err(|e| format!("sidecar amp-backend: {e}"))
}

/// `AMP_PORT` if set (fixed URLs for dev tools), else a port the OS reports free right now.
fn pick_port() -> Result<u16, String> {
    if let Some(port) = std::env::var("AMP_PORT").ok().filter(|p| !p.is_empty()) {
        return port.parse().map_err(|_| format!("AMP_PORT is not a port number: {port}"));
    }
    free_port()
}

fn free_port() -> Result<u16, String> {
    let listener = TcpListener::bind("127.0.0.1:0").map_err(|e| format!("no free port: {e}"))?;
    listener.local_addr().map(|a| a.port()).map_err(|e| e.to_string())
}

fn push_log<R: Runtime>(app: &AppHandle<R>, line: String) {
    {
        let state = app.state::<Backend>();
        let mut s = state.lock().unwrap();
        if s.logs.len() == MAX_LOG_LINES {
            s.logs.pop_front();
        }
        s.logs.push_back(line.clone());
    }
    let _ = app.emit("backend-log", line);
}

// --- Commands ---

#[tauri::command]
pub fn backend_info(state: State<'_, Backend>) -> Result<BackendInfo, String> {
    let s = state.lock().unwrap();
    s.info.clone().ok_or_else(|| s.error.clone().unwrap_or_else(|| "backend not started".into()))
}

/// Lines logged before the frontend subscribed to `backend-log` (startup errors included).
#[tauri::command]
pub fn backend_logs(state: State<'_, Backend>) -> Vec<String> {
    state.lock().unwrap().logs.iter().cloned().collect()
}

#[tauri::command]
pub async fn restart_backend<R: Runtime>(app: AppHandle<R>) -> Result<BackendInfo, String> {
    tauri::async_runtime::spawn_blocking(move || {
        stop(&app);
        start(&app);
        let state = app.state::<Backend>();
        let s = state.lock().unwrap();
        s.info.clone().ok_or_else(|| s.error.clone().unwrap_or_else(|| "backend not started".into()))
    })
    .await
    .map_err(|e| e.to_string())?
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn free_port_is_bindable() {
        let port = free_port().unwrap();
        assert!(port > 0);
        TcpListener::bind(("127.0.0.1", port)).expect("picked port should be bindable");
    }
}
