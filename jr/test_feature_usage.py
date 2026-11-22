"""jr/feature_usage.py — per-feature 'reached' and 'used' over four windows, maintainers excluded or the
report says they are not; fakes stand in for GA4."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import feature_usage as fu

END = "2026-11-16"
DOC = {"version": 1, "low_use_acting_users": 5, "low_use_windows": 4, "features": {
    "atlas": {"pages": ["/atlas"], "page_prefixes": [], "events": ["atlas_inspect", "atlas_lens_select"]},
    "flash": {"pages": [], "page_prefixes": ["/parts/", "/firmware/"], "events": ["flash_open", "flash_connect"]}}}


def rows(per_window):
    """GA4's answer for a no-dimension report over named date ranges: one row per window that has data."""
    return {"rows": [{"dimensionValues": [{"value": f"w{i}"}], "metricValues": [{"value": str(u)}, {"value": str(e)}]}
                     for i, (u, e) in enumerate(per_window) if u or e]}


def fake_ga(answers, internal_registered=True):
    calls = []

    def ex(slug, args):
        calls.append(args)
        flt = json.dumps(args.get("dimensionFilter"))
        if "customEvent:internal" in flt and not internal_registered:
            return None                                  # GA4 rejects an unregistered dimension
        if '"page_view"' in flt:
            return rows(answers["reach:" + ("atlas" if "/atlas" in flt else "?")])
        key = "used:" + ("atlas" if "atlas_inspect" in flt else "flash")
        return rows(answers[key])
    ex.calls = calls
    return ex


ANSWERS = {"used:atlas": [(2, 10), (2, 4), (0, 0), (1, 1)], "reach:atlas": [(12, 46), (5, 9), (0, 0), (0, 0)],
           "used:flash": [(60, 119), (45, 80), (30, 50), (12, 20)]}


def test_windows_are_four_back_to_back_28_day_ranges_newest_first():
    w = fu.windows(END)
    assert w[0] == ("2026-10-20", "2026-11-16") and w[1] == ("2026-09-22", "2026-10-19") and len(w) == 4
    assert w[3][1] == "2026-08-24"


def test_used_and_reached_per_feature_with_maintainers_excluded():
    ex = fake_ga(ANSWERS)
    rep = fu.build(ex, "properties/1", END, DOC)
    assert rep.internal_excluded is True and rep.unavailable == []
    by = {r.name: r for r in rep.rows}
    assert by["atlas"].used == [2, 2, 0, 1] and by["atlas"].reached == [12, 5, 0, 0] and by["atlas"].events[0] == 10
    assert by["flash"].reached is None and by["flash"].used[0] == 60          # prefix-only: reach would restate traffic
    assert [r.name for r in rep.rows] == ["flash", "atlas"]                   # most used first
    assert all("customEvent:internal" in json.dumps(c["dimensionFilter"]) for c in ex.calls)
    assert all(len(c["dateRanges"]) == 4 for c in ex.calls)


def test_low_use_needs_every_one_of_the_last_four_windows_under_the_threshold():
    rep = fu.build(fake_ga(ANSWERS), "properties/1", END, DOC)
    by = {r.name: r for r in rep.rows}
    assert by["atlas"].low_use is True and by["flash"].low_use is False
    answers = {**ANSWERS, "used:atlas": [(2, 3), (6, 9), (0, 0), (1, 1)]}
    assert {r.name: r for r in fu.build(fake_ga(answers), "properties/1", END, DOC).rows}["atlas"].low_use is False


def test_an_unregistered_internal_dimension_is_said_out_loud_never_silent():
    rep = fu.build(fake_ga(ANSWERS, internal_registered=False), "properties/1", END, DOC)
    assert rep.internal_excluded is False and {r.name for r in rep.rows} == {"atlas", "flash"}
    text = "\n".join(fu.lines(rep))
    assert "maintainers NOT excluded" in text and "maintainers excluded" not in text.replace("NOT excluded", "")


