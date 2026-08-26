"""ORACLE invariants for clarify (SPEC-clarify.md) -- confidence-gated
clarification. The confidence gate itself is deterministic (a pure function
of parse_intent()'s own output plus folded answers, never an LLM number); the
only LLM call in this module picks WHICH 1-3 questions to ask, from a FIXED
code-defined dimension catalog it can select/order but never author.

The model is stubbed throughout -- these test OUR contract, not Groq's mood.
No test in this file may perform a real network call.
"""
import json

import pytest

from esp_atlas_core.build_guide import build_guide
from esp_atlas_core.clarify import _CATALOG, clarify
from esp_atlas_core.search import get_part


class StubLLM:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def complete(self, system_prompt, user_prompt, temperature=0):
        self.calls.append({"system": system_prompt, "user": user_prompt})
        return self.payload if isinstance(self.payload, str) else json.dumps(self.payload)


class RaisingLLM:
    def complete(self, system_prompt, user_prompt, temperature=0):
        raise RuntimeError("Groq is down")


class SequenceLLM:
    """A different reply per call -- clarify() calls the LLM once for
    parse_intent's own filter parse, and (only when not confident) once more
    for question selection. This lets a test pin both replies precisely."""

    def __init__(self, payloads):
        self._payloads = list(payloads)
        self.calls = []

    def complete(self, system_prompt, user_prompt, temperature=0):
        self.calls.append(user_prompt)
        payload = self._payloads.pop(0)
        return payload if isinstance(payload, str) else json.dumps(payload)


def _all_needs_keys():
    keys = set()
    for dimension in _CATALOG.values():
        for option in dimension["options"]:
            keys.update(option["needs"])
    return keys


# --- 1. Acceptance: naming a firmware is always confident, no questions -----


def test_run_marauder_is_confident_with_no_questions(built_db_path):
    result = clarify("run marauder", db_path=built_db_path)
    assert result["confident"] is True
    assert result["confidence"] == 1.0
    assert result["questions"] == []


def test_naming_a_firmware_never_calls_the_model(built_db_path):
    stub = StubLLM({"filters": {"battery": True}, "unmapped": []})
    clarify("run marauder", llm_client=stub, db_path=built_db_path)
    assert stub.calls == [], "the recipe graph answered; no inference was needed"


# --- 2. Acceptance: >= 2 explicit specs is confident -------------------------


def test_two_explicit_specs_is_confident(built_db_path):
    stub = StubLLM({"filters": {"soc": "esp32-s3", "psram_min": 8}, "unmapped": []})
    result = clarify("esp32-s3 with 8mb psram", llm_client=stub, db_path=built_db_path)
    assert result["confident"] is True
    assert result["confidence"] == 1.0
    assert result["questions"] == []


def test_a_single_weak_spec_is_not_confident(built_db_path):
    stub = SequenceLLM(
        [
            {"filters": {"battery": True}, "unmapped": []},
            {"question_ids": ["power", "target"]},
        ]
    )
    result = clarify("something portable", llm_client=stub, db_path=built_db_path, use_cache=False)
    assert result["confident"] is False
    assert result["confidence"] == 0.5
    assert result["questions"]


# --- 3. Acceptance: an unmapped build goal is grounded, not confident -------


def test_plant_health_monitor_is_not_confident_and_returns_grounded_questions(built_db_path):
    stub = SequenceLLM(
        [
            {"filters": {"type": "board"}, "unmapped": ["plant health monitor"]},
            {"question_ids": ["target", "power", "budget"]},
        ]
    )
    result = clarify("build a plant health monitor", llm_client=stub, db_path=built_db_path, use_cache=False)

    assert result["confident"] is False
    assert 1 <= len(result["questions"]) <= 3

    known_ids = set(_CATALOG)
    known_needs = _all_needs_keys()
    for question in result["questions"]:
        assert question["id"] in known_ids
        assert question["prompt"] == _CATALOG[question["id"]]["prompt"]
        assert question["options"]
        for option in question["options"]:
            assert option["label"]
            assert set(option["needs"]) <= known_needs


# --- 4. Answering folds into needs/context and can cross the confidence line


def test_answering_target_ha_and_power_battery_becomes_confident(built_db_path):
    stub = StubLLM({"filters": {"type": "board"}, "unmapped": ["plant health monitor"]})
    result = clarify(
        "build a plant health monitor",
        answers={"target": "ha", "power": "battery"},
        llm_client=stub,
        db_path=built_db_path,
        use_cache=False,
    )
    assert result["confident"] is True
    assert result["confidence"] == 1.0
    assert result["questions"] == []
    assert result["answered_context"]["needs"] == {"radio": "wifi-4", "battery": True}
    assert result["answered_context"]["firmware_hint"] == "esphome"


