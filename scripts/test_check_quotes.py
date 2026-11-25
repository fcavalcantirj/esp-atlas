"""scripts/check_quotes.py — every quoted span in a record appears on a cited page. Fakes only: the
fixture is the Freenove FNK0060 Preface text read on 2026-11-17 and the record #1800 added."""
from __future__ import annotations

from pathlib import Path

import pytest

import check_quotes as cq

FIX = Path(__file__).resolve().parent / "fixtures" / "quotes"
PREFACE_URL = "https://docs.freenove.com/projects/fnk0060/en/latest/fnk0060/codes/C/Preface.html"
PREFACE = (FIX / "freenove-fnk0060-preface.txt").read_text()
RECORD = FIX / "freenove-esp32-wrover.board.md"
REPO_URL = "https://github.com/Freenove/Freenove_ESP32_WROVER_Board"
REPO_PAGE = "Freenove_ESP32_WROVER_Board - A kit with a Freenove ESP32 Board for learning programming and electronics."


def _pages(fm, preface=PREFACE, repo=REPO_PAGE):
    """Every cited URL unrelated, except the Preface and the GitHub repo page (which names the aka)."""
    pages = {u: "unrelated page" for u in cq.cited_urls(fm)}
    pages[PREFACE_URL] = preface
    pages[REPO_URL] = repo
    return pages


def fake_fetch(pages: dict, log=None):
    """`pages`: url -> text (readable) or None (unreadable)."""
    def fetch(url):
        if log is not None:
            log.append(url)
        text = pages.get(url)
        return cq.Page(url, cq.normalize(text) if text is not None else None, "fake" if text is not None else "HTTP 403")
    return fetch


# --- the quotes a record carries --------------------------------------------------------------------

def test_straight_quotes_are_paired_in_order_so_the_text_between_two_quotes_is_never_a_quote():
    note = 'The vendor page has a "Specs" tab (Features) and a "Pinout and GPIO table" section; see "ESP32-S3-DevKitC-1 user guide".'
    assert cq._spans(note) == ["Specs", "Pinout and GPIO table", "ESP32-S3-DevKitC-1 user guide"]
    assert cq.quotes_in({"notes": [note]}) == ["Pinout and GPIO table", "ESP32-S3-DevKitC-1 user guide"]
    assert cq._spans('run `idf.py set-target "esp32s3"` then `"CONFIG_ESPTOOLPY_FLASHSIZE=4MB"`') == []   # code, not quotes
    assert cq._spans("unbalanced \"quote at the end") == []


def test_quotes_are_the_spans_embedded_in_string_values_never_the_yaml_delimiters():
    fm = {"name": "ESP32-WROVER board with quotes", "notes": [
        'The Preface says "the ESP32-WROVER is designed based on the PCB on-board antenna-packaged ESP32-WROVER module"',
        "Freenove writes “ESP32 uses CH340 to download codes” in the CH340 section",
        'short "ab" quote is not one',
    ], "sources": [{"field": "*", "url": "https://x/\"quoted in a url\" is ignored"}]}
    assert cq.quotes_in(fm) == [
        "the ESP32-WROVER is designed based on the PCB on-board antenna-packaged ESP32-WROVER module",
        "ESP32 uses CH340 to download codes",
    ]


def test_the_freenove_record_carries_four_quotes():
    fm, _ = cq.parse_frontmatter(RECORD)
    assert len(cq.quotes_in(fm)) == 4
    assert cq.cited_urls(fm)[0] == "https://github.com/Freenove/Freenove_ESP32_WROVER_Board"


# --- normalization: typography and whitespace never fail a true quote ---------------------------------

@pytest.mark.parametrize("page, quote", [
    ("ESP32 uses CH340 to download codes.", "ESP32 uses CH340 to download codes"),
    ("ESP32 uses  CH340\nto download\tcodes", "ESP32 uses CH340 to download codes"),
    ("the “PCB on-board antenna” – integrated", 'the "PCB on-board antenna" - integrated'),
    ("ESP32 USES CH340 TO DOWNLOAD CODES", "esp32 uses ch340 to download codes"),
    ("on­board antenna", "on-board antenna".replace("-", "")),
    ("Flash: 8MB, PSRAM: 8MB", "8 MB, PSRAM: 8 MB"),                                  # a page's spacing around units
    ("a built-in USB Serial core", "built in USB Serial core"),                          # a hyphen the note dropped
    ("Dimensions 47.74 × 139.00 mm", "47.74 x 139.00 mm"),                         # the multiplication sign
    ("<tr><td>Digital I/O</td><td>x13</td></tr>", "Digital I/O | x13"),                 # a table row a note kept with |
])
def test_normalize_makes_the_page_and_the_quote_comparable(page, quote):
    assert cq.contains(cq.normalize(cq.html_to_text(page)), quote)


