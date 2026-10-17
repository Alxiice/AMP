# Backend Tests

This directory contains the test suite for the AMP backend. Tests are organized by phase.

---

## 📁 Test Files

| File | Description | Tests | Phase |
|------|-------------|-------|-------|
| `test_setup.py` | Setup verification | 3 | Phase 1 |
| `test_models.py` | SQLAlchemy database models | 4 | Phase 1 |
| `test_endpoints.py` | FastAPI API endpoints | 13 | Phase 1 |
| `test_youtube.py` | YouTube Music service | 28 | Phase 2 |
| `test_streaming.py` | Streaming service | 25 | Phase 2 |
| `test_ytm_auth.py` | Cookie-based auth service | 11 | Phase 2.5 |
| **Total** | | **92** | |

---

## ⚙️ Setup

### Prerequisites

1. Activate the virtual environment (from project root):
   ```bash
   activate.bat          # Windows CMD
   # or
   ./activate.ps1        # Windows PowerShell
   ```

2. Install test dependencies (already in requirements.txt):
   ```bash
   pip install pytest pytest-cov httpx
   ```

---

## 🏃 Running Tests

### Run all tests (92 tests)
```bash
pytest amp/backend/tests/ -v
```

### Run with coverage
```bash
pytest amp/backend/tests/ --cov=amp.backend --cov-report=term
```

### Run by phase
```bash
# Phase 1: Backend Core (20 tests)
pytest amp/backend/tests/test_setup.py amp/backend/tests/test_models.py amp/backend/tests/test_endpoints.py -v

# Phase 2: YouTube Integration (28 tests)
pytest amp/backend/tests/test_youtube.py -v

# Phase 2: Streaming (25 tests)
pytest amp/backend/tests/test_streaming.py -v

# Phase 2.5: Auth (11 tests)
pytest amp/backend/tests/test_ytm_auth.py -v
```

### Run specific test
```bash
pytest amp/backend/tests/test_ytm_auth.py::TestAuthService::test_cookie_normalization -v
```

### Run with fail-fast
```bash
pytest amp/backend/tests/ -x
```

---

## 📋 Phase 1: Backend Core Tests (20 tests) ✅ COMPLETE

| File | Tests | Status |
|------|-------|--------|
| `test_setup.py` | 3 | ✅ All pass |
| `test_models.py` | 4 | ✅ All pass |
| `test_endpoints.py` | 13 | ✅ All pass |

---

## 📋 Phase 2: YouTube Integration Tests (28 tests) ✅ COMPLETE

| File | Tests | Status |
|------|-------|--------|
| `test_youtube.py` | 28 | ✅ All pass |

Tests cover: search, song/artist/album/playlist metadata, library operations.

---

## 📋 Phase 2: Streaming Tests (25 tests) ✅ COMPLETE

| File | Tests | Status |
|------|-------|--------|
| `test_streaming.py` | 25 | ✅ All pass |

Tests cover: chunk downloading, caching, yt-dlp integration.

---

## 📋 Phase 2.5: Auth Tests (11 tests) ✅ COMPLETE

| File | Tests | Status |
|------|-------|--------|
| `test_ytm_auth.py` | 11 | ✅ All pass |

Tests cover:
- Cookie normalization
- Header building
- Auth flow (sign-in, sign-out)
- Session persistence
- Expiry handling

---

## 📋 Phase 3: Playback System Tests ⏳ NEXT

*Coming soon... Will add tests for:*
- Chunk cache management
- Streaming endpoint
- Playback controls with real audio

---

## 🛠️ Test Configuration

### Test Database
Tests use **in-memory SQLite databases** to avoid affecting your development data.

### Mocking
- YouTube API calls are mocked (no network access during tests)
- Auth tests use mock cookies (no real YouTube validation)
- Streaming tests mock yt-dlp subprocess calls

---

## 🐛 Troubleshooting

### "Module not found" errors
Make sure you're running pytest from the project root with venv activated:
```bash
cd E:\Documents\TRAVAIL\packages\AMP
activate.bat
pytest amp/backend/tests/ -v
```

### Import errors
Try setting PYTHONPATH:
```bash
PYTHONPATH=. pytest amp/backend/tests/ -v
```

### Database lock errors
Ensure no other instance of the app is running.

---

## ✅ Test Checklist

### Phase 1 ✅
- [x] All model tests pass
- [x] All endpoint tests pass
- [x] Setup verification passes

### Phase 2 ✅
- [x] YouTube service tests pass (28)
- [x] Streaming service tests pass (25)

### Phase 2.5 ✅
- [x] Auth service tests pass (11)

### All Phases
- [x] `pytest amp/backend/tests/ -v` → **92 passed**
