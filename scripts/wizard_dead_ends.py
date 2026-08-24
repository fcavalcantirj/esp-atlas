#!/usr/bin/env python3
"""Report (not a gate): sweep every 2-filter wizard combo, print the empty ones.

Complements apps/core/tests/test_wizard_oracle.py's "no dead options" invariant,
which only checks each option in isolation. Two options can each return results
individually yet return nothing together -- that's not automatically a bug: some
combinations are honestly impossible (e.g. a form factor that only ships on a
Wi-Fi-4 SoC, paired with radio=wifi-6). This script exists so a human can eyeball
the empty combos and separate "impossible combo, fine" from "missing data, not
fine" -- it never fails the build.

    python3 scripts/wizard_dead_ends.py
"""
import itertools
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "core" / "src"))

from esp_atlas_core.index_build import build_index  # noqa: E402
from esp_atlas_core.wizard import wizard  # noqa: E402

# Same fixed set as the oracle test's "no dead options" invariant.
_BUDGET_TIERS = ("cheap", "medium", "expensive")
_PSRAM_MIN_TIERS = (2, 4, 8)
_FLASH_MIN_TIERS = (4, 8, 16)


def _enumerate_options(db_path):
    all_records = wizard({}, db_path=db_path)
    form_factors = sorted({r["form_factor"] for r in all_records if r["form_factor"]})
    content_types = sorted({r["type"] for r in all_records})
    wifi_standards = sorted({r["wifi_standard"] for r in all_records if r["wifi_standard"]})
    wifi_bands = set()
    for r in all_records:
        if r["wifi_bands"]:
            wifi_bands.update(r["wifi_bands"].split(","))

    return (
        [("form", f) for f in form_factors]
        + [("type", t) for t in content_types]
        + [("radio", w) for w in wifi_standards]
        + [("band", float(b)) for b in sorted(wifi_bands, key=float)]
        + [("budget", tier) for tier in _BUDGET_TIERS]
        + [("ieee802154", True), ("usb_native", True)]
        + [("psram_min", t) for t in _PSRAM_MIN_TIERS]
        + [("flash_min", t) for t in _FLASH_MIN_TIERS]
    )


def main():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "esp-atlas.db"
        build_index(db_path=db_path)
        options = _enumerate_options(db_path)

        total = 0
        empty_combos = []
        for (k1, v1), (k2, v2) in itertools.combinations(options, 2):
            if k1 == k2:
                continue  # can't combine two values of the same need
            total += 1
            need = {k1: v1, k2: v2}
            if not wizard(need, db_path=db_path):
                empty_combos.append(need)

        print(f"{len(empty_combos)} of {total} 2-filter combos return 0 results:\n")
        for need in empty_combos:
            print(f"  {need}")


if __name__ == "__main__":
    main()
