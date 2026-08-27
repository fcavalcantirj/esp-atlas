"""A reproducible COVERAGE MATRIX for run_guide (and parse_intent's firmware/
build-filter branches) across diverse ESP32 kinds, chip families and maker
purposes -- see docs/coverage-matrix.md for the human-readable table this test
pins, and ROADMAP.md for the gaps it deliberately surfaces rather than papers
over.

This is a CHARACTERIZATION harness, not a feature test: every assertion below
is the author's own verbatim expected ground truth, checked against CURRENT
run_guide/parse_intent behavior. It exists so a future change that silently
narrows or breaks a firmware/board/purpose combination fails loudly here,
and so a newly-added firmware is caught by test_every_firmware_has_a_run_case
before it can ship with zero coverage.

Only a DeadLLM is ever injected -- run_guide's/parse_intent's own deterministic
retrieval and validation is what's under test, never Groq's mood. No test in
this file may perform a real network call.

    pytest apps/core/tests/test_coverage_matrix.py -v
"""
import json

import pytest

from esp_atlas_core.firmware import get_firmware, list_firmware, recipes_for_firmware
from esp_atlas_core.intent import parse_intent
from esp_atlas_core.run_guide import run_guide


class DeadLLM:
    """Simulates an unreachable model -- run_guide/parse_intent must degrade to
    their deterministic path, never raise, never guess."""

    def complete(self, system_prompt, user_prompt, temperature=0):
        raise RuntimeError("DeadLLM: no network call is permitted in this test file")


_DEAD = DeadLLM()


def _board(result, board_id):
    return next(b for b in result["boards"] if b["board_id"] == board_id)


def _capabilities(entries):
    return {e["capability"] for e in entries if e.get("capability")}


# --- RUN matrix: firmware x diverse ESP32 kinds/purposes --------------------
#
# Each case names a firmware and the grounded, verbatim-expected truth about
# it: the hard capability ids `requires`/`not_required` must cover (superset,
# unless `requires_exact`/`not_required_exact` pins it closed), which boards
# the recipe graph must resolve to (`boards_exact`, when the set is small
# enough to pin), which board ids a wider recipe set must at least include
# (`recipe_includes`), and any per-board `fit` a maker would see.

RUN_MATRIX = [
    dict(
        id="1_esp32marauder",
        fw="esp32marauder",
        requires_superset={"wifi", "ble"},
        not_required_superset={"psram", "lora"},
        board_fits={"m5cardputer": "ideal", "m5stick-cplus2": "works"},
    ),
    dict(
        id="2_meshtastic",
        fw="meshtastic",
        requires_exact={"lora", "ble"},
        not_required_superset={"psram", "display"},
    ),
    dict(
        id="3_rogueduck",
        fw="rogueduck",
        requires_exact={"native-usb"},
        boards_exact={"m5stick-s3"},
        board_fits={"m5stick-s3": "ideal"},
    ),
    dict(
        id="4_wled",
        fw="wled",
        requires_superset={"wifi"},
        not_required_superset={"psram", "display"},
        board_fits={"esp32-c3-devkitm-1": "ideal"},
    ),
    dict(
        id="5_esphome",
        fw="esphome",
        requires_superset={"wifi"},
        not_required_superset={"psram"},
        recipe_includes={"soldered-inkplate-10", "soldered-inkplate-6"},
    ),
    dict(
        id="6_bruce",
        fw="bruce",
        requires_superset={"wifi", "ble"},
        board_fits={"m5stack-core2": "works"},
    ),
    dict(
        id="7_launcher",
        fw="launcher",
        requires_exact={"display"},
        not_required_superset={"wifi", "ble"},
        board_fits={"m5cardputer": "ideal"},
    ),
    dict(
        id="8_infiltra",
        fw="infiltra",
        requires_superset={"wifi", "ble", "sub-ghz"},
    ),
    dict(
        id="9_m5-crystal",
        fw="m5-crystal",
        requires_superset={"wifi", "ble", "rfid-nfc", "ir"},
    ),
    dict(
        id="10_m5stick-nemo",
        fw="m5stick-nemo",
        requires_superset={"wifi", "ble", "ir"},
    ),
    dict(
        id="11_xiaozhi-esp32",
        fw="xiaozhi-esp32",
        requires_exact={"wifi"},
        boards_exact={"m5stack-cores3"},
    ),
    dict(
        id="12_tasmota",
        fw="tasmota",
        requires_exact={"wifi"},
        not_required_exact={"display"},
        boards_exact={"esp32-devkitc-v4"},
    ),
    dict(
        id="13_esp32-bit-pirate",
        fw="esp32-bit-pirate",
        requires_exact={"wifi"},
        boards_exact={"m5cardputer"},
    ),
    dict(
        id="14_openmqttgateway",
        fw="openmqttgateway",
        requires_exact={"wifi", "ble"},
        boards_exact={"esp32-c3-devkitm-1"},
    ),
    dict(
        id="15_usbarmyknife",
        fw="usbarmyknife",
        requires_exact={"native-usb"},
        boards_exact={"lilygo-t-dongle-s3"},
    ),
    dict(
        id="16_nerdminer-v2",
        fw="nerdminer-v2",
        requires_exact={"wifi", "display"},
        boards_exact={"m5stick-cplus2"},
    ),
    dict(
        # thin record (no capabilities/requires yet) — grounds via its recipe; enrich later
        # to assert requires ⊇ {wifi} once the firmware record carries capabilities.
        id="17_evil-m5project",
        fw="evil-m5project",
    ),
]


