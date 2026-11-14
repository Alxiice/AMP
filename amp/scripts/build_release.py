"""Build AMP for this machine and collect the results in <repo>/build/.

    python scripts/build_release.py [--exe-only] [--bundles LIST] [--skip-sidecar] [--smoke]

1. build_sidecar.py (PyInstaller backend → frontend/src-tauri/binaries/), unless --skip-sidecar
2. npm ci if node_modules is missing
3. npx tauri build (--no-bundle with --exe-only, --bundles LIST otherwise when given)
4. copy into build/:
     build/AMP-<version>-<os>-<arch>/   the executable and the backend next to it (portable)
     build/AMP-<version>-<os>-<arch>.zip (.tar.gz on Linux/macOS)
     build/installers/                  .msi, -setup.exe, .deb, .AppImage, .dmg…

Run it with the venv's python from amp/. Tauri can only build for the OS it runs on, so the other
platforms come from CI (.github/workflows/release.yml), which runs this same script.
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

AMP_DIR = Path(__file__).resolve().parent.parent
REPO = AMP_DIR.parent
FRONTEND = AMP_DIR / "frontend"
TAURI = FRONTEND / "src-tauri"
RELEASE = TAURI / "target" / "release"
OUT = REPO / "build"
EXE = ".exe" if sys.platform == "win32" else ""
NPX = "npx.cmd" if sys.platform == "win32" else "npx"
NPM = "npm.cmd" if sys.platform == "win32" else "npm"

# Installer files Tauri writes under target/release/bundle/<kind>/
INSTALLER_PATTERNS = ["msi/*.msi", "nsis/*.exe", "deb/*.deb", "rpm/*.rpm", "appimage/*.AppImage", "dmg/*.dmg"]


def os_name() -> str:
    return {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")


def arch() -> str:
    machine = platform.machine().lower()
    return {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(machine, machine)


def run(cmd: list[str], cwd: Path) -> None:
    print(f"\n> {' '.join(cmd)}  (in {cwd})", flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def collect_portable(version: str) -> Path:
    """The executable and the sidecar Tauri copied next to it, in a folder and an archive."""
    name = f"AMP-{version}-{os_name()}-{arch()}"
    folder = OUT / name
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    # The app looks for the backend next to its own executable, under this exact name
    for src_name, dest_name in ((f"amp{EXE}", f"AMP{EXE}"), (f"amp-backend{EXE}", f"amp-backend{EXE}")):
        src = RELEASE / src_name
        if not src.exists():
            raise SystemExit(f"tauri build produced no {src}")
        shutil.copy2(src, folder / dest_name)
    for doc in ("LICENSE", "README.md"):
        if (REPO / doc).exists():
            shutil.copy2(REPO / doc, folder / doc)
    archive = shutil.make_archive(str(folder), "zip" if sys.platform == "win32" else "gztar", OUT, name)
    print(f"Portable: {folder}\n          {archive}")
    return folder


def collect_installers() -> list[Path]:
    dest = OUT / "installers"
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    copied = []
    for pattern in INSTALLER_PATTERNS:
        for src in (RELEASE / "bundle").glob(pattern):
            shutil.copy2(src, dest / src.name)
            copied.append(dest / src.name)
            print(f"Installer: {dest / src.name}")
    return copied


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--exe-only", action="store_true", help="build the executable, no installers")
    parser.add_argument("--bundles", help="installer kinds for tauri build, e.g. deb,appimage or msi,nsis")
    parser.add_argument("--skip-sidecar", action="store_true", help="reuse the sidecar already in binaries/")
    parser.add_argument("--smoke", action="store_true", help="smoke-test the sidecar after building it")
    args = parser.parse_args()

    version = json.loads((TAURI / "tauri.conf.json").read_text(encoding="utf-8"))["version"]

    if not args.skip_sidecar:
        cmd = [sys.executable, "scripts/build_sidecar.py"] + (["--smoke"] if args.smoke else [])
        run(cmd, AMP_DIR)
    if not (FRONTEND / "node_modules").exists():
        run([NPM, "ci"], FRONTEND)

    tauri = [NPX, "tauri", "build"]
    if args.exe_only:
        tauri.append("--no-bundle")
    elif args.bundles:
        tauri += ["--bundles", args.bundles]
    run(tauri, FRONTEND)

    OUT.mkdir(exist_ok=True)
    collect_portable(version)
    if not args.exe_only and not collect_installers():
        raise SystemExit("tauri build produced no installer")
    print(f"\nDone: {OUT}")


if __name__ == "__main__":
    main()
