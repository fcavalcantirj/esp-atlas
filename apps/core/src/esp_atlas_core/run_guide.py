"""run_guide(firmware_id) -> a grounded, cited, REASONED answer to "why does
firmware X run on board Y" -- the run-answer counterpart to esp_atlas_core.ask.

Today's /intent firmware branch (esp_atlas_core.intent) only echoes the recipe's
own boilerplate reason ("the supported list says so") -- a lookup, not
reasoning. run_guide mirrors ask()'s pattern instead: retrieval is entirely
deterministic (the firmware's own capabilities, the recipe graph, and each
board's real specs straight from esp_atlas_core.search.get_part), and an LLM
is used only to EXPLAIN that already-computed fit in prose. It never fetches
or invents a fact.

    run_guide("esp32marauder")
    # -> {"firmware": "esp32marauder", "firmware_name": "ESP32 Marauder",
    #     "summary": "...", "requirements": ["2.4GHz Wi-Fi", "Bluetooth LE"],
    #     "boards": [{"board_id": "m5cardputer", "fit": "ideal",
    #                  "reasons": ["needs 2.4GHz Wi-Fi -> Cardputer has Wi-Fi wifi-4 (2.4 GHz)", ...,
    #                              "benefits from storage -> Cardputer has a microSD card slot"],
    #                  "particularities": ["esp32-s3 chip", "no PSRAM -- ESP32 Marauder does not need it", ...],
    #                  "status": "known-good", "chip_family": "esp32-s3",
    #                  "sources": [...], "note": "..."}, ...],
    #     "flash_next": [...], "citations": [...], "grounded": True}

Three things keep this honest ("nothing guessed, nothing invented"):

1. **The board set is closed over the recipe graph.** boards[] can only ever be
   the boards `recipes_for_firmware` already lists -- the LLM is never asked
   which boards run a firmware, only to explain a fit that was already decided
   by deterministic retrieval.
2. **Every reason is grounded in a real `parts` column**, computed here, never
   by the model: `_board_reasons` checks each of the firmware's own authored
   `requires` entries (never the looser `capabilities` list) against the
   board_signal it names -- the same columns esp_atlas_core.search filters on
   -- and states plainly when a capability cannot be proven from structured
   data, rather than guessing either way.
3. **A grounding validator (`validate_grounded_output`) gates every LLM
   sentence** before it can reach the response: a board id outside the recipe
   set, a source URL outside that board's own recorded sources, or a spec
   claim (a GHz band, a Bluetooth Classic claim, an MB figure) that
   contradicts the board's real record is rejected outright -- the whole note
   is dropped, not sanitized, so a partially-hallucinated sentence can never
   surface. `boards[].reasons`/`fit`/`sources` are never touched by this path
   at all; only the optional `boards[].note` and top-level `summary` come from
   the model, and both fall back to deterministic, template-only text if the
   model is unreachable, rate-limited, or returns garbage.
"""
import json
import re

from esp_atlas_core.examples import describe_firmware
from esp_atlas_core.firmware import get_firmware, recipes_for_firmware
from esp_atlas_core.llm import FAST_MODEL, GroqClient
from esp_atlas_core.search import get_part

NOT_FOUND_ANSWER = "That's not in esp-atlas yet — you can add it with a pull request."


def _match_wifi(board):
    standard = board.get("wifi_standard")
    bands = [b.strip() for b in (board.get("wifi_bands") or "").split(",") if b.strip()]
    if standard and "2.4" in bands:
        return True, f"Wi-Fi {standard} ({', '.join(bands)} GHz)"
    return False, f"wifi_standard={standard!r}, wifi_bands={board.get('wifi_bands')!r}"


def _match_ble(board):
    version = board.get("ble_version")
    if version:
        return True, f"BLE {version}"
    return False, f"ble_version={version!r}"


# firmware.schema.json `benefits_from` -- a closed vocab of SOFT/UX capabilities a
# firmware benefits from beyond its hard `capabilities`, each provable (present or
# absent) from a board's own structured frontmatter fields. Never a gate on fit,
# only a teaching point: a firmware missing one still runs, just with a named
# tradeoff (see `_fit_for`).
_BENEFIT_LABELS = {
    "display": "a display",
    "storage": "storage",
    "battery": "a battery",
    "usb-native": "native USB",
    "gps": "GPS",
}


