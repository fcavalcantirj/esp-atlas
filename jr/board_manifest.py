"""EspAtlas Jr — PlatformIO board manifests as a SECOND cited source for board fields (G3a).

The vendor doc page (jr/board_doc_resolvers.py) stays the first source. When it leaves
`usb_serial` missing, this module reads the board's PlatformIO espressif32 manifest
(`boards/<id>.json`) at a PINNED commit and derives `usb_serial` from its `build.hwids` USB
vendor id with a fixed table. Every value it returns is cited to that pinned manifest URL by the
caller (cite-or-omit, same rule as the vendor source).

Mapping a catalog board to a manifest is DETERMINISTIC: an explicit `platformio` id on the board
record wins, else the curated PIO_BOARD_IDS table. Nothing is ever fuzzy-matched — a board absent
from both is skipped `no_manifest`.

`download_mode` is written only when the manifest states it explicitly. PlatformIO's manifest
format has no download-mode key: `build.flash_mode` is the SPI flash mode (qio/dio) and
`upload.use_1200bps_touch` is a CDC reset trick, neither is a download-mode statement. So today
the manifest never grounds download_mode and reports it `field_absent`.

NO LLM, NO API KEY. The fetch is injected (board_backfill.default_fetch on real runs).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

# Per-field skip reasons, shared with board_backfill's tick report.
NO_PATTERN_MATCH = "no_pattern_match"   # the source talks about the field, no rule grounds it
FIELD_ABSENT = "field_absent"           # the source never states the field at all
DOC_UNREACHABLE = "doc_unreachable"     # the source could not be fetched (or parsed)
NO_MANIFEST = "no_manifest"             # the board has no mapped PlatformIO manifest
SOURCE_GATED = "source_gated"           # this vendor's page is known to false-positive the field

# platform-espressif32 tag v8.0.0 (commit 2026-10-19). A commit SHA, not the tag, so a cited
# URL can never change under us.
PIO_PINNED_TAG = "v8.0.0"
PIO_PINNED_REF = "39d87f8c599b0a31cf56a1cf16c7756742ca7736"
PIO_MANIFEST_BASE = ("https://raw.githubusercontent.com/platformio/platform-espressif32/"
                     f"{PIO_PINNED_REF}/boards")

# The fields this source can ground, in the order board_backfill writes them.
MANIFEST_FIELDS = ("download_mode", "usb_serial")

# Catalog board id -> PlatformIO board id. Each pair was checked by hand on 2026-11-03 against
# boards/<id>.json at PIO_PINNED_REF: same vendor, same product name, same mcu. Left out on
# purpose:
#   * lolin-s3, esp32-s3-devkitc-1 — two USB ports (native + UART bridge); the manifest hwid
#     names only the native one, so it cannot say which bridge flashes the board.
#   * heltec V3 boards — manifests list 0x303A while Heltec documents a CP2102 bridge.
#   * product-family manifests (m5stack-atom, m5stack-core-esp32, m5stack-cardputer pointing at
#     Cardputer-Adv, adafruit_feather_esp32s3 vs _nopsram) — not one product.
PIO_BOARD_IDS: dict[str, str] = {
    # adafruit
    "adafruit-feather-esp32-c6": "adafruit_feather_esp32c6",
    "adafruit-feather-esp32-s2": "adafruit_feather_esp32s2",
    "adafruit-feather-esp32-s2-reverse-tft": "adafruit_feather_esp32s2_reversetft",
    "adafruit-feather-esp32-s2-tft": "adafruit_feather_esp32s2_tft",
    "adafruit-feather-esp32-s3-no-psram": "adafruit_feather_esp32s3_nopsram",
    "adafruit-feather-esp32-s3-reverse-tft": "adafruit_feather_esp32s3_reversetft",
    "adafruit-feather-esp32-s3-tft": "adafruit_feather_esp32s3_tft",
    "adafruit-feather-esp32-v2": "adafruit_feather_esp32_v2",
    "adafruit-funhouse": "adafruit_funhouse_esp32s2",
    "adafruit-itsybitsy-esp32": "adafruit_itsybitsy_esp32",
    "adafruit-magtag": "adafruit_magtag29_esp32s2",
    "adafruit-matrixportal-s3": "adafruit_matrixportal_esp32s3",
    "adafruit-metro-esp32-s2": "adafruit_metro_esp32s2",
    "adafruit-metro-esp32-s3": "adafruit_metro_esp32s3",
    "adafruit-pycamera-s3": "adafruit_camera_esp32s3",
    "adafruit-qt-py-esp32": "adafruit_qtpy_esp32",
    "adafruit-qt-py-esp32-c3": "adafruit_qtpy_esp32c3",
    "adafruit-qt-py-esp32-s2": "adafruit_qtpy_esp32s2",
    "adafruit-qt-py-esp32-s3-no-psram": "adafruit_qtpy_esp32s3_nopsram",
    # dfrobot
    "beetle-esp32-c3": "dfrobot_beetle_esp32c3",
    "firebeetle-2-esp32-e": "dfrobot_firebeetle2_esp32e",
    "firebeetle-2-esp32-s3": "dfrobot_firebeetle2_esp32s3",
    # lilygo
    "lilygo-t-display": "lilygo-t-display",
    "lilygo-t-display-s3": "lilygo-t-display-s3",
    # lolin
    "lolin-c3-mini": "lolin_c3_mini",
    "lolin-d32": "lolin_d32",
    "lolin-d32-pro": "lolin_d32_pro",
    "lolin-s2-mini": "lolin_s2_mini",
    "lolin-s3-mini": "lolin_s3_mini",
    # m5stack
    "m5atoms3": "m5stack-atoms3",
    "m5dial": "m5stack-dial",
    "m5nanoc6": "m5stack-nanoc6",
    "m5stack-core2": "m5stack-core2",
    "m5stack-cores3": "m5stack-cores3",
    "m5stack-fire": "m5stack-fire",
    "m5stamp-c3": "m5stack-stamp-c3",
    "m5stamp-s3": "m5stack-stamps3",
    "m5stick-c": "m5stick-c",
    "m5stick-cplus": "m5stack-stickc-plus",
    "m5stick-cplus2": "m5stack-stickc-plus2",
    # seeed
    "xiao-esp32c3": "seeed_xiao_esp32c3",
    "xiao-esp32c6": "seeed_xiao_esp32c6",
    "xiao-esp32s3": "seeed_xiao_esp32s3",
    # sparkfun
    "sparkfun-esp32-thing": "esp32thing",
    "sparkfun-iot-redboard-esp32": "sparkfun_esp32_iot_redboard",
    "sparkfun-micromod-esp32-processor": "sparkfun_esp32micromod",
    "sparkfun-thing-plus-esp32-s2-wroom": "sparkfun_esp32s2_thing_plus",
    # unexpected-maker
    "um-feathers3": "um_feathers3",
    "um-nanos3": "um_nanos3",
    "um-pros3": "um_pros3",
    "um-tinys3": "um_tinys3",
}

# USB vendor id -> usb_serial. Espressif's own VID means the SoC's native USB, which is
# native-usb-serial-jtag only on a soc that has USB-Serial-JTAG (checked by the caller).
ESPRESSIF_VID = 0x303A
# WCH ships CH340, CH343 and CH9102 under one VID; the product id tells them apart, and an
# unknown WCH product id writes nothing rather than guess ch340.
WCH_VID = 0x1A86
WCH_PIDS = {0x7523: "ch340", 0x55D3: "ch343", 0x55D4: "ch9102"}
# Silicon Labs' 0xEA60 covers CP2102, CP2102N and CP2104 alike: the manifest proves a bridge,
# not which part. FTDI has no dedicated enum value ("other", as board_backfill already does).
BRIDGE_VIDS = {0x10C4: "usb-uart-bridge-unspecified", 0x0403: "other"}

NATIVE_USB = "native-usb-serial-jtag"

# A manifest id is one filename under boards/ at the pinned ref: no slash, query or fragment
# that could point the cited URL somewhere else (a moving branch), and not a bare dot segment.
_PIO_ID_RE = re.compile(r"(?!\.+$)[A-Za-z0-9_.-]+")


def manifest_id(fm: dict, board_id: str) -> str | None:
    """The board's PlatformIO board id: the record's explicit `platformio` id (when it is a plain
    filename), else the curated table. None when neither names one."""
    explicit = (fm or {}).get("platformio")
    if isinstance(explicit, str) and _PIO_ID_RE.fullmatch(explicit.strip()):
        return explicit.strip()
    return PIO_BOARD_IDS.get(board_id)


def manifest_url(pio_id: str) -> str:
    return f"{PIO_MANIFEST_BASE}/{pio_id}.json"


def _hex(value) -> int | None:
    try:
        return int(str(value), 16)
    except (TypeError, ValueError):
        return None


def _serial_for_hwid(vid: int | None, pid: int | None, serial_jtag: bool) -> str | None:
    if vid == ESPRESSIF_VID:
        return NATIVE_USB if serial_jtag else None
    if vid == WCH_VID:
        return WCH_PIDS.get(pid)
    return BRIDGE_VIDS.get(vid)


def usb_serial_from_manifest(manifest: dict, serial_jtag: bool) -> tuple[str | None, str | None]:
    """usb_serial from the manifest's `build.hwids` (see usb_serial_from_hwids)."""
    return usb_serial_from_hwids(((manifest or {}).get("build") or {}).get("hwids"), serial_jtag)


