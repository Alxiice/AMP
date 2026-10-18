#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod wsl_detect;
mod youtube_login;

use tauri::Manager;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_http::init())
        .invoke_handler(tauri::generate_handler![
            youtube_login::youtube_login,
            wsl_detect::get_wsl_host_ip,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