def _benefit_display(board):
    display = (board.get("frontmatter") or {}).get("display")
    if display:
        return True, f"has a {display} display"
    return False, "record shows no on-board display"


def _benefit_storage(board):
    extras = (board.get("frontmatter") or {}).get("extras") or []
    if "sd-card" in extras:
        return True, "has a microSD card slot"
    return False, "record shows no on-board microSD to store captures"


def _benefit_battery(board):
    battery = ((board.get("frontmatter") or {}).get("power") or {}).get("battery_connector")
    if battery:
        return True, "has a battery connector"
    return False, "record shows no battery connector"


def _benefit_usb_native(board):
    if board.get("usb_native") is True:
        return True, "has native USB"
    return False, "record shows no native USB (bridge chip only)"


def _benefit_gps(board):
    extras = (board.get("frontmatter") or {}).get("extras") or []
    if "gps" in extras:
        return True, "has an on-board GPS module"
    return False, "record shows no on-board GPS module"


_BENEFIT_MATCHERS = {
    "display": _benefit_display,
    "storage": _benefit_storage,
    "battery": _benefit_battery,
    "usb-native": _benefit_usb_native,
    "gps": _benefit_gps,
}


def _benefit_reasons(benefits, board):
    """Every soft benefit a firmware's own `benefits_from` names, checked against
    ONE board's real record -- same honesty contract as `_board_reasons`: teach
    the tradeoff by name (e.g. no microSD) rather than staying silent on it.
    Returns (reasons, benefit_match) -- benefit_match is {benefit: bool}."""
    reasons = []
    benefit_match = {}
    board_name = board["name"]
    for benefit in benefits or []:
        matcher = _BENEFIT_MATCHERS.get(benefit)
        if matcher is None:
            continue
        matched, clause = matcher(board)
        benefit_match[benefit] = matched
        label = _BENEFIT_LABELS.get(benefit, benefit)
        reasons.append(f"benefits from {label} -> {board_name} {clause}")
    return reasons, benefit_match


def _mb(value):
    """Render a MB figure the way the dataset states it: whole numbers with no
    trailing '.0' -- flash_mb/psram_mb round-trip through sqlite as floats."""
    number = float(value)
    return str(int(number)) if number.is_integer() else str(number)


def _board_particularities(board, firmware_name):
    """Salient, grounded facts about ONE board's real record -- chip generation,
    PSRAM framed explicitly against this firmware's needs (never implying PSRAM
    is required; this dataset's capability vocab never requires it), flash size,
    form factor/dimensions, battery, and USB type. Always board-derived, never
    firmware-gated -- unlike `_benefit_reasons`, these are taught regardless of
    whether the firmware declares any `benefits_from`."""
    fm = board.get("frontmatter") or {}
    facts = []

    soc = board.get("soc_ref") or fm.get("soc")
    if soc:
        facts.append(f"{soc} chip")

    psram_mb = board.get("psram_mb")
    if psram_mb == 0:
        facts.append(f"no PSRAM -- {firmware_name} does not need it")
    elif psram_mb:
        facts.append(f"{_mb(psram_mb)}MB PSRAM on board (not required by {firmware_name})")

    flash_mb = board.get("flash_mb")
    if flash_mb:
        facts.append(f"{_mb(flash_mb)}MB flash")

    form_factor = fm.get("form_factor") or board.get("form_factor")
    dims = fm.get("dimensions_mm")
    if form_factor and dims:
        facts.append(f"{form_factor} form factor ({'x'.join(str(d) for d in dims)}mm)")
    elif form_factor:
        facts.append(f"{form_factor} form factor")

    power = fm.get("power") or {}
    if power.get("battery_connector"):
        facts.append("onboard battery connector (rechargeable)" if power.get("charging") else "onboard battery connector")
    else:
        facts.append("no onboard battery connector")

    usb = fm.get("usb") or {}
    if usb.get("connector"):
        facts.append(f"{usb['connector']} USB connector")
    elif usb.get("bridge") == "native":
        facts.append("native USB (no separate bridge chip)")
    elif usb.get("bridge"):
        facts.append(f"USB via {usb['bridge']} bridge chip")

    return facts


