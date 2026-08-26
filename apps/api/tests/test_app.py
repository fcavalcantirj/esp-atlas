import asyncio
import json
import pytest
from fastapi.testclient import TestClient

from esp_atlas_core.paths import REPO_ROOT

import esp_atlas_api.main as main_module
from esp_atlas_api.main import create_app

SOC_PATH = REPO_ROOT / "data" / "socs" / "esp32-c6" / "chip.md"
BOARD_PATH = REPO_ROOT / "data" / "boards" / "espressif" / "esp32-c6-devkitc-1" / "board.md"


@pytest.fixture
def client(built_db_path):
    app = create_app(db_path=built_db_path)
    with TestClient(app) as c:
        yield c


class _StubLLM:
    """A fake GroqClient for /run tests -- no test here may reach real Groq."""

    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def complete(self, system_prompt, user_prompt, temperature=0):
        self.calls.append(user_prompt)
        return self.payload if isinstance(self.payload, str) else json.dumps(self.payload)


def _client_with_llm(built_db_path, payload):
    app = create_app(db_path=built_db_path, llm_client=_StubLLM(payload))
    return TestClient(app)


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


def test_search_form_filter_includes_price_tier(client):
    r = client.get("/search", params={"form": "xiao"})
    assert r.status_code == 200
    by_id = {rec["id"]: rec for rec in r.json()["results"]}
    assert by_id["xiao-esp32c3"]["price_tier"] == "cheap"


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


def test_wizard_budget_cheap_excludes_medium_tier_but_keeps_unrated(client):
    r = client.post("/wizard", json={"needs": {"budget": "cheap"}})
    assert r.status_code == 200
    ids = {rec["id"] for rec in r.json()["results"]}
    assert "xiao-esp32c3" in ids  # price_tier: cheap
    assert "esp32-s3-devkitc-1" not in ids  # price_tier: medium
    assert "esp32-c6" in ids  # no price_tier at all -> always included


def test_wizard_budget_medium_includes_cheap_and_medium(client):
    r = client.post("/wizard", json={"needs": {"budget": "medium"}})
    assert r.status_code == 200
    ids = {rec["id"] for rec in r.json()["results"]}
    assert "xiao-esp32c3" in ids
    assert "esp32-s3-devkitc-1" in ids


def test_wizard_budget_expensive_matches_no_budget(client):
    with_budget = client.post("/wizard", json={"needs": {"budget": "expensive"}})
    no_budget = client.post("/wizard", json={"needs": {}})
    assert {r["id"] for r in with_budget.json()["results"]} == {r["id"] for r in no_budget.json()["results"]}


def test_wizard_budget_invalid_value_rejected(client):
    r = client.post("/wizard", json={"needs": {"budget": "low"}})
    assert r.status_code == 422


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
    assert body["brand_name"] == "Espressif"
    assert body["brand_url"] == "https://www.espressif.com"


def test_parts_by_id_not_found(client):
    r = client.get("/parts/does-not-exist-at-all")
    assert r.status_code == 404


def test_validate_markdown_shape_valid_record_passes(client):
    r = client.post("/validate", json={"markdown": SOC_PATH.read_text(encoding="utf-8")})
    assert r.status_code == 200
    body = r.json()
    assert body == {"ok": True, "errors": [], "kind": "soc"}


def test_validate_markdown_shape_missing_sources_fails(client):
    text = SOC_PATH.read_text(encoding="utf-8").replace("sources:", "not_sources:")
    r = client.post("/validate", json={"markdown": text})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert any("sources" in e for e in body["errors"])
    assert body["kind"] == "soc"


def test_validate_kind_and_frontmatter_shape_valid_record_passes(client):
    from esp_atlas_core.frontmatter import parse_frontmatter

    fm, _body = parse_frontmatter(SOC_PATH)
    r = client.post("/validate", json={"kind": "soc", "frontmatter": fm})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["errors"] == []
    assert body["kind"] == "soc"


def test_validate_kind_and_frontmatter_shape_bad_enum_fails(client):
    from esp_atlas_core.frontmatter import parse_frontmatter

    fm, _body = parse_frontmatter(SOC_PATH)
    fm["cpu"]["arch"] = "bogus-arch"
    r = client.post("/validate", json={"kind": "soc", "frontmatter": fm})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["errors"]


