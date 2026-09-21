import esp_atlas_api.main as main_module
from esp_atlas_core.firmware import list_firmware as core_list_firmware
from esp_atlas_core.firmware import sort_by_popularity


def test_list_firmware_returns_every_seeded_firmware(client):
    r = client.get("/firmware")
    assert r.status_code == 200
    ids = {rec["id"] for rec in r.json()["results"]}
    assert "esp32marauder" in ids
    assert "launcher" in ids


def test_list_firmware_defaults_to_popularity_order_and_reports_total(client):
    r = client.get("/firmware")
    assert r.status_code == 200
    body = r.json()
    expected_order = [fw["id"] for fw in sort_by_popularity(core_list_firmware())]
    assert [rec["id"] for rec in body["results"]] == expected_order
    assert body["total"] == len(expected_order)
    assert len(body["results"]) == len(expected_order)


def test_list_firmware_every_record_still_carries_popularity(client):
    r = client.get("/firmware")
    assert r.status_code == 200
    for rec in r.json()["results"]:
        assert "popularity" in rec


def test_list_firmware_sort_name_orders_alphabetically(client):
    r = client.get("/firmware", params={"sort": "name"})
    assert r.status_code == 200
    ids = [rec["name"] for rec in r.json()["results"]]
    assert ids == sorted(ids)


def test_list_firmware_limit_and_offset_slice_the_popularity_order(client):
    all_ids = [fw["id"] for fw in sort_by_popularity(core_list_firmware())]

    r = client.get("/firmware", params={"limit": 5})
    assert r.status_code == 200
    body = r.json()
    assert [rec["id"] for rec in body["results"]] == all_ids[:5]
    assert body["total"] == len(all_ids)

    r = client.get("/firmware", params={"limit": 5, "offset": 5})
    assert r.status_code == 200
    body = r.json()
    assert [rec["id"] for rec in body["results"]] == all_ids[5:10]
    assert body["total"] == len(all_ids)


def test_list_firmware_offset_past_the_end_returns_empty_results_with_full_total(client):
    all_ids = [fw["id"] for fw in sort_by_popularity(core_list_firmware())]
    r = client.get("/firmware", params={"offset": len(all_ids) + 10})
    assert r.status_code == 200
    body = r.json()
    assert body["results"] == []
    assert body["total"] == len(all_ids)


def test_list_firmware_invalid_sort_is_422(client):
    r = client.get("/firmware", params={"sort": "bogus"})
    assert r.status_code == 422


def test_list_firmware_limit_over_cap_is_422(client):
    r = client.get("/firmware", params={"limit": 101})
    assert r.status_code == 422


def test_list_firmware_limit_below_one_is_422(client):
    r = client.get("/firmware", params={"limit": 0})
    assert r.status_code == 422


def test_list_firmware_negative_offset_is_422(client):
    r = client.get("/firmware", params={"offset": -1})
    assert r.status_code == 422


def test_get_firmware_known_id_returns_record(client):
    r = client.get("/firmware/esp32marauder")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "ESP32 Marauder"
    assert body["category"] == "pentest"


def test_get_firmware_unknown_id_returns_404(client):
    r = client.get("/firmware/no-such-firmware")
    assert r.status_code == 404


def test_get_firmware_returns_cited_popularity(client):
    r = client.get("/firmware/ai-stackchan2-readme")
    assert r.status_code == 200
    body = r.json()
    assert body["popularity"]["stars"] == 42


def test_get_firmware_with_a_summary_reads_the_cached_english_translation_from_disk(client, monkeypatch, tmp_path):
    fake_record = {
        "id": "fake-fw", "type": "firmware", "name": "Fake Firmware",
        "url": "https://github.com/example/fake-fw", "category": "multi",
        "socs": ["esp32-s3"],
        "sources": [{"field": "*", "url": "https://github.com/example/fake-fw", "verified": "2026-09-20"}],
        "summary": "Fake Firmware does fake things on an ESP32-S3.",
        "readme_lang": "ja",
    }
    monkeypatch.setattr(main_module, "core_get_firmware", lambda fid: fake_record if fid == "fake-fw" else None)
    monkeypatch.setattr(main_module, "FIRMWARE_DATA_DIR", tmp_path)
    (tmp_path / "fake-fw").mkdir()
    (tmp_path / "fake-fw" / "readme.en.md").write_text("# Fake Firmware\n\nTranslated body.\n", encoding="utf-8")

    r = client.get("/firmware/fake-fw")

    assert r.status_code == 200
    body = r.json()
    assert body["summary"] == "Fake Firmware does fake things on an ESP32-S3."
    assert body["readme_lang"] == "ja"
    assert body["readme_en"] == "# Fake Firmware\n\nTranslated body.\n"


def test_get_firmware_without_a_readme_en_file_leaves_it_null(client, monkeypatch, tmp_path):
    fake_record = {
        "id": "fake-fw", "type": "firmware", "name": "Fake Firmware",
        "url": "https://github.com/example/fake-fw", "category": "multi",
        "socs": ["esp32-s3"],
        "sources": [{"field": "*", "url": "https://github.com/example/fake-fw", "verified": "2026-09-20"}],
    }
    monkeypatch.setattr(main_module, "core_get_firmware", lambda fid: fake_record if fid == "fake-fw" else None)
    monkeypatch.setattr(main_module, "FIRMWARE_DATA_DIR", tmp_path)

    r = client.get("/firmware/fake-fw")

    assert r.status_code == 200
    body = r.json()
    assert body["summary"] is None
    assert body["readme_en"] is None


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
        # The status is the recipe's own trust tier, never model-generated -- and
        # not always known-good: the C5-DevKitC-1 recipe is `broken` since the
        # 2026-09-01 hardware test (v1.15.1 boot-loops on chip rev v1.2).
        assert reason["status"] in {"known-good", "reported", "declared", "unverified", "broken"}
        assert reason["chip_family"]
        assert reason["sources"] and all(s["url"] for s in reason["sources"])
        assert reason["reason"]
    by_board = {b: r for b, r in zip(body["boards"], reasons)}
    if "esp32-c5-devkitc-1" in by_board:
        assert by_board["esp32-c5-devkitc-1"]["status"] == "broken"
    assert any(r["status"] == "known-good" for r in reasons), "Marauder still has known-good boards"
