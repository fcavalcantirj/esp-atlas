"""Plain-language intent -> the wizard's own filters (SPEC-INDEX G4).

    parse_intent("a battery powered plant sensor")
    # -> {"kind": "filters", "filters": {"type": "board", "battery": True, ...},
    #     "understood": ["runs off a battery", "Wi-Fi"], "unmapped": ["humidity sensor"]}

The home's prompt used to run the raw sentence through FTS, so "a plant detector
humidity" matched e-paper display boards on stray prose words. This maps the
sentence onto real fields instead, and is explicit about the part it could not.

Three rules make it honest:

1. **The model may only emit filters the wizard already understands.** Its output
   is validated key by key and value by value against KNOWN_NEEDS and against
   values actually present in the index; anything else is discarded, never
   passed through. So a parse is always replayable by the deterministic wizard,
   and a hallucinated field cannot reach the query.
2. **What it could not map is reported, not dropped.** "waterproof" and
   "humidity sensor" have no field in this dataset. Silently ignoring them would
   imply the results honour them; `unmapped` lets the UI say otherwise.
3. **Naming a firmware never needs the model.** "run marauder" is answered from
   the recipe graph by exact match, so the headline case cannot be broken by a
   bad parse, a rate limit, or a missing API key.

Groq reads the QUERY, never the catalogue, so the bill is per-unique-phrasing
and flat in the number of boards (SPEC-home-explorer §3). Parses are cached by
query string alone -- see the intent_cache table.
"""
import json
import re
from datetime import datetime, timezone

from esp_atlas_core import db as dbmod
from esp_atlas_core.facets import facets
from esp_atlas_core.firmware import list_firmware, recipes_for_firmware
from esp_atlas_core.llm import FAST_MODEL, GroqClient
from esp_atlas_core.wizard import KNOWN_NEEDS

# What a filter means in plain words, for the "here's what I understood" chips.
_UNDERSTOOD = {
    "battery": lambda v: "runs off a battery",
    "usb_native": lambda v: "acts as a USB device",
    "ieee802154": lambda v: "smart-home mesh (Thread/Zigbee/Matter)",
    "ble": lambda v: "Bluetooth LE",
    "bt_classic": lambda v: "Bluetooth Classic",
    "psram_min": lambda v: f"PSRAM >= {v} MB",
    "flash_min": lambda v: f"flash >= {v} MB",
    "radio": lambda v: f"{v} or newer",
    "band": lambda v: f"{v} GHz Wi-Fi",
    "form": lambda v: f"{v} form factor",
    "budget": lambda v: f"{v} price tier",
    "protocol": lambda v: f"{v} mesh",
    "soc": lambda v: f"built on the {v}",
    "type": lambda v: None,  # scoping, not something the user asked for
}

_BOOLEAN_NEEDS = {"battery", "usb_native", "ieee802154", "ble", "bt_classic"}
_BUDGETS = {"cheap", "medium", "expensive"}
_TYPES = {"soc", "module", "board"}
_MEMORY_TIERS = {"psram_min": {2, 4, 8}, "flash_min": {4, 8, 16}}

