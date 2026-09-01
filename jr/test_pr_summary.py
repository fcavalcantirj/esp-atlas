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
    # Deterministic category breakdown: pentest 3, then multi/mesh/home 1 each (count desc, name asc).
    assert "pentest 3" in out
    assert "home 1" in out and "mesh 1" in out and "multi 1" in out
    assert "**Categories:**" in out


def test_miscategorized_entry_is_flagged_under_review_these():
    out = pr_summary.summarize(BATCH, client=FakeGroq())

    assert out is not None
    assert "Review these" in out
    # The internet-radio labeled `home` is Jr's own low-confidence call and must be surfaced.
    assert "`internet-radio`" in out
    assert "labeled `home`" in out
    # The factory demo mislabeled `multi` is flagged too.
    assert "`cardputer-factory-test`" in out


def test_notable_entries_ranked_by_stars_when_available():
    out = pr_summary.summarize(BATCH, client=FakeGroq())

    assert "**Notable:**" in out
    # Top by stars is Meshtastic (6000) then Marauder (5100) then Bruce (4200).
    notable_line = next(ln for ln in out.splitlines() if ln.startswith("**Notable:**"))
    assert "`meshtastic`" in notable_line
    assert "`internet-radio`" not in notable_line  # 120 stars, not notable


def test_returns_none_when_client_raises():
    out = pr_summary.summarize(BATCH, client=FakeGroq(raises=True))
    assert out is None


def test_returns_none_when_client_returns_empty():
    out = pr_summary.summarize(BATCH, client=FakeGroq(reply="   "))
    assert out is None


def test_returns_none_when_no_client_and_no_api_key():
    # No injected client and no GROQ_API_KEY -> strictly best-effort no-op.
    out = pr_summary.summarize(BATCH, env={})
    assert out is None


def test_returns_none_on_empty_batch():
    assert pr_summary.summarize([], client=FakeGroq()) is None


def test_summary_derived_only_from_facts_no_invention():
    """Every id that appears in the summary must come from the batch — nothing invented."""
    out = pr_summary.summarize(BATCH, client=FakeGroq())
    ids = {e["id"] for e in BATCH}
    categories = {e["category"] for e in BATCH}
    import re
    cited = set(re.findall(r"`([a-z0-9-]+)`", out))
    # Every backticked token is either a real batch id or a real batch category — nothing invented.
    assert cited <= (ids | categories)


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