def usb_serial_from_hwids(hwids, serial_jtag: bool) -> tuple[str | None, str | None]:
    """(value, None) when every [vid, pid] pair maps to the SAME usb_serial value through the
    fixed vendor-id table, else (None, reason): FIELD_ABSENT when there are no pairs,
    NO_PATTERN_MATCH when a pair is unknown or two pairs disagree. Shared by every source that
    states USB ids (the PlatformIO manifest, the Arduino-ESP32 boards.txt)."""
    if not hwids:
        return None, FIELD_ABSENT
    values = set()
    for pair in hwids:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            return None, NO_PATTERN_MATCH
        values.add(_serial_for_hwid(_hex(pair[0]), _hex(pair[1]), serial_jtag))
    if len(values) != 1 or None in values:
        return None, NO_PATTERN_MATCH
    return values.pop(), None


def download_mode_from_manifest(manifest: dict) -> tuple[None, str]:
    """No PlatformIO manifest key states download mode (see the module docstring), so this source
    never grounds it."""
    return None, FIELD_ABSENT


def soc_has_serial_jtag(soc: str, data_root: Path) -> bool:
    """True when data/socs/<soc>/chip.md declares native USB with a serial-jtag type."""
    path = Path(data_root) / "socs" / soc / "chip.md"
    try:
        text = path.read_text()
        fm = yaml.safe_load(text.split("---", 2)[1]) or {}
    except (OSError, IndexError, yaml.YAMLError):
        return False
    usb = fm.get("usb") or {}
    return bool(usb.get("native")) and "serial-jtag" in str(usb.get("type") or "")


