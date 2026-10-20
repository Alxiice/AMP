#!/usr/bin/env python3
"""
Integration Test: Chunk Streaming Verification
===============================================

Standalone integration test that verifies the chunk-based streaming system
works correctly on a real YouTube Music video.

This script:
1. Starts the AMP backend server
2. Retrieves video information for the test video
3. Downloads 3 random chunks using the backend's chunk download process
4. Generates a detailed markdown report with chunk information tables
5. Displays the path to the generated report
6. Raises an exception if any step fails

Test Video: LTDxBgP0lqA (The Weeknd - Blinding Lights)

Usage:
    python integration_tests/test_chunks.py
    python integration_tests/test_chunks.py --video LTDxBgP0lqA
    python integration_tests/test_chunks.py --port 8000

Requirements:
    - Network access to YouTube
    - yt-dlp installed (in venv or PATH)
    - Python dependencies installed (fastapi, uvicorn, requests, etc.)
    - Optional: cookies.json in .amp/cache/ for authentication
"""

import argparse
import json
import os
import random
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# =============================================================================
# Configuration
# =============================================================================

PROJECT_ROOT = Path(__file__).parent.parent.absolute()
AMP_DIR = PROJECT_ROOT / "amp"
BACKEND_DIR = AMP_DIR / "backend"
VENV_PYTHON = PROJECT_ROOT / "venv" / "Scripts" / "python.exe"
CACHE_DIR = PROJECT_ROOT / ".amp" / "cache"
CHUNKS_DIR = CACHE_DIR / "chunks"
REPORTS_DIR = CACHE_DIR / "integration_reports"

DEFAULT_VIDEO_ID = "LTDxBgP0lqA"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
CHUNK_SIZE_SEC = 10
NUM_RANDOM_CHUNKS = 3
BACKEND_STARTUP_TIMEOUT = 30
HTTP_TIMEOUT = 30

REPORTS_DIR.mkdir(parents=True, exist_ok=True)


# =============================================================================
# Utility Functions
# =============================================================================

def log(msg: str, level: str = "INFO") -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{level}] {msg}")


def get_python() -> str:
    return str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable


def check_yt_dlp() -> bool:
    return shutil.which("yt-dlp") is not None or shutil.which("yt-dlp.exe") is not None


def http_get(url: str, timeout: int = HTTP_TIMEOUT) -> Tuple[int, Any]:
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {"error": str(e)}
    except Exception as e:
        return 0, {"error": str(e)}


