"""A recorded binary is evidence, not permission to install a broken pairing."""
import copy

import pytest

from esp_atlas_core import flash

BROKEN_RECIPE = "esp32-c5-devkitc-1__esp32marauder"


def test_recorded_broken_c5_recipe_never_generates_or_proxies_a_binary(built_db_path):
    record = flash.get_recipe(BROKEN_RECIPE)
    assert record["status"] == "broken", "reassess this regression if the cited recipe is retested"
    assert record["flash"]["bin_url"], "keep the historical artifact as evidence"
    assert flash.build_manifest(BROKEN_RECIPE, db_path=built_db_path) is None
    assert flash.bin_url_for(BROKEN_RECIPE) is None


@pytest.mark.parametrize("status", ["known-good", "reported", "declared", "unverified", "broken"])
def test_install_guard_keeps_other_tiers_distinct_and_available(monkeypatch, built_db_path, status):
    record = copy.deepcopy(flash.get_recipe("m5cardputer__launcher"))
    record["status"] = status
    monkeypatch.setattr(flash, "get_recipe", lambda _id: record)
    assert (flash.build_manifest(record["id"], db_path=built_db_path) is not None) == (status != "broken")
    assert (flash.bin_url_for(record["id"]) is not None) == (status != "broken")
    assert record["status"] == status


@pytest.mark.parametrize("part", [None, 0, 1])
def test_broken_multipart_recipe_blocks_every_part_before_board_lookup(monkeypatch, part):
    record = {
        "id": "broken__multipart", "status": "broken", "board": "m5cardputer",
        "firmware": "launcher", "chip_family": "esp32-s3",
        "flash": {"method": "release-bin", "bin_url": "https://github.com/o/r/releases/download/v1/all.bin",
                  "parts": [{"url": "https://github.com/o/r/releases/download/v1/boot.bin", "offset": "0x0"},
                            {"url": "https://github.com/o/r/releases/download/v1/app.bin", "offset": "0x10000"}]},
    }
    monkeypatch.setattr(flash, "get_recipe", lambda _id: record)

    def forbidden_lookup(*args, **kwargs):
        raise AssertionError("broken pairing must stop before manifest construction")

    monkeypatch.setattr(flash, "get_part", forbidden_lookup)
    assert flash.build_manifest(record["id"]) is None
    assert flash.bin_url_for(record["id"], part=part) is None
