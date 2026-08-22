"""Deterministic needs -> ranked parts, no LLM, no cost, un-abusable.

    wizard({"protocol": "zigbee", "usb_native": True})
    wizard({"radio": "wifi-6", "band": 5})

Every scored need is grounded in a real `parts` column. `budget` is accepted
(the interface spec names it as an example need) but esp-atlas carries no
price data, so it is never used to score or exclude a part — it only adds a
transparency note, rather than inventing a signal the dataset doesn't have.
"""
from esp_atlas_core.search import search

# need key -> (search filter key, score, reason)
_HARD_NEEDS = {
    "protocol": lambda v: ("protocol", v, 3, f"Supports {v} over 802.15.4"),
    "radio": lambda v: ("radio", v, 2, f"{v} Wi-Fi"),
    "band": lambda v: ("band", v, 1, f"{v} GHz Wi-Fi band"),
    "ble": lambda v: ("ble", v, 1, "Bluetooth Low Energy"),
    "bt_classic": lambda v: ("bt_classic", v, 1, "Bluetooth Classic (BR/EDR)"),
    "usb_native": lambda v: ("usb_native", v, 2, "Native USB (no external UART bridge)"),
    "ieee802154": lambda v: ("ieee802154", v, 2, "802.15.4 radio present"),
    "form": lambda v: ("form", v, 1, f"{v} form factor"),
    "type": lambda v: ("type", v, 0, None),
}
KNOWN_NEEDS = set(_HARD_NEEDS) | {"budget"}

_TYPE_ORDER = {"board": 0, "module": 1, "soc": 2}


def wizard(needs, db_path=None, limit=50):
    needs = dict(needs or {})
    unknown = set(needs) - KNOWN_NEEDS
    if unknown:
        raise ValueError(f"unknown wizard need(s): {sorted(unknown)}")

    budget = needs.pop("budget", None)
    filters = {}
    score_bonus = 0
    reasons = []
    for key, value in needs.items():
        filter_key, filter_value, points, reason = _HARD_NEEDS[key](value)
        if key in ("ble", "bt_classic", "usb_native", "ieee802154") and not value:
            continue  # a False need doesn't filter or score
        filters[filter_key] = filter_value
        score_bonus += points
        if reason:
            reasons.append(reason)

    if budget is not None:
        reasons.append(f"budget={budget} not modeled — esp-atlas has no price data yet")

    records = search("", filters=filters, db_path=db_path, limit=limit * 4)

    scored = [{**rec, "score": score_bonus, "reasons": list(reasons)} for rec in records]
    scored.sort(key=lambda r: (-r["score"], _TYPE_ORDER.get(r["type"], 9), r["name"]))
    return scored[:limit]
