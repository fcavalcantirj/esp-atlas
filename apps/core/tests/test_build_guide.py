"""ORACLE invariants for build_guide (SPEC-build-guide.md) -- the grounded
"here's what you need" answer for a project goal that parse_intent correctly
calls "unmapped" (a sensor/camera/motor goal, not a spec).

Same honesty contract as run_guide/ask: firmware is picked from the REAL
catalog only (a hostile/hallucinating model can never leak an invented
firmware id), boards are NEVER chosen by the model at all (100% deterministic
retrieval, so an invented board id is structurally impossible), and a down/
rate-limited/garbage model degrades to a deterministic, still-grounded answer
rather than ever raising.

The model itself is stubbed throughout -- these test OUR contract, not Groq's
mood. No test in this file may perform a real network call.
"""
import json

import pytest

from esp_atlas_core.build_guide import build_guide
from esp_atlas_core.firmware import list_firmware
from esp_atlas_core.llm import GroqConfigError, GroqRateLimitError
from esp_atlas_core.search import get_part


class StubLLM:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def complete(self, system_prompt, user_prompt, temperature=0):
        self.calls.append({"system": system_prompt, "user": user_prompt, "temperature": temperature})
        return self.payload if isinstance(self.payload, str) else json.dumps(self.payload)


class RaisingLLM:
    def __init__(self, exc):
        self.exc = exc

    def complete(self, system_prompt, user_prompt, temperature=0):
        raise self.exc


def _stub(payload):
    return StubLLM(payload)


# --- 1. Acceptance: "build a plant health monitor" -> ESPHome ---------------


def test_plant_health_monitor_grounds_on_esphome_with_real_boards_and_sensor_addon(built_db_path):
    llm = _stub(
        {
            "firmware_id": "esphome",
            "why": "Reads sensors and reports to Home Assistant over Wi-Fi, no code.",
            "traits": {"wifi": True, "battery": False, "cheap": True},
            "add_ons": ["soil-moisture sensor"],
        }
    )
    result = build_guide("build a plant health monitor", llm_client=llm, db_path=built_db_path)

    assert result["goal"] == "build a plant health monitor"
    assert result["firmware"]["id"] == "esphome"
    assert result["firmware"]["name"] == "ESPHome"
    assert result["firmware"]["why"]

    assert result["boards"], "must recommend at least one real board"
    for board in result["boards"]:
        record = get_part(board["board_id"], db_path=built_db_path)
        assert record is not None, f"invented board id: {board['board_id']}"
        assert board["board_name"] == record["name"]
        assert board["why"]

    assert result["add_ons"] == ["soil-moisture sensor"]
    assert "sensor" in " ".join(result["add_ons"]).lower()
    assert result["note"] and "soil-moisture sensor" in result["note"]
    assert any("soil-moisture sensor" in need for need in result["needs"])


def test_plant_health_monitor_boards_come_from_the_esphome_recipe_graph(built_db_path):
    from esp_atlas_core.firmware import recipes_for_firmware

    llm = _stub(
        {
            "firmware_id": "esphome",
            "why": "Sensors to Home Assistant over YAML.",
            "traits": {"wifi": True, "battery": False, "cheap": True},
            "add_ons": ["humidity sensor"],
        }
    )
    result = build_guide("a plant health monitor", llm_client=llm, db_path=built_db_path)
    recipe_boards = {r["board"] for r in recipes_for_firmware("esphome")}
    for board in result["boards"]:
        assert board["board_id"] in recipe_boards


# --- 2. Grounded project -> firmware intuition (few-shot table) -------------


def test_led_sign_maps_to_wled(built_db_path):
    llm = _stub(
        {
            "firmware_id": "wled",
            "why": "Drives addressable LEDs from a web UI.",
            "traits": {"wifi": True, "battery": False, "cheap": True},
            "add_ons": [],
        }
    )
    result = build_guide("a scrolling LED sign", llm_client=llm, db_path=built_db_path)
    assert result["firmware"]["id"] == "wled"
    assert result["boards"]


def test_offgrid_messaging_maps_to_meshtastic(built_db_path):
    llm = _stub(
        {
            "firmware_id": "meshtastic",
            "why": "Off-grid mesh text messaging over LoRa.",
            "traits": {"wifi": False, "battery": True, "cheap": True},
            "add_ons": [],
        }
    )
    result = build_guide("off-grid text messaging", llm_client=llm, db_path=built_db_path)
    assert result["firmware"]["id"] == "meshtastic"
    assert result["boards"]


def test_wifi_deauther_maps_to_bruce_or_marauder(built_db_path):
    llm = _stub(
        {
            "firmware_id": "bruce",
            "why": "Wi-Fi deauth and recon tools.",
            "traits": {"wifi": True, "battery": True, "cheap": True},
            "add_ons": [],
        }
    )
    result = build_guide("a wifi deauther", llm_client=llm, db_path=built_db_path)
    assert result["firmware"]["id"] in {"bruce", "esp32marauder"}
    assert result["boards"]


# --- 3. No firmware fits -> honest, still boards ----------------------------


