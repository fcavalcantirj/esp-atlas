"""Repo-root path resolution, shared by every esp_atlas_core module.

apps/core/src/esp_atlas_core/paths.py -> apps/core/src -> apps/core -> apps -> <repo root>
"""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = REPO_ROOT / "data"
PROMPTS_DIR = REPO_ROOT / "prompts"
DEFAULT_DB_PATH = REPO_ROOT / "esp-atlas.db"
