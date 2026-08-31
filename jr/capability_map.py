"""EspAtlas Jr — freeform text -> controlled capability-token map (feeds scorer.py's zero-LLM scorer).

A FIXED map of description/README keyword phrases to the atlas's controlled capability
vocabulary (tools.capability_vocab()). This is the deterministic replacement for the LLM
inventing freeform phrases like "Media playback (MP3, WAV)" (DECISION-LOG.md #73): a keyword
not in this map contributes NOTHING — never a freeform string. Keys are matched as
case-insensitive substrings against a SPACE-PADDED copy of the text (capabilities_from_text pads
with a leading/trailing space) — so any key that itself starts with a leading space (" ble ",
" ble spam", " ble scan", " ir remote") only matches on a real word boundary before it. Found
at-scale: without that leading space, "ble scan" naive-substring-matched inside "configura**ble
scan** radius" (an aircraft-tracker's UNRELATED "configurable scan radius" text) and fabricated a
`ble` capability with zero Bluetooth evidence — the leading space closes that class of bug.
"""
from __future__ import annotations

CAPABILITY_KEYWORDS: dict[str, str] = {
    "wifi": "wifi", "wi-fi": "wifi", "deauth": "wifi",
    "bluetooth": "ble", " ble ": "ble", " ble spam": "ble", " ble scan": "ble",
    "nfc": "nfc",
    "rfid": "rfid-nfc",
    "infrared": "ir", " ir remote": "ir", "tv-b-gone": "ir", "tvbgone": "ir",
    "gps": "gps",
    "sub-ghz": "sub-ghz", "subghz": "subghz", "sub ghz": "sub-ghz",
    "lora": "lora",
    "mesh": "mesh",
    "mqtt": "mqtt",
    "web interface": "on-device-web-ui", "web ui": "on-device-web-ui",
    "ota update": "ota",
    "ethernet": "ethernet",
    "badusb": "badusb", "bad usb": "badusb",
    "telemetry": "telemetry",
    "artnet": "artnet",
    "e1.31": "e131", "e131": "e131",
    "ddp": "ddp",
}


def capabilities_from_text(*texts: str | None) -> list[str]:
    """Controlled-vocab capability tokens found in `texts` (deduped, sorted). Any phrase with
    no entry in CAPABILITY_KEYWORDS is silently dropped — never turned into a freeform token."""
    found: set[str] = set()
    for text in texts:
        if not text:
            continue
        low = f" {text.lower()} "
        for phrase, token in CAPABILITY_KEYWORDS.items():
            if phrase in low:
                found.add(token)
    return sorted(found)
