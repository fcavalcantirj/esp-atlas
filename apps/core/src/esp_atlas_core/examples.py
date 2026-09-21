"""Generated home examples — a computed projection of real data, never stored.

    generate_examples()  # -> [{"id": "run-launcher", "label": "Run Launcher",
                         #      "kind": "firmware", "group": "run-firmware",
                         #      "firmware": "launcher", "count": 11}, ...
                         #     {"id": "server-capable", "label": "Runs a web server / heavy app",
                         #      "kind": "needs", "group": "build-project",
                         #      "needs": {"psram_min": 2, "type": "board"}, "count": 35}, ...]

The `example` DATA ENTITY is owned by SPEC-discovery (G2, not yet specced); this
module deliberately creates no schema and no data/ folder. Every example is
recomputed from the records already in the repo, so the list can never go stale:

- kind="firmware" (Shelf A) — one "Run <name>" per firmware that has >=1 recipe,
  read off disk via esp_atlas_core.firmware (like brands, firmware/recipes are
  never in esp-atlas.db). `count` is its recipe count (= boards it runs on);
  `stars`/`forks` carry the firmware's own `popularity` when cited. The shelf
  is ordered by esp_atlas_core.firmware.sort_by_popularity -- the SAME
  comparator `/firmware?sort=popularity` uses, so the two surfaces can never
  rank a firmware differently (SPEC-firmware-popularity.md §3.C). The
  no-orphan-firmware CI rule already guarantees >=1 recipe per firmware, but
  the check here is defensive so the generator stays correct on a tree that
  never ran CI.
- kind="needs" (Shelf B/C) — fixed candidate queries over real `parts` columns
  plus the top form factors from facets(), resolved through wizard() against
  esp-atlas.db. A candidate is emitted only when it returns >=1 result, so a
  surfaced example can never be a dead end (the SPEC-INDEX G7 invariant; the
  oracle in apps/core/tests/test_wizard_oracle.py gates it).

`group` is the home's three soft shelves (SPEC-home-explorer §2): "run-firmware"
(the recipe graph), "build-project" (capability filters), "just-show-me"
(discovery). It is a property of the example, not of how a page paints it, so it
is decided here rather than re-derived in the client.

Output is deterministic for a given dataset — no analytics, no randomness
(cold-start-neutral order per SPEC-home-explorer §3b; click-ordering is L3).
"""
import json

from esp_atlas_core import db as dbmod
from esp_atlas_core.facets import facets
from esp_atlas_core.firmware import list_firmware, list_recipes, sort_by_popularity
from esp_atlas_core.wizard import wizard

# meta table key (see esp_atlas_core.db) holding generate_examples()'s output,
# precomputed once by index_build.build_index() -- see read_examples() below.
_EXAMPLES_META_KEY = "examples_json"

RUN_FIRMWARE = "run-firmware"
BUILD_PROJECT = "build-project"
JUST_SHOW_ME = "just-show-me"
GROUPS = (RUN_FIRMWARE, BUILD_PROJECT, JUST_SHOW_ME)

# (id, label, group, needs) — fixed candidates over real fields; only those with
# >=1 wizard() result are emitted. Labels are user-facing UI copy.
_NEEDS_CANDIDATES = (
    ("server-capable", "Runs a web server / heavy app", BUILD_PROJECT, {"psram_min": 2, "type": "board"}),
    ("mesh", "Smart-home mesh (Thread / Zigbee / Matter)", BUILD_PROJECT, {"ieee802154": True, "type": "board"}),
    ("cheap-native-usb", "Cheap board with native USB", BUILD_PROJECT, {"usb_native": True, "budget": "cheap", "type": "board"}),
    ("wifi-6", "Wi-Fi 6", JUST_SHOW_ME, {"radio": "wifi-6"}),
    ("band-5ghz", "5 GHz Wi-Fi", JUST_SHOW_ME, {"band": 5}),
)