def test_the_digest_lines_read_like_answers():
    text = fu.lines(fu.build(fake_ga(ANSWERS), "properties/1", END, DOC))
    assert text[0].startswith("*Feature usage*") and "maintainers excluded" in text[0]
    atlas = next(l for l in text if "atlas" in l)
    assert atlas == "  • atlas — 2 of 12 who reached it (17 %) · 5.0 actions each · → vs 2 · low use 4 windows"
    flash = next(l for l in text if "flash" in l)
    assert flash == "  • flash — 60 · 2.0 actions each · ↑ vs 45"


def test_a_failed_call_marks_that_feature_unavailable_and_keeps_the_rest():
    def ex(slug, args):
        return None if "flash_open" in json.dumps(args.get("dimensionFilter")) else fake_ga(ANSWERS)(slug, args)
    rep = fu.build(ex, "properties/1", END, DOC)
    assert rep.unavailable == ["flash"] and [r.name for r in rep.rows] == ["atlas"]
    assert "  • flash — unavailable (GA4 call failed)" in fu.lines(rep)


def test_the_committed_map_is_valid_and_names_only_events_the_site_sends():
    doc = fu.load_features()
    src = (Path(__file__).resolve().parent.parent / "apps" / "web" / "lib" / "analytics.ts").read_text()
    future = {"flash_outcome"}                                               # added by the flash-outcome PR
    for name, f in doc["features"].items():
        for ev in f["events"]:
            assert f'"{ev}"' in src or ev in future, (name, ev)


def test_a_malformed_map_fails_closed(tmp_path):
    for bad in ({}, {"features": {}}, {"features": {"x": {"events": []}}}, {"features": {"x": {"events": ["a"], "pages": "/x"}}}):
        p = tmp_path / "features.json"
        p.write_text(json.dumps(bad))
        with pytest.raises(ValueError):
            fu.load_features(p)


def test_one_transient_failure_does_not_flip_the_basis_or_blame_the_dimension():
    """Review of #1842: one failed filtered call (a GA4 quota/429) flipped every later row to unfiltered and the
    header blamed an unregistered `internal` dimension. The filter is decided once; a failed call is just that
    feature's row."""
    calls = []

    def ex(slug, args):
        calls.append(args)
        return None if "flash_open" in json.dumps(args.get("dimensionFilter")) else fake_ga(ANSWERS)(slug, args)
    rep = fu.build(ex, "properties/1", END, DOC)
    assert rep.internal_excluded is True and rep.unavailable == ["flash"]
    assert all("customEvent:internal" in json.dumps(c.get("dimensionFilter")) for c in calls)
    text = "\n".join(fu.lines(rep))
    assert "maintainers excluded" in text and "NOT excluded" not in text


def test_the_dimension_is_blamed_only_when_the_same_probe_succeeds_without_it():
    ex = fake_ga(ANSWERS, internal_registered=False)
    rep = fu.build(ex, "properties/1", END, DOC)
    assert rep.internal_excluded is False
    assert not any("customEvent:internal" in json.dumps(c.get("dimensionFilter")) for c in ex.calls[2:])

    def down(slug, args):                                # GA4 answers nothing at all: no cause is named
        return None
    rep = fu.build(down, "properties/1", END, DOC)
    assert rep.internal_excluded is True and rep.rows == [] and rep.unavailable == ["atlas", "flash"]
    assert "NOT excluded" not in "\n".join(fu.lines(rep))


def test_a_page_features_use_is_counted_only_on_its_own_pages():
    """Review of #1842: '/' fires wizard_submit and relax_filter too (HomeView -> executeWizard), and /wizard
    fires example_click. Counting those as wizard or examples use overstated the feature and divided two
    different groups ('15 of 11 who reached it'). A page feature's action counts only on its pages; a
    prefix-only feature has no reach to divide by and keeps every page."""
    ex = fake_ga(ANSWERS)
    fu.build(ex, "properties/1", END, DOC)
    used = [json.dumps(c["dimensionFilter"]) for c in ex.calls if '"page_view"' not in json.dumps(c["dimensionFilter"])
            and '"eventName"' in json.dumps(c["dimensionFilter"])]
    atlas = next(f for f in used if "atlas_inspect" in f)
    assert '"pagePath", "inListFilter": {"values": ["/atlas"]}' in atlas
    flash = next(f for f in used if "flash_open" in f)
    assert "pagePath" not in flash
