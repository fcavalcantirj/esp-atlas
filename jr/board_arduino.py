"""EspAtlas Jr — the Arduino-ESP32 core `boards.txt` as a THIRD cited source for `usb_serial` (G3b).

Order per field stays: the vendor doc page (jr/board_doc_resolvers.py), then the PlatformIO
manifest (jr/board_manifest.py), then this. It is consulted only for a board whose `usb_serial`
is still missing after both, and it grounds nothing else — download_mode and pinout are out of
its scope. Every value it returns is cited by the caller to boards.txt at a PINNED release commit
(cite-or-omit, same rule as the other sources).

Mapping a catalog board to a boards.txt key is DETERMINISTIC: the curated ARDUINO_BOARD_KEYS
table only. Nothing is ever fuzzy-matched — a board absent from it is skipped `no_board_key`.

`usb_serial` comes from the key's own `<key>.vid.N` / `<key>.pid.N` lines, read through the SAME
vendor-id table the PlatformIO source uses (board_manifest.usb_serial_from_hwids): an unknown id
writes nothing.

NO LLM, NO API KEY. The fetch is injected (board_backfill.default_fetch on real runs).
"""
from __future__ import annotations

import re
from pathlib import Path

from board_manifest import DOC_UNREACHABLE, soc_has_serial_jtag, usb_serial_from_hwids

NO_BOARD_KEY = "no_board_key"   # the board has no (or no longer a) boards.txt entry

# arduino-esp32 release tag 3.3.9. A commit SHA, not the tag, so a cited URL can never change
# under us.
ARDUINO_PINNED_TAG = "3.3.9"
ARDUINO_PINNED_REF = "5b5114c832dfe309f3e73879d2ac8922c8276559"
BOARDS_TXT_URL = ("https://raw.githubusercontent.com/espressif/arduino-esp32/"
                  f"{ARDUINO_PINNED_REF}/boards.txt")

# The fields this source can ground.
ARDUINO_FIELDS = ("usb_serial",)

# Catalog board id -> boards.txt key. Each pair was checked by hand on 2026-11-03 against
# boards.txt at ARDUINO_PINNED_REF: same vendor, same product name (`<key>.name`), same mcu.
# Left out on purpose:
#   * lolin-s3, esp32-s3-devkitc-1 — two USB ports (native + UART bridge).
#   * heltec V3 boards — same exclusion as G3a's PIO_BOARD_IDS: their PlatformIO hwid says
#     0x303A while Heltec documents a CP2102 bridge, so no USB-id table entry is trusted for them.
#   * one key for several products: m5stack_atom (Atom Lite/Matrix/Echo) for m5atom-lite;
#     m5stack_core (Basic/Gray/AWS) for m5stack-core, m5stack-core-aws; m5stack_atoms3 for
#     m5atoms3-lite; m5stack_cores3 for m5stack-cores3-se; m5stack_cardputer (Cardputer and
#     Cardputer-Adv) for m5cardputer; XIAO_ESP32S3 for xiao-esp32s3-sense; t-beam (revisions
#     ship different USB bridges) for lilygo-t-beam; esp32wroverkit ("all versions") for
#     esp-wrover-kit; pico32 (the PICO-D4 chip target) for esp32-pico-kit; heltec_wireless_tracker
#     vs _v2 for heltec-wireless-tracker.
#   * adafruit-qt-py-esp32-s3 — its record name says "No PSRAM", so it is not plainly either
#     adafruit_qtpy_esp32s3_nopsram or _n4r2.
#   * sparkfun-thing-plus-esp32-wroom — not provably esp32thing_plus or esp32thing_plus_c.
#   * espressif DevKits — boards.txt has generic "<SoC> Dev Module" targets, not the kits.
ARDUINO_BOARD_KEYS: dict[str, str] = {
    # adafruit
    "adafruit-feather-esp32-c6": "adafruit_feather_esp32c6",
    "adafruit-feather-esp32-s2": "adafruit_feather_esp32s2",
    "adafruit-feather-esp32-s2-reverse-tft": "adafruit_feather_esp32s2_reversetft",
    "adafruit-feather-esp32-s2-tft": "adafruit_feather_esp32s2_tft",
    "adafruit-feather-esp32-s3": "adafruit_feather_esp32s3",
    "adafruit-feather-esp32-s3-no-psram": "adafruit_feather_esp32s3_nopsram",
    "adafruit-feather-esp32-s3-reverse-tft": "adafruit_feather_esp32s3_reversetft",
    "adafruit-feather-esp32-s3-tft": "adafruit_feather_esp32s3_tft",
    "adafruit-feather-esp32-v2": "adafruit_feather_esp32_v2",
    "adafruit-funhouse": "adafruit_funhouse_esp32s2",
    "adafruit-huzzah32-esp32-feather": "featheresp32",
    "adafruit-itsybitsy-esp32": "adafruit_itsybitsy_esp32",
    "adafruit-magtag": "adafruit_magtag29_esp32s2",
    "adafruit-matrixportal-s3": "adafruit_matrixportal_esp32s3",
    "adafruit-metro-esp32-s2": "adafruit_metro_esp32s2",
    "adafruit-metro-esp32-s3": "adafruit_metro_esp32s3",
    "adafruit-pycamera-s3": "adafruit_camera_esp32s3",
    "adafruit-qt-py-esp32": "adafruit_qtpy_esp32_pico",
    "adafruit-qt-py-esp32-c3": "adafruit_qtpy_esp32c3",
    "adafruit-qt-py-esp32-s2": "adafruit_qtpy_esp32s2",
    "adafruit-qt-py-esp32-s3-no-psram": "adafruit_qtpy_esp32s3_nopsram",
    "adafruit-qualia-esp32-s3": "adafruit_qualia_s3_rgb666",
    "adafruit-sparkle-motion": "sparklemotion",
    "adafruit-sparkle-motion-mini": "sparklemotionmini",
    "adafruit-sparkle-motion-stick": "sparklemotionstick",
    # dfrobot
    "beetle-esp32-c3": "dfrobot_beetle_esp32c3",
    "beetle-esp32-c6": "dfrobot_beetle_esp32c6",
    "firebeetle-2-esp32-c6": "dfrobot_firebeetle2_esp32c6",
    "firebeetle-2-esp32-e": "dfrobot_firebeetle2_esp32e",
    "firebeetle-2-esp32-s3": "dfrobot_firebeetle2_esp32s3",
    "firebeetle-esp32": "firebeetle32",
    # heltec
    "heltec-wireless-paper": "heltec_wireless_paper",
    # lilygo
    "lilygo-t-display": "lilygo_t_display",
    "lilygo-t-display-s3": "lilygo_t_display_s3",
    "lilygo-t-watch-s3": "twatchs3",
    # lolin
    "lolin-c3-mini": "lolin_c3_mini",
    "lolin-d32": "d32",
    "lolin-d32-pro": "d32_pro",
    "lolin-s2-mini": "lolin_s2_mini",
    "lolin-s3-mini": "lolin_s3_mini",
    # m5stack
    "m5atoms3": "m5stack_atoms3",
    "m5dial": "m5stack_dial",
    "m5nanoc6": "m5stack_nanoc6",
    "m5stack-core2": "m5stack_core2",
    "m5stack-cores3": "m5stack_cores3",
    "m5stack-fire": "m5stack_fire",
    "m5stamp-c3": "m5stack_stamp_c3",
    "m5stamp-s3": "m5stack_stamp_s3",
    "m5stick-c": "m5stack_stickc",
    "m5stick-cplus": "m5stack_stickc_plus",
    "m5stick-cplus2": "m5stack_stickc_plus2",
    # seeed
    "xiao-esp32c3": "XIAO_ESP32C3",
    "xiao-esp32c5": "XIAO_ESP32C5",
    "xiao-esp32c6": "XIAO_ESP32C6",
    "xiao-esp32s3": "XIAO_ESP32S3",
    # sparkfun
    "sparkfun-esp32-thing": "esp32thing",
    "sparkfun-iot-redboard-esp32": "sparkfun_esp32_iot_redboard",
    "sparkfun-micromod-esp32-processor": "esp32micromod",
    "sparkfun-thing-plus-esp32-s2-wroom": "sparkfun_esp32s2_thing_plus",
    # unexpected-maker
    "um-feathers3": "um_feathers3",
    "um-nanos3": "um_nanos3",
    "um-pros3": "um_pros3",
    "um-tinys3": "um_tinys3",
}

