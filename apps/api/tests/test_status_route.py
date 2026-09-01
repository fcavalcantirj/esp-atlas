"""GET /status -- the public health snapshot (INTERFACE-SPEC.md).

Separate file from test_app.py to keep that file under the ~900-line ceiling.
Reuses the `client`/`built_db_path` fixtures from conftest.py -- the real
seeded ESP32/firmware dataset, never lorem ipsum.
"""
import pytest
from fastapi.testclient import TestClient

import esp_atlas_api.main as main_module
from esp_atlas_api.main import create_app

_COMPONENT_NAMES = ["API", "Data", "Jr / catalog", "Deploy"]


@pytest.fixture
def client(built_db_path):
    app = create_app(db_path=built_db_path)
    with TestClient(app) as c:
        yield c


def test_status_returns_200_with_documented_shape(client):
    r = client.get("/status")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"status", "generated_at", "components"}
    assert body["status"] in ("operational", "degraded", "down")
    assert body["generated_at"]
    assert [c["name"] for c in body["components"]] == _COMPONENT_NAMES
    for component in body["components"]:
        assert set(component) == {"name", "status", "detail"}
        assert component["status"] in ("ok", "warn", "down")
        assert isinstance(component["detail"], str) and component["detail"]


def test_status_operational_on_healthy_fixture(client):
    r = client.get("/status")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "operational"
    assert all(c["status"] == "ok" for c in body["components"])


def test_status_degraded_when_a_component_is_forced_to_warn(built_db_path, monkeypatch):
    def fake_compute_status(db_path=None, data_dir=None):
        return {
            "status": "degraded",
            "generated_at": "2026-09-01T00:00:00+00:00",
            "components": [
                {"name": "API", "status": "ok", "detail": "serving, index has 42 records"},
                {"name": "Data", "status": "warn", "detail": "schema_valid=false"},
                {"name": "Jr / catalog", "status": "ok", "detail": "newest: wled (verified 2026-08-24)"},
                {"name": "Deploy", "status": "ok", "detail": "local"},
            ],
        }

    monkeypatch.setattr(main_module, "core_compute_status", fake_compute_status)
    app = create_app(db_path=built_db_path)
    with TestClient(app) as c:
        r = c.get("/status")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "degraded"
    data = next(c for c in body["components"] if c["name"] == "Data")
    assert data["status"] == "warn"


def test_status_never_500s_even_if_the_core_computation_blows_up(built_db_path, monkeypatch):
    """Defense in depth: even a totally unexpected exception from
    esp_atlas_core.status must not surface as a 500 -- the route itself
    degrades to an honest 'down' response rather than crashing."""

    def raise_unexpected(*args, **kwargs):
        raise RuntimeError("totally unexpected failure")

    monkeypatch.setattr(main_module, "core_compute_status", raise_unexpected)
    app = create_app(db_path=built_db_path)
    with TestClient(app) as c:
        r = c.get("/status")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "down"
    assert body["components"] == []


def test_status_is_exempt_from_rate_limiting_like_health(built_db_path):
    """A public status page auto-refreshing every 30s from many visitors
    behind shared IPs must never trip the read rate limit."""
    app = create_app(db_path=built_db_path, rate_limits={"read": "2/minute", "llm": "2/minute", "flash": "2/minute"})
    with TestClient(app) as c:
        for _ in range(5):
            r = c.get("/status")
            assert r.status_code == 200


def test_health_search_and_wizard_routes_still_work(client):
    """GET /status must not disturb any existing route."""
    assert client.get("/health").status_code == 200
    assert client.get("/search").status_code == 200
    assert client.post("/wizard", json={"needs": {}}).status_code == 200