def test_answered_context_anchors_build_guide_on_esphome_with_a_battery_board(built_db_path):
    intent_stub = StubLLM({"filters": {"type": "board"}, "unmapped": ["plant health monitor"]})
    clarified = clarify(
        "build a plant health monitor",
        answers={"target": "ha", "power": "battery"},
        llm_client=intent_stub,
        db_path=built_db_path,
        use_cache=False,
    )
    assert clarified["confident"] is True

    build_stub = StubLLM(
        {
            "firmware_id": None,
            "why": "nothing obviously fits",
            "traits": {"wifi": False, "battery": False, "cheap": False},
            "add_ons": ["soil-moisture sensor"],
        }
    )
    result = build_guide(
        "build a plant health monitor",
        llm_client=build_stub,
        db_path=built_db_path,
        answered_context=clarified["answered_context"],
    )

    assert result["firmware"]["id"] == "esphome"
    assert result["boards"], "must recommend at least one real board"
    battery_boards = []
    for board in result["boards"]:
        record = get_part(board["board_id"], db_path=built_db_path)
        assert record is not None
        if ((record.get("frontmatter") or {}).get("power") or {}).get("battery_connector"):
            battery_boards.append(board["board_id"])
    assert battery_boards, "the battery trait must surface at least one battery-capable board"


def test_answering_an_unknown_option_value_is_ignored_not_invented(built_db_path):
    stub = StubLLM({"filters": {"type": "board"}, "unmapped": ["plant health monitor"]})
    result = clarify(
        "build a plant health monitor",
        answers={"power": "some-made-up-value", "not-a-real-dimension": "x"},
        llm_client=stub,
        db_path=built_db_path,
        use_cache=False,
    )
    assert result["answered_context"]["needs"] == {}
    assert result["answered_context"]["firmware_hint"] is None


# --- 5. Question selection: Groq unreachable -> deterministic default order -


def test_groq_unreachable_for_question_selection_falls_back_to_default_order(built_db_path):
    class RaisesOnSecondCall:
        def __init__(self):
            self.calls = 0

        def complete(self, system_prompt, user_prompt, temperature=0):
            self.calls += 1
            if self.calls == 1:
                return json.dumps({"filters": {"type": "board"}, "unmapped": ["plant health monitor"]})
            raise RuntimeError("Groq is down")

    result = clarify(
        "build a plant health monitor", llm_client=RaisesOnSecondCall(), db_path=built_db_path, use_cache=False
    )
    assert result["confident"] is False
    assert [q["id"] for q in result["questions"]] == ["target", "power", "environment"]


def test_groq_returns_garbage_for_question_selection_falls_back_to_default_order(built_db_path):
    stub = SequenceLLM(
        [
            {"filters": {"type": "board"}, "unmapped": ["plant health monitor"]},
            "not json at all",
        ]
    )
    result = clarify("build a plant health monitor", llm_client=stub, db_path=built_db_path, use_cache=False)
    assert result["confident"] is False
    assert [q["id"] for q in result["questions"]] == ["target", "power", "environment"]


# --- 6. Grounding validator: an invented question id is dropped, never surfaced


def test_invented_question_id_is_rejected_never_surfaced(built_db_path):
    stub = SequenceLLM(
        [
            {"filters": {"type": "board"}, "unmapped": ["plant health monitor"]},
            {"question_ids": ["target", "totally-invented-dimension", "power"]},
        ]
    )
    result = clarify("build a plant health monitor", llm_client=stub, db_path=built_db_path, use_cache=False)
    ids = [q["id"] for q in result["questions"]]
    assert "totally-invented-dimension" not in ids
    assert ids == ["target", "power"]


def test_a_reply_with_only_invented_ids_falls_back_to_default_order(built_db_path):
    stub = SequenceLLM(
        [
            {"filters": {"type": "board"}, "unmapped": ["plant health monitor"]},
            {"question_ids": ["nope", "also-nope"]},
        ]
    )
    result = clarify("build a plant health monitor", llm_client=stub, db_path=built_db_path, use_cache=False)
    assert [q["id"] for q in result["questions"]] == ["target", "power", "environment"]


# --- 7. Edge / battle cases --------------------------------------------------


def test_empty_answers_dict_behaves_like_no_answers(built_db_path):
    stub = SequenceLLM(
        [
            {"filters": {"type": "board"}, "unmapped": ["plant health monitor"]},
            {"question_ids": ["target", "power"]},
        ]
    )
    result = clarify("build a plant health monitor", answers={}, llm_client=stub, db_path=built_db_path)
    assert result["confident"] is False
    assert result["answered_context"] == {"needs": {}, "firmware_hint": None}


def test_answers_supplied_for_a_firmware_query_stay_confident(built_db_path):
    result = clarify(
        "run marauder",
        answers={"target": "ha", "power": "battery"},
        db_path=built_db_path,
    )
    assert result["confident"] is True
    assert result["questions"] == []


def test_unmapped_query_with_all_dimensions_already_answered_has_no_more_questions(built_db_path):
    stub = StubLLM({"filters": {"type": "board"}, "unmapped": ["a mystery gadget"]})
    result = clarify(
        "a mystery gadget",
        answers={
            "power": "plugged",
            "environment": "indoor",
            "target": "standalone",
            "interaction": "headless",
            "budget": "pricier",
        },
        llm_client=stub,
        db_path=built_db_path,
    )
    # every negative option contributes zero needs keys, so confidence stays low
    assert result["confident"] is False
    assert result["questions"] == []


@pytest.mark.parametrize("garbage", ["not json at all", '{"filters":', "```json\n{}\n```", ""])
def test_gibberish_query_degrades_honestly(built_db_path, garbage):
    result = clarify("asdfqwer zzzz", llm_client=StubLLM(garbage), db_path=built_db_path, use_cache=False)
    assert result["confident"] is False
    assert isinstance(result["questions"], list)
