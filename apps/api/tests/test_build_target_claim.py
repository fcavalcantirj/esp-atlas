"""A build-target recipe keeps its claim through the API, so the page can name the commit and env it proves
(Jr redesign plan, 2026-11-22). Other tiers have no claim and serialize it as null."""
from esp_atlas_api.models import RecipeRecord

BASE = {"id": "b__f", "type": "recipe", "board": "b", "firmware": "f", "chip_family": "esp32-s3",
        "sources": [{"field": "claim", "url": "https://github.com/o/r/blob/971c066b37dbe3dbb9ac1096d9e72f32ab5b3452/platformio.ini#L1",
                     "verified": "2026-11-22"}]}
CLAIM = {"kind": "pio-env", "repo": {"slug": "o/r", "id": 1}, "sha": "971c066b37dbe3dbb9ac1096d9e72f32ab5b3452",
         "env": "heltecv3demo", "board_id": "heltec_wifi_kit_32_V3", "platformio_version": "6.2.0",
         "platform": {"spec": "x", "package_digest": "a" * 64, "manifest_digest": "b" * 64},
         "files": [{"path": "platformio.ini", "blob": "c" * 40}],
         "sections": [{"name": "env:heltecv3demo", "file": "platformio.ini", "line": 1}]}


def test_the_claim_survives_the_response_model():
    r = RecipeRecord(**BASE, status="build-target", claim=CLAIM).model_dump()
    assert r["claim"]["sha"] == CLAIM["sha"] and r["claim"]["env"] == "heltecv3demo"
    assert r["claim"]["repo"] == {"slug": "o/r", "id": 1} and r["claim"]["board_id"] == "heltec_wifi_kit_32_V3"


def test_other_tiers_serialize_no_claim():
    assert RecipeRecord(**BASE, status="unverified").model_dump()["claim"] is None
