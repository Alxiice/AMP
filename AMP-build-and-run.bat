@echo off
rem Rebuilds AMP into build\ if the code changed since the last build, then starts it.
rem Double-click or run from a terminal. Needs the venv in amp\venv (see README).
pushd "%~dp0amp"
if not exist venv\Scripts\python.exe (
  echo amp\venv not found: create it first, see README.md "Launch the app".
  pause
  exit /b 1
)
venv\Scripts\python.exe scripts\build_release.py --run
if errorlevel 1 pause
popd
