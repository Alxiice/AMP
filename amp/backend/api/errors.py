"""One error shape for the streaming API: {"detail": {"code": …, "message": …}}.

| code                | HTTP | raised when                                  |
|---------------------|------|----------------------------------------------|
| invalid_id          | 400  | validate_song_id fails (InvalidSongId)       |
| unavailable         | 404  | ExtractionError("unavailable")               |
| no_audio            | 404  | no audio-only format                         |
| auth_required       | 401  | age-gated / members-only, signed out         |
| node_missing        | 503  | no JS runtime for yt-dlp                     |
| extract_failed      | 502  | anything else from the extractor             |
| segment_unavailable | 502  | ensure_segment failure (serving.py)          |

Library routes still raise HTTPException with a string detail; the frontend
accepts both shapes.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from backend.services.extractor import ExtractionError
from backend.services.streaming import InvalidSongId
from backend.services.streaming.serving import EXTRACTION_MESSAGES, EXTRACTION_STATUS, error_body


class ApiError(Exception):
    def __init__(self, code: str, message: str, status: int) -> None:
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def extraction_api_error(e: ExtractionError) -> ApiError:
    code = e.code if e.code in EXTRACTION_STATUS else "extract_failed"
    return ApiError(code, EXTRACTION_MESSAGES[code], EXTRACTION_STATUS[code])


def _json(err: ApiError) -> JSONResponse:
    return JSONResponse(error_body(err.code, err.message), status_code=err.status)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        return _json(exc)

    @app.exception_handler(InvalidSongId)
    async def _invalid_id(request: Request, exc: InvalidSongId) -> JSONResponse:
        return _json(ApiError("invalid_id", str(exc), 400))

    @app.exception_handler(ExtractionError)
    async def _extraction(request: Request, exc: ExtractionError) -> JSONResponse:
        return _json(extraction_api_error(exc))
