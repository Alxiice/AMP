// AMP v2 — Tauri v2 entry point
// The backend is spawned and owned by the backend module (Rust), never by the frontend.
// YouTube login is handled by the youtube_login module.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod backend;
mod youtube_login;

use tauri::{Manager, RunEvent};

fn main() {
    let app = tauri::Builder::default()
        // One instance: two backends sharing one data dir would each own the same segment cache.
        // Launching again focuses the running window instead. Must be the first plugin.
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.unminimize();
                let _ = window.set_focus();
            }
        }))
        .plugin(tauri_plugin_shell::init())
        .manage(backend::Backend::default())
        .setup(|app| {
            backend::start(app.handle());
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            youtube_login::youtube_login,
            backend::backend_info,
            backend::backend_logs,
            backend::restart_backend,
        ])
        .build(tauri::generate_context!())
        .expect("error while building AMP v2");

    app.run(|app, event| {
        if let RunEvent::Exit = event {
            backend::stop(app);
        }
    });
}
