"""build_guide(query) -> the grounded "here's what you need" answer for a
project goal that parse_intent() correctly calls "unmapped" (SPEC-build-guide.md).

    build_guide("build a plant health monitor")
    # -> {"goal": "build a plant health monitor",
    #     "needs": ["A Wi-Fi ESP32 board to run ESPHome", "soil-moisture sensor -- not a board esp-atlas catalogs"],
    #     "firmware": {"id": "esphome", "name": "ESPHome", "why": "..."},
    #     "boards": [{"board_id": "m5nanoc6", "board_name": "M5NanoC6", "why": "Wi-Fi wifi-6 (2.4, 5 GHz), cheap price tier"}, ...],
    #     "add_ons": ["soil-moisture sensor"],
    #     "note": "esp-atlas catalogs firmware and boards, not soil-moisture sensor -- ..."}

`parse_intent` already tells the truth about "unmapped" -- the catalog has no
board FIELD for "plant health monitor". But that leaves a maker with nothing
to act on. This module mirrors `esp_atlas_core.ask`/`run_guide`'s grounding
discipline to turn "I can't narrow this" into an actual answer:

1. **Firmware is constrained to the real catalog.** Groq is given the goal
   plus the ACTUAL `list_firmware()` list and picks ONE id from it (or null).
   A returned id outside that list is rejected outright -- treated as null,
   never surfaced. This is the only thing an LLM decides.
2. **Boards are never chosen by the model at all.** Selection is 100%
   deterministic: the firmware's own `recipes_for_firmware()` set (ranked by
   real board columns against the traits Groq named), or -- no firmware fits
   -- cheap Wi-Fi boards straight from `wizard()`. The LLM's reply is never
   even read for a board id, so a hostile model naming a fake board has
   nowhere to leak it.
3. **Every board's `why` is built from that board's own real record**
   (Wi-Fi standard/bands, price tier, battery connector) -- never LLM prose.
4. **Add-ons are named, not dropped.** Whatever the goal needs beyond a
   firmware+board (a sensor, camera, motor...) becomes `add_ons`, stated
   plainly as "not a board esp-atlas catalogs".
5. **Groq unreachable/rate-limited/garbage -> deterministic fallback,
   never raises.** A keyword matcher applies the SAME project->firmware
   table taught to Groq as few-shot, and boards still come from the same
   deterministic retrieval -- the fallback is exactly as grounded, just
   without a `why` sentence or add-ons a down model can't be asked for.
"""
import json

from esp_atlas_core.examples import describe_firmware
from esp_atlas_core.firmware import get_firmware, list_firmware, recipes_for_firmware
from esp_atlas_core.llm import FAST_MODEL, GroqClient
from esp_atlas_core.search import get_part
from esp_atlas_core.wizard import wizard

_BOARD_LIMIT = 4
_MAX_ADD_ONS = 5

_NO_FIRMWARE_NOTE = "No ready-made firmware in esp-atlas fits this goal -- you'd write your own on a Wi-Fi ESP32."

# The SAME project->firmware intuition taught to Groq as few-shot below, kept
# here as a deterministic keyword matcher for when the model is unreachable
# or returns garbage -- so the headline cases never depend on Groq being up.
# Ordered most-specific-category first; the first matching keyword wins.
_FALLBACK_KEYWORDS = (
    ("rogueduck", ("badusb", "keystroke injection", "rubber ducky", "hid injection", "keystroke")),
    ("wled", ("led strip", "led sign", "scrolling led", "led matrix", "neopixel", "addressable led")),
    ("meshtastic", ("off-grid", "off grid", "long-range", "long range", "mesh network", "gps tracker", "lora mesh")),
    ("launcher", ("app loader", "app-loader", "multi-tool", "multi tool", "firmware switcher", "firmware launcher")),
    ("bruce", ("deauth", "wifi pentest", "wi-fi pentest", "wardriving", "wifi recon", "ble pentest")),
    ("esphome", ("plant", "sensor", "monitor", "environment", "home automation", "dashboard", "humidity", "temperature")),
)


def _fallback_firmware_id(query):
    lowered = query.lower()
    valid_ids = {fw["id"] for fw in list_firmware()}
    for firmware_id, keywords in _FALLBACK_KEYWORDS:
        if firmware_id not in valid_ids:
            continue
        if any(keyword in lowered for keyword in keywords):
            return firmware_id
    return None


def _catalog_block():
    lines = []
    for fw in list_firmware():
        description = describe_firmware(fw) or fw.get("category") or ""
        lines.append(f"- {fw['id']}: {fw['name']} ({description})")
    return "\n".join(lines)