@pytest.mark.parametrize("case", RUN_MATRIX, ids=[c["id"] for c in RUN_MATRIX])
def test_run_case(built_db_path, case):
    result = run_guide(case["fw"], llm_client=_DEAD, db_path=built_db_path)
    assert result["grounded"] is True, case["fw"]

    requires = _capabilities(result["requires"])
    not_required = _capabilities(result["not_required"])

    if "requires_exact" in case:
        assert requires == case["requires_exact"], case["fw"]
    if "requires_superset" in case:
        assert requires >= case["requires_superset"], case["fw"]
    if "not_required_exact" in case:
        assert not_required == case["not_required_exact"], case["fw"]
    if "not_required_superset" in case:
        assert not_required >= case["not_required_superset"], case["fw"]

    if "boards_exact" in case:
        assert {b["board_id"] for b in result["boards"]} == case["boards_exact"], case["fw"]
    if "recipe_includes" in case:
        assert case["recipe_includes"] <= {b["board_id"] for b in result["boards"]}, case["fw"]

    for board_id, expected_fit in case.get("board_fits", {}).items():
        assert _board(result, board_id)["fit"] == expected_fit, f"{case['fw']} x {board_id}"


# --- 1b. run_guide board ORDER: fit-ranked, best-fit-first --------------------
#
# boards[] must read best-fit-first: "ideal" boards before "works"/
# "works-with-tradeoff", and "unconfirmed" last of all -- a maker scanning top
# to bottom should never hit a lesser-fit board before a better one. This is
# an ordering contract distinct from the `fit` values themselves (pinned
# above via `board_fits`), so it gets its own rank map here rather than
# reaching into run_guide's private `_FIT_RANK`.

_ORDER_RANK = {"ideal": 0, "works": 1, "works-with-tradeoff": 1, "unconfirmed": 2}


def _fit_rank(fit):
    return _ORDER_RANK.get(fit, max(_ORDER_RANK.values()) + 1)


def test_bruce_ideal_boards_all_rank_before_works_boards(built_db_path):
    result = run_guide("bruce", llm_client=_DEAD, db_path=built_db_path)
    boards = result["boards"]
    ideal_indexes = [i for i, b in enumerate(boards) if b["fit"] == "ideal"]
    works_indexes = [i for i, b in enumerate(boards) if b["fit"] in ("works", "works-with-tradeoff")]
    assert ideal_indexes and works_indexes, "bruce must have both ideal and works boards to pin this"
    assert max(ideal_indexes) < min(works_indexes), boards


def test_launcher_unconfirmed_board_is_last(built_db_path):
    result = run_guide("launcher", llm_client=_DEAD, db_path=built_db_path)
    boards = result["boards"]
    unconfirmed_indexes = [i for i, b in enumerate(boards) if b["fit"] == "unconfirmed"]
    assert unconfirmed_indexes, "launcher must have an unconfirmed board to pin this"
    assert unconfirmed_indexes[-1] == len(boards) - 1, boards


@pytest.mark.parametrize("fw", ["bruce", "launcher", "esp32marauder"])
def test_board_fit_rank_sequence_is_non_decreasing(built_db_path, fw):
    result = run_guide(fw, llm_client=_DEAD, db_path=built_db_path)
    ranks = [_fit_rank(b["fit"]) for b in result["boards"]]
    assert ranks == sorted(ranks), f"{fw}: {[(b['board_id'], b['fit']) for b in result['boards']]}"


# --- 2. Meshtastic: LoRa/GPS reason must read MET/unconfirmed by real extras,
# never a stale "not verifiable" -- pins the same bug the run_guide oracle
# suite (test_run_guide_oracle.py) already guards, kept here too so the
# coverage matrix is self-contained. ---------------------------------------


