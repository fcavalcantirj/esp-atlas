"""Tests for the Vercel entrypoint (api/index.py) — verifies it mounts the
esp_atlas_api backend under /api without altering the inner app's own routes.
"""
import sys
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from api.index import app  # noqa: E402


def test_health_resolves_under_api_prefix():
    with TestClient(app) as c:
        r = c.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_search_resolves_under_api_prefix():
    with TestClient(app) as c:
        r = c.get("/api/search", params={"q": "zigbee"})
    assert r.status_code == 200
    assert r.json()["results"]


def test_unprefixed_paths_are_not_reachable_on_the_outer_app():
    with TestClient(app) as c:
        r = c.get("/health")
    assert r.status_code == 404
