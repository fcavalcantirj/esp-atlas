"""Vercel serverless entrypoint, co-located under apps/web (the project Root
Directory) so Vercel bundles it with the Next.js app.

The `vercel-build` script copies data/, schema/ and the esp_atlas_core /
esp_atlas_api packages into ./_bundle (shipped via includeFiles). We import from
there and point esp_atlas_core at it.

Vercel's serverless ASGI adapter does NOT run FastAPI lifespan startup, so the
SQLite index (normally built in lifespan) is built here at cold-start import,
to the resolved db path (/tmp on Vercel — the only writable dir).
"""
import os
import sys
from pathlib import Path

_BUNDLE = Path(__file__).resolve().parent / "_bundle"
sys.path.insert(0, str(_BUNDLE))
os.environ.setdefault("ESP_ATLAS_REPO_ROOT", str(_BUNDLE))

from fastapi import FastAPI  # noqa: E402
from esp_atlas_api.main import app as _inner_app  # noqa: E402
from esp_atlas_api.settings import resolve_db_path  # noqa: E402
from esp_atlas_core.index_build import build_index  # noqa: E402

_db = Path(resolve_db_path())
if not _db.exists():
    build_index(db_path=_db)

app = FastAPI()
app.mount("/api", _inner_app)
