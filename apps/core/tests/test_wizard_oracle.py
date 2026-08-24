"""ORACLE test suite for the wizard: mechanical invariants over the full,
exhaustively-enumerated filter space (the board set is small enough to sweep
in full, so we do — no sampling).

These are not example-based regression tests (see test_wizard.py for those);
they encode properties that must hold for *any* value the wizard can offer,
derived from what is actually present in the built index, so a new board or
a new form factor is automatically swept in. Each assertion names the exact
offending query (and, for the inheritance check, the offending board) so a
failure is immediately actionable.

The wifi-4/wifi-6 superset bug (radio="wifi-4" wrongly excluding wifi-6
parts) is exactly what invariant 1 below is built to catch mechanically,
instead of relying on a human writing one more example test per regression.
"""
import pytest

from esp_atlas_core.examples import generate_examples
from esp_atlas_core.firmware import recipes_for_firmware
from esp_atlas_core.wizard import wizard

# Fixed by wizard._BUDGET_TIERS / SPEC.md's price_tier field -- not derived
# from data, since "expensive" boards may not exist yet and the option must
# still be swept.
_BUDGET_TIERS = ("cheap", "medium", "expensive")

# Fixed by SPEC-hosting-lane.md's UI dropdowns -- not derived from data, same
# reasoning as _BUDGET_TIERS above.
_PSRAM_MIN_TIERS = (2, 4, 8)
_FLASH_MIN_TIERS = (4, 8, 16)


@pytest.fixture(scope="module")
def all_records(built_db_path):
    return wizard({}, db_path=built_db_path)


@pytest.fixture(scope="module")
def form_factors(all_records):
    return sorted({r["form_factor"] for r in all_records if r["form_factor"]})


@pytest.fixture(scope="module")
def content_types(all_records):
    return sorted({r["type"] for r in all_records})


@pytest.fixture(scope="module")
def wifi_standards(all_records):
    return sorted({r["wifi_standard"] for r in all_records if r["wifi_standard"]})


@pytest.fixture(scope="module")
def wifi_bands(all_records):
    bands = set()
    for r in all_records:
        if r["wifi_bands"]:
            bands.update(r["wifi_bands"].split(","))
    return sorted(bands, key=float)


def _ids(records):
    return {r["id"] for r in records}


# ---------------------------------------------------------------------------
# 1. Superset monotonicity: a "minimum capability" filter (radio, band) must
#    return a superset of the stricter filter it dominates. This is the exact
#    oracle for the wifi-4/wifi-6 bug just fixed.
# ---------------------------------------------------------------------------


def test_radio_wifi4_is_superset_of_radio_wifi6(built_db_path):
    wifi4_ids = _ids(wizard({"radio": "wifi-4"}, db_path=built_db_path))
    wifi6_ids = _ids(wizard({"radio": "wifi-6"}, db_path=built_db_path))
    missing = wifi6_ids - wifi4_ids
    assert not missing, (
        "wizard(radio=wifi-4) must be a superset of wizard(radio=wifi-6); "
        f"missing ids: {sorted(missing)}"
    )


def test_band_2_4_is_superset_of_band_5(built_db_path):
    band_2_4_ids = _ids(wizard({"band": 2.4}, db_path=built_db_path))
    band_5_ids = _ids(wizard({"band": 5}, db_path=built_db_path))
    missing = band_5_ids - band_2_4_ids
    assert not missing, (
        "wizard(band=2.4) must be a superset of wizard(band=5); "
        f"missing ids: {sorted(missing)}"
    )


def test_psram_min_is_superset_monotonic(built_db_path):
    failures = []
    for lo, hi in zip(_PSRAM_MIN_TIERS, _PSRAM_MIN_TIERS[1:]):
        lo_ids = _ids(wizard({"psram_min": lo}, db_path=built_db_path))
        hi_ids = _ids(wizard({"psram_min": hi}, db_path=built_db_path))
        missing = hi_ids - lo_ids
        if missing:
            failures.append(f"psram_min={lo} must be a superset of psram_min={hi}; missing ids: {sorted(missing)}")
    assert not failures, "\n".join(failures)


