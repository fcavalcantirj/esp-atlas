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

from esp_atlas_core.build_guide import _deterministic_io_heavy, build_guide
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


# --- io_heavy: hard exclusion on cited GPIO counts (SPEC-io-power.md §6) ----

_IO_HEAVY_QUERY = "4 LED strips + 4 fans + sensors + UART data going in and out"

_FULL_HEADER_DEVKITS = {"esp32-s3-devkitc-1", "esp32-devkitc-v4", "esp32-c6-devkitc-1"}


def test_io_heavy_excludes_pin_poor_board_ranked_on_its_own_cited_count(built_db_path):
    """Without the fix, m5atoms3-lite (esphome recipe, cheap+wifi) tops this
    exact ranking on the old three-axis score alone -- SPEC-io-power.md §1's
    real prod bug. With io_heavy set, its OWN cited `io.gpio_exposed: 6`
    (docs.m5stack.com) is below the goal's ~11-line channel count, so it's
    hard-excluded, not merely demoted."""
    llm = _stub(
        {
            "firmware_id": "esphome",
            "why": "Reads sensors and reports over Wi-Fi.",
            "traits": {"wifi": True, "battery": False, "cheap": True, "io_heavy": True},
            "add_ons": [],
        }
    )
    result = build_guide(_IO_HEAVY_QUERY, llm_client=llm, db_path=built_db_path)

    board_ids = {b["board_id"] for b in result["boards"]}
    assert "m5atoms3-lite" not in board_ids

    # confirm the exclusion -- not a coincidence of ranking -- by proving that
    # a genuinely non-io_heavy goal (no output groups at all, so the A1
    # deterministic signal stays False too) puts m5atoms3-lite right back on
    # top. Reusing _IO_HEAVY_QUERY here would no longer prove anything: as of
    # BIBLE-PLAN.md A1 that exact query is DETERMINISTICALLY io_heavy no
    # matter what the stub says (see the A1 section below).
    baseline_llm = _stub(
        {
            "firmware_id": "esphome",
            "why": "Reads sensors and reports over Wi-Fi.",
            "traits": {"wifi": True, "battery": False, "cheap": True, "io_heavy": False},
            "add_ons": [],
        }
    )
    baseline = build_guide("a plant health monitor", llm_client=baseline_llm, db_path=built_db_path)
    assert baseline["boards"][0]["board_id"] == "m5atoms3-lite"


def test_io_heavy_surfaces_a_full_header_devkit_with_its_gpio_count_in_why(built_db_path):
    """Drives the REAL recipe path (SPEC-io-power.md §6 addendum): esphome is
    the firmware Groq actually matches for this exact goal (SPEC-io-power.md
    §1), and esphome's own recipe graph carries NO full-header devkit -- only
    pin-poor m5 display/tiny boards. The prior version of this golden stubbed
    firmware_id="wled" instead, whose recipe graph already ships two
    full-header devkits, so it passed without ever exercising the
    supplement-from-fallback path -- the actual prod bug (esphome's recipe
    pool having no adequate board) was invisible to it. m5atoms3-lite AND the
    now-cited pin-poor esphome boards (m5nanoc6, m5stack-core2,
    m5stack-cores3, m5dial) must all be excluded on their own cited/derived
    GPIO counts, and a full-header devkit must still surface, grounded in its
    own `gpio_free`."""
    llm = _stub(
        {
            "firmware_id": "esphome",
            "why": "Reads sensors and reports over Wi-Fi.",
            "traits": {"wifi": True, "battery": False, "cheap": True, "io_heavy": True},
            "add_ons": [],
        }
    )
    result = build_guide(_IO_HEAVY_QUERY, llm_client=llm, db_path=built_db_path)

    board_ids = {b["board_id"] for b in result["boards"]}
    for excluded in {"m5atoms3-lite", "m5nanoc6", "m5stack-core2", "m5stack-cores3", "m5dial"}:
        assert excluded not in board_ids, f"{excluded} has a known GPIO count below the goal's channel need"

    devkits = [b for b in result["boards"] if b["board_id"] in _FULL_HEADER_DEVKITS]
    assert devkits, f"expected a full-header devkit in {sorted(board_ids)}"
    assert "usable GPIO" in devkits[0]["why"]