SYSTEM_PROMPT = """You pick the single best-fit firmware for a maker's build goal from a REAL
catalog, and name what a board for it needs.

Reply with JSON only, no prose, in exactly this shape:
{"firmware_id": "<an id from the catalog below, or null>",
 "why": "<=1 sentence: why this firmware fits the goal>",
 "traits": {"wifi": true|false, "battery": true|false, "cheap": true|false},
 "add_ons": ["<a physical thing the goal needs that is NOT a firmware or a board -- a sensor, camera, screen, motor>", ...]}

RULES:
- firmware_id MUST be one of the ids in the catalog below, spelled exactly, or
  null if nothing in the catalog fits. NEVER invent an id.
- wifi: true for almost any goal that reads a sensor, reports a value, serves
  a UI, or otherwise talks to a network -- true for nearly every "monitor" /
  "dashboard" / "tracker" style goal, false for a purely local tool (BadUSB).
- battery: true ONLY when the goal states or implies portable, wearable,
  outdoor, or battery/solar power. Otherwise false -- never guess portable.
- cheap: true by default. false only if the goal explicitly asks for a
  premium/high-end part.
- add_ons: name the physical thing(s) the goal needs beyond a board+firmware --
  short, plain nouns (e.g. "soil-moisture sensor", "camera module"). Empty
  list if the goal needs nothing beyond a board and firmware.

Project -> firmware intuition (apply the SAME reasoning to any wording):
- plant / environment / soil / humidity / temperature sensor, home dashboard -> esphome (home automation: sensors to Home Assistant over YAML, no code)
- LED strip / sign / lighting / matrix -> wled
- off-grid messaging / long-range comms / GPS tracker -> meshtastic
- Wi-Fi/BLE pentest, deauth, recon, wardriving -> bruce or esp32marauder
- BadUSB / keystroke injection -> rogueduck
- app-loader / multi-tool / firmware switcher -> launcher
- nothing in the catalog fits (a robot's motor control, a synth, a purely
  mechanical build) -> null, and say so plainly in `why`.

Firmware catalog:
__CATALOG__"""


def _valid_firmware_ids():
    return {fw["id"] for fw in list_firmware()}


def _parse_json(text):
    """The model is asked for JSON only; tolerate a fenced block around it."""
    body = (text or "").strip()
    if body.startswith("```"):
        body = body.split("```")[1]
        if body.startswith("json"):
            body = body[4:]
    start, end = body.find("{"), body.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(body[start : end + 1])
    except json.JSONDecodeError:
        return None


def _sanitize_add_ons(raw):
    seen = set()
    out = []
    for item in raw or []:
        text = str(item).strip()
        if not text or text.lower() in seen:
            continue
        seen.add(text.lower())
        out.append(text)
        if len(out) >= _MAX_ADD_ONS:
            break
    return out


def _validate_llm_output(raw, valid_ids):
    """The grounding gate for the LLM's reply -- keeps ONLY a firmware id that
    is really in the catalog (anything else becomes null), coerces traits to
    booleans with the documented defaults, and sanitizes add_ons. Never reads
    any other key the model might have added (e.g. a hallucinated `boards`
    list) -- board selection never looks at the model's reply at all."""
    firmware_id = raw.get("firmware_id")
    if firmware_id not in valid_ids:
        firmware_id = None

    why = raw.get("why")
    why = why.strip() if isinstance(why, str) and why.strip() else None

    traits_raw = raw.get("traits") if isinstance(raw.get("traits"), dict) else {}
    traits = {
        "wifi": bool(traits_raw.get("wifi", True)),
        "battery": bool(traits_raw.get("battery", False)),
        "cheap": bool(traits_raw.get("cheap", True)),
    }

    return {
        "firmware_id": firmware_id,
        "why": why,
        "traits": traits,
        "add_ons": _sanitize_add_ons(raw.get("add_ons")),
    }


_DEFAULT_TRAITS = {"wifi": True, "battery": False, "cheap": True}


def _board_why(board, traits):
    facts = []
    standard = board.get("wifi_standard")
    if standard:
        bands = [b.strip() for b in (board.get("wifi_bands") or "").split(",") if b.strip()]
        facts.append(f"Wi-Fi {standard}" + (f" ({', '.join(bands)} GHz)" if bands else ""))
    if traits.get("battery"):
        has_battery = ((board.get("frontmatter") or {}).get("power") or {}).get("battery_connector")
        facts.append("has a battery connector" if has_battery else "no battery connector -- wired power only")
    if board.get("price_tier"):
        facts.append(f"{board['price_tier']} price tier")
    return ", ".join(facts) if facts else f"{board['name']} is in the esp-atlas catalog"


def _board_score(board, traits):
    score = 0
    if traits.get("wifi") and board.get("wifi_standard"):
        score += 1
    if traits.get("battery"):
        has_battery = ((board.get("frontmatter") or {}).get("power") or {}).get("battery_connector")
        if has_battery:
            score += 2
    if traits.get("cheap") and board.get("price_tier") == "cheap":
        score += 1
    return score