def test_validate_board_unknown_module_ref_fails(client):
    from esp_atlas_core.frontmatter import parse_frontmatter

    fm, _body = parse_frontmatter(BOARD_PATH)
    fm["module"] = "does-not-exist-anywhere"
    r = client.post("/validate", json={"kind": "board", "frontmatter": fm})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert any("does-not-exist-anywhere" in e for e in body["errors"])


def test_validate_rejects_neither_shape(client):
    r = client.post("/validate", json={})
    assert r.status_code == 422


def test_validate_rejects_unknown_fields(client):
    r = client.post("/validate", json={"markdown": "x", "bogus": "y"})
    assert r.status_code == 422


# --- part detail, facets, soc/module filters --------------------------------------


def test_parts_by_id_returns_frontmatter_body_chain_and_related(client):
    r = client.get("/parts/m5stack-cores3")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "m5stack-cores3"
    assert body["frontmatter"]["usb"]["connector"] == "usb-c"
    assert body["frontmatter"]["display"].startswith("2.0in")
    assert body["body"].startswith("# ")
    assert body["chain"]["soc"]["id"] == "esp32-s3"
    assert body["chain"]["module"] is None
    related_ids = [rec["id"] for rec in body["related"]]
    assert "lilygo-t-display-s3" in related_ids
    assert "m5stack-cores3" not in related_ids
    assert "esp32-s3" not in related_ids


def test_parts_by_id_board_via_module_has_full_chain(client):
    r = client.get("/parts/esp32-c6-devkitc-1")
    assert r.status_code == 200
    body = r.json()
    assert body["chain"]["module"]["id"] == "esp32-c6-wroom-1"
    assert body["chain"]["soc"]["id"] == "esp32-c6"
    # chain entries are full records, usable as cards
    assert body["chain"]["soc"]["wifi_standard"] == "wifi-6"
    assert body["chain"]["soc"]["_path"].endswith("chip.md")


def test_parts_by_id_soc_has_empty_chain_and_lists_boards(client):
    r = client.get("/parts/esp32-c6")
    assert r.status_code == 200
    body = r.json()
    assert body["chain"] == {"soc": None, "module": None}
    assert body["frontmatter"]["cpu"]["arch"] == "risc-v"
    related_ids = [rec["id"] for rec in body["related"]]
    assert "xiao-esp32c6" in related_ids
    assert "esp32-c6-wroom-1" in related_ids


def test_facets_endpoint_shape(client):
    r = client.get("/facets")
    assert r.status_code == 200
    body = r.json()
    for key in (
        "type", "form_factor", "wifi_standard",
        "price_tier", "soc_ref", "wifi_bands", "ieee802154_protocols",
    ):
        assert key in body, key
        assert body[key], key
        assert set(body[key][0]) == {"value", "count"}
    assert {e["value"] for e in body["type"]} == {"soc", "module", "board"}
    assert any(e["value"] == "devkit" for e in body["form_factor"])
    assert {e["value"] for e in body["wifi_bands"]} == {"2.4", "5"}


def test_facets_endpoint_vendor_or_brand_has_display_name(client):
    r = client.get("/facets")
    assert r.status_code == 200
    body = r.json()
    assert "vendor_or_brand" in body
    assert body["vendor_or_brand"]
    for entry in body["vendor_or_brand"]:
        assert {"value", "count", "display_name"} <= set(entry)
    by_value = {e["value"]: e for e in body["vendor_or_brand"]}
    assert by_value["espressif"]["display_name"] == "Espressif"
    assert by_value["espressif"]["url"] == "https://www.espressif.com"


def test_search_soc_filter(client):
    r = client.get("/search", params={"soc": "esp32-c6"})
    assert r.status_code == 200
    results = r.json()["results"]
    assert results
    assert all(rec["soc_ref"] == "esp32-c6" for rec in results)
    assert any(rec["id"] == "xiao-esp32c6" for rec in results)


def test_search_soc_filter_combined_with_type(client):
    r = client.get("/search", params={"soc": "esp32-c6", "type": "board"})
    assert r.status_code == 200
    results = r.json()["results"]
    assert results
    assert all(rec["type"] == "board" and rec["soc_ref"] == "esp32-c6" for rec in results)


def test_search_brand_filter(client):
    r = client.get("/search", params={"brand": "adafruit"})
    assert r.status_code == 200
    results = r.json()["results"]
    assert results
    assert all(rec["vendor_or_brand"] == "adafruit" for rec in results)
    assert any(rec["id"] == "adafruit-feather-esp32-s3" for rec in results)


