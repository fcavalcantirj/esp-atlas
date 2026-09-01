"""Tests for jr/pr_summary.py — the best-effort LLM smart-summary for a drain PR DESCRIPTION.

The summary is prose-only: it decorates the top of the PR body and NEVER touches any data/ file,
source, firmware.md, recipe, or the cited list. It is derived ONLY from the deterministic facts
the drain already authored, and it is strictly best-effort — any LLM failure yields None and the
drain PR falls back to its terse cited template.

Every test injects a FAKE Groq client exposing `.complete(system, user, temperature=0) -> str`,
so no real network call is ever made. Fixtures use coding-domain example firmware (ESP32 launchers
and tools), never lorem ipsum.

Run: cd jr && python3 -m pytest test_pr_summary.py -v
"""
from __future__ import annotations

import pr_summary


class FakeGroq:
    """Injected stand-in for esp_atlas_core.llm.GroqClient. Records the prompts and returns a
    canned headline (or raises / returns empty to exercise the best-effort fallback)."""

    def __init__(self, reply="14 new firmware — mostly pentest launchers for Cardputer", raises=False):
        self.reply = reply
        self.raises = raises
        self.calls = []

    def complete(self, system_prompt, user_prompt, temperature=0):
        self.calls.append((system_prompt, user_prompt, temperature))
        if self.raises:
            raise RuntimeError("simulated Groq outage")
        return self.reply


# A realistic batch. The "internet-radio" entry is DELIBERATELY mislabeled `home` — Jr should flag
# its own uncertain call. The "cardputer-factory-test" is a factory demo mislabeled `multi`.
BATCH = [
    {"id": "bruce", "name": "Bruce", "category": "pentest", "url": "https://github.com/pr3y/Bruce",
     "capabilities": ["wifi", "ble", "ir", "sub-ghz"], "board": "m5stack-cardputer", "stars": 4200},
    {"id": "marauder", "name": "ESP32 Marauder", "category": "pentest",
     "url": "https://github.com/justcallmekoko/ESP32Marauder",
     "capabilities": ["wifi", "ble"], "board": "esp32-devkitc", "stars": 5100},
    {"id": "nemo", "name": "Nemo", "category": "pentest", "url": "https://github.com/n0xa/m5stick-nemo",
     "capabilities": ["ir", "sub-ghz"], "board": "m5stick-c-plus", "stars": 900},
    {"id": "meshtastic", "name": "Meshtastic", "category": "mesh", "url": "https://github.com/meshtastic/firmware",
     "capabilities": ["lora", "ble"], "board": "heltec-lora32", "stars": 6000},
    {"id": "internet-radio", "name": "ESP32 Internet Radio Player", "category": "home",
     "url": "https://github.com/example/esp32-internet-radio",
     "capabilities": ["wifi", "audio"], "board": "esp32-devkitc", "stars": 120},
    {"id": "cardputer-factory-test", "name": "Cardputer Factory Test Firmware", "category": "multi",
     "url": "https://github.com/m5stack/cardputer-factory", "capabilities": ["display", "wifi"],
     "board": "m5stack-cardputer", "stars": 30},
]


def test_normal_batch_returns_summary_with_headline_and_category_breakdown():
    fake = FakeGroq()
    out = pr_summary.summarize(BATCH, client=fake)

    assert out is not None
    assert fake.calls, "the LLM client was consulted for the headline"
    assert fake.reply in out  # the LLM-written headline is included verbatim
    assert out.splitlines()[0] == fake.reply  # the headline is PREPENDED as the first line
    # Deterministic category breakdown: pentest 3, then multi/mesh/home 1 each (count desc, name asc).
    assert "pentest 3" in out
    assert "home 1" in out and "mesh 1" in out and "multi 1" in out
    assert "Categories:" in out


