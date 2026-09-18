"""Vercel serverless entrypoint, co-located under apps/web (the project Root
Directory) so Vercel bundles it with the Next.js app.

The `vercel-build` script copies data/, schema/ and the esp_atlas_core /
esp_atlas_api packages into ./_bundle (shipped via includeFiles). We import from
there and point esp_atlas_core at it.

Vercel's serverless ASGI adapter does NOT run FastAPI lifespan startup, so the
SQLite index (normally built in lifespan) is built here at cold-start import,
to the resolved db path (/tmp on Vercel — the only writable dir).
"""
import json
import logging
import os
import sys
import time
from pathlib import Path

_BUNDLE = Path(__file__).resolve().parent / "_bundle"
sys.path.insert(0, str(_BUNDLE))
os.environ.setdefault("ESP_ATLAS_REPO_ROOT", str(_BUNDLE))

from fastapi import FastAPI, Request  # noqa: E402
from esp_atlas_api.main import app as _inner_app  # noqa: E402
from esp_atlas_api.settings import resolve_db_path  # noqa: E402
from esp_atlas_core.index_build import build_index  # noqa: E402

_db = Path(resolve_db_path())
if not _db.exists():
    build_index(db_path=_db)

app = FastAPI()

_telemetry_logger = logging.getLogger("esp_atlas.api_telemetry")
_telemetry_logger.setLevel(logging.INFO)
_telemetry_logger.propagate = False
if not _telemetry_logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _telemetry_logger.addHandler(_handler)


def _looks_programmatic(request: Request) -> bool:
    """Best-effort guess that a request came from an agent/REST/MCP caller
    rather than a browser: browsers always send Sec-Fetch-* on navigations
    and fetches, and a recognizable browser token in User-Agent."""
    headers = request.headers
    if any(h.lower().startswith("sec-fetch-") for h in headers.keys()):
        return False
    user_agent = headers.get("user-agent", "")
    browser_markers = ("mozilla", "chrome", "safari", "firefox", "edg/", "webkit")
    if user_agent and any(marker in user_agent.lower() for marker in browser_markers):
        return False
    return True


@app.middleware("http")
async def _log_request_telemetry(request: Request, call_next):
    start = time.monotonic()
    response = await call_next(request)
    try:
        duration_ms = round((time.monotonic() - start) * 1000, 2)
        record = {
            "ts": time.time(),
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": duration_ms,
            "programmatic": _looks_programmatic(request),
        }
        _telemetry_logger.info(json.dumps(record))
    except Exception:
        pass
    return response


app.mount("/api", _inner_app)