# capability (data/firmware/*/firmware.md `requires`/`not_required`) -> the
# human label run_guide's requirement-rationale teaching uses. This is the
# SOLE source for a firmware's hard "needs" labels (`requirements_for_firmware`,
# `_board_reasons`) -- the legacy `capabilities` list is never consulted here:
# it names what the firmware DOES, not what a board must have to run it.
_CAP_LABELS = {
    "wifi": "2.4GHz Wi-Fi",
    "ble": "Bluetooth LE",
    "bt_classic": "Bluetooth Classic",
    "badusb": "USB HID (native USB)",
    "native-usb": "native USB",
    "lora": "LoRa radio",
    "gps": "GPS",
    "sub-ghz": "Sub-GHz radio",
    "rfid-nfc": "RFID/NFC",
    "nfc": "NFC",
    "ir": "IR blaster/receiver",
    "mesh": "802.15.4 mesh radio",
    "ethernet": "Ethernet",
    "display": "a display",
    "storage": "storage",
    "psram": "PSRAM",
}


def _signal_native_usb(board):
    """board_signal "native-usb": usb.bridge=='native' OR the board's own SoC
    is esp32-s2/esp32-s3 -- the narrower "can run BadUSB/HID" test, distinct
    from the broader `usb_native` column (which also covers RISC-V SoCs whose
    native USB is serial-JTAG only, not a HID-capable OTG device)."""
    fm = board.get("frontmatter") or {}
    bridge = (fm.get("usb") or {}).get("bridge")
    soc = board.get("soc_ref")
    if bridge == "native":
        return True, "usb.bridge=native"
    if soc in ("esp32-s2", "esp32-s3"):
        return True, f"{soc} has native USB-OTG"
    return False, f"soc={soc!r}, usb.bridge={bridge!r}"


def _signal_display(board):
    display = (board.get("frontmatter") or {}).get("display")
    if display:
        return True, display
    return False, "record shows no on-board display"


def _signal_storage(board):
    extras = (board.get("frontmatter") or {}).get("extras") or []
    if "sd-card" in extras:
        return True, "has a microSD card slot"
    return False, "record shows no on-board microSD"


def _signal_lora(board):
    extras = (board.get("frontmatter") or {}).get("extras") or []
    if "lora" in extras:
        return True, "extras include a LoRa radio"
    return False, "record shows no on-board LoRa radio"


def _signal_gps(board):
    extras = (board.get("frontmatter") or {}).get("extras") or []
    if "gps" in extras:
        return True, "extras include GPS"
    return False, "record shows no on-board GPS"


# board_signal (schema/firmware.schema.json `requires[].board_signal`) -> the
# matcher that proves it true/false from ONE board's own structured record.
# radio-wifi/radio-ble reuse the same real columns _match_wifi/_match_ble
# already check; the rest read frontmatter fields no `capabilities` matcher
# above touches. A capability's board_signal is `null` (absent here) when this
# dataset cannot prove or disprove it from any board's structured record.
_SIGNAL_MATCHERS = {
    "radio-wifi": _match_wifi,
    "radio-ble": _match_ble,
    "native-usb": _signal_native_usb,
    "display": _signal_display,
    "storage": _signal_storage,
    "lora": _signal_lora,
    "gps": _signal_gps,
}


def _requires_teaching(firmware, board):
    """Every `requires` entry a firmware declares, taught against ONE board:
    a grounded met/unmet statement when `board_signal` names a checkable field,
    or an honest "can't verify from structured data" note when it's `null` --
    never a silent guess either way. `why` is the author's own rationale,
    encoded verbatim; entries without one are still taught, just undecorated."""
    lines = []
    board_name = board["name"]
    for req in firmware.get("requires") or []:
        capability = req.get("capability")
        if not capability:
            continue
        label = _CAP_LABELS.get(capability, capability)
        why = req.get("why")
        need = f"needs {label} ({why})" if why else f"needs {label}"
        signal = req.get("board_signal")
        matcher = _SIGNAL_MATCHERS.get(signal) if signal else None
        if matcher is None:
            lines.append(f"{need} -> check your board has this peripheral (not in structured specs)")
            continue
        matched, fact = matcher(board)
        state = f"{board_name} has it ({fact})" if matched else f"{board_name} lacks it ({fact})"
        lines.append(f"{need} -> {state}")
    return lines


