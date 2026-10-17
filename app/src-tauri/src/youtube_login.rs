//! "Connect YouTube Music": opens a normal Google sign-in page in a Tauri window,
//! waits until the user is signed in, then returns the session cookies to the frontend.
//! The user never copies anything.
//!
//! Requires tauri >= 2.4 (Webview::cookies_for_url) and in Cargo.toml:
//!   tokio = { version = "1", features = ["time"] }
//!
//! NOTE: written against the Tauri 2 API but NOT compiled here - run `cargo check`.

use std::time::{Duration, Instant};

use serde::Serialize;
use tauri::{AppHandle, Manager, Url, WebviewUrl, WebviewWindowBuilder};

const WINDOW_LABEL: &str = "ytm-login";
// Sign in to Google, then land on YouTube Music so the youtube.com cookies get set.
const LOGIN_URL: &str =
    "https://accounts.google.com/ServiceLogin?service=youtube&continue=https%3A%2F%2Fmusic.youtube.com%2F";
const COOKIE_URL: &str = "https://music.youtube.com/";
const SESSION_COOKIE: &str = "__Secure-3PAPISID";
// Google sometimes refuses sign-in from "embedded browsers" it can identify by user agent.
// A plain desktop Chrome UA avoids most of that. Keep it roughly current.
const USER_AGENT: &str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 \
(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36";

#[derive(Serialize)]
pub struct CookieDto {
    name: String,
    value: String,
    domain: Option<String>,
}

// Must be `async`: on Windows, reading webview cookies from a sync command deadlocks.
#[tauri::command]
pub async fn youtube_login(app: AppHandle) -> Result<Vec<CookieDto>, String> {
    // Close a previous attempt if the user clicked "Connect" twice.
    if let Some(old) = app.get_webview_window(WINDOW_LABEL) {
        let _ = old.close();
    }

    let url: Url = LOGIN_URL.parse().map_err(|e| format!("{e}"))?;
    let win = WebviewWindowBuilder::new(&app, WINDOW_LABEL, WebviewUrl::External(url))
        .title("Sign in to YouTube Music")
        .inner_size(480.0, 760.0)
        .center()
        .user_agent(USER_AGENT)
        // .incognito(true)  // enable if you want every sign-in to start clean ("switch account")
        .build()
        .map_err(|e| e.to_string())?;

    let cookie_url: Url = COOKIE_URL.parse().map_err(|e| format!("{e}"))?;
    let deadline = Instant::now() + Duration::from_secs(10 * 60);

    loop {
        tokio::time::sleep(Duration::from_millis(800)).await;

        // Window gone => the user closed it.
        if app.get_webview_window(WINDOW_LABEL).is_none() {
            return Err("cancelled".into());
        }
        if Instant::now() > deadline {
            let _ = win.close();
            return Err("timeout".into());
        }

        let cookies = match win.cookies_for_url(cookie_url.clone()) {
            Ok(c) => c,
            Err(_) => continue, // webview not ready yet
        };
        if !cookies.iter().any(|c| c.name() == SESSION_COOKIE) {
            continue; // still on the login pages
        }

        // Signed in. Give the redirect chain a moment to finish setting the rest, then re-read.
        tokio::time::sleep(Duration::from_millis(1500)).await;
        let cookies = win.cookies_for_url(cookie_url.clone()).map_err(|e| e.to_string())?;
        let out = cookies
            .iter()
            .map(|c| CookieDto {
                name: c.name().to_string(),
                value: c.value().to_string(),
                domain: c.domain().map(|d| d.to_string()),
            })
            .collect();
        let _ = win.close();
        return Ok(out);
    }
}

// In main.rs:
//   mod youtube_login;
//   tauri::Builder::default()
//       .invoke_handler(tauri::generate_handler![youtube_login::youtube_login])
