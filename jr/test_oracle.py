"""Tests for the oracle-review quality gate (oracle.py): a STRONGER model fact-checks a
drafted board record against its own cited source page BEFORE it is proposed. Network is
always mocked — these must never make a live HTTP call to Groq/OpenRouter. Simulates the live
bug that motivated this gate: the Adafruit MagTag (real chip ESP32-S2) authored with
module: esp32-wrover-e (a classic dual-core ESP32) — see tools.py's board_triple_validate
chip-family cross-check for the deterministic half of this defense.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import oracle

_BOARD_MD = (
    "---\nid: magtag\ntype: board\nbrand: adafruit\nname: Adafruit MagTag\n"
    "module: esp32-wrover-e\nsources:\n- field: '*'\n  url: https://www.adafruit.com/product/4800\n"
    "  verified: '2026-08-28'\n---\n\n# Adafruit MagTag\n"
)
_PAGE_TEXT = "Adafruit MagTag - Powered by the ESP32-S2 chip. 2MB PSRAM, native USB."
_SCHEMA_SUMMARY = "board record: id, brand, name, soc-or-module, sources[]"


class _FakeResponse:
    def __init__(self, content: str, status_ok: bool = True):
        self._content = content
        self._status_ok = status_ok

    def raise_for_status(self):
        if not self._status_ok:
            raise requests_HTTPError("simulated bad status")

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


class requests_HTTPError(Exception):
    pass


def test_oracle_review_flags_wrong_chip_family_and_rejects(monkeypatch):
    """The live MagTag bug: module: esp32-wrover-e (classic ESP32) vs page saying ESP32-S2."""
    verdict_json = (
        '{"approve": false, "issues": ['
        '"module esp32-wrover-e is a classic dual-core ESP32; the page names the ESP32-S2"], '
        '"notes": "wrong chip family"}'
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setattr(oracle.requests, "post", lambda *a, **k: _FakeResponse(verdict_json))

    result = oracle.oracle_review(_BOARD_MD, _PAGE_TEXT, _SCHEMA_SUMMARY)

    assert result["approve"] is False
    assert any("esp32-wrover-e" in i.lower() and "esp32-s2" in i.lower() for i in result["issues"])


def test_oracle_review_approves_when_record_matches_page(monkeypatch):
    verdict_json = '{"approve": true, "issues": [], "notes": "soc matches the page"}'
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setattr(oracle.requests, "post", lambda *a, **k: _FakeResponse(verdict_json))

    result = oracle.oracle_review(_BOARD_MD, _PAGE_TEXT, _SCHEMA_SUMMARY)

    assert result == {"approve": True, "issues": [], "notes": "soc matches the page"}


def test_oracle_review_tolerates_code_fenced_json(monkeypatch):
    fenced = '```json\n{"approve": true, "issues": [], "notes": "ok"}\n```'
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setattr(oracle.requests, "post", lambda *a, **k: _FakeResponse(fenced))

    result = oracle.oracle_review(_BOARD_MD, _PAGE_TEXT, _SCHEMA_SUMMARY)

    assert result["approve"] is True


def test_oracle_review_unparseable_output_fails_closed(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setattr(oracle.requests, "post",
                        lambda *a, **k: _FakeResponse("Sure, that board looks fine to me!"))

    result = oracle.oracle_review(_BOARD_MD, _PAGE_TEXT, _SCHEMA_SUMMARY)

    assert result["approve"] is False
    assert result["issues"] == ["oracle response unparseable"]


def test_oracle_review_missing_approve_key_fails_closed(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setattr(oracle.requests, "post",
                        lambda *a, **k: _FakeResponse('{"issues": [], "notes": "no approve key"}'))

    result = oracle.oracle_review(_BOARD_MD, _PAGE_TEXT, _SCHEMA_SUMMARY)

    assert result["approve"] is False
    assert result["issues"] == ["oracle response unparseable"]


def test_oracle_review_network_error_fails_closed(monkeypatch):
    def _raise(*a, **k):
        raise ConnectionError("simulated network failure")

    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setattr(oracle.requests, "post", _raise)

    result = oracle.oracle_review(_BOARD_MD, _PAGE_TEXT, _SCHEMA_SUMMARY)

    assert result["approve"] is False
    assert "oracle request failed" in result["issues"][0]


def test_oracle_review_bad_status_fails_closed(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setattr(oracle.requests, "post",
                        lambda *a, **k: _FakeResponse("", status_ok=False))

    result = oracle.oracle_review(_BOARD_MD, _PAGE_TEXT, _SCHEMA_SUMMARY)

    assert result["approve"] is False
    assert "oracle request failed" in result["issues"][0]


def test_oracle_review_posts_to_configured_provider_endpoint(monkeypatch):
    """Honors JR_ORACLE_MODEL — a groq override should hit Groq's endpoint, not OpenRouter's."""
    calls = []

    def _capture(url, headers=None, json=None, timeout=None):
        calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return _FakeResponse('{"approve": true, "issues": [], "notes": "ok"}')

    monkeypatch.setenv("JR_ORACLE_MODEL", "groq:llama-3.1-70b")
    monkeypatch.setenv("GROQ_API_KEY", "g-key")
    monkeypatch.setattr(oracle.requests, "post", _capture)

    oracle.oracle_review(_BOARD_MD, _PAGE_TEXT, _SCHEMA_SUMMARY)

    assert len(calls) == 1
    assert calls[0]["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert calls[0]["headers"]["Authorization"] == "Bearer g-key"
    assert calls[0]["json"]["model"] == "llama-3.1-70b"


def test_oracle_review_defaults_to_openrouter_free_model(monkeypatch):
    calls = []

    def _capture(url, headers=None, json=None, timeout=None):
        calls.append({"url": url, "json": json})
        return _FakeResponse('{"approve": true, "issues": [], "notes": "ok"}')

    monkeypatch.delenv("JR_ORACLE_MODEL", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setattr(oracle.requests, "post", _capture)

    oracle.oracle_review(_BOARD_MD, _PAGE_TEXT, _SCHEMA_SUMMARY)

    assert calls[0]["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert calls[0]["json"]["model"] == "z-ai/glm-5.2:free"