def _rank_boards(boards, traits):
    return sorted(boards, key=lambda b: (-_board_score(b, traits), b["name"]))


def _boards_for_firmware(firmware_id, traits, db_path):
    boards = []
    for recipe in recipes_for_firmware(firmware_id):
        board = get_part(recipe["board"], db_path=db_path)
        if board is not None:
            boards.append(board)
    return _rank_boards(boards, traits)[:_BOARD_LIMIT]


def _boards_fallback(traits, db_path):
    needs = {"type": "board"}
    if traits.get("wifi", True):
        needs["radio"] = "wifi-4"
    if traits.get("battery"):
        needs["battery"] = True
    if traits.get("cheap"):
        needs["budget"] = "cheap"
    records = wizard(needs, db_path=db_path, limit=50)
    boards = []
    for record in records:
        board = get_part(record["id"], db_path=db_path)
        if board is not None:
            boards.append(board)
    return _rank_boards(boards, traits)[:_BOARD_LIMIT]


def _needs_lines(firmware, traits, add_ons):
    lines = []
    if firmware:
        battery_bit = ", battery-powered" if traits.get("battery") else ""
        radio_bit = "Wi-Fi " if traits.get("wifi") else ""
        lines.append(f"A {radio_bit}ESP32 board{battery_bit} to run {firmware['name']}")
    else:
        lines.append("A Wi-Fi ESP32 board -- no ready-made firmware fits this goal, you'd write your own")
    for add_on in add_ons:
        lines.append(f"{add_on} -- not a board esp-atlas catalogs")
    return lines


def _addons_note(add_ons):
    if not add_ons:
        return None
    if len(add_ons) == 1:
        joined = add_ons[0]
    else:
        joined = ", ".join(add_ons)
    return f"esp-atlas catalogs firmware and boards, not {joined} -- that's an add-on part you source and wire yourself."


def _note(firmware, add_ons):
    addons_note = _addons_note(add_ons)
    if firmware is None:
        return f"{_NO_FIRMWARE_NOTE} {addons_note}" if addons_note else _NO_FIRMWARE_NOTE
    return addons_note


def _resolve_parse(query, llm_client, valid_ids):
    """The LLM call, fully guarded -- any failure (down/rate-limited/garbage)
    returns None so the caller falls back to the deterministic path. Mirrors
    run_guide's try/except-around-the-model pattern: this function must never
    raise, so build_guide() itself never needs a try/except at its callsite."""
    client = llm_client or GroqClient(model=FAST_MODEL)
    system_prompt = SYSTEM_PROMPT.replace("__CATALOG__", _catalog_block())
    try:
        raw_text = client.complete(system_prompt, query, temperature=0)
    except Exception:
        return None
    raw = _parse_json(raw_text)
    if raw is None or not isinstance(raw, dict):
        return None
    return _validate_llm_output(raw, valid_ids)


def build_guide(query, llm_client=None, db_path=None):
    """A grounded "here's what you need" answer for a project goal -- see
    module docstring for the shape and the honesty guarantees. Never raises:
    a down/rate-limited/garbage model degrades to a deterministic, still-
    grounded answer (keyword firmware match + cheap Wi-Fi boards)."""
    valid_ids = _valid_firmware_ids()
    parsed = _resolve_parse(query, llm_client, valid_ids)

    if parsed is not None:
        firmware_id = parsed["firmware_id"]
        why = parsed["why"]
        traits = parsed["traits"]
        add_ons = parsed["add_ons"]
    else:
        fallback_id = _fallback_firmware_id(query)
        firmware_id = fallback_id if fallback_id in valid_ids else None
        why = None
        traits = dict(_DEFAULT_TRAITS)
        add_ons = []

    firmware_record = get_firmware(firmware_id) if firmware_id else None

    if firmware_record:
        boards = _boards_for_firmware(firmware_record["id"], traits, db_path)
        if not boards:  # a recipe-less firmware would otherwise be a dead end -- degrade to the catalog
            boards = _boards_fallback(traits, db_path)
    else:
        boards = _boards_fallback(traits, db_path)

    firmware_out = None
    if firmware_record:
        firmware_out = {
            "id": firmware_record["id"],
            "name": firmware_record["name"],
            "why": why or describe_firmware(firmware_record) or f"{firmware_record['name']} fits this goal.",
        }

    boards_out = [
        {"board_id": board["id"], "board_name": board["name"], "why": _board_why(board, traits)} for board in boards
    ]

    return {
        "goal": query,
        "needs": _needs_lines(firmware_out, traits, add_ons),
        "firmware": firmware_out,
        "boards": boards_out,
        "add_ons": add_ons,
        "note": _note(firmware_out, add_ons),
    }