def _not_required_teaching(firmware):
    """Every `not_required` entry a firmware declares -- board-independent by
    design (see PART C: PSRAM is taught as not-needed the same way whether a
    board carries 0MB or 8MB; the point is to teach the firmware's own need,
    not to react to what one board happens to have)."""
    lines = []
    for entry in firmware.get("not_required") or []:
        capability = entry.get("capability")
        if not capability:
            continue
        label = _CAP_LABELS.get(capability, capability)
        why = entry.get("why")
        lines.append(f"does not need {label}: {why}" if why else f"does not need {label}")
    return lines


# Chip ids this dataset seeds (data/socs/*/chip.md), longest/most-specific
# form first so "esp32-s3" wins over the bare "esp32" it contains.
_CHIP_IDS = (
    "esp32-c61", "esp32-c6", "esp32-c5", "esp32-c3", "esp32-c2",
    "esp32-h4", "esp32-h2", "esp32-p4", "esp32-s2", "esp32-s3", "esp32",
)
_CHIP_SUFFIXES = ("c61", "c6", "c5", "c3", "c2", "h4", "h2", "p4", "s2", "s3")
_CHIP_SUFFIX_RE = re.compile(
    r"esp[\s-]*32[\s-]*(" + "|".join(_CHIP_SUFFIXES) + r")\b"
)


def parse_chip_constraint(text):
    """The chip family a maker's phrase names ("on a esp32", "esp32s3", "ESP32-C6"),
    or None. Deterministic word-boundary matching against the dataset's actual
    SoC ids -- no model involved, so a constraint can never be dropped just
    because inference is unavailable."""
    if not text:
        return None
    normalized = _CHIP_SUFFIX_RE.sub(r"esp32-\1", str(text).lower())
    for chip in _CHIP_IDS:
        if re.search(rf"(?<![a-z0-9]){re.escape(chip)}(?![a-z0-9])", normalized):
            return chip
    return None


def requirements_for_firmware(firmware):
    """The human-readable HARD requirements a firmware declares -- sourced
    SOLELY from its authored `requires` array (schema/firmware.schema.json),
    never from the legacy `capabilities` list. `capabilities` describes what a
    firmware DOES (its feature set, e.g. meshtastic also does gps/telemetry/
    mesh-software), which is not the same claim as "a board must have this
    hardware to run it" -- conflating the two produced false/wrong needs (e.g.
    meshtastic's `capabilities` include `gps`, but a maker's board with no GPS
    still runs Meshtastic fine; GPS is a `benefits_from`, not a `requires`)."""
    labels = []
    for req in firmware.get("requires") or []:
        capability = req.get("capability")
        label = _CAP_LABELS.get(capability, capability)
        if label and label not in labels:
            labels.append(label)
    return labels


def _board_reasons(requires, board):
    """Every HARD requirement this firmware's own `requires` array declares,
    checked against ONE board's real record via that entry's `board_signal` --
    the SAME signal matchers `_requires_teaching` uses (see BUG 2: a
    board_signal of "lora"/"gps" is met when the board's `extras` names it, not
    a permanent "not verifiable"). Requirement entries with no board_signal
    (e.g. sub-ghz, rfid-nfc, ir) are named honestly as unverifiable, never
    guessed either way. Returns (reasons, hardware_match, matched_count,
    total_hardware) -- hardware_match is {capability: bool}, used later by the
    grounding validator to catch an LLM claiming a capability the board record
    denies."""
    reasons = []
    hardware_match = {}
    seen = set()
    board_name = board["name"]
    for req in requires or []:
        capability = req.get("capability")
        if not capability or capability in seen:
            continue
        seen.add(capability)
        label = _CAP_LABELS.get(capability, capability)
        signal = req.get("board_signal")
        matcher = _SIGNAL_MATCHERS.get(signal) if signal else None
        if matcher is None:
            reasons.append(f"needs {label} -> not verifiable from {board_name}'s structured board record")
            continue
        matched, fact = matcher(board)
        hardware_match[capability] = matched
        if matched:
            reasons.append(f"needs {label} -> {board_name} has {fact}")
        else:
            reasons.append(f"needs {label} -> {board_name} record shows no {label} ({fact})")

    total_hardware = sum(1 for v in hardware_match.values())
    matched_count = sum(1 for v in hardware_match.values() if v)
    return reasons, hardware_match, matched_count, total_hardware