def ground_from_manifest(fm: dict, board_id: str, soc: str, data_root: Path, fields: list[str],
                         fetch) -> dict:
    """Ground the requested `fields` (a subset of MANIFEST_FIELDS) from the board's manifest.
    Returns {"url": <pinned manifest url or None>, "values": {field: value},
    "reasons": {field: reason}} — every requested field lands in exactly one of the two."""
    fields = [f for f in MANIFEST_FIELDS if f in fields]
    out: dict = {"url": None, "values": {}, "reasons": {}}
    if not fields:
        return out
    pio_id = manifest_id(fm, board_id)
    if not pio_id:
        out["reasons"] = {f: NO_MANIFEST for f in fields}
        return out
    if "usb_serial" not in fields:   # download_mode alone: the manifest cannot state it, no fetch
        out["reasons"] = {f: FIELD_ABSENT for f in fields}
        return out
    url = manifest_url(pio_id)
    manifest = _fetch_manifest(url, fetch)
    if manifest is None:
        out["reasons"] = {f: DOC_UNREACHABLE for f in fields}
        return out
    out["url"] = url
    for field in fields:
        if field == "usb_serial":
            value, reason = usb_serial_from_manifest(manifest, soc_has_serial_jtag(soc, data_root))
        else:
            value, reason = download_mode_from_manifest(manifest)
        if value is None:
            out["reasons"][field] = reason
        else:
            out["values"][field] = value
    return out


def _fetch_manifest(url: str, fetch) -> dict | None:
    res = fetch(url)
    if not res.get("ok"):
        return None
    try:
        data = json.loads(res.get("text") or "")
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None
