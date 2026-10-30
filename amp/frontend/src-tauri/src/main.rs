// AMP v2 — Tauri v2 entry point
// The backend is spawned as a sidecar by the frontend (sidecar.ts).
// YouTube login is handled by the youtube_login module.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod youtube_login;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![youtube_login::youtube_login])
        .run(tauri::generate_context!())
        .expect("error while running AMP v2");
}
