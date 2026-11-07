fn main() {
    // tauri_build only says "resource path ... doesn't exist" when the sidecar is missing; say how to fix it
    let target = std::env::var("TARGET").unwrap_or_default();
    let ext = if target.contains("windows") { ".exe" } else { "" };
    let sidecar = format!("binaries/amp-backend-{target}{ext}");
    if !std::path::Path::new(&sidecar).exists() {
        panic!("\n\n  Missing backend sidecar {sidecar}.\n  Build it once from amp/:  venv/Scripts/python.exe scripts/build_sidecar.py\n  (Linux/macOS: venv/bin/python scripts/build_sidecar.py)\n\n");
    }
    tauri_build::build()
}
