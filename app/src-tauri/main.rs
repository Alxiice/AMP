#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::Manager;
use std::sync::{Arc, Mutex};
use tauri::api::webview::WebviewUrl;

// State to hold authentication results
#[derive(Debug, Clone)]
struct AuthState {
    cookies: Option<String>,
    is_authenticated: bool,
}

impl AuthState {
    fn new() -> Self {
        Self {
            cookies: None,
            is_authenticated: false,
        }
    }
}

// Define custom commands
#[tauri::command]
async fn start_youtube_auth(
    state: tauri::State<'_, Arc<Mutex<AuthState>>>,
    window: tauri::Window,
) -> Result<(), String> {
    let youtube_url = "https://music.youtube.com";
    
    // Open YouTube Music in the default browser
    // We'll use the shell plugin to open the browser
    // In Tauri 2.0, we need to use the shell command
    
    // For now, just open in external browser
    // The user will need to manually copy cookies
    // In the future, we can implement a more automated solution
    
    // Update state
    {
        let mut state_lock = state.lock().unwrap();
        state_lock.is_authenticated = false;
    }
    
    // Open browser using shell command
    let _ = window.eval(&format!("window.open('{}', '_blank')", youtube_url));
    
    Ok(())
}

#[tauri::command]
async fn complete_auth_with_cookies(
    state: tauri::State<'_, Arc<Mutex<AuthState>>>,
    cookies: String,
) -> Result<(), String> {
    let mut state_lock = state.lock().unwrap();
    state_lock.cookies = Some(cookies);
    state_lock.is_authenticated = true;
    Ok(())
}

#[tauri::command]
async fn get_auth_status(
    state: tauri::State<'_, Arc<Mutex<AuthState>>>,
) -> Result<AuthState, String> {
    let state_lock = state.lock().unwrap();
    Ok(state_lock.clone())
}

#[tauri::command]
async fn save_cookies_to_file(
    cookies: String,
    path: Option<String>,
) -> Result<String, String> {
    use std::fs;
    use std::path::Path;
    
    let save_path = if let Some(p) = path {
        Path::new(&p)
    } else {
        // Default path
        let mut path = std::env::current_dir().unwrap();
        path.push(".amp");
        path.push("cache");
        fs::create_dir_all(&path).map_err(|e| e.to_string())?;
        path.push("cookies.json");
        path
    };
    
    fs::write(&save_path, cookies).map_err(|e| e.to_string())?;
    
    Ok(save_path.to_string_lossy().into_owned())
}

fn main() {
    // Initialize shared state
    let auth_state = Arc::new(Mutex::new(AuthState::new()));
    
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_http::init())
        .manage(auth_state)
        .invoke_handler(tauri::generate_handler![
            start_youtube_auth,
            complete_auth_with_cookies,
            get_auth_status,
            save_cookies_to_file,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