def test_flash_min_is_superset_monotonic(built_db_path):
    failures = []
    for lo, hi in zip(_FLASH_MIN_TIERS, _FLASH_MIN_TIERS[1:]):
        lo_ids = _ids(wizard({"flash_min": lo}, db_path=built_db_path))
        hi_ids = _ids(wizard({"flash_min": hi}, db_path=built_db_path))
        missing = hi_ids - lo_ids
        if missing:
            failures.append(f"flash_min={lo} must be a superset of flash_min={hi}; missing ids: {sorted(missing)}")
    assert not failures, "\n".join(failures)


# ---------------------------------------------------------------------------
# 2. Subset monotonicity: adding any single filter to any base query must
#    never grow the result set.
# ---------------------------------------------------------------------------


def test_subset_monotonicity_adding_a_filter_never_grows_results(
    built_db_path, form_factors, content_types, wifi_standards, wifi_bands
):
    candidate_filters = (
        [("form", f) for f in form_factors]
        + [("type", t) for t in content_types]
        + [("radio", w) for w in wifi_standards]
        + [("band", float(b)) for b in wifi_bands]
        + [("budget", tier) for tier in _BUDGET_TIERS]
        + [("ieee802154", True), ("usb_native", True)]
        + [("psram_min", t) for t in _PSRAM_MIN_TIERS]
        + [("flash_min", t) for t in _FLASH_MIN_TIERS]
    )
    base_queries = [
        {},
        {"protocol": "zigbee"},
        {"radio": "wifi-4"},
        {"form": "xiao"},
        {"usb_native": True},
        {"ieee802154": True},
        {"type": "board"},
        {"budget": "cheap"},
    ]

    failures = []
    for base in base_queries:
        base_ids = _ids(wizard(base, db_path=built_db_path))
        for key, value in candidate_filters:
            if key in base:
                continue  # not "adding" a filter if the base already sets it
            extended = {**base, key: value}
            extended_ids = _ids(wizard(extended, db_path=built_db_path))
            grew = extended_ids - base_ids
            if grew:
                failures.append(
                    f"base={base} + {key}={value!r} added {sorted(grew)} "
                    f"not present in base query {base}"
                )
    assert not failures, "subset monotonicity violated:\n" + "\n".join(failures)


# ---------------------------------------------------------------------------
# 3. No dead options: every value the wizard actually offers must return at
#    least one result on its own.
# ---------------------------------------------------------------------------


def test_no_dead_wizard_options(
    built_db_path, form_factors, content_types, wifi_standards, wifi_bands
):
    options = (
        [({"form": f}, f"form={f}") for f in form_factors]
        + [({"type": t}, f"type={t}") for t in content_types]
        + [({"radio": w}, f"radio={w}") for w in wifi_standards]
        + [({"band": float(b)}, f"band={b}") for b in wifi_bands]
        + [({"budget": tier}, f"budget={tier}") for tier in _BUDGET_TIERS]
        + [({"ieee802154": True}, "ieee802154=True")]
        + [({"usb_native": True}, "usb_native=True")]
        + [({"psram_min": t}, f"psram_min={t}") for t in _PSRAM_MIN_TIERS]
        + [({"flash_min": t}, f"flash_min={t}") for t in _FLASH_MIN_TIERS]
    )

    dead = [label for need, label in options if not wizard(need, db_path=built_db_path)]
    assert not dead, f"dead wizard option(s), 0 results: {dead}"


# ---------------------------------------------------------------------------
# 4. Soundness: every result actually satisfies the need, re-derived from its
#    own record fields (not from the query that produced it).
# ---------------------------------------------------------------------------


