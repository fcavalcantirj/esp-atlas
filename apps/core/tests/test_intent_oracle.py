"""ORACLE invariants for intent parsing (SPEC-INDEX G4).

The home's prompt promises understanding and must not deliver keyword noise.
These are properties that must hold for ANY parse, not examples of one: a parse
may only ever emit filters the deterministic wizard understands, with values
present in this index; whatever it cannot map must be reported rather than
dropped; and naming a firmware must never depend on a model being reachable.

The model itself is stubbed — these test OUR contract, not Groq's mood. Live
acceptance runs against real inference are recorded in the PR.
"""
import json

import pytest

from esp_atlas_core.intent import (
    describe,
    firmware_named_in,
    parse_intent,
    validate_filters,
)
from esp_atlas_core.search import _KNOWN_FILTERS
from esp_atlas_core.wizard import KNOWN_NEEDS, wizard


class StubLLM:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def complete(self, system_prompt, user_prompt, temperature=0):
        self.calls.append(user_prompt)
        return self.payload if isinstance(self.payload, str) else json.dumps(self.payload)


def _parse(built_db_path, payload, query="something"):
    return parse_intent(query, llm_client=StubLLM(payload), db_path=built_db_path, use_cache=False)


# --- 1. A parse is always replayable by the deterministic wizard -------------

def test_emitted_filters_are_always_wizard_needs(built_db_path):
    """Whatever the model says, the result must be a legal wizard query."""
    hostile = {
        "filters": {
            "battery": True,
            "sensor": "humidity",          # invented field
            "waterproof": True,            # invented field
            "psram_min": 3,                # not a real tier
            "form": "not-a-real-form",     # not in the data
            "radio": "wifi-9",             # not in the data
            "soc": "esp32-z9",             # not in the data
            "budget": "free",              # not a tier
            "band": 60,                    # not in the data
        },
        "unmapped": [],
    }
    parsed = _parse(built_db_path, hostile)
    assert set(parsed["filters"]) <= KNOWN_NEEDS
    # and it really runs — wizard() raises ValueError on an unknown need
    wizard(parsed["filters"], db_path=built_db_path)


def test_invented_fields_are_reported_not_silently_dropped(built_db_path):
    """A user must be able to see that 'waterproof' did not shape the results."""
    parsed = _parse(built_db_path, {"filters": {"battery": True, "waterproof": True}, "unmapped": ["humidity sensor"]})
    assert "battery" in parsed["filters"]
    assert "waterproof" not in parsed["filters"]
    assert any("waterproof" in u for u in parsed["unmapped"])
    assert "humidity sensor" in parsed["unmapped"]


@pytest.mark.parametrize("garbage", ['not json at all', '{"filters":', '```json\n{"filters": {}}\n```', ''])
def test_malformed_model_output_degrades_honestly(built_db_path, garbage):
    """A broken reply must never become a garbage query."""
    parsed = _parse(built_db_path, garbage)
    assert parsed["kind"] in {"filters", "unreadable"}
    assert set(parsed["filters"]) <= KNOWN_NEEDS


# --- 2. Honest fallback, never a silent keyword dump ------------------------

def test_nothing_mappable_is_explicitly_unreadable(built_db_path):
    parsed = _parse(built_db_path, {"filters": {}, "unmapped": ["blorp"]})
    assert parsed["kind"] == "unreadable"
    assert parsed["filters"] == {}
    assert parsed["unmapped"] == ["blorp"]


def test_type_alone_is_not_understanding(built_db_path):
    """'board' is scoping. Returning every board is the noise we are replacing."""
    parsed = _parse(built_db_path, {"filters": {"type": "board"}, "unmapped": ["waterproof"]})
    assert parsed["kind"] == "unreadable", "type-only must not masquerade as a understood intent"


# --- 3. Firmware routing never depends on a model ---------------------------

def test_naming_a_firmware_never_calls_the_model(built_db_path):
    """'run marauder' must work with no API key, no quota, no network."""
    stub = StubLLM({"filters": {"battery": True}, "unmapped": []})
    parsed = parse_intent("run marauder", llm_client=stub, db_path=built_db_path, use_cache=False)
    assert parsed["kind"] == "firmware"
    assert parsed["firmware"] == "esp32marauder"
    assert stub.calls == [], "the recipe graph answered; no inference was needed"


def test_every_firmware_is_routable_by_name(built_db_path):
    """No dead intents: each firmware in the catalogue must be findable by name."""
    from esp_atlas_core.firmware import list_firmware, recipes_for_firmware

    unroutable = []
    for fw in list_firmware():
        hit = firmware_named_in(f"run {fw['name']}")
        if not hit or hit[0]["id"] != fw["id"]:
            unroutable.append(fw["id"])
    assert not unroutable, f"firmware not routable from its own name: {unroutable}"


def test_firmware_routes_resolve_to_real_boards(built_db_path):
    """A firmware intent must land on boards, never an empty promise."""
    from esp_atlas_core.firmware import list_firmware

    for fw in list_firmware():
        parsed = parse_intent(f"run {fw['name']}", db_path=built_db_path, use_cache=False)
        assert parsed["kind"] == "firmware"
        assert parsed["boards"], f"{fw['id']} routed to zero boards"


# --- 4. Every understood parse actually resolves ----------------------------

def test_understood_filters_are_described_for_a_human(built_db_path):
    parsed = _parse(built_db_path, {"filters": {"battery": True, "psram_min": 8}, "unmapped": []})
    assert parsed["understood"], "the UI must be able to show what was understood"
    assert not any("type" in text for text in parsed["understood"])


def test_describe_covers_every_need_the_parser_can_emit():
    """A new filter must not appear as a raw key in the UI chips."""
    undescribed = []
    for need in sorted(KNOWN_NEEDS):
        if need == "type":
            continue  # scoping, deliberately rendered as nothing
        value = 2 if need.endswith("_min") else ("board" if need == "type" else True)
        chips = describe({need: value})
        if not chips or chips[0].startswith(f"{need}:"):
            undescribed.append(need)
    assert not undescribed, f"needs with no human wording: {undescribed}"


def test_validated_filters_are_a_subset_of_search_filters(built_db_path):
    """Whatever survives validation must be something search can actually apply."""
    filters, _ = validate_filters(
        {"battery": True, "psram_min": 8, "soc": "esp32-s3", "type": "board"}, db_path=built_db_path
    )
    assert set(filters) <= (_KNOWN_FILTERS | {"budget"})
    assert wizard(filters, db_path=built_db_path), "a valid parse must resolve to parts"
