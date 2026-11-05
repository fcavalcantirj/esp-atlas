"""Trust-tier honesty for run_guide's top-level summary.

A recipe is a cited board x firmware edge with a trust tier (known-good,
reported, declared, unverified, broken) -- never proof the firmware runs. The
summary must say which boards HAVE a recipe and at which tier, never promote
an unverified pairing into "Known to run on", whether the text comes from the
deterministic fallback or from the model.

Hermetic: the recipe set is pinned in-test (monkeypatched over the real
`recipes_for_firmware`), boards come from the session's tmp-built db, and the
model is a stub -- nothing here reads or writes the data dirs' recipe state.
"""
import json

import pytest

from esp_atlas_core import run_guide as run_guide_mod
from esp_atlas_core.run_guide import run_guide, validate_grounded_output

CORE2_UNVERIFIED = {
    "id": "m5stack-core2__circuitpython",
    "type": "recipe",
    "board": "m5stack-core2",
    "firmware": "circuitpython",
    "status": "unverified",
    "chip_family": "esp32",
    "sources": [{"field": "*", "url": "https://github.com/adafruit/circuitpython", "verified": "2026-09-02"}],
    "reason": "the repo lists m5stack-core2 as a supported device.",
}

CARDPUTER_KNOWN_GOOD = {
    "id": "m5cardputer__circuitpython",
    "type": "recipe",
    "board": "m5cardputer",
    "firmware": "circuitpython",
    "status": "known-good",
    "chip_family": "esp32-s3",
    "sources": [{"field": "*", "url": "https://circuitpython.org/board/m5stack_cardputer/", "verified": "2026-09-02"}],
    "reason": "circuitpython.org has a download page for this board.",
}

OVERCLAIMS = ("known to run", "runs on", "run on")


class StubLLM:
    def __init__(self, payload):
        self.payload = payload

    def complete(self, system_prompt, user_prompt, temperature=0):
        return json.dumps(self.payload)


_QUIET = StubLLM({"summary": "", "boards": []})


@pytest.fixture
def pin_recipes(monkeypatch):
    def pin(*recipes):
        monkeypatch.setattr(run_guide_mod, "recipes_for_firmware", lambda _fid: [dict(r) for r in recipes])

    return pin


def _assert_no_overclaim(summary):
    lowered = summary.lower()
    for phrase in OVERCLAIMS:
        assert phrase not in lowered, f"{phrase!r} overclaims a recipe: {summary!r}"


# --- deterministic fallback --------------------------------------------------


def test_fallback_never_says_known_to_run_for_an_unverified_recipe(built_db_path, pin_recipes):
    pin_recipes(CORE2_UNVERIFIED)
    result = run_guide("circuitpython", llm_client=_QUIET, db_path=built_db_path)
    _assert_no_overclaim(result["summary"])
    assert "Boards with a recipe" in result["summary"]
    assert "Core2 (unverified" in result["summary"]


def test_fallback_keeps_the_unverified_caveat(built_db_path, pin_recipes):
    pin_recipes(CORE2_UNVERIFIED)
    result = run_guide("circuitpython", llm_client=_QUIET, db_path=built_db_path)
    assert "not confirmed for this board" in result["summary"]


def test_fallback_with_no_recipes_stays_scope_neutral(built_db_path, pin_recipes):
    pin_recipes(CORE2_UNVERIFIED)
    result = run_guide("circuitpython", constraints="esp32-c6", llm_client=_QUIET, db_path=built_db_path)
    _assert_no_overclaim(result["summary"])
    assert "No boards in esp-atlas matching esp32-c6 have a recipe for it yet." in result["summary"]


# --- LLM summary path --------------------------------------------------------


def test_llm_known_to_run_summary_cannot_reach_the_response(built_db_path, pin_recipes):
    pin_recipes(CORE2_UNVERIFIED)
    stub = StubLLM({"summary": "Known to run on: Core2.", "boards": []})
    result = run_guide("circuitpython", llm_client=stub, db_path=built_db_path)
    _assert_no_overclaim(result["summary"])
    assert "Core2 (unverified" in result["summary"]


def test_llm_summary_that_only_describes_the_firmware_is_kept_with_the_trust_line(built_db_path, pin_recipes):
    pin_recipes(CORE2_UNVERIFIED)
    described = "CircuitPython is a beginner-friendly Python for microcontrollers."
    result = run_guide("circuitpython", llm_client=StubLLM({"summary": described, "boards": []}), db_path=built_db_path)
    assert result["summary"].startswith(described)
    assert "Core2 (unverified" in result["summary"]


@pytest.mark.parametrize(
    "summary",
    [
        "Known to run on: Core2.",
        "CircuitPython runs on the Core2.",
        "CircuitPython works on m5stack-core2 out of the box.",
        "It is supported on the Core2.",
        "CircuitPython has been verified on Core2 hardware.",
        "The Core2 is compatible with CircuitPython.",
        "The Core2 is a great match for CircuitPython.",
    ],
)
def test_validator_rejects_a_summary_claiming_compatibility(summary):
    validated = validate_grounded_output(
        json.dumps({"summary": summary, "boards": []}),
        {"m5stack-core2"},
        {"m5stack-core2": {"https://github.com/adafruit/circuitpython"}},
        {"m5stack-core2": {}},
        {"m5stack-core2": {"id": "m5stack-core2", "name": "Core2"}},
    )
    assert validated["summary"] is None


# --- mixed trust tiers -------------------------------------------------------


def test_mixed_tiers_keep_each_boards_own_status_and_never_promote(built_db_path, pin_recipes):
    pin_recipes(CORE2_UNVERIFIED, CARDPUTER_KNOWN_GOOD)
    stub = StubLLM({"summary": "Known to run on: Core2, Cardputer.", "boards": []})
    for client in (_QUIET, stub):
        result = run_guide("circuitpython", llm_client=client, db_path=built_db_path)
        summary = result["summary"]
        _assert_no_overclaim(summary)
        assert "Core2 (unverified" in summary
        assert "Cardputer (known-good" in summary
        assert "Core2 (known-good" not in summary
        statuses = {b["board_id"]: b["status"] for b in result["boards"]}
        assert statuses == {"m5stack-core2": "unverified", "m5cardputer": "known-good"}