_HWID_RE = re.compile(r"(vid|pid)\.(\d+)")


def board_key(board_id: str) -> str | None:
    """The board's boards.txt key from the curated table; None when it has none."""
    return ARDUINO_BOARD_KEYS.get(board_id)


def hwids_for_key(text: str, key: str) -> list[tuple[str | None, str | None]] | None:
    """The key's own [(vid, pid), ...] in index order, read only from non-comment
    `<key>.vid.N=` / `<key>.pid.N=` lines. [] when the key has no vid/pid lines, None when the
    key is not in the file at all."""
    prefix = f"{key}."
    found = False
    by_index: dict[int, dict[str, str]] = {}
    for line in (text or "").splitlines():
        line = line.strip()
        if not line.startswith(prefix) or "=" not in line:
            continue
        found = True
        prop, value = line[len(prefix):].split("=", 1)
        m = _HWID_RE.fullmatch(prop.strip())
        if m:
            by_index.setdefault(int(m.group(2)), {})[m.group(1)] = value.strip()
    if not found:
        return None
    return [(ids.get("vid"), ids.get("pid")) for _, ids in sorted(by_index.items())]


def usb_serial_from_boards_txt(text: str, key: str, serial_jtag: bool) -> tuple[str | None, str | None]:
    """(value, None) when the key's vid/pid pairs all map to one usb_serial value, else
    (None, reason): NO_BOARD_KEY when the key is not in the file, otherwise the reason
    board_manifest.usb_serial_from_hwids gives."""
    hwids = hwids_for_key(text, key)
    if hwids is None:
        return None, NO_BOARD_KEY
    return usb_serial_from_hwids(hwids, serial_jtag)


def ground_from_boards_txt(board_id: str, soc: str, data_root: Path, fields: list[str],
                           fetch) -> dict:
    """Ground the requested `fields` (a subset of ARDUINO_FIELDS) from boards.txt at the pinned
    commit. Returns {"url": <pinned url or None>, "values": {field: value},
    "reasons": {field: reason}} — every requested in-scope field lands in exactly one of the two;
    fields out of this source's scope are not reported at all."""
    fields = [f for f in ARDUINO_FIELDS if f in fields]
    out: dict = {"url": None, "values": {}, "reasons": {}}
    if not fields:
        return out
    key = board_key(board_id)
    if not key:
        out["reasons"] = {f: NO_BOARD_KEY for f in fields}
        return out
    res = fetch(BOARDS_TXT_URL)
    if not res.get("ok"):
        out["reasons"] = {f: DOC_UNREACHABLE for f in fields}
        return out
    out["url"] = BOARDS_TXT_URL
    value, reason = usb_serial_from_boards_txt(res.get("text") or "", key,
                                               soc_has_serial_jtag(soc, data_root))
    if value is None:
        out["reasons"]["usb_serial"] = reason
    else:
        out["values"]["usb_serial"] = value
    return out
