"""esp-atlas.db path resolution for the API process."""
import os
from pathlib import Path

from esp_atlas_core.paths import DEFAULT_DB_PATH


def resolve_db_path():
    raw = os.environ.get("ESP_ATLAS_DB_PATH")
    return Path(raw) if raw else DEFAULT_DB_PATH
