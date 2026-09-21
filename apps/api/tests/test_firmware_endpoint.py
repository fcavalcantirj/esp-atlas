import esp_atlas_api.main as main_module


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
        assert reason["status"] in {"known-good", "reported", "unverified", "broken"}
        assert reason["chip_family"]
        assert reason["sources"] and all(s["url"] for s in reason["sources"])
        assert reason["reason"]
    by_board = {b: r for b, r in zip(body["boards"], reasons)}
    if "esp32-c5-devkitc-1" in by_board:
        assert by_board["esp32-c5-devkitc-1"]["status"] == "broken"
    assert any(r["status"] == "known-good" for r in reasons), "Marauder still has known-good boards"