SYSTEM_PROMPT = """You turn a maker's plain-language goal into filters over a catalogue of ESP32 chips, modules and boards.

Reply with JSON only, no prose, in exactly this shape:
{"filters": {...}, "unmapped": ["..."]}

`filters` may ONLY use these keys, with these values:
- "type": "board" | "module" | "soc"   (almost always "board" — a person choosing hardware wants a board)
- "battery": true                       (the project is portable, wearable, outdoors, or says battery/solar)
- "usb_native": true                    (must ACT AS a USB device: keyboard, mouse, storage, HID, BadUSB)
- "ieee802154": true                    (Thread, Zigbee, or Matter-over-Thread smart-home mesh)
- "ble": true                           (Bluetooth)
- "bt_classic": true                    (Bluetooth Classic / audio A2DP)
- "radio": "wifi-4" | "wifi-6"          (needs Wi-Fi; use "wifi-4" for ordinary Wi-Fi, it also matches newer)
- "band": 2.4 | 5                       (only if a band is named explicitly)
- "psram_min": 2 | 4 | 8                (runs a web server, camera, display buffer, or heavy app)
- "flash_min": 4 | 8 | 16               (needs storage room for assets)
- "form": "<exact form factor>"         (only if a shape is named explicitly)
- "soc": "esp32" | "esp32-s2" | "esp32-s3" | "esp32-c3" | "esp32-c6" | "esp32-h2" | "esp32-c5" | "esp32-c2" | "esp32-p4"
                                        (only if a specific chip is named)
- "budget": "cheap" | "medium" | "expensive"

Omit any key you are not confident about. An empty filters object is a valid answer.

Map ONLY what the maker actually said. This project's one promise is "nothing
guessed, nothing invented" — so NEVER infer a need they did not state. Do NOT add
`battery` unless they say portable/wearable/outdoors/battery/solar. Do NOT add
`radio` unless they name Wi-Fi or say the thing reports/streams/connects over a
network. A bare "plant humidity sensor" could be mains-powered and wired — add
neither. Add a filter ONLY when the words state it or literally require it (you
cannot "host a web dashboard" without Wi-Fi + some memory; "wearable" states
portable → battery; "reports over Wi-Fi" states Wi-Fi).

When the heart of the goal is something the catalogue can't filter (a sensor,
camera, screen, motor) and nothing else is clearly stated, return an EMPTY or
minimal `filters` and put that need in `unmapped`. A short honest "I couldn't
narrow this — tell me more (portable? Wi-Fi? cheap?)" beats a long list padded
with guesses. An empty filters object is a GOOD answer, not a failure.

`unmapped` lists the parts of the goal this catalogue has NO field for — sensors of
any kind, cameras, screens, motors, waterproofing, GPS, LoRa, specific pin counts.
Put them there verbatim-ish and short. NEVER invent a filter key to cover them.

Examples:
"a plant humidity sensor" -> {"filters": {"type": "board"}, "unmapped": ["humidity sensor"]}
"a battery-powered plant sensor that reports over Wi-Fi" -> {"filters": {"type": "board", "battery": true, "radio": "wifi-4"}, "unmapped": ["humidity sensor"]}
"esp32-s3 with 8mb psram" -> {"filters": {"type": "board", "psram_min": 8}, "unmapped": []}
"a board to host a web dashboard" -> {"filters": {"type": "board", "psram_min": 2, "radio": "wifi-4"}, "unmapped": []}
"asdfqwer zzzz" -> {"filters": {}, "unmapped": ["asdfqwer zzzz"]}"""


def _normalize(query):
    return " ".join(query.lower().split())


def _read_cache(db_path, query):
    conn = dbmod.connect(db_path)
    try:
        row = conn.execute("SELECT parsed_json FROM intent_cache WHERE query = ?", (query,)).fetchone()
    finally:
        conn.close()
    return json.loads(row["parsed_json"]) if row else None


