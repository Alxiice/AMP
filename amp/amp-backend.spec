# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the AMP v2 backend sidecar binary.

Build (and copy to frontend/src-tauri/binaries/amp-backend-<target-triple>[.exe]):
    python scripts/build_sidecar.py

Output: dist/amp-backend(.exe). Rebuild after every yt-dlp upgrade.
Node.js is not bundled: it must be on PATH at runtime (/api/health reports it).
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Project root (amp/)
project_root = Path(SPECPATH)

a = Analysis(
    [str(project_root / "backend" / "main.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        # yt-dlp's own hook (pyinstaller40 entry point) also adds these; explicit so a hook change can't drop them
        *collect_data_files("yt_dlp_ejs", includes=["**/*.js"]),  # JS challenge solver (P2)
        *collect_data_files("ytmusicapi"),  # locales/*.mo
    ],
    hiddenimports=[
        # uvicorn
        "uvicorn",
        "uvicorn.loops.auto",
        "uvicorn.loops.asyncio",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.protocols.websockets.websockets_impl",
        "uvicorn.lifespan.on",
        "uvicorn.logging",
        # FastAPI / Starlette
        "fastapi",
        "starlette",
        "starlette.routing",
        "starlette.middleware",
        "starlette.middleware.cors",
        # SQLAlchemy
        "sqlalchemy",
        "sqlalchemy.dialects.sqlite",
        "sqlalchemy.dialects.sqlite.pysqlite",
        # yt-dlp
        "yt_dlp",
        "yt_dlp.extractor",
        "yt_dlp.extractor.youtube",
        # ytmusicapi
        "ytmusicapi",
        # HTTP
        "requests",
        "urllib3",
        # pydantic
        "pydantic",
        "pydantic_settings",
        "pydantic_core",
        # Backend modules (tests excluded)
        *collect_submodules("backend", filter=lambda name: ".tests" not in name),
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy",
        "pandas",
        "PIL",
        "pytest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="amp-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    # Console subsystem: stdin/stdout/stderr must be real pipes (--parent-watch, log forwarding;
    # uvicorn's logging fails on a None stdout). Tauri spawns it with CREATE_NO_WINDOW: no window.
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