def test_an_elided_quote_needs_every_fragment_in_order():
    page = cq.normalize("ESP32-S3 Dual Core 240MHz Tensilica processor - the next generation of ESP32-Sx, with native USB so it can act like a keyboard")
    assert cq.contains(page, "ESP32-S3 Dual Core 240MHz Tensilica processor ... with native USB")
    assert cq.contains(page, "Dual Core … native USB … keyboard")
    assert not cq.contains(page, "with native USB ... Dual Core")                        # out of order
    assert not cq.contains(page, "Dual Core ... with native Ethernet")
    assert cq.fragments("...") == [] and cq.fragments("plain") == ["plain"]


def test_the_cited_url_itself_counts_as_shown_text_for_an_aka_that_is_the_file_name():
    class R:
        status_code, headers, content = 200, {"content-type": "application/json"}, b'{"name": "CrowPanel 5.79"}'
        text = content.decode()

    class C:
        def get(self, url, follow_redirects=True):
            return R()

    page = cq.fetch_page(C(), "https://github.com/pioarduino/platform-espressif32/blob/32f6bf40/boards/elecrow_crowpanel_579.json")
    assert cq.contains(page.text, "elecrow_crowpanel_579") and cq.contains(page.text, "CrowPanel 5.79")


def test_a_github_blob_url_is_read_raw_and_html_is_reduced_to_text():
    assert cq.fetch_url("https://github.com/o/r/blob/abc123/boards/x.json") == "https://raw.githubusercontent.com/o/r/abc123/boards/x.json"
    assert cq.fetch_url("https://docs.example.com/p.html") == "https://docs.example.com/p.html"
    assert cq.normalize(cq.html_to_text("<p>ESP32 <b>uses</b> CH340&nbsp;to <script>x()</script>download codes</p>")) \
        == "esp32usesch340todownloadcodes"


# --- verdicts ---------------------------------------------------------------------------------------

def test_the_freenove_record_passes_against_the_preface_it_cites():
    fm, _ = cq.parse_frontmatter(RECORD)
    rep = cq.check_record(RECORD, fm, {}, fake_fetch(_pages(fm)))
    assert rep.verdict == cq.PASS and [q.verdict for q in rep.quotes] == [cq.PASS] * 4
    assert [q.where for q in rep.quotes] == [PREFACE_URL] * 3 + [REPO_URL]


def test_a_quote_on_none_of_the_readable_cited_pages_fails():
    fm, _ = cq.parse_frontmatter(RECORD)
    rep = cq.check_record(RECORD, fm, {}, fake_fetch(_pages(fm, preface=PREFACE.replace("CH340 to download codes", "CH341 to download codes"))))
    assert rep.verdict == cq.FAIL
    failed = [q for q in rep.quotes if q.verdict == cq.FAIL]
    assert [q.quote for q in failed] == ["ESP32 uses CH340 to download codes"]
    assert failed[0].where.startswith("on none of the")


def test_an_unreadable_cited_page_makes_a_missing_quote_inconclusive_never_a_fail():
    fm, _ = cq.parse_frontmatter(RECORD)
    rep = cq.check_record(RECORD, fm, {}, fake_fetch(_pages(fm, preface=None)))   # 403 bot wall on the Preface
    assert rep.verdict == cq.INCONCLUSIVE
    assert [q.verdict for q in rep.quotes] == [cq.INCONCLUSIVE] * 3 + [cq.PASS]     # the aka is on the repo page
    assert "HTTP 403" in rep.quotes[0].where


def test_a_quote_found_on_a_readable_page_passes_even_when_another_cited_page_is_down():
    fm, _ = cq.parse_frontmatter(RECORD)
    pages = {u: None for u in cq.cited_urls(fm)}
    pages[PREFACE_URL] = PREFACE
    pages[REPO_URL] = REPO_PAGE
    rep = cq.check_record(RECORD, fm, {}, fake_fetch(pages))
    assert rep.verdict == cq.PASS


def test_each_cited_url_is_fetched_once_per_run_across_records():
    fm, _ = cq.parse_frontmatter(RECORD)
    log = []
    cache = {}
    fetch = fake_fetch({u: PREFACE for u in cq.cited_urls(fm)}, log)
    cq.check_record(RECORD, fm, cache, fetch)
    cq.check_record(RECORD, fm, cache, fetch)
    assert sorted(log) == sorted(cq.cited_urls(fm))


def test_a_record_without_quotes_is_skipped_and_exit_code_follows_fail(tmp_path, capsys):
    plain = tmp_path / "board.md"
    plain.write_text("---\nid: x\nname: Plain\nsources:\n- field: '*'\n  url: https://x/\n---\nBody.\n")
    fm, _ = cq.parse_frontmatter(RECORD)
    pages = _pages(fm, preface="unrelated")
    reports, code = cq.run([plain, RECORD], fake_fetch(pages))
    out = capsys.readouterr().out
    assert code == 1 and [r.verdict for r in reports] == [cq.FAIL]
    assert "1 record(s) with quotes: 0 pass, 1 FAIL" in out and str(plain) not in out
    pages[PREFACE_URL] = PREFACE
    reports, code = cq.run([RECORD], fake_fetch(pages))
    assert code == 0 and reports[0].verdict == cq.PASS


