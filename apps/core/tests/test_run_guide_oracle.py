"""ORACLE invariants for run_guide (the grounded, REASONED "why does firmware X
run on board Y" answer -- see esp_atlas_core.run_guide module docstring).

These test properties that must hold for ANY run_guide() call, not examples of
one: the board set is always exactly the recipe graph (never wider, never an
LLM's own idea), every per-board reason is grounded in that board's real
columns, a hostile/hallucinating model can never leak an invented board, spec,
or citation into the response, an unknown firmware degrades honestly, and a
down/rate-limited/garbage-returning model degrades to the deterministic
grounded facts rather than ever raising.

The model itself is stubbed throughout -- these test OUR contract, not Groq's
mood. No test in this file may perform a real network call.
"""
import json

import pytest

from esp_atlas_core.firmware import get_firmware, list_firmware, recipes_for_firmware
from esp_atlas_core.llm import GroqConfigError, GroqRateLimitError
from esp_atlas_core.run_guide import (
    NOT_FOUND_ANSWER,
    parse_chip_constraint,
    requirements_for_firmware,
    run_guide,
    validate_grounded_output,
)


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


_QUIET = StubLLM({"summary": "", "boards": []})  # a "no opinion" stub -- forces the deterministic fallback


# --- 1. Marauder acceptance: the deep, fully-grounded case ------------------


def test_marauder_requirements_include_wifi_and_ble(built_db_path):
    result = run_guide("esp32marauder", llm_client=_QUIET, db_path=built_db_path)
    assert "2.4GHz Wi-Fi" in result["requirements"]
    assert "Bluetooth LE" in result["requirements"]


def test_marauder_boards_are_exactly_the_recipe_set_no_more_no_less(built_db_path):
    result = run_guide("esp32marauder", llm_client=_QUIET, db_path=built_db_path)
    recipe_boards = {r["board"] for r in recipes_for_firmware("esp32marauder")}
    assert recipe_boards == {"m5cardputer", "m5stick-cplus2"}
    assert {b["board_id"] for b in result["boards"]} == recipe_boards


def test_marauder_board_reasons_are_grounded_in_real_radio_specs(built_db_path):
    result = run_guide("esp32marauder", llm_client=_QUIET, db_path=built_db_path)
    by_id = {b["board_id"]: b for b in result["boards"]}

    cardputer = by_id["m5cardputer"]
    assert any("needs 2.4GHz Wi-Fi" in r and "Wi-Fi" in r for r in cardputer["reasons"])
    assert any("needs Bluetooth LE" in r and "BLE" in r for r in cardputer["reasons"])
    assert cardputer["fit"] == "strong"
    assert cardputer["status"] == "known-good"
    assert cardputer["chip_family"] == "esp32-s3"

    stick = by_id["m5stick-cplus2"]
    assert any("needs 2.4GHz Wi-Fi" in r and "Wi-Fi" in r for r in stick["reasons"])
    assert any("needs Bluetooth LE" in r and "BLE" in r for r in stick["reasons"])
    assert stick["fit"] == "strong"


def test_marauder_citations_are_non_empty_and_match_recipe_sources(built_db_path):
    result = run_guide("esp32marauder", llm_client=_QUIET, db_path=built_db_path)
    assert result["citations"]
    assert set(result["citations"]) == {"https://github.com/justcallmekoko/ESP32Marauder"}


def test_marauder_summary_states_what_it_is(built_db_path):
    result = run_guide("esp32marauder", llm_client=_QUIET, db_path=built_db_path)
    lowered = result["summary"].lower()
    assert "wifi" in lowered or "wi-fi" in lowered
    assert "ble" in lowered or "bluetooth" in lowered


# --- 2. Grounding validator: a hostile model can never leak ------------------