def test_no_firmware_fits_is_honest_and_still_recommends_boards(built_db_path):
    llm = _stub(
        {
            "firmware_id": None,
            "why": "Nothing in the catalog does line-following robot control.",
            "traits": {"wifi": True, "battery": True, "cheap": True},
            "add_ons": ["motor driver", "line sensor array"],
        }
    )
    result = build_guide("a line-following robot", llm_client=llm, db_path=built_db_path)
    assert result["firmware"] is None
    assert result["boards"], "no firmware fitting must still recommend boards"
    for board in result["boards"]:
        assert get_part(board["board_id"], db_path=built_db_path) is not None
    assert "no ready-made firmware" in result["note"].lower()
    assert any("no ready-made firmware" in need.lower() for need in result["needs"])


# --- 4. Grounding validator: a hostile model can never leak -----------------


def test_invented_firmware_id_is_rejected_never_surfaced(built_db_path):
    llm = _stub(
        {
            "firmware_id": "totally-invented-firmware-xyz",
            "why": "this would be invented",
            "traits": {"wifi": True, "battery": False, "cheap": True},
            "add_ons": [],
        }
    )
    result = build_guide("build a plant health monitor", llm_client=llm, db_path=built_db_path)
    assert result["firmware"] is None
    valid_ids = {fw["id"] for fw in list_firmware()}
    assert "totally-invented-firmware-xyz" not in valid_ids
    # still degrades to a grounded, non-empty board list -- never a dead end
    assert result["boards"]


def test_a_board_naming_field_in_the_llm_reply_is_never_read_or_surfaced(built_db_path):
    """Board selection is 100% deterministic (see module docstring) -- the
    module never even looks at a 'boards' key on the LLM reply, so a hostile
    model naming a fake board there cannot leak it into the response."""
    llm = _stub(
        {
            "firmware_id": "esphome",
            "why": "ok",
            "traits": {"wifi": True, "battery": False, "cheap": True},
            "add_ons": [],
            "boards": [{"board_id": "not-a-real-board-at-all", "why": "invented"}],
        }
    )
    result = build_guide("build a plant health monitor", llm_client=llm, db_path=built_db_path)
    board_ids = {b["board_id"] for b in result["boards"]}
    assert "not-a-real-board-at-all" not in board_ids
    for board_id in board_ids:
        assert get_part(board_id, db_path=built_db_path) is not None


@pytest.mark.parametrize("garbage", ["not json at all", '{"firmware_id":', "```json\n{}\n```", ""])
def test_malformed_llm_json_degrades_honestly(built_db_path, garbage):
    result = build_guide("build a plant health monitor", llm_client=_stub(garbage), db_path=built_db_path)
    assert result["boards"], "a malformed reply must still fall back to grounded boards"
    valid_ids = {fw["id"] for fw in list_firmware()} | {None}
    assert (result["firmware"]["id"] if result["firmware"] else None) in valid_ids


# --- 5. Groq failure/rate-limit -> graceful degradation, never raises -------


def test_groq_config_error_falls_back_to_grounded_boards(built_db_path):
    result = build_guide(
        "build a plant health monitor", llm_client=RaisingLLM(GroqConfigError("no key")), db_path=built_db_path
    )
    assert result["boards"]
    for board in result["boards"]:
        assert get_part(board["board_id"], db_path=built_db_path) is not None


def test_groq_rate_limit_falls_back_to_grounded_boards(built_db_path):
    result = build_guide(
        "build a plant health monitor",
        llm_client=RaisingLLM(GroqRateLimitError("rate limited")),
        db_path=built_db_path,
    )
    assert result["boards"]


def test_deterministic_fallback_still_maps_led_sign_to_wled_by_keyword(built_db_path):
    """The keyword fallback applies the SAME project->firmware table as the
    system prompt's few-shot, so a down model doesn't lose the headline case."""
    result = build_guide(
        "a scrolling LED sign", llm_client=RaisingLLM(GroqConfigError("no key")), db_path=built_db_path
    )
    assert result["firmware"] is not None
    assert result["firmware"]["id"] == "wled"


# --- 6. Board recommendation is capped and real ------------------------------


def test_boards_are_capped_at_a_handful_never_the_whole_catalog(built_db_path):
    llm = _stub(
        {
            "firmware_id": "esphome",
            "why": "ok",
            "traits": {"wifi": True, "battery": False, "cheap": True},
            "add_ons": [],
        }
    )
    result = build_guide("a home dashboard", llm_client=llm, db_path=built_db_path)
    assert 1 <= len(result["boards"]) <= 4


def test_no_duplicate_boards_recommended(built_db_path):
    llm = _stub(
        {
            "firmware_id": "esphome",
            "why": "ok",
            "traits": {"wifi": True, "battery": False, "cheap": True},
            "add_ons": [],
        }
    )
    result = build_guide("a home dashboard", llm_client=llm, db_path=built_db_path)
    ids = [b["board_id"] for b in result["boards"]]
    assert len(ids) == len(set(ids))


# --- 7. Never touches the model for firmware selection when it's told null --


def test_firmware_null_from_llm_produces_wifi_boards_from_the_full_catalog(built_db_path):
    llm = _stub(
        {
            "firmware_id": None,
            "why": "nothing fits",
            "traits": {"wifi": True, "battery": False, "cheap": True},
            "add_ons": ["camera module"],
        }
    )
    result = build_guide("a doorbell camera", llm_client=llm, db_path=built_db_path)
    assert result["firmware"] is None
    for board in result["boards"]:
        record = get_part(board["board_id"], db_path=built_db_path)
        assert record is not None
        assert record["wifi_standard"] is not None
