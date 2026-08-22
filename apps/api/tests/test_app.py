import pytest
from fastapi.testclient import TestClient

import esp_atlas_api.main as main_module
from esp_atlas_api.main import create_app


@pytest.fixture
def client(built_db_path):
    app = create_app(db_path=built_db_path)
    with TestClient(app) as c:
        yield c


def test_lifespan_builds_missing_db(tmp_path):
    db_path = tmp_path / "fresh.db"
    app = create_app(db_path=db_path)
    with TestClient(app) as c:
        r = c.get("/health")
    assert r.status_code == 200
    assert r.json()["count"] > 0
    assert db_path.exists()


def test_health_reports_status_and_count(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["count"] > 0


def test_search_no_params_returns_all(client):
    r = client.get("/search")
    assert r.status_code == 200
    assert len(r.json()["results"]) > 0


def test_search_free_text_zigbee(client):
    r = client.get("/search", params={"q": "zigbee"})
    assert r.status_code == 200
    ids = [rec["id"] for rec in r.json()["results"]]
    assert "esp32-c6" in ids


def test_search_band_5_returns_esp32_c5(client):
    r = client.get("/search", params={"band": 5})
    assert r.status_code == 200
    ids = [rec["id"] for rec in r.json()["results"]]
    assert "esp32-c5" in ids


def test_search_form_filter(client):
    r = client.get("/search", params={"form": "xiao"})
    assert r.status_code == 200
    ids = [rec["id"] for rec in r.json()["results"]]
    assert any("xiao" in i for i in ids)


def test_search_invalid_type_rejected(client):
    r = client.get("/search", params={"type": "bogus"})
    assert r.status_code == 422


def test_search_radio_filter(client):
    r = client.get("/search", params={"radio": "wifi-6"})
    assert r.status_code == 200
    for rec in r.json()["results"]:
        assert rec["wifi_standard"] == "wifi-6"


def test_search_ieee802154_and_ble_and_bt_classic_and_usb_native_filters(client):
    r = client.get(
        "/search",
        params={"ieee802154": "true", "ble": "true", "bt_classic": "false", "usb_native": "true"},
    )
    assert r.status_code == 200
    for rec in r.json()["results"]:
        assert rec["ieee802154"] is True
        assert rec["ble_version"] is not None
        assert rec["usb_native"] is True


def test_search_protocol_filter(client):
    r = client.get("/search", params={"protocol": "thread"})
    assert r.status_code == 200
    ids = [rec["id"] for rec in r.json()["results"]]
    assert "esp32-h2" in ids or "esp32-c6" in ids


def test_search_propagates_core_value_error_as_400(client, monkeypatch):
    def raise_value_error(*args, **kwargs):
        raise ValueError("unknown search filter(s): ['bogus']")

    monkeypatch.setattr(main_module, "core_search", raise_value_error)
    r = client.get("/search")
    assert r.status_code == 400
    assert "bogus" in r.json()["detail"]


def test_search_response_includes_sources(client):
    r = client.get("/search", params={"q": "", "type": "soc"})
    assert r.status_code == 200
    results = r.json()["results"]
    assert results
    assert results[0]["sources"]
    assert "url" in results[0]["sources"][0]


def test_wizard_zigbee_and_usb_native(client):
    r = client.post("/wizard", json={"needs": {"protocol": "zigbee", "usb_native": True}})
    assert r.status_code == 200
    results = r.json()["results"]
    assert results
    ids = [rec["id"] for rec in results]
    assert "esp32-c6" in ids or "esp32-c5" in ids
    for rec in results:
        assert "score" in rec
        assert "reasons" in rec
        assert isinstance(rec["reasons"], list)


def test_wizard_empty_needs_returns_everything(client):
    r = client.post("/wizard", json={"needs": {}})
    assert r.status_code == 200
    assert len(r.json()["results"]) > 0


def test_wizard_default_body_omitted_needs(client):
    r = client.post("/wizard", json={})
    assert r.status_code == 200
    assert len(r.json()["results"]) > 0


def test_wizard_unknown_need_rejected(client):
    r = client.post("/wizard", json={"needs": {"bogus_need": "x"}})
    assert r.status_code == 422


def test_wizard_propagates_core_value_error_as_400(client, monkeypatch):
    def raise_value_error(*args, **kwargs):
        raise ValueError("unknown wizard need(s): ['bogus']")

    monkeypatch.setattr(main_module, "core_wizard", raise_value_error)
    r = client.post("/wizard", json={"needs": {}})
    assert r.status_code == 400
    assert "bogus" in r.json()["detail"]


def test_parts_lists_all(client):
    r = client.get("/parts")
    assert r.status_code == 200
    results = r.json()["results"]
    assert len(results) > 0
    assert any(rec["id"] == "esp32-c5" for rec in results)


def test_parts_by_id_found(client):
    r = client.get("/parts/esp32-c5")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "esp32-c5"
    assert body["name"]


def test_parts_by_id_not_found(client):
    r = client.get("/parts/does-not-exist-at-all")
    assert r.status_code == 404
