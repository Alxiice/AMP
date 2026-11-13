@echo off
rem Starts the AMP desktop app in dev mode (npm run tauri dev). Double-click or run from a terminal.
pushd "%~dp0amp\frontend"
if not exist node_modules call npm install
call npm run tauri dev
if errorlevel 1 pause
popd
