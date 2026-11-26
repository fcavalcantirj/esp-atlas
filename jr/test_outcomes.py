"""jr/outcomes.py — SPEC-outcome-attribution.md. Pure functions over fake git log text and fake GSC rows."""
from datetime import date

import outcomes as oc

LOG = ("@@ 1111111 2026-11-02T15:00:00Z jr/tick-20261102-1400-bf\n"
       "M\tdata/boards/espressif/esp32-devkitc/board.md\n"
       "@@ 2222222 2026-11-03T02:00:00Z jr/tick-20261103-0100\n"
       "A\tdata/firmware/newfw/firmware.md\n"
       "A\tdata/recipes/m5cardputer__newfw/recipe.md\n"
       "@@ 3333333 2026-11-04T10:00:00Z feat/site\n"
       "M\tapps/web/app/page.tsx\n")


def test_changes_come_from_main_history_with_urls_kind_lane_and_pacific_day():
    ch = oc.changes_from_log(LOG)
    assert [(c["sha"], c["lane"], c["kind"]) for c in ch] == [("1111111", "backfill", "modified"), ("2222222", "tick", "added")]
    assert ch[0]["urls"] == ["/parts/esp32-devkitc"]
    assert set(ch[1]["urls"]) == {"/firmware/newfw", "/parts/m5cardputer"}       # a recipe touches both pages
    assert ch[1]["day"] == date(2026, 11, 2)                                    # 02:00Z is Nov 2 in Pacific time


def _rows(page, start, days, impr):
    return [{"keys": [f"https://esp-atlas.com{page}", (start + __import__("datetime").timedelta(d)).isoformat()],
             "clicks": 0, "impressions": impr(d), "position": 9.0} for d in range(days)]


def test_effect_is_difference_in_differences_against_untouched_pages_of_the_same_type():
    start = date(2026, 10, 19)
    rows = (_rows("/parts/esp32-devkitc", start, 40, lambda d: 10 if d < 14 else 20)       # treated: x2 after
            + _rows("/parts/control-a", start, 40, lambda d: 100 if d < 14 else 150))     # site trend: x1.5
    ch = [{"sha": "1", "day": date(2026, 11, 2), "urls": ["/parts/esp32-devkitc"], "lane": "backfill", "kind": "modified"}]
    out = oc.cohort_effects(ch, oc.page_days(rows), today=date(2026, 12, 15), windows=(7,))
    w = out[0]["windows"][7]
    assert w["pre"] == 70 and w["post"] == 140 and w["mature"]
    assert abs(w["control_ratio"] - 1.5) < 1e-9 and abs(w["effect"] - 35) < 1e-9      # 70 - 70*0.5


def test_a_window_not_yet_past_is_immature_never_a_verdict():
    ch = [{"sha": "1", "day": date(2026, 11, 20), "urls": ["/parts/x"], "lane": "backfill", "kind": "modified"}]
    out = oc.cohort_effects(ch, {}, today=date(2026, 11, 26), windows=(28,))
    assert out[0]["windows"][28]["mature"] is False and out[0]["windows"][28]["effect"] is None


def test_new_pages_have_no_pre_and_no_did():
    ch = [{"sha": "2", "day": date(2026, 11, 2), "urls": ["/firmware/newfw"], "lane": "tick", "kind": "added"}]
    rows = _rows("/firmware/newfw", date(2026, 11, 5), 10, lambda d: 3)
    w = oc.cohort_effects(ch, oc.page_days(rows), today=date(2026, 12, 15), windows=(7,))[0]["windows"][7]
    assert w["pre"] is None and w["post"] == 21 and w["effect"] is None


def test_a_thin_control_gives_no_effect():
    """Real run 2026-11-26: launch weeks had a control ratio of x159 from near-zero pre impressions."""
    start = date(2026, 10, 19)
    rows = (_rows("/parts/esp32-devkitc", start, 40, lambda d: 10 if d < 14 else 20)
            + _rows("/parts/control-a", start, 40, lambda d: 1 if d < 14 else 15))           # 7 control pre impressions
    ch = [{"sha": "1", "day": date(2026, 11, 2), "urls": ["/parts/esp32-devkitc"], "lane": "backfill", "kind": "modified"}]
    w = oc.cohort_effects(ch, oc.page_days(rows), today=date(2026, 12, 15), windows=(7,))[0]["windows"][7]
    assert w["control_ratio"] is None and w["effect"] is None and w["pre"] == 70