def test_soundness_every_result_satisfies_its_need(
    built_db_path, form_factors, content_types
):
    failures = []

    def check(need, predicate, label):
        for r in wizard(need, db_path=built_db_path):
            if not predicate(r):
                failures.append(f"{label}: {r['id']} does not satisfy it (record={r})")

    check({"ieee802154": True}, lambda r: bool(r["ieee802154"]), "ieee802154=True")
    check({"usb_native": True}, lambda r: bool(r["usb_native"]), "usb_native=True")

    check({"budget": "cheap"}, lambda r: r["price_tier"] in ("cheap", None), "budget=cheap")
    check(
        {"budget": "medium"},
        lambda r: r["price_tier"] in ("cheap", "medium", None),
        "budget=medium",
    )
    check({"budget": "expensive"}, lambda r: True, "budget=expensive")

    check({"radio": "wifi-6"}, lambda r: r["wifi_standard"] == "wifi-6", "radio=wifi-6")
    check(
        {"radio": "wifi-4"},
        lambda r: r["wifi_standard"] in ("wifi-4", "wifi-6"),
        "radio=wifi-4",
    )

    check({"band": 2.4}, lambda r: "2.4" in (r["wifi_bands"] or "").split(","), "band=2.4")
    check({"band": 5}, lambda r: "5" in (r["wifi_bands"] or "").split(","), "band=5")

    for f in form_factors:
        check({"form": f}, lambda r, f=f: r["form_factor"] == f, f"form={f}")
    for t in content_types:
        check({"type": t}, lambda r, t=t: r["type"] == t, f"type={t}")

    assert not failures, "soundness violations:\n" + "\n".join(failures)


# ---------------------------------------------------------------------------
# 5. Unknown-exclusion: a psram_min/flash_min floor above 0 must never return a
#    part whose psram_mb/flash_mb is unknown (null) -- an unproven part is not
#    a match, never a silent 0.
# ---------------------------------------------------------------------------


def test_psram_min_and_flash_min_exclude_unknown_memory(built_db_path):
    failures = []
    for t in _PSRAM_MIN_TIERS:
        for r in wizard({"psram_min": t}, db_path=built_db_path):
            if r["psram_mb"] is None:
                failures.append(f"psram_min={t}: {r['id']} has unknown psram_mb but was returned")
    for t in _FLASH_MIN_TIERS:
        for r in wizard({"flash_min": t}, db_path=built_db_path):
            if r["flash_mb"] is None:
                failures.append(f"flash_min={t}: {r['id']} has unknown flash_mb but was returned")
    assert not failures, "unknown-exclusion violations:\n" + "\n".join(failures)


# ---------------------------------------------------------------------------
# 6. Board<->SoC inheritance consistency: a board's derived radio capabilities
#    must equal those of the SoC it (directly or via a module) references.
# ---------------------------------------------------------------------------


def test_board_soc_inheritance_consistency(all_records):
    boards = [r for r in all_records if r["type"] == "board"]
    socs_by_id = {r["id"]: r for r in all_records if r["type"] == "soc"}
    inherited_fields = ("ieee802154", "wifi_standard", "wifi_bands", "ble_version")

    mismatches = []
    for board in boards:
        soc_id = board["soc_ref"]
        soc = socs_by_id.get(soc_id)
        if soc is None:
            mismatches.append(f"{board['id']}: soc_ref={soc_id!r} does not match any known soc")
            continue
        for field in inherited_fields:
            if board[field] != soc[field]:
                mismatches.append(
                    f"{board['id']}: {field}={board[field]!r} disagrees with its soc "
                    f"{soc_id} ({field}={soc[field]!r})"
                )
    assert not mismatches, "board<->soc inheritance mismatches:\n" + "\n".join(mismatches)


# ---------------------------------------------------------------------------
# 7. No dead examples (SPEC-INDEX G7): every generated home example must
#    resolve to at least one result -- a needs-example through the wizard, a
#    firmware-example through its recipe list. The generator drops empty
#    candidates by construction; this is the independent gate that keeps it
#    honest as data changes.
# ---------------------------------------------------------------------------


def test_no_dead_examples_every_generated_example_resolves(built_db_path):
    examples = generate_examples(db_path=built_db_path)
    assert examples, "generate_examples returned nothing at all"

    dead = []
    for ex in examples:
        if ex["kind"] == "needs":
            if not wizard(ex["needs"], db_path=built_db_path):
                dead.append(f"{ex['id']}: needs={ex['needs']} returns 0 wizard results")
        elif ex["kind"] == "firmware":
            if not recipes_for_firmware(ex["firmware"]):
                dead.append(f"{ex['id']}: firmware={ex['firmware']} has 0 recipes")
        else:
            dead.append(f"{ex['id']}: unknown kind {ex['kind']!r}")
    assert not dead, "dead example(s), 0 results:\n" + "\n".join(dead)