# Display order for boards[]: best fit first. "works-with-tradeoff" is kept
# alongside "works" (same rank) in case a future fit label uses that exact
# spelling; any fit value not named here (e.g. "partial", or a future/unknown
# value) sorts last -- defensive, so an unrecognized fit never jumps the queue.
_FIT_RANK = {
    "ideal": 0,
    "works": 1,
    "works-with-tradeoff": 1,
    "unconfirmed": 2,
}
_UNRANKED_FIT = max(_FIT_RANK.values()) + 1


def _board_sort_key(board_out):
    """boards[] ranks by fit first (ideal, then works[-with-tradeoff], then
    unconfirmed, then anything else last); within the same fit, a known-good
    recipe sorts before other statuses, then board display name A->Z -- both
    stable, deterministic tie-breakers so the order never depends on recipe
    graph iteration order."""
    return (
        _FIT_RANK.get(board_out["fit"], _UNRANKED_FIT),
        0 if board_out["status"] == "known-good" else 1,
        board_out["board_name"],
    )


def _fit_for(hardware_match, benefit_match):
    """Hard requirements gate fit; benefits refine it once hardware is fully met --
    "ideal" needs every benefit too, "works" names the specific one missing. A
    firmware with no `benefits_from` at all still reaches "ideal" on full hardware
    match, same as the old all-boards-"strong" case, just honestly renamed."""
    total = len(hardware_match)
    if total == 0:
        return "unconfirmed"
    ratio = sum(1 for v in hardware_match.values() if v) / total
    if ratio == 1:
        if benefit_match and not all(benefit_match.values()):
            return "works"
        return "ideal"
    if ratio >= 0.5:
        return "works"
    if ratio > 0:
        return "partial"
    return "unconfirmed"


def _apply_chip_constraint(recipes, chip):
    if not chip:
        return list(recipes), []
    included, excluded = [], []
    for recipe in recipes:
        if recipe.get("chip_family") == chip:
            included.append(recipe)
        else:
            excluded.append(
                {
                    "board": recipe["board"],
                    "reason": f"chip_family={recipe.get('chip_family')!r} does not match requested {chip!r}",
                }
            )
    return included, excluded


def _citations(firmware, recipes):
    seen = set()
    urls = []
    for src in (firmware.get("sources") or []) + [s for r in recipes for s in (r.get("sources") or [])]:
        url = src.get("url")
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def _flash_next(recipes):
    entries = []
    for recipe in recipes:
        flash = recipe.get("flash") or {}
        if flash.get("method") == "release-bin":
            entries.append(
                {"board": recipe["board"], "recipe_id": recipe["id"], "manifest_url": f"/manifest/{recipe['id']}.json"}
            )
    return entries


def _fallback_summary(firmware, requirements, board_entries, chip_constraint):
    description = describe_firmware(firmware) or firmware.get("category") or "Firmware"
    req_text = f" It needs: {', '.join(requirements)}." if requirements else ""
    if not board_entries:
        constraint_text = f" matching {chip_constraint}" if chip_constraint else ""
        return f"{firmware['name']} ({description}).{req_text} No boards in esp-atlas{constraint_text} are known to run it yet."
    names = ", ".join(e["board"]["name"] for e in board_entries)
    return f"{firmware['name']} ({description}).{req_text} Known to run on: {names}."


def _not_found(firmware_id):
    return {
        "firmware": firmware_id,
        "firmware_name": None,
        "summary": NOT_FOUND_ANSWER,
        "requirements": [],
        "boards": [],
        "flash_next": [],
        "citations": [],
        "grounded": False,
    }


SYSTEM_PROMPT = """You explain, in plain language, why a firmware runs well -- or with
which named tradeoff -- on a set of boards.

You are given the firmware's name and requirements, and for EACH board a list
of facts already verified against that board's own real specs -- the exact
requirement-to-capability matches, the benefit matches, its particularities
(chip, PSRAM, flash, form factor, battery, USB), and its already-decided fit.
You do not decide fit and you do not invent facts: you only phrase what is
already given, using ONLY the board ids, specs, and source URLs present in the
data below. When fit is "works" rather than "ideal", say what the board lacks
using only the given facts -- never invent a missing spec, and never state
that PSRAM is required.

Reply with JSON only, no prose, in exactly this shape:
{"summary": "<=2 sentences: what the firmware is and why these boards run it>",
 "boards": [{"board_id": "<id from the data>", "note": "<=1 sentence elaborating that board's fit, using ONLY the given facts>", "source_url": "<a url from that board's own sources, or null>"}]}

Never name a board_id that is not listed below. Never state a spec, a GHz band,
a Bluetooth capability, or a memory size that is not given for that board.
Never cite a URL that is not in that board's own sources. If you are unsure,
omit the board or leave source_url null rather than guess."""