def test_io_heavy_supplements_from_the_deterministic_fallback_when_no_recipe_board_is_confirmed_adequate(
    built_db_path,
):
    """The general SPEC-io-power.md §6 addendum mechanism, independent of the
    esphome-specific recipe fix above: `openmqttgateway`'s own recipe graph is
    a single board (esp32-c3-devkitm-1) with a cited GPIO count of 10, below
    the goal's channel need of 11 -- confirmed inadequate, not merely neutral.
    With no board in the recipe pool CONFIRMED adequate, a confirmed-adequate
    high-`gpio_free` board from the same deterministic `wizard()` pool
    `_boards_fallback` draws from must supplement the candidate set, so an
    io_heavy goal is never stranded on a firmware whose own recipe graph
    happens to be pin-poor. (Was `launcher` until BIBLE-PLAN.md A2 batch 1 gave
    `m5stick-s3` a cited `gpio_free: 11` -- exactly the goal's channel need --
    retiring `launcher` from this scenario; then `meshtastic` until BIBLE-PLAN.md
    A2 batch 6 gave three Heltec LoRa+display boards (`heltec-wifi-lora-32-v3`
    gpio_free=18, `heltec-wireless-paper`=14, `heltec-wireless-tracker`=11)
    cited `gpio_free` counts meeting the goal's channel need, making them
    genuine CONFIRMED-adequate members of `meshtastic`'s own recipe graph and
    retiring `meshtastic` from this scenario; `openmqttgateway` still has no
    confirmed-adequate recipe member.)"""
    from esp_atlas_core.firmware import recipes_for_firmware

    llm = _stub(
        {
            "firmware_id": "openmqttgateway",
            "why": "MQTT gateway bridging BLE/433MHz/IR devices onto the network.",
            "traits": {"wifi": True, "battery": False, "cheap": True, "io_heavy": True},
            "add_ons": [],
        }
    )
    result = build_guide(_IO_HEAVY_QUERY, llm_client=llm, db_path=built_db_path)

    recipe_boards = {r["board"] for r in recipes_for_firmware("openmqttgateway")}
    board_ids = {b["board_id"] for b in result["boards"]}
    assert board_ids - recipe_boards, "expected a supplemented board outside openmqttgateway's own recipe graph"

    for board in result["boards"]:
        record = get_part(board["board_id"], db_path=built_db_path)
        io = (record["frontmatter"] or {}).get("io") or {}
        known = io.get("gpio_free", io.get("gpio_exposed"))
        if board["board_id"] not in recipe_boards:
            assert known is not None and known >= 11, "a supplemented board must be a CONFIRMED-adequate board"


def test_io_heavy_never_excludes_a_board_with_no_cited_io_data(built_db_path):
    """Absence is neutral, never inventive (SPEC-io-power.md §7.3/§8.3): a
    board with no `io` record at all (most of the catalog, still) is never
    excluded and never gets an invented GPIO count -- it just can't win the
    `io_heavy` `why` bonus."""
    llm = _stub(
        {
            "firmware_id": "esphome",
            "why": "Reads sensors and reports over Wi-Fi.",
            "traits": {"wifi": True, "battery": False, "cheap": True, "io_heavy": True},
            "add_ons": [],
        }
    )
    result = build_guide(_IO_HEAVY_QUERY, llm_client=llm, db_path=built_db_path)
    assert result["boards"], "io_heavy must never wipe the list down to nothing"
    for board in result["boards"]:
        record = get_part(board["board_id"], db_path=built_db_path)
        io = (record["frontmatter"] or {}).get("io") or {}
        if io.get("gpio_free") is None and io.get("gpio_exposed") is None:
            continue  # no cited count -- correctly kept despite io_heavy
        known = io.get("gpio_free", io.get("gpio_exposed"))
        assert known >= 11, f"{board['board_id']} has a known count below the channel need and should be excluded"


# --- A1: deterministic-first io_heavy classification (BIBLE-PLAN.md A1) -----
# io_heavy must never depend solely on Groq's boolean -- the prod bug
# SPEC-io-power.md §1 documents was exactly Groq unreliably returning false
# for a goal that obviously needed it. The deterministic signal is OR'd with
# Groq's boolean and can never be pulled back to False by the model.


@pytest.mark.parametrize(
    "query, expected",
    [
        ("build a plant health monitor", False),
        ("a plant monitor", False),
        ("1 LED strip", False),
        ("a scrolling LED sign", False),
        ("off-grid text messaging", False),
        ("3 relays", False),
        ("1 relay and 1 servo", False),
        ("4 LED strips", True),
        ("4 LED strips + 4 fans + sensors + UART data going in and out", True),
        ("2 fans and 2 motors", True),
        ("2 relays and 3 servos", True),
    ],
)
def test_deterministic_io_heavy_predicate_table(query, expected):
    assert _deterministic_io_heavy(query) is expected