def _write_cache(db_path, query, parsed):
    conn = dbmod.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO intent_cache (query, parsed_json, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT(query) DO UPDATE SET parsed_json = excluded.parsed_json",
            (query, json.dumps(parsed), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


# Tokens too generic to identify a project: they appear in nearly every query.
_FIRMWARE_STOPWORDS = frozenset({"esp32", "esp", "m5", "the", "for", "and", "run", "runs"})
_MIN_FIRMWARE_TOKEN = 4


def _firmware_keys(fw):
    """The strings that identify this firmware in a query."""
    keys = {fw["id"].lower(), fw["name"].lower()}
    for token in fw["name"].lower().replace("-", " ").split():
        if len(token) >= _MIN_FIRMWARE_TOKEN and token not in _FIRMWARE_STOPWORDS:
            keys.add(token)
    return {k for k in keys if k not in _FIRMWARE_STOPWORDS}


def firmware_named_in(query):
    """The firmware a query names, by exact match — no model involved.

    (ask.py carries an equivalent private matcher on the Ask branch; once both
    land they should share this one rather than keeping two copies.)
    """
    haystack = query.lower()
    matched = []
    for fw in list_firmware():
        for key in _firmware_keys(fw):
            # Word boundaries, not substrings: "m5stick" is a substring of
            # "m5sticks3", so a naive match sends "run M5StickS3 RogueDuck" to
            # M5Stick NEMO. Longer, more specific names must win outright.
            if re.search(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])", haystack):
                matched.append((len(key), fw))
                break
    # most specific name first, so an exact product name beats a shared prefix
    return [fw for _length, fw in sorted(matched, key=lambda m: -m[0])]


def _valid_values(db_path):
    """Values that actually exist in this index, so a parse can't invent one."""
    data = facets(db_path)
    return {
        "form": {f["value"] for f in data.get("form_factor", [])},
        "radio": {f["value"] for f in data.get("wifi_standard", [])},
        "band": {float(f["value"]) for f in data.get("wifi_bands", [])},
        "protocol": {f["value"].split("-")[0] for f in data.get("ieee802154_protocols", [])},
        "soc": {f["value"] for f in data.get("soc_ref", [])},
    }


def validate_filters(raw, db_path=None):
    """Keep only filters the wizard understands, with values present in the data.

    Returns (filters, rejected) — `rejected` is reported to the user rather than
    hidden, so a bad parse is visible instead of silently narrowing results.
    """
    allowed = _valid_values(db_path)
    filters, rejected = {}, []

    for key, value in (raw or {}).items():
        if key not in KNOWN_NEEDS:
            rejected.append(f"{key}={value}")
            continue
        if key in _BOOLEAN_NEEDS:
            if value is True:
                filters[key] = True
            continue  # false/None means "no preference", never a filter
        if key == "type" and value in _TYPES:
            filters[key] = value
        elif key == "budget" and value in _BUDGETS:
            filters[key] = value
        elif key in _MEMORY_TIERS:
            try:
                number = int(value)
            except (TypeError, ValueError):
                rejected.append(f"{key}={value}")
                continue
            if number in _MEMORY_TIERS[key]:
                filters[key] = number
            else:
                rejected.append(f"{key}={value}")
        elif key == "band":
            try:
                number = float(value)
            except (TypeError, ValueError):
                rejected.append(f"{key}={value}")
                continue
            if number in allowed["band"]:
                filters[key] = number
            else:
                rejected.append(f"{key}={value}")
        elif key in ("form", "radio", "protocol", "soc"):
            if value in allowed[key]:
                filters[key] = value
            else:
                rejected.append(f"{key}={value}")
        else:
            rejected.append(f"{key}={value}")

    return filters, rejected


def describe(filters):
    """Plain-language chips for what the parse understood."""
    out = []
    for key, value in filters.items():
        render = _UNDERSTOOD.get(key)
        text = render(value) if render else f"{key}: {value}"
        if text:
            out.append(text)
    return out


def _parse_json(text):
    """The model is asked for JSON only; tolerate a fenced block around it."""
    body = text.strip()
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


def parse_intent(query, llm_client=None, db_path=None, use_cache=True):
    """A plain-language goal -> {kind, filters, understood, unmapped, ...}.

    kind is "firmware" (the query names one — answered from the recipe graph),
    "filters" (mapped onto real fields), or "unreadable" (nothing could be
    mapped, and the caller should say so rather than pretend).
    """
    normalized = _normalize(query)
    if not normalized:
        return {"kind": "unreadable", "filters": {}, "understood": [], "unmapped": [], "cached": False}

    # Firmware first, deterministically: "run marauder" must work with no API key.
    named = firmware_named_in(normalized)
    if named:
        firmware = named[0]
        boards = [r["board"] for r in recipes_for_firmware(firmware["id"])]
        return {
            "kind": "firmware",
            "firmware": firmware["id"],
            "firmware_name": firmware["name"],
            "boards": boards,
            "filters": {},
            "understood": [f"runs {firmware['name']}"],
            "unmapped": [],
            "cached": False,
        }

    if use_cache:
        cached = _read_cache(db_path, normalized)
        if cached is not None:
            return {**cached, "cached": True}

    client = llm_client or GroqClient(model=FAST_MODEL)
    raw = _parse_json(client.complete(SYSTEM_PROMPT, normalized, temperature=0)) or {}
    filters, rejected = validate_filters(raw.get("filters"), db_path=db_path)
    unmapped = [str(u) for u in (raw.get("unmapped") or []) if str(u).strip()] + rejected

    # `type` alone is scoping, not understanding -- it must not count as a hit.
    understood_anything = any(key != "type" for key in filters)
    parsed = {
        "kind": "filters" if understood_anything else "unreadable",
        "filters": filters if understood_anything else {},
        "understood": describe(filters) if understood_anything else [],
        "unmapped": unmapped,
        "cached": False,
    }
    if use_cache:
        _write_cache(db_path, normalized, parsed)
    return parsed
