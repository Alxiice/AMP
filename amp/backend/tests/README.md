# Backend Tests

This directory contains test scripts for the AMP backend. Tests are organized into two categories:

- **Unit tests**: Test individual components (models, utilities) in isolation.
- **Integration tests**: Test API endpoints and database interactions.

---

## 📁 Test Files

| File | Description | Type |
|------|-------------|------|
| `test_models.py` | Tests for SQLAlchemy database models | Unit |
| `test_endpoints.py` | Tests for FastAPI API endpoints | Integration |

---

## ⚙️ Setup

### Prerequisites

1. Install Python dependencies:
   ```bash
   pip install pytest pytest-cov
   ```

2. Ensure the backend is properly configured:
   ```bash
   cd backend
   ```

---

## 🏃 Running Tests

### Run all tests
```bash
pytest backend/tests/
```

### Run with coverage
```bash
pytest backend/tests/ --cov=backend --cov-report=term
```

### Run specific test file
```bash
pytest backend/tests/test_models.py
pytest backend/tests/test_endpoints.py
```

### Run specific test class
```bash
pytest backend/tests/test_models.py::TestSongModel
pytest backend/tests/test_endpoints.py::TestSearchEndpoint
```

### Run specific test function
```bash
pytest backend/tests/test_models.py::TestSongModel::test_create_song
pytest backend/tests/test_endpoints.py::TestHealthEndpoint::test_health_check
```

### Run with verbose output
```bash
pytest backend/tests/ -v
```

### Run with fail-fast (stop on first failure)
```bash
pytest backend/tests/ -x
```

---

## 📋 Phase 1: Backend Core Tests

### After Creating Models (models.py)
Run model tests to verify database schema:
```bash
pytest backend/tests/test_models.py -v
```

**Expected output**:
- All model tests should pass (creating/reading songs, playlists, queues, playback state).

### After Creating Endpoints (endpoints.py)
Run endpoint tests to verify API functionality:
```bash
pytest backend/tests/test_endpoints.py -v
```

**Expected output**:
- Health check: ✅ 200 OK
- Search: ✅ Returns mock song list
- Song by ID: ✅ Returns mock song data
- Queue select: ✅ Creates a queue
- Queue get: ✅ Returns queue info
- Playback controls: ✅ All return success messages
- Playback status: ✅ Returns status with default values

---

## 📋 Phase 2: YouTube Integration Tests

*Coming soon... Will add tests for:*
- `ytmusicapi` search functionality
- Song/artist/album metadata fetching
- OAuth flow (mocked)

---

## 📋 Phase 3: Playback System Tests

*Coming soon... Will add tests for:*
- Chunk cache management
- Streaming endpoint
- Playback controls with real audio

---

## 🛠️ Test Configuration

### Test Database
Tests use **in-memory SQLite databases** to avoid affecting your development data. No files are created on disk during testing.

### Fixtures
- `test_userdb`: In-memory userdb for unit tests
- `test_playdb`: In-memory playdb for unit tests
- `client`: TestClient for FastAPI integration tests

### Mock Data
For now, endpoints return **mock data** where real implementations are pending. As we implement features, these will be replaced with real calls to YouTube Music API.

---

## 🐛 Troubleshooting

### "Module not found" errors
Make sure you're running pytest from the project root:
```bash
cd E:\Documents\TRAVAIL\packages\AMP
pytest backend/tests/
```

### Database lock errors
If you see SQLite lock errors, ensure:
1. No other instance of the app is running
2. You're using the test fixtures (in-memory DBs)

### Import errors
If you get import errors like `ModuleNotFoundError: No module named 'backend'`:
1. Make sure you're in the project root directory
2. Try: `PYTHONPATH=. pytest backend/tests/`

---

## ✅ Test Checklist for Phase 1

- [ ] `pytest backend/tests/test_models.py` - All model tests pass
- [ ] `pytest backend/tests/test_endpoints.py::TestHealthEndpoint` - Health check works
- [ ] `pytest backend/tests/test_endpoints.py::TestSearchEndpoint` - Search returns results
- [ ] `pytest backend/tests/test_endpoints.py::TestSongEndpoint` - Song by ID works
- [ ] `pytest backend/tests/test_endpoints.py::TestQueueEndpoints` - Queue operations work
- [ ] `pytest backend/tests/test_endpoints.py::TestPlaybackEndpoints` - Playback controls work
- [ ] `pytest backend/tests/ -v` - All tests pass

**When all checks pass, Phase 1 (Backend Core) is complete!** 🎉