def test_miscategorized_entry_is_flagged_under_review():
    out = pr_summary.summarize(BATCH, client=FakeGroq())

    assert out is not None
    assert "Review" in out
    # The internet-radio labeled `home` is Jr's own low-confidence call and must be surfaced.
    assert "internet-radio" in out
    assert "labeled home" in out
    # The factory demo mislabeled `multi` is flagged too.
    assert "cardputer-factory-test" in out


def test_notable_entries_ranked_by_stars_when_available():
    out = pr_summary.summarize(BATCH, client=FakeGroq())

    assert "Notable:" in out
    # Top by stars is Meshtastic (6000) then Marauder (5100) then Bruce (4200).
    notable_line = next(ln for ln in out.splitlines() if ln.startswith("Notable:"))
    assert "meshtastic" in notable_line
    # internet-radio (120 stars) is not among the top-3 notable picks.
    assert "internet-radio" not in notable_line


def test_deterministic_body_still_returned_when_client_raises():
    """LLM outage -> headline omitted, but the deterministic body (breakdown + review) still
    renders. Only an EMPTY batch yields None."""
    out = pr_summary.summarize(BATCH, client=FakeGroq(raises=True))
    assert out is not None
    assert "Categories:" in out and "pentest 3" in out
    assert "internet-radio" in out  # the review flag is deterministic, no LLM needed
    assert "mostly pentest launchers" not in out  # no headline garnish on failure


def test_deterministic_body_still_returned_when_client_returns_empty():
    out = pr_summary.summarize(BATCH, client=FakeGroq(reply="   "))
    assert out is not None
    assert "Categories:" in out
    assert out.splitlines()[0].startswith("Categories:")  # no headline prepended


def test_deterministic_body_returned_when_no_client_and_no_api_key():
    # No injected client and no GROQ_API_KEY -> the DETERMINISTIC summary must STILL render.
    # This is the real cron box: no key, but the maintainer must still get the nudge.
    out = pr_summary.summarize(BATCH, env={})
    assert out is not None
    assert "Categories:" in out and "pentest 3" in out
    # The "review these" entry must be present even with no LLM at all.
    assert "internet-radio" in out and "labeled home" in out
    assert out.splitlines()[0].startswith("Categories:")  # no headline, body only


def test_returns_none_on_empty_batch():
    assert pr_summary.summarize([], client=FakeGroq()) is None
    assert pr_summary.summarize([], env={}) is None


def test_summary_derived_only_from_facts_no_invention():
    """Every entry id that appears in the summary must come from the batch — nothing invented."""
    out = pr_summary.summarize(BATCH, env={})  # deterministic body only
    ids = {e["id"] for e in BATCH}
    entries_line = next(ln for ln in out.splitlines() if ln.startswith("Entries:"))
    cited = {tok.strip() for tok in entries_line[len("Entries:"):].split("·")}
    # Every listed entry id is a real batch id — nothing invented.
    assert cited == ids


def test_drain_pr_body_falls_back_to_terse_template_when_summary_is_none():
    """When the summary is None (best-effort miss), drain_pr still builds a valid terse body with
    every id, its URL, and the guard-green statement — the PR opens regardless."""
    import shutil

    import drain_pr
    import tools

    fid = "zzz-test-fixture-pr-summary-fallback"
    url = "https://github.com/octocat/esp32-launcher"
    d = tools.FIRMWARE_DIR / fid
    d.mkdir(parents=True, exist_ok=True)
    (d / "firmware.md").write_text(
        f"---\nid: {fid}\nname: Zzz Launcher\nurl: {url}\ncategory: multi\nsocs: [esp32-s3]\n---\n\nA launcher.\n"
    )
    try:
        body = drain_pr._pr_body([fid], None)
        assert fid in body and url in body
        assert "guard" in body.lower() and "green" in body.lower()
        assert "Review these" not in body  # no summary prepended
        # And with a summary present it is prepended above the cited list.
        body2 = drain_pr._pr_body([fid], "SMART HEADLINE\n\n**Categories:** multi 1")
        assert body2.index("SMART HEADLINE") < body2.index(fid)
    finally:
        shutil.rmtree(d, ignore_errors=True)
