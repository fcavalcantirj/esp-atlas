"""extract_usb_serial must only ever emit values in the schema's usb_serial enum —
a value outside it fails the guard and aborts the whole tick."""
import json

import board_backfill as bb

_ENUM = set(json.load(open(bb.REPO / "schema" / "board.schema.json"))["properties"]["usb_serial"]["enum"])


def test_every_emitted_value_is_in_the_schema_enum():
    samples = [
        "embedded FTDI FT2232HL chip",          # FTDI -> other
        "FT232RL usb bridge",                   # FTDI -> other
        "built-in USB Serial/JTAG controller",  # slash form -> native-usb-serial-jtag
        "CP2102N USB-to-UART bridge",           # cp2102n
        "uses a CH340 bridge",                  # ch340
    ]
    for text in samples:
        v = bb.extract_usb_serial(text)
        assert v in _ENUM, f"{text!r} -> {v!r} is NOT a valid usb_serial enum value"


def test_ftdi_maps_to_other_and_jtag_slash_is_native():
    assert bb.extract_usb_serial("embedded FTDI FT2232HL chip") == "other"
    assert bb.extract_usb_serial("via the USB Serial/JTAG controller") == "native-usb-serial-jtag"
    assert bb.extract_usb_serial("a generic USB-to-UART bridge") is None   # unnamed -> omit