_ALLOWED = {"m5cardputer"}
_SOURCES = {"m5cardputer": {"https://docs.m5stack.com/en/core/Cardputer"}}
_HW_MATCH = {"m5cardputer": {"wifi": True, "ble": True, "bt_classic": False, "badusb": True}}
_FACTS = {"m5cardputer": {"psram_mb": 0, "flash_mb": 8, "wifi_bands": "2.4", "usb_native": True}}


def _validate(payload):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return validate_grounded_output(text, _ALLOWED, _SOURCES, _HW_MATCH, _FACTS)


def test_validator_rejects_a_board_outside_the_recipe_set():
    result = _validate({"summary": "ok", "boards": [{"board_id": "totally-invented-board", "note": "great fit"}]})
    assert result["notes"] == {}


def test_validator_rejects_an_unknown_source_url():
    result = _validate(
        {
            "summary": "ok",
            "boards": [
                {"board_id": "m5cardputer", "note": "solid choice", "source_url": "https://not-a-real-source.example"}
            ],
        }
    )
    assert "m5cardputer" not in result["notes"]


def test_validator_rejects_a_psram_claim_the_record_does_not_support():
    """Cardputer's real record is psram_mb=0 -- an 8MB PSRAM claim must be rejected."""
    result = _validate({"summary": "ok", "boards": [{"board_id": "m5cardputer", "note": "8MB PSRAM headroom to spare"}]})
    assert "m5cardputer" not in result["notes"]


def test_validator_rejects_a_bluetooth_classic_claim_the_record_denies():
    result = _validate(
        {"summary": "ok", "boards": [{"board_id": "m5cardputer", "note": "also streams over Bluetooth Classic audio"}]}
    )
    assert "m5cardputer" not in result["notes"]


def test_validator_rejects_a_5ghz_claim_the_record_does_not_support():
    result = _validate({"summary": "ok", "boards": [{"board_id": "m5cardputer", "note": "runs great on 5GHz networks"}]})
    assert "m5cardputer" not in result["notes"]


def test_validator_keeps_a_fully_grounded_note():
    result = _validate(
        {
            "summary": "ok",
            "boards": [
                {
                    "board_id": "m5cardputer",
                    "note": "Native USB and Wi-Fi make it a strong fit.",
                    "source_url": "https://docs.m5stack.com/en/core/Cardputer",
                }
            ],
        }
    )
    assert result["notes"]["m5cardputer"]["note"] == "Native USB and Wi-Fi make it a strong fit."


@pytest.mark.parametrize("garbage", ["not json at all", '{"boards":', "```json\n{}\n```", ""])
def test_validator_degrades_honestly_on_malformed_output(garbage):
    result = _validate(garbage)
    assert result == {"summary": None, "notes": {}}


def test_run_guide_strips_a_hallucinated_board_end_to_end(built_db_path):
    hostile = StubLLM(
        {
            "summary": "ok",
            "boards": [
                {"board_id": "not-a-real-board", "note": "invented", "source_url": "https://not-real.example"},
                {"board_id": "m5cardputer", "note": "512MB PSRAM!!", "source_url": None},
            ],
        }
    )
    result = run_guide("esp32marauder", llm_client=hostile, db_path=built_db_path)
    board_ids = {b["board_id"] for b in result["boards"]}
    assert board_ids == {"m5cardputer", "m5stick-cplus2"}
    by_id = {b["board_id"]: b for b in result["boards"]}
    assert "note" not in by_id["m5cardputer"]  # the ungrounded PSRAM claim never leaked through


# --- 3. Chip constraint: "on a esp32" restricts, never silently ignored -----


@pytest.mark.parametrize(
    "text,expected",
    [
        ("on a esp32", "esp32"),
        ("run marauder on esp32-s3", "esp32-s3"),
        ("on esp32s3", "esp32-s3"),
        ("ESP32-C6 please", "esp32-c6"),
        ("run marauder", None),
        (None, None),
        ("", None),
    ],
)
def test_parse_chip_constraint(text, expected):
    assert parse_chip_constraint(text) == expected