def http_post(url: str, timeout: int = HTTP_TIMEOUT) -> Tuple[int, Any]:
    try:
        req = urllib.request.Request(url, method="POST", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {"error": str(e)}
    except Exception as e:
        return 0, {"error": str(e)}


def fmt_dur(ms: Optional[int]) -> str:
    if ms is None:
        return "N/A"
    s = ms // 1000
    return f"{s // 60}:{s % 60:02d}"


def fmt_size(b: int) -> str:
    if b < 1024:
        return f"{b} B"
    if b < 1048576:
        return f"{b / 1024:.1f} KB"
    return f"{b / 1048576:.2f} MB"


# =============================================================================
# Backend Management
# =============================================================================

class Backend:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.proc: Optional[subprocess.Popen] = None
        self.url = f"http://{host}:{port}"
        self._log_fh = None

    def start(self) -> None:
        log(f"Starting backend on {self.host}:{self.port}...")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(AMP_DIR)
        log_path = CACHE_DIR / "integration_reports" / "backend.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_fh = open(str(log_path), "w", encoding="utf-8")
        self.proc = subprocess.Popen(
            [get_python(), str(BACKEND_DIR / "main.py"), "--host", self.host, "--port", str(self.port)],
            cwd=str(AMP_DIR),
            env=env,
            stdout=self._log_fh,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        )
        log(f"Backend output -> {log_path}")
        log("Waiting for backend...")
        deadline = time.time() + BACKEND_STARTUP_TIMEOUT
        while time.time() < deadline:
            if self.proc.poll() is not None:
                self._log_fh.close()
                out = log_path.read_text(encoding="utf-8", errors="replace")
                raise RuntimeError(f"Backend died during startup.\n{out[-3000:]}")
            try:
                s, _ = http_get(f"{self.url}/api/health", timeout=5)
                if s == 200:
                    log(f"Backend ready at {self.url}")
                    return
            except Exception:
                pass
            time.sleep(0.5)
        raise RuntimeError(f"Backend did not start within {BACKEND_STARTUP_TIMEOUT}s. See log: {log_path}")

    def stop(self) -> None:
        if not self.proc:
            return
        log("Stopping backend...")
        try:
            if sys.platform == "win32":
                self.proc.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                self.proc.terminate()
            self.proc.wait(timeout=10)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        if hasattr(self, "_log_fh") and self._log_fh:
            self._log_fh.close()
        log("Backend stopped")

    def stop(self) -> None:
        if not self.proc:
            return
        log("Stopping backend...")
        try:
            if sys.platform == "win32":
                self.proc.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                self.proc.terminate()
            self.proc.wait(timeout=10)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        log("Backend stopped")


# =============================================================================
# Test Data Classes
# =============================================================================

class Step:
    def __init__(self, name: str, desc: str):
        self.name = name
        self.desc = desc
        self.status = "pending"
        self.dur: Optional[int] = None
        self.err: Optional[str] = None
        self.det: Dict[str, Any] = {}

    def ok(self, dur: int, **kw) -> None:
        self.status = "passed"
        self.dur = dur
        self.det = kw

    def bad(self, dur: int, err: str, **kw) -> None:
        self.status = "failed"
        self.dur = dur
        self.err = err
        self.det = kw

    def skip(self, reason: str) -> None:
        self.status = "skipped"
        self.err = reason


class Chunk:
    def __init__(self, idx: int, start: int, end: int):
        self.idx = idx
        self.start = start
        self.end = end
        self.status = "not_downloaded"
        self.tested = False
        self.path: Optional[str] = None
        self.size: Optional[int] = None
        self.dl_ms: Optional[int] = None
        self.err: Optional[str] = None


# =============================================================================
# Main Test Runner
# =============================================================================

class Test:
    def __init__(self, vid: str, host: str, port: int):
        self.vid = vid
        self.vurl = f"https://music.youtube.com/watch?v={vid}"
        self.be = Backend(host, port)
        self.steps: List[Step] = []
        self.chunks: List[Chunk] = []
        self.total = 0
        self.dur_ms: Optional[int] = None
        self.title: Optional[str] = None
        self.selected_indices: List[int] = []

    def add(self, name: str, desc: str) -> Step:
        s = Step(name, desc)
        self.steps.append(s)
        return s

    def run(self) -> None:
        log("=" * 70)
        log("CHUNK STREAMING INTEGRATION TEST")
        log(f"Video: {self.vid} ({self.vurl})")
        log("=" * 70)

        try:
            self._prereqs()
            self._start_be()
            self._video_info()
            self._init_chunks()
            self._dl_chunks()
            self._verify()
            self._final_chunks()
        except Exception as e:
            log(f"FATAL ERROR: {e}", "ERROR")
            raise
        finally:
            if self.be.proc:
                self.be.stop()

        rp = self._report()
        self._summary(rp)

        failed = [s for s in self.steps if s.status == "failed"]
        if failed:
            raise RuntimeError(
                f"Integration test FAILED: {len(failed)} step(s) failed: "
                + ", ".join(s.name for s in failed)
            )

    def _prereqs(self) -> None:
        s = self.add("prereqs", "Check prerequisites (yt-dlp, Python, network)")
        t = time.time()
        try:
            if not check_yt_dlp():
                s.bad(int((time.time() - t) * 1000), "yt-dlp not found in PATH")
                log("yt-dlp not found - some tests may fail", "WARN")
            else:
                log("yt-dlp found")
            log(f"Python: {sys.executable}")
            cf = CACHE_DIR / "cookies.json"
            df = CACHE_DIR / ".cookies.json"
            if cf.exists():
                log(f"Cookies found: {cf}")
            elif df.exists():
                log(f"Cookies found: {df}")
            else:
                log("No cookies file found - may hit rate limits", "WARN")
            s.ok(int((time.time() - t) * 1000), yt_dlp=check_yt_dlp())
            log("Prerequisites check passed")
        except Exception as e:
            s.bad(int((time.time() - t) * 1000), str(e))
            raise

    def _start_be(self) -> None:
        s = self.add("start_backend", "Start the AMP backend server")
        t = time.time()
        try:
            self.be.start()
            s.ok(int((time.time() - t) * 1000), url=self.be.url)
            log(f"Backend started at {self.be.url}")
        except Exception as e:
            s.bad(int((time.time() - t) * 1000), str(e))
            raise

    def _video_info(self) -> None:
        s = self.add("video_info", "Get video information (title, duration, chunks)")
        t = time.time()
        try:
            st, d = http_get(f"{self.be.url}/api/stream/info/{self.vid}", timeout=60)
            if st != 200:
                em = d.get("detail", d.get("error", f"HTTP {st}"))
                s.bad(int((time.time() - t) * 1000), em)
                log(f"Failed to get video info: {em}", "ERROR")
                raise RuntimeError(f"Failed to get video info: {em}")
            self.title = d.get("title")
            self.dur_ms = d.get("duration_ms")
            self.total = d.get("total_chunks", 0)
            log(f"Video: {self.title}")
            log(f"Duration: {fmt_dur(self.dur_ms)} ({self.dur_ms}ms)")
            log(f"Total chunks: {self.total}")
            s.ok(int((time.time() - t) * 1000), title=self.title, duration_ms=self.dur_ms, total=self.total)
        except Exception as e:
            s.bad(int((time.time() - t) * 1000), str(e))
            raise

    def _init_chunks(self) -> None:
        s = self.add("init_chunks", "Get initial chunk download status")
        t = time.time()
        try:
            st, d = http_get(f"{self.be.url}/api/stream/{self.vid}/chunks", timeout=30)
            if st != 200:
                s.bad(int((time.time() - t) * 1000), f"HTTP {st}")
                log(f"Failed to get chunk status: HTTP {st}", "WARN")
                return
            total = d.get("total_chunks", self.total)
            cs = d.get("chunk_status", {})
            for i in range(total):
                sm = i * CHUNK_SIZE_SEC * 1000
                em = sm + CHUNK_SIZE_SEC * 1000
                c = Chunk(i, sm, em)
                c.status = cs.get(str(i), cs.get(i, "not_downloaded"))
                self.chunks.append(c)
            cached = d.get("cached_count", 0)
            downloading = d.get("downloading_count", 0)
            log(f"Initial status: {cached} cached, {downloading} downloading, {total} total")
            s.ok(int((time.time() - t) * 1000), total=total, cached=cached, downloading=downloading)
        except Exception as e:
            s.bad(int((time.time() - t) * 1000), str(e))
            log(f"Failed to get initial chunk status: {e}", "WARN")

    def _dl_chunks(self) -> None:
        if self.total == 0:
            s = self.add("dl_chunks", "Download 3 random chunks")
            s.skip("No chunks to download (total_chunks=0)")
            return

        idxs = list(range(self.total))
        random.seed(42)
        sel = sorted(random.sample(idxs, min(NUM_RANDOM_CHUNKS, len(idxs))))
        self.selected_indices = sel
        log(f"Selected chunks to download: {sel}")

        s = self.add("dl_chunks", f"Download {len(sel)} random chunks: {sel}")
        t = time.time()

        # Start playback first (triggers buffering)
        try:
            st, _ = http_post(f"{self.be.url}/api/stream/{self.vid}/play", timeout=30)
            log(f"Playback started: HTTP {st}")
        except Exception as e:
            log(f"Failed to start playback: {e}", "WARN")

        res = []
        for ci in sel:
            ct = time.time()
            try:
                url = f"{self.be.url}/api/stream/{self.vid}/chunk/{ci}"
                with urllib.request.urlopen(url, timeout=60) as r:
                    data = r.read()
                dt = int((time.time() - ct) * 1000)
                c = next((x for x in self.chunks if x.idx == ci), None)
                if c:
                    c.status = "downloaded"
                    c.tested = True
                    c.dl_ms = dt
                    c.size = len(data)
                res.append({"idx": ci, "ok": True, "size": len(data), "ms": dt})
                log(f"  Chunk {ci}: downloaded {fmt_size(len(data))} in {dt}ms")
            except Exception as e:
                dt = int((time.time() - ct) * 1000)
                c = next((x for x in self.chunks if x.idx == ci), None)
                if c:
                    c.status = "error"
                    c.tested = True
                    c.err = str(e)
                    c.dl_ms = dt
                res.append({"idx": ci, "ok": False, "err": str(e), "ms": dt})
                log(f"  Chunk {ci}: FAILED - {e}", "ERROR")

        s.ok(int((time.time() - t) * 1000), chunks=res, selected=sel)

    def _verify(self) -> None:
        s = self.add("verify", "Verify chunk files exist on disk")
        t = time.time()
        try:
            sid = self.vid.replace("/", "_").replace("?", "_")
            found = 0
            if CHUNKS_DIR.exists():
                for f in CHUNKS_DIR.glob(f"{sid}_*"):
                    if "_full" not in f.name:
                        found += 1
                        # Exact match: filename is {sid}_{idx:04d}.opus
                        stem = f.stem  # e.g. "LTDxBgP0lqA_0010"
                        prefix = f"{sid}_"
                        if stem.startswith(prefix):
                            idx_str = stem[len(prefix):]
                            if idx_str.isdigit():
                                fidx = int(idx_str)
                                for c in self.chunks:
                                    if c.idx == fidx:
                                        c.path = str(f)
                                        if c.size is None:
                                            c.size = f.stat().st_size
            full = 0
            if CHUNKS_DIR.exists():
                full = len(list(CHUNKS_DIR.glob(f"{sid}_full*")))
            log(f"Found {found} chunk files on disk, {full} _full files")
            if full:
                log(f"WARNING: Found {full} _full files (should not exist!)", "WARN")
            s.ok(int((time.time() - t) * 1000), chunk_files=found, full_files=full)
        except Exception as e:
            s.bad(int((time.time() - t) * 1000), str(e))
            log(f"Failed to verify chunk files: {e}", "WARN")

    def _final_chunks(self) -> None:
        s = self.add("final_chunks", "Get final chunk download status")
        t = time.time()
        try:
            st, d = http_get(f"{self.be.url}/api/stream/{self.vid}/chunks", timeout=30)
            if st != 200:
                s.bad(int((time.time() - t) * 1000), f"HTTP {st}")
                return
            fs = d.get("chunk_status", {})
            for c in self.chunks:
                c.status = fs.get(str(c.idx), fs.get(c.idx, c.status))
            log(f"Final status: {d.get('cached_count', 0)} cached, {d.get('downloading_count', 0)} downloading")
            s.ok(int((time.time() - t) * 1000), cached=d.get("cached_count", 0))
        except Exception as e:
            s.bad(int((time.time() - t) * 1000), str(e))
            log(f"Failed to get final chunk status: {e}", "WARN")

    def _report(self) -> Path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        rp = REPORTS_DIR / f"chunk_test_{self.vid}_{ts}.md"
        L = []
        L.append("# Chunk Streaming Integration Test Report")
        L.append("")
        L.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        L.append(f"**Video ID:** `{self.vid}`")
        L.append(f"**Video URL:** {self.vurl}")
        L.append(f"**Title:** {self.title or 'N/A'}")
        L.append(f"**Duration:** {fmt_dur(self.dur_ms)} ({self.dur_ms or 0}ms)")
        L.append("")

        p = sum(1 for s in self.steps if s.status == "passed")
        f = sum(1 for s in self.steps if s.status == "failed")
        sk = sum(1 for s in self.steps if s.status == "skipped")

        L.append("## Summary")
        L.append("")
        L.append("| Metric | Value |")
        L.append("|--------|-------|")
        L.append(f"| Total Steps | {len(self.steps)} |")
        L.append(f"| Passed | {p} |")
        L.append(f"| Failed | {f} |")
        L.append(f"| Skipped | {sk} |")
        tested = [c for c in self.chunks if c.tested]
        tested_ok = [c for c in tested if c.status == "downloaded"]
        L.append(f"| Total Chunks | {self.total} |")
        L.append(f"| Chunks Selected for Testing | {len(tested)} |")
        L.append(f"| Chunks Downloaded Successfully | {len(tested_ok)} |")
        L.append("")

        if f == 0:
            L.append("> **RESULT: PASS** - All steps completed successfully.")
        else:
            L.append(f"> **RESULT: FAIL** - {f} step(s) failed.")
        L.append("")

        L.append("## Test Steps")
        L.append("")
        L.append("| # | Step | Description | Status | Duration |")
        L.append("|---|------|-------------|--------|----------|")
        for i, s in enumerate(self.steps, 1):
            sd = {"passed": "PASS", "failed": "FAIL", "skipped": "SKIP", "pending": "PEND"}[s.status]
            d = f"{s.dur}ms" if s.dur else "-"
            L.append(f"| {i} | `{s.name}` | {s.desc} | {sd} | {d} |")
        L.append("")

        L.append("## Chunk Overview")
        L.append("")
        L.append("| Chunk # | Start | End | Duration | Status | Tested |")
        L.append("|---------|-------|-----|----------|--------|--------|")
        for c in self.chunks:
            tested_mark = "**Yes**" if c.tested else "-"
            L.append(
                f"| {c.idx} | {fmt_dur(c.start)} | {fmt_dur(c.end)} "
                f"| {CHUNK_SIZE_SEC}s | {c.status} | {tested_mark} |"
            )
        L.append("")

        dcs = [c for c in self.chunks if c.tested]
        if dcs:
            L.append("## Tested Chunks Detail")
            L.append("")
            L.append("| Chunk # | File Path | File Size | Download Time | Status |")
            L.append("|---------|-----------|-----------|---------------|--------|")
            for c in dcs:
                pth = c.path or "N/A"
                if len(pth) > 80:
                    pth = "..." + pth[-77:]
                sz = fmt_size(c.size) if c.size else "N/A"
                tm = f"{c.dl_ms}ms" if c.dl_ms else "N/A"
                L.append(f"| {c.idx} | `{pth}` | {sz} | {tm} | {c.status} |")
            L.append("")

        L.append("## Environment")
        L.append("")
        L.append("| Setting | Value |")
        L.append("|---------|-------|")
        L.append(f"| Python | {sys.executable} |")
        L.append(f"| yt-dlp available | {'Yes' if check_yt_dlp() else 'No'} |")
        L.append(f"| Backend URL | {self.be.url} |")
        L.append(f"| Cache Directory | {CACHE_DIR} |")
        L.append(f"| Chunks Directory | {CHUNKS_DIR} |")
        L.append("")

        errs = [(s.name, s.err) for s in self.steps if s.status == "failed" and s.err]
        if errs:
            L.append("## Errors")
            L.append("")
            for n, e in errs:
                L.append(f"### {n}")
                L.append("```")
                L.append(str(e))
                L.append("```")
                L.append("")

        rp.write_text("\n".join(L), encoding="utf-8")
        return rp

    def _summary(self, rp: Path) -> None:
        print()
        log("=" * 70)
        log("TEST SUMMARY")
        log("=" * 70)
        for s in self.steps:
            sd = {"passed": "PASS", "failed": "FAIL", "skipped": "SKIP", "pending": "PEND"}[s.status]
            d = f" ({s.dur}ms)" if s.dur else ""
            log(f"  [{sd}] {s.name}: {s.desc}{d}")
            if s.err and s.status == "failed":
                log(f"         Error: {s.err}", "ERROR")
        p = sum(1 for s in self.steps if s.status == "passed")
        f = sum(1 for s in self.steps if s.status == "failed")
        sk = sum(1 for s in self.steps if s.status == "skipped")
        log("")
        log(f"Results: {p} passed, {f} failed, {sk} skipped (of {len(self.steps)} steps)")
        log("")
        log(f"Report saved to: {rp}")
        log("=" * 70)


# =============================================================================
# Entry Point
# =============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="Chunk Streaming Integration Test")
    parser.add_argument("--video", default=DEFAULT_VIDEO_ID, help=f"YouTube video ID (default: {DEFAULT_VIDEO_ID})")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Backend host (default: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Backend port (default: {DEFAULT_PORT})")
    args = parser.parse_args()
    Test(args.video, args.host, args.port).run()


if __name__ == "__main__":
    main()
