//! Detect the Windows host IP when running inside WSL2.
//!
//! In WSL2, the Windows host is reachable via the gateway IP, which is the
//! first nameserver in /etc/resolv.conf. The frontend uses this to reach a
//! backend running on the Windows host (e.g. `python amp/backend/main.py`).

use std::fs;

/// Returns the WSL2 gateway IP (Windows host) as a string, or None if not in WSL2.
#[tauri::command]
pub fn get_wsl_host_ip() -> Option<String> {
    // Quick check: WSL2 sets this env var.
    let is_wsl = std::env::var("WSL_DISTRO_NAME").is_ok()
        || std::env::var("WSL_INTEROP").is_ok();
    if !is_wsl {
        return None;
    }

    // Read /etc/resolv.conf and extract the first nameserver.
    let content = fs::read_to_string("/etc/resolv.conf").ok()?;
    for line in content.lines() {
        let line = line.trim();
        if let Some(rest) = line.strip_prefix("nameserver") {
            let ip = rest.trim();
            if !ip.is_empty() {
                return Some(ip.to_string());
            }
        }
    }
    None
}