def test_chip_constraint_restricts_to_matching_family_and_still_returns_boards(built_db_path):
    result = run_guide("esp32marauder", constraints="run marauder on a esp32", llm_client=_QUIET, db_path=built_db_path)
    assert {b["board_id"] for b in result["boards"]} == {"m5stick-cplus2"}
    assert result["constraint"] == {"chip": "esp32"}
    assert {e["board"] for e in result["excluded_boards"]} == {"m5cardputer"}


def test_no_chip_constraint_carries_no_constraint_key(built_db_path):
    result = run_guide("esp32marauder", llm_client=_QUIET, db_path=built_db_path)
    assert "constraint" not in result
    assert "excluded_boards" not in result


# --- 4. Honest fallback for unknown/misspelled firmware ---------------------


def test_unknown_firmware_is_an_honest_not_found(built_db_path):
    result = run_guide("totally-not-a-firmware-xyz", db_path=built_db_path)
    assert result["grounded"] is False
    assert result["boards"] == []
    assert result["citations"] == []
    assert result["summary"] == NOT_FOUND_ANSWER


def test_unknown_firmware_never_touches_the_model(built_db_path):
    stub = StubLLM({"summary": "x", "boards": []})
    run_guide("totally-not-a-firmware-xyz", llm_client=stub, db_path=built_db_path)
    assert stub.calls == []


# --- 5. Groq failure/rate-limit/garbage -> graceful degradation, never 500 --


def test_groq_config_error_falls_back_to_grounded_facts(built_db_path):
    result = run_guide("esp32marauder", llm_client=RaisingLLM(GroqConfigError("no key")), db_path=built_db_path)
    assert result["grounded"] is True
    assert {b["board_id"] for b in result["boards"]} == {"m5cardputer", "m5stick-cplus2"}
    assert result["summary"]


def test_groq_rate_limit_falls_back_to_grounded_facts(built_db_path):
    result = run_guide("esp32marauder", llm_client=RaisingLLM(GroqRateLimitError("rate limited")), db_path=built_db_path)
    assert result["grounded"] is True
    assert {b["board_id"] for b in result["boards"]} == {"m5cardputer", "m5stick-cplus2"}
    assert result["summary"]


def test_malformed_llm_json_falls_back_honestly(built_db_path):
    result = run_guide("esp32marauder", llm_client=StubLLM("not json at all"), db_path=built_db_path)
    assert result["grounded"] is True
    assert result["boards"]
    assert result["summary"]


# --- 6. Every seeded firmware produces a fully-grounded answer --------------


def test_every_firmware_produces_a_grounded_answer_with_no_invented_boards(built_db_path):
    for fw in list_firmware():
        recipes = recipes_for_firmware(fw["id"])
        result = run_guide(fw["id"], llm_client=_QUIET, db_path=built_db_path)
        assert result["grounded"] is True, fw["id"]
        assert {b["board_id"] for b in result["boards"]} == {r["board"] for r in recipes}, fw["id"]
        assert result["citations"], f"{fw['id']} has no citations"
        for board in result["boards"]:
            # a firmware whose capabilities are all software-only (e.g. launcher's
            # ota/firmware-store) has no hardware requirement to reason about --
            # an empty reasons list is honest there, not a gap.
            if requirements_for_firmware(fw):
                assert board["reasons"], f"{fw['id']} x {board['board_id']} has no reasons"
            assert board["sources"], f"{fw['id']} x {board['board_id']} has no sources"


def test_requirements_for_firmware_never_duplicates_a_label():
    for fw in list_firmware():
        requirements = requirements_for_firmware(fw)
        assert len(requirements) == len(set(requirements)), fw["id"]


def test_get_firmware_still_works_as_the_id_lookup_run_guide_relies_on():
    assert get_firmware("esp32marauder")["name"] == "ESP32 Marauder"
    assert get_firmware("no-such-firmware") is None
