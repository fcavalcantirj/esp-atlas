"""esp-atlas.db path resolution for the API process.

Delegates to esp_atlas_core.paths.resolve_db_path(), which honors
ESP_ATLAS_DB_PATH and falls back to /tmp on Vercel or a read-only repo root.
"""
from esp_atlas_core.paths import resolve_db_path
