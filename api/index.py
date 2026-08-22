"""Vercel serverless entrypoint — mounts the esp-atlas FastAPI backend under /api.

Local packages are imported from bundled source (apps/*/src, shipped via
vercel.json includeFiles) rather than pip-installed: Vercel's uv rejects path
installs whose directory name differs from the package metadata name. data/ and
schema/ are bundled too; ESP_ATLAS_REPO_ROOT points esp_atlas_core at them and
the SQLite index builds to /tmp (the only writable dir on Vercel).
"""
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "apps" / "core" / "src"))
sys.path.insert(0, str(_ROOT / "apps" / "api" / "src"))
os.environ.setdefault("ESP_ATLAS_REPO_ROOT", str(_ROOT))

from fastapi import FastAPI  # noqa: E402
from esp_atlas_api.main import app as _inner_app  # noqa: E402

app = FastAPI()
app.mount("/api", _inner_app)