def test_search_results_include_brand_name_and_url(client):
    r = client.get("/search", params={"brand": "adafruit"})
    assert r.status_code == 200
    results = r.json()["results"]
    by_id = {rec["id"]: rec for rec in results}
    r = by_id["adafruit-feather-esp32-s3"]
    assert r["brand_name"] == "Adafruit"
    assert r["brand_url"] == "https://www.adafruit.com"


def test_search_brand_filter_combined_with_type(client):
    r = client.get("/search", params={"brand": "espressif", "type": "soc"})
    assert r.status_code == 200
    results = r.json()["results"]
    assert results
    assert all(rec["type"] == "soc" and rec["vendor_or_brand"] == "espressif" for rec in results)


def test_search_unknown_brand_returns_empty(client):
    r = client.get("/search", params={"brand": "no-such-brand"})
    assert r.status_code == 200
    assert r.json()["results"] == []


def test_search_module_filter(client):
    r = client.get("/search", params={"module": "esp32-c6-wroom-1"})
    assert r.status_code == 200
    results = r.json()["results"]
    assert any(rec["id"] == "esp32-c6-devkitc-1" for rec in results)
    assert all(rec["module_ref"] == "esp32-c6-wroom-1" for rec in results)


def test_search_unknown_soc_returns_empty_200(client):
    r = client.get("/search", params={"soc": "esp32-nope"})
    assert r.status_code == 200
    assert r.json()["results"] == []


# --- brand page ---------------------------------------------------------------


def test_brand_page_known_slug_returns_brand_and_results(client):
    r = client.get("/brands/lilygo")
    assert r.status_code == 200
    body = r.json()
    assert body["brand"] == {"slug": "lilygo", "name": "LILYGO", "url": "https://lilygo.cc"}
    assert body["results"]
    assert all(rec["vendor_or_brand"] == "lilygo" for rec in body["results"])


def test_brand_page_unknown_slug_returns_empty_results_200(client):
    r = client.get("/brands/no-such-brand")
    assert r.status_code == 200
    body = r.json()
    assert body["brand"] == {"slug": "no-such-brand", "name": "no-such-brand", "url": None}
    assert body["results"] == []


# --- firmware / recipes ---------------------------------------------------------


def test_list_firmware_returns_every_seeded_firmware(client):
    r = client.get("/firmware")
    assert r.status_code == 200
    ids = {rec["id"] for rec in r.json()["results"]}
    assert "esp32marauder" in ids
    assert "launcher" in ids


def test_get_firmware_known_id_returns_record(client):
    r = client.get("/firmware/esp32marauder")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "ESP32 Marauder"
    assert body["category"] == "pentest"


def test_get_firmware_unknown_id_returns_404(client):
    r = client.get("/firmware/no-such-firmware")
    assert r.status_code == 404


def test_list_recipes_no_params_returns_all(client):
    r = client.get("/recipes")
    assert r.status_code == 200
    ids = {rec["id"] for rec in r.json()["results"]}
    assert "m5cardputer__esp32marauder" in ids


def test_list_recipes_filters_by_board(client):
    r = client.get("/recipes", params={"board": "m5cardputer"})
    assert r.status_code == 200
    results = r.json()["results"]
    assert results
    assert all(rec["board"] == "m5cardputer" for rec in results)


def test_list_recipes_filters_by_firmware(client):
    r = client.get("/recipes", params={"firmware": "launcher"})
    assert r.status_code == 200
    results = r.json()["results"]
    assert results
    assert all(rec["firmware"] == "launcher" for rec in results)


def test_list_recipes_unknown_board_returns_empty(client):
    r = client.get("/recipes", params={"board": "no-such-board"})
    assert r.status_code == 200
    assert r.json()["results"] == []


def test_intent_firmware_query_surfaces_cited_board_reasons(client):
    """Acceptance case: /intent for 'marauder' must answer with WHY, not just
    WHICH -- status, chip_family, a cited source url and the reason sentence
    per board, all grounded in the recipe data (never model-generated)."""
    r = client.post("/intent", json={"query": "marauder"})
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "firmware"
    assert body["firmware"] == "esp32marauder"
    assert body["firmware_description"]
    reasons = body["board_reasons"]
    assert reasons and len(reasons) == len(body["boards"])
    for reason in reasons:
        assert reason["status"] == "known-good"
        assert reason["chip_family"]
        assert reason["sources"] and all(s["url"] for s in reason["sources"])
        assert reason["reason"]


