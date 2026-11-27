"""jr/build_targets.py — the shadow producer of build-target facts (Jr redesign plan, step 8). No network: the
fact source is faked; the writer and selection are real."""
import json
from pathlib import Path

import pytest
import yaml

import build_targets as bt

SHA = "971c066b37dbe3dbb9ac1096d9e72f32ab5b3452"
CLAIM = {"kind": "pio-env", "repo": {"slug": "o/r", "id": 42}, "sha": SHA, "env": "feather", "board_id": "adafruit_feather_esp32s3_tft",
         "platformio_version": "6.2.0", "platform": {"spec": "x", "package_digest": "a" * 64, "manifest_digest": "b" * 64},
         "files": [{"path": "platformio.ini", "blob": "c" * 40}],
         "sections": [{"name": "env:feather", "file": "platformio.ini", "line": 111}]}


def test_switches_both_default_off():
    assert bt.enabled({}, {}) == (False, "switch off: jr/autonomy.json build_target_shadow is not true")
    assert bt.enabled({"build_target_shadow": True}, {"JR_BUILD_TARGETS": "0"})[0] is False
    assert bt.enabled({"build_target_shadow": True}, {})[0] is True


def test_round_robin_picks_the_next_repos_and_wraps():
    repos = ["a/1", "b/2", "c/3", "d/4"]
    assert bt.pick(repos, cursor="b/2", n=2) == (["c/3", "d/4"], "d/4")
    assert bt.pick(repos, cursor="d/4", n=2) == (["a/1", "b/2"], "b/2")
    assert bt.pick(repos, cursor=None, n=3) == (["a/1", "b/2", "c/3"], "c/3")


def test_a_fact_becomes_a_valid_build_target_recipe(tmp_path):
    rid, text = bt.render("adafruit-feather-esp32-s3-tft", "nightdriverstrip", "esp32-s3", CLAIM, "2026-11-23")
    assert rid == "adafruit-feather-esp32-s3-tft__nightdriverstrip"
    fm = yaml.safe_load(text.split("---")[1])
    assert fm["status"] == "build-target" and fm["claim"] == CLAIM and "flash" not in fm
    assert fm["sources"][0] == {"field": "claim", "url": f"https://github.com/o/r/blob/{SHA}/platformio.ini#L111", "verified": "2026-11-23"}
    from esp_atlas_core.validate import validate_frontmatter
    assert validate_frontmatter(fm, "recipe", ids=None)["errors"] == []
    body = text.split("---", 2)[2]
    assert "Configuration only: not built or tested on hardware." in body and "runs on" not in body


def test_plan_keeps_only_linked_new_pairs_and_caps_them():
    facts = [dict(CLAIM, env=f"e{i}", board_id=f"id{i}") for i in range(14)]
    link = {f"id{i}": f"board-{i}" for i in range(14) if i != 3}                      # id3 links to no board
    existing = {"board-0__fw"}                                                          # an existing pair is never touched
    picked = bt.plan([("fw", "o/r", facts)], link=lambda bid, dig: link.get(bid), existing=existing, cap=10)
    ids = [p[0] for p in picked]
    assert "board-0__fw" not in ids and not any(p[1] == "board-3" for p in picked)
    assert len(ids) == 10 and len(set(ids)) == 10


def test_one_pair_written_once_even_when_two_envs_select_the_same_board():
    facts = [dict(CLAIM, env="a"), dict(CLAIM, env="b")]
    picked = bt.plan([("fw", "o/r", facts)], link=lambda bid, dig: "board-x", existing=set(), cap=10)
    assert [p[0] for p in picked] == ["board-x__fw"] and picked[0][3]["env"] == "a"


def test_a_pair_a_person_removed_is_never_written_back(tmp_path):
    """Real dry run 2026-11-23: the shadow proposed m5stamp-s3__adversary, the recipe the owner removed on
    2026-11-11 (jr/overrides/adversary__edges.json). A person's removal is never overridden by the machine."""
    repo = Path(__file__).resolve().parent.parent
    assert "m5stamp-s3__adversary" in bt.blocked_ids("adversary", repo)
    facts = [dict(CLAIM, board_id="m5stack-stamps3")]
    picked = bt.plan([("adversary", "Isonimus/adversary", facts)], link=lambda bid, dig: "m5stamp-s3",
                     existing=bt.blocked_ids("adversary", repo), cap=10)
    assert picked == []


