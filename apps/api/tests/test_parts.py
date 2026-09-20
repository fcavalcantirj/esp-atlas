from conftest import BOARD_PATH, SOC_PATH


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


def test_parts_by_id_soc_includes_grounded_faq(client):
    r = client.get("/parts/esp32-c6")
    assert r.status_code == 200
    faq = r.json()["faq"]
    assert len(faq) >= 4
    assert all(set(item) == {"id", "question", "answer"} for item in faq)
    assert any(item["id"] == "vs-sibling" and "ESP32-C3" in item["question"] for item in faq)


def test_parts_by_id_board_has_empty_faq(client):
    r = client.get("/parts/esp32-c6-devkitc-1")
    assert r.status_code == 200
    assert r.json()["faq"] == []


def test_boards_boot_returns_c5_with_download_mode(client):
    r = client.get("/boards/boot")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    by_id = {b["id"]: b for b in body}
    assert "esp32-c5-devkitc-1" in by_id, "C5-DevKitC-1 (First-Flash P0 reference) must be present"
    c5 = by_id["esp32-c5-devkitc-1"]
    assert c5["name"] == "ESP32-C5-DevKitC-1"
    assert c5["download_mode"]["mode"] == "manual"
    assert c5["download_mode"]["steps"]  # cited button sequence
    assert c5["usb_serial"] == "native-usb-serial-jtag"
    # First-flash gotcha (2026-09-01): a unit shipped without the J5 current-measurement
    # jumper -- bridge enumerates, LED lights, chip dead. The troubleshooter must be able to say so.
    assert any("J5" in n for n in c5["first_flash_notes"]), c5["first_flash_notes"]
    for b in body:
        assert isinstance(b["first_flash_notes"], list)
    # Every returned board must carry a download_mode with a mode -- that is the
    # whole point of the endpoint (boards without one are omitted).
    for b in body:
        assert b["download_mode"]["mode"] in {"auto", "manual"}


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
