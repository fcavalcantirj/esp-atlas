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
