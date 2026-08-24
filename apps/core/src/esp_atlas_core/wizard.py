"""Deterministic needs -> ranked parts, no LLM, no cost, un-abusable.

    wizard({"protocol": "zigbee", "usb_native": True})
    wizard({"radio": "wifi-6", "band": 5})
    wizard({"budget": "cheap"})  # spending ceiling over each board's editorial price_tier

Every scored need is grounded in a real `parts` column. `budget` never scores
a part (price is editorial, not a hard spec) — it only filters: a part whose
`price_tier` is above the chosen ceiling is dropped, while a part with no
`price_tier` at all (unrated) is always kept, since an unknown price is never
grounds to hide a part.
"""
from esp_atlas_core.search import search

# need key -> (search filter key, score, reason)
_HARD_NEEDS = {
    "protocol": lambda v: ("protocol", v, 3, f"Supports {v} over 802.15.4"),
    "radio": lambda v: ("radio", v, 2, f"{v} Wi-Fi or newer (backward compatible)"),
    "band": lambda v: ("band", v, 1, f"{v} GHz Wi-Fi band"),
    "ble": lambda v: ("ble", v, 1, "Bluetooth Low Energy"),
    "bt_classic": lambda v: ("bt_classic", v, 1, "Bluetooth Classic (BR/EDR)"),
    "usb_native": lambda v: ("usb_native", v, 2, "Native USB (no external UART bridge)"),
    "ieee802154": lambda v: ("ieee802154", v, 3, "802.15.4 mesh radio (Thread/Zigbee/Matter)"),
    "form": lambda v: ("form", v, 1, f"{v} form factor"),
    "type": lambda v: ("type", v, 0, None),
    "psram_min": lambda v: (
        "psram_min",
        v,
        0,
        f"psram_min={v}: PSRAM >= {v} MB (headroom to host a web app); boards without PSRAM data excluded",
    ),
    "flash_min": lambda v: (
        "flash_min",
        v,
        0,
        f"flash_min={v}: Flash >= {v} MB; boards without flash data excluded",
    ),
}
KNOWN_NEEDS = set(_HARD_NEEDS) | {"budget"}

_TYPE_ORDER = {"board": 0, "module": 1, "soc": 2}

# cumulative spending ceiling: budget=X includes every tier up to and including X
_BUDGET_TIERS = ("cheap", "medium", "expensive")


def _normalize_budget(budget):
    if budget in (None, ""):
        return None
    if budget not in _BUDGET_TIERS:
        raise ValueError(f"unknown budget tier: {budget!r}, expected one of {_BUDGET_TIERS} or ''")
    return budget


def _within_budget(price_tier, budget):
    if budget is None or price_tier is None:
        return True  # no ceiling, or an unrated (unknown) part — never excluded
    return _BUDGET_TIERS.index(price_tier) <= _BUDGET_TIERS.index(budget)


def wizard(needs, db_path=None, limit=500):
    needs = dict(needs or {})
    unknown = set(needs) - KNOWN_NEEDS
    if unknown:
        raise ValueError(f"unknown wizard need(s): {sorted(unknown)}")

    budget = _normalize_budget(needs.pop("budget", None))
    filters = {}
    score_bonus = 0
    reasons = []
    for key, value in needs.items():
        filter_key, filter_value, points, reason = _HARD_NEEDS[key](value)
        if key in ("ble", "bt_classic", "usb_native", "ieee802154", "psram_min", "flash_min") and not value:
            continue  # a falsy need (False, or a 0/None floor) doesn't filter or score
        filters[filter_key] = filter_value
        score_bonus += points
        if reason:
            reasons.append(reason)

    if budget is not None:
        reasons.append(f"budget={budget}: price_tier <= {budget} (parts with no price_tier are always included)")

    records = search("", filters=filters, db_path=db_path, limit=limit * 4)
    records = [r for r in records if _within_budget(r["price_tier"], budget)]

    scored = [{**rec, "score": score_bonus, "reasons": list(reasons)} for rec in records]
    scored.sort(key=lambda r: (-r["score"], _TYPE_ORDER.get(r["type"], 9), r["name"]))
    return scored[:limit]