def test_main_reads_the_given_paths_with_an_injected_fetch(capsys):
    fm, _ = cq.parse_frontmatter(RECORD)
    pages = {u: PREFACE for u in cq.cited_urls(fm)}
    assert cq.main([str(RECORD)], fetch=fake_fetch(pages)) == 0
    assert "✓ PASS" in capsys.readouterr().out


# --- a PR is judged on the quotes it adds, not on drift already on main (2026-11-25) ---------------------
# Measured: 40 quotes on 28 boards already on main FAIL against today's vendor pages (page drift, table and
# id spans). Every Jr backfill PR that touched one of those boards went red on `quotes` for spans it never
# wrote and expired unmerged (#1951 ... #1991, #2050, #2052). The approved merge rule (2026-11-21) checks
# the board fields a PR ADDS; drift already on main stays visible (--all, and in the log) but does not block.

def _record(tmp_path, name, quotes):
    p = tmp_path / name
    notes = " ".join(f'\\"{q}\\"' for q in quotes)
    p.write_text(f'---\nid: x\nname: X\nnotes: "{notes}"\nsources:\n- field: \'*\'\n  url: https://x/\n---\nBody.\n')
    return p


def test_a_quote_already_on_main_that_fails_is_reported_but_does_not_fail_the_pr(tmp_path, capsys):
    rec = _record(tmp_path, "board.md", ["old drifted span here", "new verified span here"])
    page = {"https://x/": "page with new verified span here only"}
    reports, code = cq.run([rec], fake_fetch(page), known={rec: {"old drifted span here"}})
    out = capsys.readouterr().out
    assert code == 0 and reports[0].verdict == cq.PASS
    assert "already on main" in out and "old drifted span here" in out


def test_a_new_quote_that_fails_still_fails_the_pr_beside_known_drift(tmp_path):
    rec = _record(tmp_path, "board.md", ["old drifted span here", "new unverified span"])
    reports, code = cq.run([rec], fake_fetch({"https://x/": "nothing relevant"}), known={rec: {"old drifted span here"}})
    assert code == 1 and reports[0].verdict == cq.FAIL
    assert [q.verdict for q in reports[0].quotes] == [cq.KNOWN, cq.FAIL]


def test_without_a_base_every_failing_quote_fails_as_before(tmp_path):
    rec = _record(tmp_path, "board.md", ["old drifted span here"])
    _reports, code = cq.run([rec], fake_fetch({"https://x/": "nothing relevant"}))
    assert code == 1


def test_known_quotes_come_from_the_record_at_the_merge_base(tmp_path):
    import subprocess
    g = lambda *a: subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True, text=True).stdout
    g("init", "-q", "-b", "main"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
    (tmp_path / "data").mkdir()
    old = _record(tmp_path / "data", "board.md", ["old drifted span here"])
    g("add", "."); g("commit", "-qm", "base")
    g("checkout", "-qb", "pr")
    _record(tmp_path / "data", "board.md", ["old drifted span here", "new verified span here"])
    (tmp_path / "data" / "new.md").write_text(old.read_text())
    g("add", "."); g("commit", "-qm", "pr")
    known = cq.base_quotes("main", [tmp_path / "data" / "board.md", tmp_path / "data" / "new.md"], repo=tmp_path)
    assert known[tmp_path / "data" / "board.md"] == {"old drifted span here"}
    assert known[tmp_path / "data" / "new.md"] == set()             # an added record has nothing on main


def test_a_pr_that_drops_or_swaps_a_cited_url_gets_no_excuse_for_the_old_spans(tmp_path):
    """Review BLOCK of #2087: a span is excused only while every URL the record cited on main is still cited.
    A PR that removes or replaces a source can make an old span fail; that failure is the PR's own."""
    import subprocess
    g = lambda *a: subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True, text=True).stdout
    g("init", "-q", "-b", "main"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
    (tmp_path / "data").mkdir()
    rec = tmp_path / "data" / "board.md"
    rec.write_text('---\nid: x\nnotes: "\\"flash is 8 MB\\""\nsources:\n- field: \'*\'\n  url: https://vendor/a\n---\n')
    g("add", "."); g("commit", "-qm", "base")
    g("checkout", "-qb", "pr")
    rec.write_text('---\nid: x\nnotes: "\\"flash is 8 MB\\""\nsources:\n- field: \'*\'\n  url: https://vendor/b\n---\n')
    g("add", "."); g("commit", "-qm", "pr")
    known = cq.base_quotes("main", [rec], repo=tmp_path)
    assert known[rec] == set()
    _reports, code = cq.run([rec], fake_fetch({"https://vendor/b": "nothing"}), known=known)
    assert code == 1