def test_an_unreadable_override_blocks_the_whole_firmware(tmp_path):
    (tmp_path / "jr" / "overrides").mkdir(parents=True)
    (tmp_path / "jr" / "overrides" / "fw__edges.json").write_text("{not json")
    assert bt.blocked_ids("fw", tmp_path) is None
    assert bt.blocked_ids("other", tmp_path) == set()


class _P:
    def __init__(self, rc, err=""):
        self.returncode, self.stderr, self.stdout = rc, err, ""


def test_label_falls_back_to_rest_when_pr_edit_fails():
    calls = []
    def gh(*a):
        calls.append(a)
        return _P(1, "GraphQL: something") if a[:2] == ("pr", "edit") else _P(0)
    ok, why = bt.add_label("https://github.com/o/r/pull/2074", gh)
    assert ok and why == ""
    assert calls[1] == ("api", "--method", "POST", "repos/o/r/issues/2074/labels", "-f", "labels[]=jr-data")


def test_label_failure_is_reported_not_swallowed():
    ok, why = bt.add_label("https://github.com/o/r/pull/7", lambda *a: _P(1, "denied"))
    assert not ok and "pr edit: denied" in why and "REST issues labels: denied" in why


# --- striking distance first (united plan pilot E, 2026-11-26) -------------------------------------------------------

PAGES = [{"page": "/firmware/bruce", "impressions": 480, "clicks": 12, "position": 10.98},
         {"page": "/firmware/top", "impressions": 900, "clicks": 90, "position": 2.1},        # already top: not a target
         {"page": "/firmware/thin", "impressions": 5, "clicks": 0, "position": 9.0},          # too little evidence
         {"page": "/firmware/cathack", "impressions": 156, "clicks": 16, "position": 6.2},
         {"page": "/parts/esp32-c6", "impressions": 500, "clicks": 2, "position": 10.8}]      # not a firmware page


def test_striking_distance_firmware_is_ranked_by_impressions_times_the_position_gap():
    assert bt.striking(PAGES) == ["bruce", "cathack"]


def test_a_run_takes_at_most_two_striking_pages_first_then_the_round_robin():
    repos = ["a\to/a", "bruce\to/bruce", "c\to/c", "cathack\to/cat", "d\to/d"]
    picked, cursor = bt.pick_with_striking(repos, cursor="a\to/a", n=3, striking_ids=["cathack", "bruce", "zzz"])
    assert picked[:2] == ["cathack\to/cat", "bruce\to/bruce"] and len(picked) == 3
    assert picked[2] not in picked[:2] and cursor == picked[2]         # the round robin advances only by its own picks


# --- the product-name refusal (2026-11-27; owner rule of 2026-11-11) -------------------------------------------------

def test_an_env_named_for_another_catalogued_product_never_links_to_a_generic_option():
    import claims_pio_sources as src
    names = src.product_names(Path(__file__).resolve().parent.parent / "data")
    assert src.product_conflict("cardputer", "m5stamp-s3", names) == "m5cardputer"          # the Nov 11 class
    assert src.product_conflict("cardputer", "esp32-s3-devkitc-1", names) == "m5cardputer"
    assert src.product_conflict("esp32-m5atom-lite", "esp32-pico-kit", names) == "m5atom-lite"
    assert src.product_conflict("esp32p4_16MB", "esp32-p4-function-ev-board", names) is None
    assert src.product_conflict("cardputer", "m5cardputer", names) is None                 # its own product
    facts = [dict(CLAIM, env="cardputer", board_id="m5stack-stamps3")]
    picked = bt.plan([("cardputer-ai", "o/r", facts)], link=lambda bid, dig: "m5stamp-s3", existing=set(),
                     conflict=lambda env, board: src.product_conflict(env, board, names))
    assert picked == []