def test_meshtastic_heltec_lora_reason_reads_met_not_unverifiable(built_db_path):
    result = run_guide("meshtastic", llm_client=_DEAD, db_path=built_db_path)
    board = _board(result, "heltec-wifi-lora-32-v3")
    lora_reasons = [r for r in board["reasons"] if "LoRa" in r]
    assert lora_reasons
    assert any("has" in r for r in lora_reasons)
    assert not any("not verifiable" in r for r in lora_reasons)


def test_meshtastic_tbeam_gps_reason_reads_met(built_db_path):
    result = run_guide("meshtastic", llm_client=_DEAD, db_path=built_db_path)
    board = _board(result, "lilygo-t-beam")
    gps_reasons = [r for r in board["reasons"] if "GPS" in r]
    assert gps_reasons
    assert any("has" in r for r in gps_reasons)


def test_meshtastic_xiao_esp32s3_lora_not_confirmed_no_false_onboard_claim(built_db_path):
    result = run_guide("meshtastic", llm_client=_DEAD, db_path=built_db_path)
    board = _board(result, "xiao-esp32s3")
    lora_reasons = [r for r in board["reasons"] if "LoRa" in r]
    assert lora_reasons
    assert not any("has" in r for r in lora_reasons)


# --- 3. BUILD/intent matrix: plain-language goal -> mapped filters ----------
#
# parse_intent's own mapping of prose to a need is an LLM judgment call, not a
# deterministic function -- so each case injects a DEAD-simulating stub that
# returns the filters an on-target parse would produce, and asserts that
# validate_filters/parse_intent's plumbing keeps them intact end to end
# (present in KNOWN_NEEDS, present in the live index's own facet values).
# This pins OUR contract (nothing a maker asked for is silently dropped or
# corrupted on the way to the wizard), not Groq's phrasing judgment.


class _FilterStub:
    def __init__(self, filters):
        self._filters = filters
        self.calls = 0

    def complete(self, system_prompt, user_prompt, temperature=0):
        self.calls += 1
        return json.dumps({"filters": self._filters, "unmapped": []})


BUILD_MATRIX = [
    dict(id="17_wifi6", query="a wifi 6 board", filters={"radio": "wifi-6"}, expect={"radio": "wifi-6"}),
    dict(
        id="18_thread_zigbee_matter",
        query="thread zigbee matter smart-home mesh",
        filters={"ieee802154": True},
        expect={"ieee802154": True},
    ),
    dict(
        id="19_s3_8mb_psram",
        query="esp32-s3 board with 8mb psram",
        filters={"soc": "esp32-s3", "psram_min": 8},
        expect={"soc": "esp32-s3", "psram_min": 8},
    ),
    dict(
        id="20_battery_wearable",
        query="a battery powered wearable",
        filters={"battery": True},
        expect={"battery": True},
    ),
    dict(
        id="21_c6_native_usb",
        query="esp32-c6 with native usb",
        filters={"soc": "esp32-c6", "usb_native": True},
        expect={"soc": "esp32-c6", "usb_native": True},
    ),
]


@pytest.mark.parametrize("case", BUILD_MATRIX, ids=[c["id"] for c in BUILD_MATRIX])
def test_build_case(built_db_path, case):
    stub = _FilterStub(case["filters"])
    result = parse_intent(case["query"], llm_client=stub, db_path=built_db_path, use_cache=False)
    assert result["kind"] == "filters", case["query"]
    for key, value in case["expect"].items():
        assert result["filters"].get(key) == value, f"{case['query']}: filters={result['filters']}"


# --- 4. Coverage assertion: every seeded firmware has a RUN case ------------
#
# Keeps this harness honest as data grows -- a new data/firmware/<id>/ with no
# matching RUN_MATRIX entry must fail here, not slip in silently uncovered.


def test_every_firmware_has_a_run_case():
    matrix_ids = {c["fw"] for c in RUN_MATRIX}
    seeded_ids = {fw["id"] for fw in list_firmware()}
    missing = seeded_ids - matrix_ids
    assert not missing, (
        f"firmware seeded with no coverage-matrix RUN case: {sorted(missing)} -- "
        "add a case to RUN_MATRIX in this file (and to docs/coverage-matrix.md)"
    )
    extra = matrix_ids - seeded_ids
    assert not extra, f"RUN_MATRIX names firmware no longer seeded: {sorted(extra)}"


def test_run_matrix_firmware_ids_are_real():
    for case in RUN_MATRIX:
        assert get_firmware(case["fw"]) is not None, case["fw"]


def test_boards_exact_cases_match_the_real_recipe_graph():
    for case in RUN_MATRIX:
        if "boards_exact" in case:
            recipe_boards = {r["board"] for r in recipes_for_firmware(case["fw"])}
            assert recipe_boards == case["boards_exact"], case["fw"]
