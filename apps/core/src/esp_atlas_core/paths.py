"""Repo-root path resolution, shared by every esp_atlas_core module.

Default layout: apps/core/src/esp_atlas_core/paths.py -> apps/core/src ->
apps/core -> apps -> <repo root>, with data/, schema/ and esp-atlas.db living
at that root.

That layout doesn't hold once this package is installed into a Vercel Python
serverless function: the bundle isn't nested four parents deep, and the only
writable directory at runtime is /tmp. ESP_ATLAS_REPO_ROOT overrides where
data/, schema/ and prompts/ are found; ESP_ATLAS_DB_PATH overrides the db
file directly. Absent an explicit ESP_ATLAS_DB_PATH, the db path falls back
to /tmp/esp-atlas.db whenever VERCEL is set or the repo root isn't writable,
so a build never fails trying to write next to read-only source.
"""
import os
from pathlib import Path

_PACKAGE_REPO_ROOT = Path(__file__).resolve().parents[4]


def resolve_repo_root():
    raw = os.environ.get("ESP_ATLAS_REPO_ROOT")
    return Path(raw) if raw else _PACKAGE_REPO_ROOT


def _repo_root_writable(repo_root):
    return os.access(str(repo_root), os.W_OK)


def resolve_db_path(repo_root=None):
    raw = os.environ.get("ESP_ATLAS_DB_PATH")
    if raw:
        return Path(raw)
    root = repo_root if repo_root is not None else resolve_repo_root()
    if os.environ.get("VERCEL") or not _repo_root_writable(root):
        return Path("/tmp/esp-atlas.db")
    return root / "esp-atlas.db"


REPO_ROOT = resolve_repo_root()
DATA_DIR = REPO_ROOT / "data"
PROMPTS_DIR = REPO_ROOT / "prompts"
DEFAULT_DB_PATH = resolve_db_path(REPO_ROOT)
