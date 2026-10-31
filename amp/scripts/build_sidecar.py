"""Build the backend sidecar and put it where Tauri looks for it.

    python scripts/build_sidecar.py [--skip-pyinstaller] [--smoke]

1. pyinstaller amp-backend.spec --noconfirm   → dist/amp-backend[.exe]
2. target triple from `rustc -vV` (host: line)
3. copy to frontend/src-tauri/binaries/amp-backend-<triple>[.exe] (tauri.conf.json externalBin)

--smoke starts the copied binary on a free port with a scratch data dir, checks /api/health
and a search, then closes its stdin (--parent-watch) and checks that it exits.
Used by CI (.github/workflows/tauri-build.yml) and by hand. Run with the venv's python.
"""

from __future__ import annotations

import argparse
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

AMP_DIR = Path(__file__).resolve().parent.parent
BINARIES_DIR = AMP_DIR / "frontend" / "src-tauri" / "binaries"
EXE = ".exe" if sys.platform == "win32" else ""


def target_triple() -> str:
    out = subprocess.run(["rustc", "-vV"], capture_output=True, text=True, check=True).stdout
    for line in out.splitlines():
        if line.startswith("host:"):
            return line.split(":", 1)[1].strip()
    raise SystemExit("rustc -vV printed no host: line")


def build() -> Path:
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "amp-backend.spec"],
                   cwd=AMP_DIR, check=True)
    built = AMP_DIR / "dist" / f"amp-backend{EXE}"
    if not built.exists():
        raise SystemExit(f"PyInstaller produced no {built}")
    return built


def install(built: Path) -> Path:
    BINARIES_DIR.mkdir(parents=True, exist_ok=True)
    dest = BINARIES_DIR / f"amp-backend-{target_triple()}{EXE}"
    shutil.copy2(built, dest)
    print(f"Sidecar: {dest} ({dest.stat().st_size / 1e6:.1f} MB)")
    return dest


def _get(url: str, timeout: float = 30) -> dict | list:
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 — loopback only
        return json.loads(resp.read().decode("utf-8"))


def smoke(binary: Path) -> None:
    """Start the binary like Tauri does; health + search; stdin EOF → exits."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="amp-smoke-") as data_dir:
        proc = subprocess.Popen(
            [str(binary), "--port", str(port), "--data-dir", data_dir, "--parent-watch"],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            base = f"http://127.0.0.1:{port}"
            deadline = time.monotonic() + 90  # one-file binaries unpack themselves first
            health = None
            while time.monotonic() < deadline and proc.poll() is None:
                try:
                    health = _get(f"{base}/api/health", timeout=2)
                    break
                except OSError:
                    time.sleep(0.5)
            if health is None:
                raise SystemExit(f"smoke: no /api/health (exit code {proc.poll()}); see {data_dir}/logs/app.log")
            print(f"smoke: health {health['services']['extractor']}")
            if not health["services"]["extractor"].get("yt_dlp"):
                raise SystemExit("smoke: yt-dlp missing from the binary")

            results = _get(f"{base}/api/search?q=daft%20punk&type=songs&limit=3")
            print(f"smoke: search returned {len(results)} songs")
            if not results:
                raise SystemExit("smoke: search returned nothing")

            proc.stdin.close()
            proc.wait(timeout=10)
            print(f"smoke: exited with code {proc.returncode} after stdin EOF")
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--skip-pyinstaller", action="store_true", help="reuse dist/amp-backend[.exe]")
    parser.add_argument("--smoke", action="store_true", help="run the binary and check health + search")
    args = parser.parse_args()

    built = AMP_DIR / "dist" / f"amp-backend{EXE}" if args.skip_pyinstaller else build()
    dest = install(built)
    if args.smoke:
        smoke(dest)


if __name__ == "__main__":
    main()
