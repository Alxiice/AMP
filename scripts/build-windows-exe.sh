#!/usr/bin/env bash
# Build a clean Windows .exe for AMP from WSL2.
#
# Usage (in WSL2 terminal):
#   bash scripts/build-windows-exe.sh
#
# Output:
#   build/windows/AMP.exe          - The executable
#   build/windows/WebView2Loader.dll - Required runtime DLL
#
# Requirements (one-time setup):
#   sudo apt install -y mingw-w64
#   rustup target add x86_64-pc-windows-gnu

set -euo pipefail

# Resolve project root (script is in scripts/, project root is one level up)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

APP_DIR="$PROJECT_ROOT/app"
SRC_TAURI="$APP_DIR/src-tauri"
DIST_DIR="$PROJECT_ROOT/dist"
TARGET_TRIPLE="x86_64-pc-windows-gnu"
BUILD_DIR="/tmp/amp-build"
OUTPUT_DIR="$PROJECT_ROOT/build/windows"

echo "=== AMP Windows Build ==="
echo "Project root: $PROJECT_ROOT"
echo ""

# --- Step 1: Check prerequisites ---
echo "--- Step 1: Checking prerequisites ---"

if ! command -v cargo &>/dev/null; then
    echo "ERROR: Rust/cargo not found. Install: https://rustup.rs/"
    exit 1
fi

if ! rustup target list --installed | grep -q "$TARGET_TRIPLE"; then
    echo "Adding Rust target: $TARGET_TRIPLE"
    rustup target add "$TARGET_TRIPLE"
fi

if ! command -v x86_64-w64-mingw32-gcc &>/dev/null; then
    echo "ERROR: mingw-w64 not found. Install: sudo apt install -y mingw-w64"
    exit 1
fi

echo "Prerequisites OK"
echo ""

# --- Step 2: Build frontend ---
echo "--- Step 2: Building frontend ---"
cd "$APP_DIR"
if [ ! -d node_modules ]; then
    echo "Installing npm dependencies..."
    npm install
fi
npm run build
echo "Frontend built at: $DIST_DIR"
echo ""

# --- Step 3: Cross-compile Rust/Tauri ---
echo "--- Step 3: Cross-compiling Windows .exe ---"
echo "Target dir: $BUILD_DIR (WSL2 filesystem, avoids /mnt/e permission issues)"
export CARGO_TARGET_DIR="$BUILD_DIR"

cd "$SRC_TAURI"
cargo build --target "$TARGET_TRIPLE" --release

EXE_PATH="$BUILD_DIR/$TARGET_TRIPLE/release/app.exe"
if [ ! -f "$EXE_PATH" ]; then
    echo "ERROR: Build failed — $EXE_PATH not found"
    exit 1
fi
echo "Build succeeded: $EXE_PATH"
echo ""

# --- Step 4: Create clean release folder ---
echo "--- Step 4: Creating clean release folder ---"
rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

# Copy the exe
cp "$EXE_PATH" "$OUTPUT_DIR/AMP.exe"

# Copy WebView2Loader.dll (required at runtime)
WEBVIEW2_DLL="$BUILD_DIR/$TARGET_TRIPLE/release/WebView2Loader.dll"
if [ -f "$WEBVIEW2_DLL" ]; then
    cp "$WEBVIEW2_DLL" "$OUTPUT_DIR/WebView2Loader.dll"
    echo "Copied WebView2Loader.dll"
else
    echo "WARNING: WebView2Loader.dll not found in build output."
    echo "The exe may need it at runtime. Download from:"
    echo "https://developer.microsoft.com/en-us/microsoft-edge/webview2/"
fi

# Copy icons (optional, for shortcuts)
if [ -d "$SRC_TAURI/icons" ]; then
    cp -r "$SRC_TAURI/icons" "$OUTPUT_DIR/icons" 2>/dev/null || true
fi

# Create a README in the build folder
cat > "$OUTPUT_DIR/README.txt" << 'EOF'
AMP - Another Music Player
==========================

Files:
  AMP.exe              - The application
  WebView2Loader.dll   - Required runtime library (WebView2)
  icons/               - App icons (optional)

Requirements:
  - Windows 10/11 with WebView2 runtime
    (pre-installed on Windows 11, download for Windows 10:
     https://developer.microsoft.com/en-us/microsoft-edge/webview2/)

Running:
  1. Start the backend:
       python amp/backend/main.py
  2. Double-click AMP.exe
  3. The app connects to http://127.0.0.1:8000 automatically

Sign-in:
  Click "Connect YouTube Music" — a sign-in window opens.
  Sign in with any Google account. The window closes automatically.
EOF

echo ""
echo "=== Build Complete ==="
echo "Release folder: $OUTPUT_DIR"
echo ""
ls -lh "$OUTPUT_DIR"
echo ""
echo "To run on Windows:"
echo "  1. Copy the '$OUTPUT_DIR' folder to your Windows machine"
echo "  2. Start the backend: python amp/backend/main.py"
echo "  3. Double-click AMP.exe"