def _build_prompt(firmware, requirements, board_entries, chip_constraint):
    lines = [
        f"Firmware: {firmware['name']} ({firmware['id']})",
        f"Category: {firmware.get('category')}",
        f"Requirements: {', '.join(requirements) if requirements else 'none stated'}",
    ]
    if chip_constraint:
        lines.append(f"Constraint: only {chip_constraint}-family boards are in scope")
    lines.append("")
    for entry in board_entries:
        board, recipe = entry["board"], entry["recipe"]
        sources = ", ".join(s["url"] for s in (recipe.get("sources") or []))
        lines.append(f"Board {board['id']} ({board['name']}, chip_family={recipe.get('chip_family')}, status={recipe.get('status')}):")
        for reason in entry["reasons"]:
            lines.append(f"  - {reason}")
        for fact in entry["particularities"]:
            lines.append(f"  - particularity: {fact}")
        lines.append(f"  fit: {entry['fit']}")
        lines.append(f"  sources: {sources or 'none'}")
        lines.append("")
    return "\n".join(lines)


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


_MB_CLAIM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*mb\s*(psram|flash)?")
_5GHZ_RE = re.compile(r"5\s*ghz")
_SD_CARD_RE = re.compile(r"microsd|sd[\s-]?card")
_PSRAM_REQUIRED_RE = re.compile(r"(needs?|requires?)\s+psram|psram\s+(?:is\s+)?(?:required|needed)")


def _has_ungrounded_spec_claim(note, board, hardware_match):
    """True if free-text `note` asserts something this board's real record
    contradicts -- a spec claim the grounding validator must reject outright."""
    text = note.lower()
    if "bluetooth classic" in text and hardware_match.get("bt_classic") is False:
        return True
    if ("native usb" in text or "usb hid" in text) and hardware_match.get("native-usb") is False:
        return True
    if _5GHZ_RE.search(text):
        bands = [b.strip() for b in (board.get("wifi_bands") or "").split(",") if b.strip()]
        if "5" not in bands:
            return True
    if _PSRAM_REQUIRED_RE.search(text):
        return True  # this dataset's capability vocab never requires PSRAM
    if _SD_CARD_RE.search(text):
        extras = (board.get("frontmatter") or {}).get("extras") or []
        if "sd-card" not in extras:
            return True
    for value, kind in _MB_CLAIM_RE.findall(text):
        if not kind:
            continue
        try:
            number = float(value)
        except ValueError:
            continue
        actual = board.get(f"{kind}_mb")
        if actual is None or number != actual:
            return True
    return False


def validate_grounded_output(raw_text, allowed_board_ids, sources_by_board, hardware_match_by_board, board_facts_by_id):
    """The grounding gate: turns a raw LLM reply into {"summary", "notes"},
    keeping ONLY prose that is fully backed by the given facts. A board id
    outside `allowed_board_ids`, a source URL outside that board's own
    recorded sources, or a spec claim `_has_ungrounded_spec_claim` catches
    each reject the WHOLE board entry -- never a partially-cleaned sentence."""
    parsed = _parse_json(raw_text) or {}

    summary = parsed.get("summary")
    summary = summary.strip() if isinstance(summary, str) and summary.strip() else None

    notes = {}
    for entry in parsed.get("boards") or []:
        if not isinstance(entry, dict):
            continue
        board_id = entry.get("board_id")
        if board_id not in allowed_board_ids:
            continue  # names a board outside the recipe set -- reject

        note = entry.get("note")
        note = note.strip() if isinstance(note, str) and note.strip() else None
        if note is None:
            continue

        source_url = entry.get("source_url")
        if source_url is not None:
            if not isinstance(source_url, str) or source_url not in sources_by_board.get(board_id, set()):
                continue  # cites a source not in the data -- reject

        if _has_ungrounded_spec_claim(note, board_facts_by_id[board_id], hardware_match_by_board.get(board_id, {})):
            continue  # asserts a spec the board record does not have -- reject

        notes[board_id] = {"note": note, "source_url": source_url}

    return {"summary": summary, "notes": notes}


