# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the AMP v2 backend sidecar binary.

Build:
    pip install pyinstaller
    pyinstaller amp-backend.spec

Output: dist/amp-backend(.exe) — placed into frontend/src-tauri/binaries/
"""

import sys
from pathlib import Path

block_cipher = None

# Project root (amp/)
project_root = Path(SPECPATH)

a = Analysis(
    [str(project_root / "backend" / "main.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        # Include package data if any
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
        # Backend modules
        "backend",
        "backend.config",
        "backend.main",
        "backend.api",
        "backend.api.server",
        "backend.api.endpoints",
        "backend.api.auth_routes",
        "backend.services",
        "backend.services.auth",
        "backend.services.youtube",
        "backend.services.extractor",
        "backend.services.streaming",
        "backend.services.streaming.service",
        "backend.services.streaming.registry",
        "backend.services.streaming.downloader",
        "backend.services.streaming.cache",
        "backend.services.streaming.serving",
        "backend.services.streaming.playback",
        "backend.database",
        "backend.database.models",
        "backend.database.session",
        "backend.utils",
        "backend.utils.logger",
        "backend.utils.layout",
        "backend.utils.mp4",
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
    console=False,  # No console window in production
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
