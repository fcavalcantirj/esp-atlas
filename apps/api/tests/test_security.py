from fastapi.testclient import TestClient
from starlette.requests import Request

from esp_atlas_api.main import create_app
from esp_atlas_api.security import client_ip, resolve_cors_origins, resolve_rate_limits


def _request(headers=None, client_host="9.9.9.9"):
    scope = {
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "client": (client_host, 1234),
    }
    return Request(scope)


# -- CORS allowlist -----------------------------------------------------

def test_default_cors_origins_exclude_wildcard_and_include_prod(monkeypatch):
    monkeypatch.delenv("ESP_ATLAS_CORS_ORIGINS", raising=False)
    origins = resolve_cors_origins()
    assert "*" not in origins
    assert "https://esp-atlas.com" in origins
    assert "http://localhost:3000" in origins


def test_cors_origins_env_override(monkeypatch):
    monkeypatch.setenv("ESP_ATLAS_CORS_ORIGINS", "https://a.example, https://b.example")
    assert resolve_cors_origins() == ["https://a.example", "https://b.example"]


def test_cors_reflects_allowed_origin_not_disallowed(built_db_path):
    app = create_app(db_path=built_db_path, cors_origins=["https://esp-atlas.com", "http://localhost:3000"])
    with TestClient(app) as c:
        allowed = c.get("/health", headers={"Origin": "https://esp-atlas.com"})
        assert allowed.headers.get("access-control-allow-origin") == "https://esp-atlas.com"

        disallowed = c.get("/health", headers={"Origin": "https://evil.example.com"})
        assert disallowed.headers.get("access-control-allow-origin") != "https://evil.example.com"
        assert "access-control-allow-origin" not in disallowed.headers


# -- client IP resolution ------------------------------------------------

def test_client_ip_uses_trusted_forwarded_header(monkeypatch):
    monkeypatch.delenv("ESP_ATLAS_TRUSTED_FORWARDED_HEADER", raising=False)
    req = _request(headers={"X-Forwarded-For": "203.0.113.7, 10.0.0.1"}, client_host="10.0.0.1")
    assert client_ip(req) == "203.0.113.7"


def test_client_ip_falls_back_to_remote_addr_without_header(monkeypatch):
    monkeypatch.delenv("ESP_ATLAS_TRUSTED_FORWARDED_HEADER", raising=False)
    req = _request(client_host="127.0.0.5")
    assert client_ip(req) == "127.0.0.5"


def test_client_ip_ignores_forwarded_header_when_disabled(monkeypatch):
    monkeypatch.setenv("ESP_ATLAS_TRUSTED_FORWARDED_HEADER", "")
    req = _request(headers={"X-Forwarded-For": "203.0.113.7"}, client_host="10.0.0.1")
    assert client_ip(req) == "10.0.0.1"


# -- rate limit defaults ---------------------------------------------------

def test_resolve_rate_limits_defaults(monkeypatch):
    for var in ("ESP_ATLAS_RATE_LIMIT_READ", "ESP_ATLAS_RATE_LIMIT_LLM", "ESP_ATLAS_RATE_LIMIT_FLASH"):
        monkeypatch.delenv(var, raising=False)
    limits = resolve_rate_limits()
    assert limits == {"read": "120/minute", "llm": "10/minute", "flash": "60/minute"}


def test_resolve_rate_limits_env_override(monkeypatch):
    monkeypatch.setenv("ESP_ATLAS_RATE_LIMIT_LLM", "5/hour")
    assert resolve_rate_limits()["llm"] == "5/hour"


# -- enforcement: expensive endpoint gets a strict limit -------------------

def test_expensive_endpoint_429s_after_strict_limit(built_db_path):
    app = create_app(
        db_path=built_db_path,
        rate_limits={"read": "1000/minute", "llm": "2/minute", "flash": "1000/minute"},
    )
    with TestClient(app) as c:
        for _ in range(2):
            r = c.post("/intent", json={"query": "wifi board"})
            assert r.status_code != 429

        r = c.post("/intent", json={"query": "wifi board"})
        assert r.status_code == 429


def test_flash_bin_429s_after_strict_limit(built_db_path):
    app = create_app(
        db_path=built_db_path,
        rate_limits={"read": "1000/minute", "llm": "1000/minute", "flash": "2/minute"},
    )
    with TestClient(app) as c:
        for _ in range(2):
            r = c.get("/flash-bin", params={"recipe": "does-not-exist"})
            assert r.status_code != 429

        r = c.get("/flash-bin", params={"recipe": "does-not-exist"})
        assert r.status_code == 429


# -- enforcement: read endpoint tolerates a burst, then the generous limit bites --

def test_read_endpoint_tolerates_burst_then_429s_past_generous_limit(built_db_path):
    app = create_app(
        db_path=built_db_path,
        rate_limits={"read": "3/minute", "llm": "1000/minute", "flash": "1000/minute"},
    )
    with TestClient(app) as c:
        for _ in range(3):
            r = c.get("/search")
            assert r.status_code == 200

        r = c.get("/search")
        assert r.status_code == 429


def test_health_is_exempt_from_the_read_limit(built_db_path):
    app = create_app(
        db_path=built_db_path,
        rate_limits={"read": "1/minute", "llm": "1000/minute", "flash": "1000/minute"},
    )
    with TestClient(app) as c:
        for _ in range(3):
            r = c.get("/health")
            assert r.status_code == 200