def run_guide(firmware_id, constraints=None, llm_client=None, db_path=None):
    """A grounded, cited, reasoned answer to "why does `firmware_id` run on
    these boards" -- see module docstring for the shape and the honesty
    guarantees. Never raises for a bad/unknown firmware or a down/rate-limited
    model; both degrade to an honest, deterministic answer."""
    firmware = get_firmware(firmware_id)
    if firmware is None:
        return _not_found(firmware_id)

    all_recipes = recipes_for_firmware(firmware_id)
    if not all_recipes:
        return _not_found(firmware_id)

    chip_constraint = parse_chip_constraint(constraints)
    included_recipes, excluded = _apply_chip_constraint(all_recipes, chip_constraint)
    requirements = requirements_for_firmware(firmware)
    not_required_lines = _not_required_teaching(firmware)

    board_entries = []
    for recipe in included_recipes:
        board = get_part(recipe["board"], db_path=db_path)
        if board is None:
            continue
        reasons, hardware_match, _matched, _total = _board_reasons(firmware.get("requires"), board)
        benefit_reasons, benefit_match = _benefit_reasons(firmware.get("benefits_from"), board)
        board_entries.append(
            {
                "recipe": recipe,
                "board": board,
                "reasons": reasons + benefit_reasons,
                "hardware_match": hardware_match,
                "benefit_match": benefit_match,
                "particularities": _board_particularities(board, firmware["name"]),
                "fit": _fit_for(hardware_match, benefit_match),
                "requires": _requires_teaching(firmware, board),
                "not_required": not_required_lines,
            }
        )

    allowed_board_ids = {e["recipe"]["board"] for e in board_entries}
    sources_by_board = {
        e["recipe"]["board"]: {s["url"] for s in (e["recipe"].get("sources") or [])} for e in board_entries
    }
    hardware_match_by_board = {e["recipe"]["board"]: e["hardware_match"] for e in board_entries}
    board_facts_by_id = {e["recipe"]["board"]: e["board"] for e in board_entries}

    summary = _fallback_summary(firmware, requirements, board_entries, chip_constraint)
    notes = {}

    if board_entries:
        client = llm_client or GroqClient(model=FAST_MODEL)
        prompt = _build_prompt(firmware, requirements, board_entries, chip_constraint)
        try:
            raw = client.complete(SYSTEM_PROMPT, prompt, temperature=0)
            validated = validate_grounded_output(
                raw, allowed_board_ids, sources_by_board, hardware_match_by_board, board_facts_by_id
            )
            if validated["summary"]:
                summary = validated["summary"]
            notes = validated["notes"]
        except Exception:
            pass  # graceful degradation: keep the deterministic fallback, never invent, never raise

    boards_out = []
    for entry in board_entries:
        recipe, board = entry["recipe"], entry["board"]
        board_id = recipe["board"]
        out = {
            "board_id": board_id,
            "board_name": board["name"],
            "fit": entry["fit"],
            "reasons": entry["reasons"],
            "particularities": entry["particularities"],
            "requires": entry["requires"],
            "not_required": entry["not_required"],
            "status": recipe.get("status"),
            "chip_family": recipe.get("chip_family"),
            "sources": recipe.get("sources") or [],
        }
        note = notes.get(board_id)
        if note and note["note"]:
            out["note"] = note["note"]
        boards_out.append(out)

    boards_out.sort(key=_board_sort_key)

    result = {
        "firmware": firmware["id"],
        "firmware_name": firmware["name"],
        "summary": summary,
        "requirements": requirements,
        "requires": firmware.get("requires") or [],
        "not_required": firmware.get("not_required") or [],
        "boards": boards_out,
        "flash_next": _flash_next([e["recipe"] for e in board_entries]),
        "citations": _citations(firmware, [e["recipe"] for e in board_entries]),
        "grounded": True,
    }
    if chip_constraint:
        result["constraint"] = {"chip": chip_constraint}
    if excluded:
        result["excluded_boards"] = excluded
    return result