# form factors with a recognizable size identity; vendor-specific values
# (heltec, inkplate, firebeetle, ...) read as brand names, not intents, and the
# free-string form_factor column has 32 values — so only curated ones become
# examples. Extend the map to surface another.
# firmware `category` (a fixed enum) rendered for humans. The card's middle tier
# says what a firmware IS, and it is derived from the record -- never editorial
# copy someone typed, which the project does not do.
_CATEGORY_LABELS = {
    "pentest": "Pentest",
    "mesh": "Mesh",
    "badusb": "BadUSB",
    "display": "Display",
    "home": "Home automation",
    "multi": "Multi-tool",
}
_DESCRIPTION_CAPABILITIES = 3

_FORM_LABELS = {"xiao": "XIAO-sized", "feather": "Feather-sized", "m5-core": "M5-core-sized"}
_FORM_EXAMPLE_LIMIT = 2


def describe_firmware(fw):
    """"Pentest · wifi, ble, sub-ghz" — the category plus what it can do.

    Capabilities that merely restate the category are dropped, so a badusb
    firmware whose only capability is `badusb` reads "BadUSB", not "BadUSB · badusb".
    """
    category = fw.get("category")
    label = _CATEGORY_LABELS.get(category, category)
    caps = [c for c in (fw.get("capabilities") or []) if c != category][:_DESCRIPTION_CAPABILITIES]
    if label and caps:
        return f"{label} · {', '.join(caps)}"
    return label or (", ".join(caps) if caps else None)


def _firmware_examples():
    # Group once instead of calling recipes_for_firmware() per firmware -- that
    # helper rescans and reparses every recipe file on disk on each call, which
    # turns this loop into an N+1 storm (dozens of firmware x hundreds of files).
    recipes_by_firmware = {}
    for recipe in list_recipes():
        recipes_by_firmware.setdefault(recipe["firmware"], []).append(recipe)

    examples = []
    for fw in sort_by_popularity(list_firmware()):
        recipes = recipes_by_firmware.get(fw["id"], [])
        if not recipes:
            continue
        example = {
            "id": f"run-{fw['id']}",
            "label": f"Run {fw['name']}",
            "kind": "firmware",
            "group": RUN_FIRMWARE,
            "firmware": fw["id"],
            "count": len(recipes),
        }
        description = describe_firmware(fw)
        if description:
            example["description"] = description
        popularity = fw.get("popularity") or {}
        if popularity.get("stars") is not None:
            example["stars"] = popularity["stars"]
        if popularity.get("forks") is not None:
            example["forks"] = popularity["forks"]
        examples.append(example)
    return examples


def _form_candidates(db_path):
    candidates = []
    for entry in facets(db_path).get("form_factor", []):
        value = entry["value"]
        if value not in _FORM_LABELS:
            continue
        candidates.append((f"form-{value}", _FORM_LABELS[value], JUST_SHOW_ME, {"form": value}))
        if len(candidates) >= _FORM_EXAMPLE_LIMIT:
            break
    return candidates


def _needs_examples(db_path):
    examples = []
    for example_id, label, group, needs in tuple(_NEEDS_CANDIDATES) + tuple(_form_candidates(db_path)):
        count = len(wizard(needs, db_path=db_path))
        if not count:
            continue
        examples.append(
            {
                "id": example_id,
                "label": label,
                "kind": "needs",
                "group": group,
                "needs": dict(needs),
                "count": count,
            }
        )
    return examples


def generate_examples(db_path=None):
    """Every currently-generatable example; each resolves to >=1 result."""
    return _firmware_examples() + _needs_examples(db_path)


def read_examples(db_path=None):
    """generate_examples()'s output, read from the precomputed row index_build.
    build_index() stores at build time (see there) instead of recomputing it on
    every call. Falls back to generate_examples() itself when the index
    predates the cache (e.g. a build that hasn't run since this landed)."""
    conn = dbmod.connect(db_path)
    try:
        cached = dbmod.get_meta(conn, _EXAMPLES_META_KEY)
    finally:
        conn.close()
    if cached is None:
        return generate_examples(db_path=db_path)
    return json.loads(cached)