def test_io_heavy_fires_deterministically_even_when_the_llm_says_false(built_db_path):
    """Same exclusion/surfacing assertions as the io_heavy goldens above, but
    with the LLM explicitly stubbed io_heavy=False -- proving the DETERMINISTIC
    signal alone (not Groq's boolean) drives the exclusion and the
    full-header-devkit surfacing."""
    llm = _stub(
        {
            "firmware_id": "esphome",
            "why": "Reads sensors and reports over Wi-Fi.",
            "traits": {"wifi": True, "battery": False, "cheap": True, "io_heavy": False},
            "add_ons": [],
        }
    )
    result = build_guide(_IO_HEAVY_QUERY, llm_client=llm, db_path=built_db_path)

    board_ids = {b["board_id"] for b in result["boards"]}
    for excluded in {"m5atoms3-lite", "m5nanoc6", "m5stack-core2", "m5stack-cores3", "m5dial"}:
        assert excluded not in board_ids, f"{excluded} should be excluded by the deterministic signal alone"

    devkits = [b for b in result["boards"] if b["board_id"] in _FULL_HEADER_DEVKITS]
    assert devkits, f"expected a full-header devkit even with a false-stubbed LLM, got {sorted(board_ids)}"
    assert "usable GPIO" in devkits[0]["why"]


def test_single_peripheral_goal_is_not_treated_io_heavy_despite_a_false_stub(built_db_path):
    """A single-peripheral goal must never be spuriously excluded -- confirms
    the deterministic signal is not a blanket True, using the exact goal
    BIBLE-PLAN.md A1 names."""
    llm = _stub(
        {
            "firmware_id": "esphome",
            "why": "Reads sensors and reports to Home Assistant over Wi-Fi.",
            "traits": {"wifi": True, "battery": False, "cheap": True, "io_heavy": False},
            "add_ons": ["soil-moisture sensor"],
        }
    )
    result = build_guide("build a plant health monitor", llm_client=llm, db_path=built_db_path)
    assert result["boards"], "must still recommend real boards"
    board_ids = {b["board_id"] for b in result["boards"]}
    assert "m5atoms3-lite" in board_ids, "a single-peripheral goal must not spuriously exclude a pin-poor board"


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


# --- 8. answered_context (esp_atlas_core.clarify, SPEC-clarify.md §6) ------


def test_answered_context_firmware_hint_overrides_the_llm_pick(built_db_path):
    """A clarify()-shaped answered_context's firmware_hint anchors the answer
    even when the LLM (or fallback) picked something else entirely."""
    llm = _stub(
        {
            "firmware_id": "wled",
            "why": "a guess unrelated to the clarified answer",
            "traits": {"wifi": True, "battery": False, "cheap": True},
            "add_ons": [],
        }
    )
    result = build_guide(
        "build a plant health monitor",
        llm_client=llm,
        db_path=built_db_path,
        answered_context={"needs": {"radio": "wifi-4"}, "firmware_hint": "esphome"},
    )
    assert result["firmware"]["id"] == "esphome"
    assert result["boards"]


def test_answered_context_battery_need_surfaces_a_battery_capable_board(built_db_path):
    llm = _stub(
        {
            "firmware_id": "esphome",
            "why": "ok",
            "traits": {"wifi": True, "battery": False, "cheap": True},
            "add_ons": [],
        }
    )
    result = build_guide(
        "build a plant health monitor",
        llm_client=llm,
        db_path=built_db_path,
        answered_context={"needs": {"battery": True}, "firmware_hint": None},
    )
    boards = result["boards"]
    assert boards
    top = get_part(boards[0]["board_id"], db_path=built_db_path)
    assert ((top.get("frontmatter") or {}).get("power") or {}).get("battery_connector") is True


def test_answered_context_with_an_invented_firmware_hint_is_ignored(built_db_path):
    """A firmware_hint outside the real catalog must never surface -- same
    grounding rule as the LLM's own firmware_id (see test 4 above)."""
    llm = _stub(
        {
            "firmware_id": None,
            "why": "nothing fits",
            "traits": {"wifi": True, "battery": False, "cheap": True},
            "add_ons": [],
        }
    )
    result = build_guide(
        "build a plant health monitor",
        llm_client=llm,
        db_path=built_db_path,
        answered_context={"needs": {}, "firmware_hint": "totally-invented-firmware-xyz"},
    )
    assert result["firmware"] is None
    assert result["boards"]


def test_answered_context_none_is_a_no_op(built_db_path):
    """Default None must reproduce the exact same answer as omitting the
    argument entirely -- every existing call site (POST /build) is unaffected."""
    llm_a = _stub(
        {
            "firmware_id": "esphome",
            "why": "ok",
            "traits": {"wifi": True, "battery": False, "cheap": True},
            "add_ons": [],
        }
    )
    llm_b = _stub(llm_a.payload)
    without = build_guide("build a plant health monitor", llm_client=llm_a, db_path=built_db_path)
    with_none = build_guide(
        "build a plant health monitor", llm_client=llm_b, db_path=built_db_path, answered_context=None
    )
    assert without == with_none


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
