# Backend Tests

Test suite for the AMP backend. **92 tests total**, all passing.

---

## Test Files

| File | Tests | Phase | Description |
|------|-------|-------|-------------|
| `test_setup.py` | 3 | 1 | Setup verification |
| `test_models.py` | 4 | 1 | SQLAlchemy models |
| `test_endpoints.py` | 13 | 1 | FastAPI endpoints |
| `test_youtube.py` | 28 | 2 | YouTube Music service |
| `test_streaming.py` | 25 | 2 | Streaming service |
| `test_ytm_auth.py` | 11 | 2 | Cookie-based auth service |
| **Total** | **92** | | |

---

## Running Tests

```bash
# From amp/ directory, with venv activated
cd amp && ../venv/Scripts/python.exe -m pytest backend/tests/ -v

# Specific file
../venv/Scripts/python.exe -m pytest backend/tests/test_ytm_auth.py -v

# With coverage
../venv/Scripts/python.exe -m pytest backend/tests/ --cov=backend --cov-report=term
```

---

## Test Configuration

- **In-memory SQLite** databases (no side effects)
- **Mocked YouTube API** calls (no network access)
- **Mock cookies** for auth tests (no real YouTube validation)

---

## Phase 3 Tests ⏳ NEXT

*Coming soon: chunk cache management, streaming endpoint, playback controls*
