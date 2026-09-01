"""EspAtlas Jr — pytest for the deterministic scorer (jr/scorer.py).

Runs score_entry() over golden_set.json — 29 REAL cases: the original 12-case spike proof
(DECISION-LOG.md's four documented failure modes: #74 fork-of-catalogued, #71 wrong-chip, #73
freeform-capabilities, plus clean device-in-name cases) PLUS 17 hard cases hand-picked from an
at-scale run of score_entry() over the entire real live launcher catalog (2671 entries) — noise/
junk firmware, wrong-chip-via-device-name-lookalike, fused device-name spelling, multi-device-
per-repo, described (non-fork) ports of catalogued repos, malformed github URLs, fork-of-
uncatalogued, and new board coverage. Measures per-field + overall accuracy against hand-authored
expected records. GOAL: prove the zero-LLM deterministic scorer beats the LLM agent's historical
record (DECISION-LOG.md: 0/6 clean autonomous PRs — every one needed a human fix or was closed as
junk) — not just on a curated set, but at scale.

Run: cd jr && python3 -m pytest test_scorer.py -v -s
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scorer import score_entry, _repo_name_from_url, _slug  # noqa: E402
from device_map import device_from_text  # noqa: E402

JR_DIR = Path(__file__).resolve().parent
GOLDEN = json.loads((JR_DIR / "golden_set.json").read_text())
CATALOGUED_REPOS = set(GOLDEN["catalogued_repos"])
CATALOGUED_TOKENS = set(GOLDEN["catalogued_tokens"])
CASES = GOLDEN["cases"]

RECORD_FIELDS = ("id", "url", "category", "board", "chip", "capabilities", "maintainer")


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_case_decision(case):
    """Every case's top-level decision (authored vs skip) must match the hand-authored
    expected outcome — this is the gate that matters most: does the scorer correctly decide
    whether to propose or skip?"""
    result = score_entry(case["entry"], case["repo_meta"], CATALOGUED_REPOS, CATALOGUED_TOKENS)
    assert result["decision"] == case["expected"]["decision"], (
        f"{case['id']}: expected decision={case['expected']['decision']!r}, "
        f"got {result['decision']!r} ({result.get('reason') or result.get('record')})")


@pytest.mark.parametrize("case", [c for c in CASES if c["expected"]["decision"] == "skip"],
                         ids=[c["id"] for c in CASES if c["expected"]["decision"] == "skip"])
def test_skip_reason_matches(case):
    """A skip must cite the RIGHT reason, not just any reason (a fork wrongly reported as
    'no_board_evidence' would still be a skip, but for the wrong cause)."""
    result = score_entry(case["entry"], case["repo_meta"], CATALOGUED_REPOS, CATALOGUED_TOKENS)
    assert case["expected"]["reason_substring"] in result["reason"], (
        f"{case['id']}: reason {result['reason']!r} missing {case['expected']['reason_substring']!r}")


@pytest.mark.parametrize("case", [c for c in CASES if c["expected"]["decision"] == "authored"],
                         ids=[c["id"] for c in CASES if c["expected"]["decision"] == "authored"])
def test_authored_record_matches(case):
    """Every field of an authored record must match the hand-authored expected value exactly —
    this is the field-by-field accuracy check (the #71/#73 classes of bug are exactly a single
    wrong field slipping through)."""
    result = score_entry(case["entry"], case["repo_meta"], CATALOGUED_REPOS, CATALOGUED_TOKENS)
    assert result["decision"] == "authored", f"{case['id']}: expected authored, got {result}"
    got = result["record"]
    want = case["expected"]["record"]
    for field in RECORD_FIELDS:
        got_v = got[field]
        want_v = want[field]
        if isinstance(want_v, list):
            got_v, want_v = sorted(got_v), sorted(want_v)
        assert got_v == want_v, f"{case['id']}.{field}: expected {want_v!r}, got {got_v!r}"


def test_cathack_chip_derivation_is_not_fabricated():
    """DIRECT regression test for #71: the LLM fabricated `esp32-s3` for CatHack, an esp32-only
    board (M5StickC-Plus2). CatHack is now already in the atlas (hand-corrected, merged) so the
    full score_entry() pipeline short-circuits on the already_catalogued dedup before ever
    reaching board/chip derivation (see the already_catalogued_cathack_regression case above).
    This test proves the derivation logic itself — device_from_text + tools.board_soc — gets
    the chip right, using CatHack's REAL README title ('CatHack Firmware for M5StickCPlus2',
    fetched live via `gh api repos/Stachugit/CatHack/readme`)."""
    import tools
    board = device_from_text("CatHack", None, "CatHack Firmware for M5StickCPlus2")
    assert board == "m5stick-cplus2"
    chip = tools.board_soc(board)
    assert chip == "esp32", f"#71 regression: expected esp32, got {chip!r} — never esp32-s3"


def test_accuracy_report(capsys):
    """Computes and PRINTS per-field + overall accuracy across the whole golden set. Run with -s
    to see it. This is a real regression gate (fully_correct == total below), earned by fixing
    every bug the at-scale hunt surfaced — it does NOT claim the scorer is 100% accurate on the
    full live catalog (see the at-scale report in the promotion summary for the honest number:
    most of the catalog is correctly SKIPPED, not authored, and a residual of genuinely-hard
    cases the deterministic approach can't resolve is documented there, not hidden here)."""
    total = len(CASES)
    decision_correct = 0
    fully_correct = 0
    field_correct = {f: 0 for f in RECORD_FIELDS}
    field_total = {f: 0 for f in RECORD_FIELDS}
    skip_reason_correct = 0
    skip_total = 0

    for case in CASES:
        result = score_entry(case["entry"], case["repo_meta"], CATALOGUED_REPOS, CATALOGUED_TOKENS)
        exp = case["expected"]
        decision_ok = result["decision"] == exp["decision"]
        decision_correct += decision_ok

        if exp["decision"] == "skip":
            skip_total += 1
            reason_ok = decision_ok and exp["reason_substring"] in result.get("reason", "")
            skip_reason_correct += reason_ok
            fully_correct += reason_ok
        else:
            all_fields_ok = decision_ok
            if decision_ok:
                got = result["record"]
                want = exp["record"]
                for field in RECORD_FIELDS:
                    field_total[field] += 1
                    got_v, want_v = got[field], want[field]
                    if isinstance(want_v, list):
                        got_v, want_v = sorted(got_v), sorted(want_v)
                    ok = got_v == want_v
                    field_correct[field] += ok
                    all_fields_ok = all_fields_ok and ok
            fully_correct += all_fields_ok

    lines = [
        "",
        "=== EspAtlas Jr scorer — golden-set accuracy ===",
        f"decision accuracy:      {decision_correct}/{total} ({100*decision_correct/total:.0f}%)",
        f"skip-reason accuracy:   {skip_reason_correct}/{skip_total} ({100*skip_reason_correct/skip_total:.0f}%)"
        if skip_total else "skip-reason accuracy:   n/a (no skip cases)",
        f"FULLY correct records:  {fully_correct}/{total} ({100*fully_correct/total:.0f}%)",
        "per-field accuracy (authored cases only):",
    ]
    for field in RECORD_FIELDS:
        if field_total[field]:
            lines.append(f"  {field:12s} {field_correct[field]}/{field_total[field]} "
                         f"({100*field_correct[field]/field_total[field]:.0f}%)")
    lines += [
        "",
        "LLM agent historical record (DECISION-LOG.md, 2026-08-27):",
        "  0/6 autonomous PRs merged clean — every one needed a human fix, or was closed",
        "  (#69 broke main, #71 fabricated esp32-s3, #73 freeform capabilities, #74 fork junk,",
        "   1 run left garbage ids, #70 was hand-authored by the operator, not the agent).",
        f"Deterministic scorer this run: {fully_correct}/{total} fully correct, ZERO LLM calls.",
    ]
    report = "\n".join(lines)
    with capsys.disabled():
        print(report)

    assert fully_correct == total, f"scorer only got {fully_correct}/{total} fully correct"


# ─────────────────────── Bug 1: garbage id slug (id derivation) ───────────────────────
# Real bug from a live drain run: github.com/sosprz/meshcore-cardputer-adv/releases was
# authored with id 'releases' — the id took the URL's trailing path segment instead of the
# repo name. Fixed via scorer._repo_name_from_url + scorer._slug's marketing-noise strip.

@pytest.mark.parametrize("url,expected_repo_name", [
    ("https://github.com/sosprz/meshcore-cardputer-adv/releases", "meshcore-cardputer-adv"),
    ("https://github.com/sosprz/meshcore-cardputer-adv/releases/latest", "meshcore-cardputer-adv"),
    ("https://github.com/someone/some-repo/tree/main", "some-repo"),
    ("https://github.com/someone/some-repo/tree/feature/branch-name", "some-repo"),
    ("https://github.com/someone/some-repo/blob/main/README.md", "some-repo"),
    ("https://github.com/someone/some-repo/archive/refs/heads/main.zip", "some-repo"),
    ("https://github.com/someone/some-repo?tab=readme-ov-file", "some-repo"),
    ("https://github.com/someone/some-repo#readme", "some-repo"),
    ("https://github.com/someone/some-repo.git", "some-repo"),
], ids=["releases", "releases-latest", "tree-branch", "tree-nested-branch", "blob", "archive",
       "query", "fragment", "dot-git"])
def test_repo_name_from_url_strips_trailing_path_query_and_fragment(url, expected_repo_name):
    assert _repo_name_from_url(url) == expected_repo_name


def test_slug_of_meshcore_releases_url_is_the_repo_not_releases():
    """DIRECT regression for the reported bug: a github url pointing at a repo's /releases page
    must slug to the repo name, never the trailing path segment 'releases'."""
    repo_name = _repo_name_from_url("https://github.com/sosprz/meshcore-cardputer-adv/releases")
    assert _slug(repo_name) == "meshcore-cardputer-adv"


def test_slug_strips_parenthetical_marketing_noise():
    assert _slug("MP3Player for Cardputer & ADV( load 2000+ songs)") == "mp3player-for-cardputer-adv"
    assert _slug("M5stickC Plus 2 Marauder (BLE Fix)") == "m5stickc-plus-2-marauder"


def test_score_entry_meshcore_releases_url_authors_clean_repo_name_id():
    """End-to-end regression for the exact reported case: the catalog entry's github url points
    at the repo's /releases page, and the authored record's id must be the clean repo slug."""
    entry = {
        "name": "Meshcore for Cardputer ADV",
        "description": "Meshcore firmware port for the M5Stack Cardputer ADV.",
        "category": "cardputer",
        "github": "https://github.com/sosprz/meshcore-cardputer-adv/releases",
        "download": 1200,
    }
    repo_meta = {
        "full_name": "sosprz/meshcore-cardputer-adv",
        "fork": False,
        "source_full_name": None,
        "stars": 5,
        "description": "Meshcore firmware port for the M5Stack Cardputer ADV.",
    }
    result = score_entry(entry, repo_meta, set(), set())
    assert result["decision"] == "authored"
    assert result["record"]["id"] == "meshcore-cardputer-adv"


def test_score_entry_strips_parenthetical_from_authored_name():
    entry = {
        "name": "MP3Player for Cardputer & ADV( load 2000+ songs)",
        "description": None,
        "category": "cardputer",
        "github": "https://github.com/someone/cardputer-mp3-player",
        "download": 800,
    }
    repo_meta = {
        "full_name": "someone/cardputer-mp3-player",
        "fork": False,
        "source_full_name": None,
        "stars": 3,
        "description": None,
    }
    result = score_entry(entry, repo_meta, set(), set())
    assert result["decision"] == "authored"
    assert result["record"]["name"] == "MP3Player for Cardputer & ADV"
    assert "(" not in result["record"]["name"]


# ─────────────────────── Bug 2: fork/variant dedup miss ───────────────────────
# Real bug from a live drain run: 'M5stickC Plus 2 Marauder (BLE Fix)' at ATOMNFT/M5stick-
# Marauder was authored as NEW even though ESP32Marauder (justcallmekoko/ESP32Marauder) is
# already catalogued — a device-port fork slipped dedup because the catalogued firmware id
# ('esp32marauder') has no delimiter to split its core token ('marauder') out of. Fixed in
# tools._catalogued_repos_and_tokens() (see test_tools.py); these tests exercise score_entry()
# with the tokens that fixed function now produces.

MARAUDER_CATALOGUED_TOKENS = {"esp32marauder", "marauder"}   # what the FIXED
# tools._catalogued_repos_and_tokens() now yields for the catalogued esp32marauder firmware
# (id token 'esp32marauder' + core name-token 'marauder' from its 'ESP32 Marauder' frontmatter
# name — 'esp32' itself is excluded as a generic vendor/chip token).


def test_score_entry_skips_marauder_style_device_port_as_variant():
    """Real reported case: a device-port fork of the catalogued ESP32Marauder must be skipped
    as a variant, not authored as new firmware."""
    entry = {
        "name": "M5stickC Plus 2 Marauder (BLE Fix)",
        "description": None,
        "category": "stickc",
        "github": "https://github.com/ATOMNFT/M5stick-Marauder",
        "download": 300,
    }
    repo_meta = {
        "full_name": "ATOMNFT/M5stick-Marauder",
        "fork": False,
        "source_full_name": None,
        "stars": 2,
        "description": None,
    }
    result = score_entry(entry, repo_meta, set(), MARAUDER_CATALOGUED_TOKENS)
    assert result["decision"] == "skip"
    assert "name_token_matches_catalogued" in result["reason"]


def test_score_entry_generic_shared_word_alone_does_not_false_skip():
    """A candidate that shares only the GENERIC chip word 'esp32' with a catalogued firmware
    (not its actual core name-token) must NOT be treated as a port — over-matching on a common
    word would false-skip genuinely different, genuinely-new firmware."""
    entry = {
        "name": "ESP32 Weather Station for Cardputer",
        "description": None,
        "category": "cardputer",
        "github": "https://github.com/coolusername/esp32-weather-cardputer",
        "download": 150,
    }
    repo_meta = {
        "full_name": "coolusername/esp32-weather-cardputer",
        "fork": False,
        "source_full_name": None,
        "stars": 1,
        "description": None,
    }
    result = score_entry(entry, repo_meta, set(), MARAUDER_CATALOGUED_TOKENS)
    assert result["decision"] == "authored"
    assert result["record"]["board"] == "m5cardputer"
