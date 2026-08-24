"""Generated home examples — a computed projection of real data, never stored.

    generate_examples()  # -> [{"id": "run-launcher", "label": "Run Launcher",
                         #      "kind": "firmware", "firmware": "launcher", "count": 11}, ...
                         #     {"id": "server-capable", "label": "Runs a web server / heavy app",
                         #      "kind": "needs", "needs": {"psram_min": 2, "type": "board"},
                         #      "count": 35}, ...]

The `example` DATA ENTITY is owned by SPEC-discovery (G2, not yet specced); this
module deliberately creates no schema and no data/ folder. Every example is
recomputed from the records already in the repo, so the list can never go stale:

- kind="firmware" (Shelf A) — one "Run <name>" per firmware that has >=1 recipe,
  read off disk via esp_atlas_core.firmware (like brands, firmware/recipes are
  never in esp-atlas.db). `count` is its recipe count (= boards it runs on);
  the shelf is ordered by (-count, label). The no-orphan-firmware CI rule already
  guarantees >=1 recipe per firmware, but the check here is defensive so the
  generator stays correct on a tree that never ran CI.
- kind="needs" (Shelf B/C) — fixed candidate queries over real `parts` columns
  plus the top form factors from facets(), resolved through wizard() against
  esp-atlas.db. A candidate is emitted only when it returns >=1 result, so a
  surfaced example can never be a dead end (the SPEC-INDEX G7 invariant; the
  oracle in apps/core/tests/test_wizard_oracle.py gates it).

Output is deterministic for a given dataset — no analytics, no randomness
(cold-start-neutral order per SPEC-home-explorer §3b; click-ordering is L3).
"""
from esp_atlas_core.facets import facets
from esp_atlas_core.firmware import list_firmware, recipes_for_firmware
from esp_atlas_core.wizard import wizard

# (id, label, needs) — fixed candidates over real fields; only those with >=1
# wizard() result are emitted. Labels are user-facing UI copy.
_NEEDS_CANDIDATES = (
    ("server-capable", "Runs a web server / heavy app", {"psram_min": 2, "type": "board"}),
    ("mesh", "Smart-home mesh (Thread / Zigbee / Matter)", {"ieee802154": True, "type": "board"}),
    ("cheap-native-usb", "Cheap board with native USB", {"usb_native": True, "budget": "cheap", "type": "board"}),
    ("wifi-6", "Wi-Fi 6", {"radio": "wifi-6"}),
    ("band-5ghz", "5 GHz Wi-Fi", {"band": 5}),
)

# form factors with a recognizable size identity; vendor-specific values
# (heltec, inkplate, firebeetle, ...) read as brand names, not intents, and the
# free-string form_factor column has 32 values — so only curated ones become
# examples. Extend the map to surface another.
_FORM_LABELS = {"xiao": "XIAO-sized", "feather": "Feather-sized", "m5-core": "M5-core-sized"}
_FORM_EXAMPLE_LIMIT = 2


def _firmware_examples():
    examples = []
    for fw in list_firmware():
        recipes = recipes_for_firmware(fw["id"])
        if not recipes:
            continue
        examples.append(
            {
                "id": f"run-{fw['id']}",
                "label": f"Run {fw['name']}",
                "kind": "firmware",
                "firmware": fw["id"],
                "count": len(recipes),
            }
        )
    examples.sort(key=lambda e: (-e["count"], e["label"]))
    return examples


def _form_candidates(db_path):
    candidates = []
    for entry in facets(db_path).get("form_factor", []):
        value = entry["value"]
        if value not in _FORM_LABELS:
            continue
        candidates.append((f"form-{value}", _FORM_LABELS[value], {"form": value}))
        if len(candidates) >= _FORM_EXAMPLE_LIMIT:
            break
    return candidates


def _needs_examples(db_path):
    examples = []
    for example_id, label, needs in tuple(_NEEDS_CANDIDATES) + tuple(_form_candidates(db_path)):
        count = len(wizard(needs, db_path=db_path))
        if not count:
            continue
        examples.append(
            {"id": example_id, "label": label, "kind": "needs", "needs": dict(needs), "count": count}
        )
    return examples


def generate_examples(db_path=None):
    """Every currently-generatable example; each resolves to >=1 result."""
    return _firmware_examples() + _needs_examples(db_path)
