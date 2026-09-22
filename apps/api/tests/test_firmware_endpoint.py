import pytest

import esp_atlas_api.main as main_module
from esp_atlas_core.firmware import list_firmware as core_list_firmware
from esp_atlas_core.firmware import sort_by_mode
from esp_atlas_core.firmware import sort_by_popularity

# --- P2 sort delegation (SPEC-firmware-ordering.md §5.2) --------------------
#
# Coding-tool-named fixture (never lorem/animals/food, matching the P1 oracle
# convention in apps/core/tests/test_firmware.py) with every FirmwareRecord
# field FastAPI's response_model requires -- the core oracle already pins the
# exact per-mode id order; this fixture only has to prove `/firmware?sort=`
# delegates to `sort_by_mode` end-to-end (not re-derive the oracle).
_SORT_FIXTURE = [
    {
        "id": "cargo", "type": "firmware", "name": "Cargo",
        "url": "https://github.com/example/cargo", "category": "multi",
        "socs": ["esp32"], "sources": [],
        "popularity": {"stars": 200, "forks": 80}, "boards": 3,
    },
    {
        "id": "rustc", "type": "firmware", "name": "Rustc",
        "url": "https://github.com/example/rustc", "category": "multi",
        "socs": ["esp32"], "sources": [],
        "popularity": {"stars": 150, "forks": 90}, "boards": 1,
    },
    {
        "id": "eslint", "type": "firmware", "name": "ESLint",
        "url": "https://github.com/example/eslint", "category": "multi",
        "socs": ["esp32"], "sources": [],
        "popularity": {"stars": 50, "forks": 10}, "boards": 5,
    },
    {
        "id": "prettier", "type": "firmware", "name": "Prettier",
        "url": "https://github.com/example/prettier", "category": "multi",
        "socs": ["esp32"], "sources": [],
        "popularity": {"stars": 300, "forks": 5}, "boards": 2,
    },
    {
        "id": "vite", "type": "firmware", "name": "vite",
        "url": "https://github.com/example/vite", "category": "multi",
        "socs": ["esp32"], "sources": [],
        "popularity": {"stars": 10, "forks": 1}, "boards": 1,
    },
]


@pytest.mark.parametrize("mode", ["popularity", "name", "name-desc", "forks", "boards"])
def test_list_firmware_sort_modes_delegate_to_core_sort_by_mode(client, monkeypatch, mode):
    monkeypatch.setattr(main_module, "core_list_firmware", lambda: _SORT_FIXTURE)
    r = client.get("/firmware", params={"sort": mode})
    assert r.status_code == 200
    expected_order = [rec["id"] for rec in sort_by_mode(_SORT_FIXTURE, mode)]
    assert [rec["id"] for rec in r.json()["results"]] == expected_order


def test_list_firmware_unknown_sort_clamps_to_popularity(client, monkeypatch):
    monkeypatch.setattr(main_module, "core_list_firmware", lambda: _SORT_FIXTURE)
    r = client.get("/firmware", params={"sort": "not-a-real-mode"})
    assert r.status_code == 200
    expected_order = [rec["id"] for rec in sort_by_mode(_SORT_FIXTURE, "popularity")]
    assert [rec["id"] for rec in r.json()["results"]] == expected_order


def test_list_firmware_limit_and_offset_slice_after_name_sort(client, monkeypatch):
    monkeypatch.setattr(main_module, "core_list_firmware", lambda: _SORT_FIXTURE)
    all_ids = [rec["id"] for rec in sort_by_mode(_SORT_FIXTURE, "name")]
    r = client.get("/firmware", params={"sort": "name", "limit": 2, "offset": 1})
    assert r.status_code == 200
    body = r.json()
    assert [rec["id"] for rec in body["results"]] == all_ids[1:3]
    assert body["total"] == len(all_ids)


def test_list_firmware_boards_present_on_every_record(client, monkeypatch):
    monkeypatch.setattr(main_module, "core_list_firmware", lambda: _SORT_FIXTURE)
    r = client.get("/firmware")
    assert r.status_code == 200
    boards_by_id = {rec["id"]: rec["boards"] for rec in r.json()["results"]}
    assert boards_by_id == {"cargo": 3, "rustc": 1, "eslint": 5, "prettier": 2, "vite": 1}


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


def test_list_firmware_sort_name_matches_core_name_key_order(client):
    r = client.get("/firmware", params={"sort": "name"})
    assert r.status_code == 200
    expected_order = [fw["id"] for fw in sort_by_mode(core_list_firmware(), "name")]
    assert [rec["id"] for rec in r.json()["results"]] == expected_order


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