# --- /run (grounded run-answer) ---------------------------------------------------------


def test_run_marauder_returns_grounded_boards_and_reasons(built_db_path):
    client = _client_with_llm(built_db_path, {"summary": "", "boards": []})
    with client:
        r = client.get("/run/esp32marauder")
    assert r.status_code == 200
    body = r.json()
    assert body["firmware"] == "esp32marauder"
    assert body["grounded"] is True
    assert "2.4GHz Wi-Fi" in body["requirements"]
    assert "Bluetooth LE" in body["requirements"]
    board_ids = {b["board_id"] for b in body["boards"]}
    assert board_ids == {"m5cardputer", "m5stick-cplus2"}
    for board in body["boards"]:
        assert board["reasons"]
        assert board["sources"] and all(s["url"] for s in board["sources"])
    assert set(body["citations"]) == {"https://github.com/justcallmekoko/ESP32Marauder"}


def test_run_chip_constraint_restricts_boards(built_db_path):
    client = _client_with_llm(built_db_path, {"summary": "", "boards": []})
    with client:
        r = client.get("/run/esp32marauder", params={"constraints": "on a esp32"})
    assert r.status_code == 200
    body = r.json()
    assert {b["board_id"] for b in body["boards"]} == {"m5stick-cplus2"}
    assert body["constraint"] == {"chip": "esp32"}
    assert {e["board"] for e in body["excluded_boards"]} == {"m5cardputer"}


def test_run_unknown_firmware_is_honest_not_found_not_a_404(built_db_path):
    client = _client_with_llm(built_db_path, {"summary": "", "boards": []})
    with client:
        r = client.get("/run/no-such-firmware")
    assert r.status_code == 200
    body = r.json()
    assert body["grounded"] is False
    assert body["boards"] == []


def test_run_strips_a_hallucinated_board_from_the_model(built_db_path):
    client = _client_with_llm(
        built_db_path,
        {
            "summary": "ok",
            "boards": [{"board_id": "not-a-real-board", "note": "invented", "source_url": "https://not-real.example"}],
        },
    )
    with client:
        r = client.get("/run/esp32marauder")
    body = r.json()
    board_ids = {b["board_id"] for b in body["boards"]}
    assert board_ids == {"m5cardputer", "m5stick-cplus2"}


# --- /build (grounded build-guide) ------------------------------------------


def test_build_plant_health_monitor_returns_esphome_and_real_boards(built_db_path):
    payload = {
        "firmware_id": "esphome",
        "why": "Reads sensors and reports to Home Assistant over Wi-Fi.",
        "traits": {"wifi": True, "battery": False, "cheap": True},
        "add_ons": ["soil-moisture sensor"],
    }
    client = _client_with_llm(built_db_path, payload)
    with client:
        r = client.post("/build", json={"query": "build a plant health monitor"})
    assert r.status_code == 200
    body = r.json()
    assert body["goal"] == "build a plant health monitor"
    assert body["firmware"]["id"] == "esphome"
    assert body["boards"]
    board_ids = {b["board_id"] for b in body["boards"]}
    for board_id in board_ids:
        assert client.get(f"/parts/{board_id}").status_code == 200
    assert body["add_ons"] == ["soil-moisture sensor"]
    assert "soil-moisture sensor" in body["note"]


def test_build_rejects_an_invented_firmware_id_from_the_model(built_db_path):
    payload = {
        "firmware_id": "totally-invented-firmware-xyz",
        "why": "invented",
        "traits": {"wifi": True, "battery": False, "cheap": True},
        "add_ons": [],
    }
    client = _client_with_llm(built_db_path, payload)
    with client:
        r = client.post("/build", json={"query": "build a plant health monitor"})
    assert r.status_code == 200
    assert r.json().get("firmware") is None
    assert r.json()["boards"], "must still recommend boards rather than dead-end"


def test_build_no_firmware_fits_is_honest_and_still_200(built_db_path):
    payload = {
        "firmware_id": None,
        "why": "nothing fits",
        "traits": {"wifi": True, "battery": True, "cheap": True},
        "add_ons": ["motor driver"],
    }
    client = _client_with_llm(built_db_path, payload)
    with client:
        r = client.post("/build", json={"query": "a line-following robot"})
    assert r.status_code == 200
    body = r.json()
    assert body.get("firmware") is None
    assert body["boards"]
    assert "no ready-made firmware" in body["note"].lower()


def test_build_empty_query_is_422(client):
    r = client.post("/build", json={"query": ""})
    assert r.status_code == 422


def test_examples_endpoint_returns_resolvable_entries(client):
    r = client.get("/examples")
    assert r.status_code == 200
    results = r.json()["results"]
    assert results
    for ex in results:
        assert ex["count"] >= 1, ex["id"]
        if ex["kind"] == "firmware":
            assert ex["firmware"] and "needs" not in ex
        else:
            assert ex["kind"] == "needs"
            assert ex["needs"] and "firmware" not in ex


def test_examples_needs_round_trip_through_wizard(client):
    for ex in client.get("/examples").json()["results"]:
        if ex["kind"] != "needs":
            continue
        r = client.post("/wizard", json={"needs": ex["needs"]})
        assert r.status_code == 200, (ex["id"], r.text)
        assert r.json()["results"], f"{ex['id']}: needs round-trip returned 0 results"


def test_manifest_endpoint_serves_an_absolute_same_origin_proxy_url(client):
    r = client.get("/manifest/m5cardputer__launcher.json")
    assert r.status_code == 200
    build = r.json()["builds"][0]
    assert build["chipFamily"] == "ESP32-S3"
    assert "serialType" not in build
    # The path must resolve against this deployment (the API sits at /api on
    # Vercel but at the root under uvicorn), so it is built from the request.
    assert build["parts"][0]["path"].startswith("http://testserver/flash-bin?recipe=")


def test_manifest_404s_when_a_recipe_cannot_flash_in_browser(client):
    assert client.get("/manifest/nope__nope.json").status_code == 404
    # web-flasher recipes are guided handoffs, not in-browser flashes
    assert client.get("/manifest/m5cardputer__m5stick-nemo.json").status_code == 404


def test_flash_bin_refuses_a_recipe_it_cannot_resolve(client):
    """The proxy only ever fetches what a record points at."""
    assert client.get("/flash-bin?recipe=nope__nope").status_code == 403
    # a release-bin recipe with no recorded binary is still a refusal
    assert client.get("/flash-bin?recipe=m5cardputer__esp32marauder").status_code == 403


def test_flash_bin_takes_no_caller_supplied_url(client):
    """There must be no request shape that turns this into an open proxy."""
    r = client.get("/flash-bin?url=https://evil.example.com/x.bin")
    assert r.status_code == 422  # `recipe` is required; `url` is not a parameter
    r = client.get("/flash-bin?recipe=m5cardputer__launcher&url=https://evil.example.com/x.bin")
    assert r.status_code in (200, 502)  # the stray param is ignored, never honoured


class _FakeResponse:
    def __init__(self, status_code, headers=None):
        self.status_code = status_code
        self.headers = headers or {}

    async def aclose(self):
        pass


class _RedirectingClient:
    """Minimal httpx stand-in that replays a scripted redirect chain."""

    def __init__(self, *responses):
        self._responses = list(responses)
        self.requested = []

    def build_request(self, method, url, headers=None):
        return (method, url, headers)

    async def send(self, request, stream=False):
        self.requested.append(request[1])
        return self._responses.pop(0)


def test_proxy_refuses_a_redirect_off_the_allowlist():
    """An allowlisted host that 302s elsewhere must be stopped mid-chain."""
    from esp_atlas_api.main import _fetch_following_allowlisted_redirects

    client = _RedirectingClient(
        _FakeResponse(302, {"location": "https://evil.example.com/payload.bin"})
    )
    with pytest.raises(PermissionError):
        asyncio.run(
            _fetch_following_allowlisted_redirects(
                client, "https://github.com/o/r/releases/download/1/fw.bin", {}
            )
        )
    assert client.requested == ["https://github.com/o/r/releases/download/1/fw.bin"], (
        "the off-allowlist hop must never be requested"
    )


def test_proxy_follows_the_real_github_hop():
    """github.com -> objects.githubusercontent.com is the normal path and must work."""
    from esp_atlas_api.main import _fetch_following_allowlisted_redirects

    client = _RedirectingClient(
        _FakeResponse(302, {"location": "https://objects.githubusercontent.com/fw.bin"}),
        _FakeResponse(200),
    )
    response = asyncio.run(
        _fetch_following_allowlisted_redirects(
            client, "https://github.com/o/r/releases/download/1/fw.bin", {}
        )
    )
    assert response.status_code == 200
    assert client.requested[-1] == "https://objects.githubusercontent.com/fw.bin"
