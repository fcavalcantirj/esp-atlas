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

    assert result == {"approve": True, "issues": [], "notes": "soc matches the page",
                       "usage": {"prompt_tokens": 0, "completion_tokens": 0}}


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


# ─────────────── family-semantic calibration (stop identifier-literal false-rejects) ───────────────
# Live bug: the oracle rejected the Adafruit MagTag (soc: esp32-s2) TWICE because the source page
# says "ESP32-S2 wireless module" and never contains the literal hyphenated string "esp32-s2". The
# soc/module value is a CANONICAL catalog id, never expected to appear verbatim on a vendor page.

_MAGTAG_SOC_MD = (
    "---\nid: adafruit-magtag\ntype: board\nbrand: adafruit\nname: Adafruit MagTag\n"
    "soc: esp32-s2\nsources:\n- field: '*'\n  url: https://www.adafruit.com/product/4800\n"
    "  verified: '2026-08-28'\n---\n\n# Adafruit MagTag\n"
)


def test_oracle_system_prompt_treats_soc_as_canonical_not_literal():
    """Locks in the recalibration: the prompt must tell the oracle the soc/module value is a
    canonical catalog id matched by chip FAMILY, not a literal string expected on the page."""
    prompt = oracle.ORACLE_SYSTEM_PROMPT.lower()
    assert "canonical" in prompt
    assert "family" in prompt
    assert "literal" in prompt or "hyphenated" in prompt


def test_oracle_review_approves_soc_when_page_only_names_chip_family_in_prose(monkeypatch):
    """Regression for the live MagTag false-reject: the page never contains the literal
    'esp32-s2' string, only prose naming the chip family. A correctly-calibrated oracle approves."""
    page_text = "The Adafruit MagTag features an ESP32-S2 wireless module for connectivity."
    verdict_json = ('{"approve": true, "issues": [], '
                    '"notes": "page names the ESP32-S2 family; soc: esp32-s2 matches semantically"}')
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setattr(oracle.requests, "post", lambda *a, **k: _FakeResponse(verdict_json))

    result = oracle.oracle_review(_MAGTAG_SOC_MD, page_text, _SCHEMA_SUMMARY)

    assert result["approve"] is True


def test_oracle_review_still_rejects_when_page_names_a_different_chip_family(monkeypatch):
    """Loosening on identifier literalism must NOT loosen the wrong-family check."""
    page_text = "This board is powered by an ESP32-S3 module with native USB."
    verdict_json = ('{"approve": false, "issues": '
                    '["page names ESP32-S3, record uses esp32-s2 — different chip family"], "notes": ""}')
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setattr(oracle.requests, "post", lambda *a, **k: _FakeResponse(verdict_json))

    result = oracle.oracle_review(_MAGTAG_SOC_MD, page_text, _SCHEMA_SUMMARY)

    assert result["approve"] is False
    assert any("esp32-s3" in i.lower() for i in result["issues"])


def test_oracle_review_still_rejects_an_unsupported_spec_value(monkeypatch):
    """Loosening on identifier literalism must NOT loosen strictness on spec VALUES (flash,
    psram, usb, display, dimensions, extras) the page doesn't support."""
    board_md = (
        "---\nid: adafruit-magtag\ntype: board\nbrand: adafruit\nname: Adafruit MagTag\n"
        "soc: esp32-s2\npsram_mb: 8\nsources:\n- field: '*'\n  url: https://www.adafruit.com/product/4800\n"
        "  verified: '2026-08-28'\n---\n\n# Adafruit MagTag\n"
    )
    page_text = "The Adafruit MagTag features an ESP32-S2 wireless module. 2MB PSRAM."
    verdict_json = ('{"approve": false, "issues": '
                    '["record claims psram_mb: 8 but the page states 2MB PSRAM"], "notes": ""}')
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setattr(oracle.requests, "post", lambda *a, **k: _FakeResponse(verdict_json))

    result = oracle.oracle_review(board_md, page_text, _SCHEMA_SUMMARY)

    assert result["approve"] is False
    assert any("psram" in i.lower() for i in result["issues"])


# ─────────────────────────── oracle spend accounting (usage tokens) ───────────────────────────

class _FakeResponseWithUsage(_FakeResponse):
    def __init__(self, content: str, prompt_tokens: int, completion_tokens: int):
        super().__init__(content)
        self._usage = {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens}

    def json(self):
        d = super().json()
        d["usage"] = self._usage
        return d


def test_oracle_review_returns_usage_tokens_from_the_http_response(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setattr(oracle.requests, "post", lambda *a, **k: _FakeResponseWithUsage(
        '{"approve": true, "issues": [], "notes": "ok"}', 321, 87))

    result = oracle.oracle_review(_BOARD_MD, _PAGE_TEXT, _SCHEMA_SUMMARY)

    assert result["usage"] == {"prompt_tokens": 321, "completion_tokens": 87}


def test_oracle_review_usage_defaults_to_zero_when_absent_from_response(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setattr(oracle.requests, "post",
                        lambda *a, **k: _FakeResponse('{"approve": true, "issues": [], "notes": "ok"}'))

    result = oracle.oracle_review(_BOARD_MD, _PAGE_TEXT, _SCHEMA_SUMMARY)

    assert result["usage"] == {"prompt_tokens": 0, "completion_tokens": 0}


def test_oracle_review_usage_defaults_to_zero_on_unparseable_response(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setattr(oracle.requests, "post",
                        lambda *a, **k: _FakeResponse("not json at all"))

    result = oracle.oracle_review(_BOARD_MD, _PAGE_TEXT, _SCHEMA_SUMMARY)

    assert result["usage"] == {"prompt_tokens": 0, "completion_tokens": 0}


def test_oracle_review_usage_defaults_to_zero_on_network_error(monkeypatch):
    def _raise(*a, **k):
        raise ConnectionError("simulated network failure")

    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setattr(oracle.requests, "post", _raise)

    result = oracle.oracle_review(_BOARD_MD, _PAGE_TEXT, _SCHEMA_SUMMARY)

    assert result["usage"] == {"prompt_tokens": 0, "completion_tokens": 0}


# ────────────── module hierarchy calibration (WROOM/WROVER/MINI package the base soc) ──────────────
# Live bug: the SparkFun ESP32 Thing Plus C has soc: esp32 and the page says "ESP32 WROOM" — the
# oracle wrongly rejected it as "soc esp32 does not match chip family ESP32 WROOM". WROOM is a
# MODULE (silicon + flash + antenna can) that PACKAGES the base esp32 soc, not a separate family.

_THING_PLUS_MD = (
    "---\nid: sparkfun-esp32-thing-plus-c\ntype: board\nbrand: sparkfun\n"
    "name: SparkFun ESP32 Thing Plus C\nsoc: esp32\nsources:\n"
    "- field: '*'\n  url: https://www.sparkfun.com/products/17381\n"
    "  verified: '2026-08-28'\n---\n\n# SparkFun ESP32 Thing Plus C\n"
)


def test_oracle_review_approves_soc_esp32_when_page_names_wroom_module(monkeypatch):
    """Regression for the live SparkFun ESP32 Thing Plus C false-reject: the page says
    'ESP32-WROOM-32 module' / 'ESP32 WROOM' (no -S2/-S3 suffix) which packages the base esp32
    soc. Asserts the system prompt ACTUALLY sent teaches the module hierarchy (not just that the
    mocked verdict says approve=true) — this must FAIL before the module-hierarchy paragraph is
    added to ORACLE_SYSTEM_PROMPT, and PASS after."""
    calls = []

    def _capture(url, headers=None, json=None, timeout=None):
        calls.append(json)
        return _FakeResponse('{"approve": true, "issues": [], '
                             '"notes": "ESP32-WROOM-32 module packages the base esp32 soc"}')

    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setattr(oracle.requests, "post", _capture)

    page_text = "SparkFun ESP32 Thing Plus C - powered by the ESP32-WROOM-32 module. ESP32 WROOM."
    result = oracle.oracle_review(_THING_PLUS_MD, page_text, _SCHEMA_SUMMARY)

    system_msg = calls[0]["messages"][0]["content"].lower()
    assert "wroom" in system_msg
    assert "packages the base esp32 soc" in system_msg or "contain the base esp32 soc" in system_msg
    assert result["approve"] is True


def test_oracle_review_approves_soc_esp32_s3_when_page_names_s3_wroom_module(monkeypatch):
    board_md = (
        "---\nid: some-s3-board\ntype: board\nbrand: espressif\nname: Some S3 Board\n"
        "soc: esp32-s3\nsources:\n- field: '*'\n  url: https://example.com/s3-board\n"
        "  verified: '2026-08-28'\n---\n\n# Some S3 Board\n"
    )
    page_text = "Powered by the ESP32-S3-WROOM-1 module."
    verdict_json = ('{"approve": true, "issues": [], '
                    '"notes": "ESP32-S3-WROOM-1 module contains the esp32-s3 soc"}')
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setattr(oracle.requests, "post", lambda *a, **k: _FakeResponse(verdict_json))

    result = oracle.oracle_review(board_md, page_text, _SCHEMA_SUMMARY)

    assert result["approve"] is True


def test_oracle_review_still_rejects_esp32_s2_when_page_names_s3(monkeypatch):
    """Module-hierarchy loosening must NOT loosen the wrong-family check."""
    board_md = (
        "---\nid: some-s2-board\ntype: board\nbrand: espressif\nname: Some S2 Board\n"
        "soc: esp32-s2\nsources:\n- field: '*'\n  url: https://example.com/s2-board\n"
        "  verified: '2026-08-28'\n---\n\n# Some S2 Board\n"
    )
    page_text = "Powered by the ESP32-S3-WROOM-1 module."
    verdict_json = ('{"approve": false, "issues": '
                    '["page names ESP32-S3-WROOM-1 (esp32-s3), record uses esp32-s2 — different '
                    'chip family"], "notes": ""}')
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setattr(oracle.requests, "post", lambda *a, **k: _FakeResponse(verdict_json))

    result = oracle.oracle_review(board_md, page_text, _SCHEMA_SUMMARY)

    assert result["approve"] is False
    assert any("esp32-s3" in i.lower() for i in result["issues"])


def test_oracle_review_rejects_when_primary_chip_is_non_esp_coprocessor(monkeypatch):
    """A non-ESP primary MCU (e.g. STM32) with the ESP chip only as a secondary radio
    co-processor must still be flagged, even though the ESP chip family itself matches."""
    board_md = (
        "---\nid: some-stm32-board\ntype: board\nbrand: acme\nname: Some STM32 Board\n"
        "soc: esp32-c3\nsources:\n- field: '*'\n  url: https://example.com/stm32-board\n"
        "  verified: '2026-08-28'\n---\n\n# Some STM32 Board\n"
    )
    page_text = ("Powered by an STM32H743 microcontroller as the main application processor, "
                 "with an ESP32-C3 module onboard providing Wi-Fi/BLE connectivity.")
    verdict_json = ('{"approve": false, "issues": '
                    '["board primary processor is STM32H743, ESP32-C3 is only a secondary '
                    'radio co-processor"], "notes": ""}')
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setattr(oracle.requests, "post", lambda *a, **k: _FakeResponse(verdict_json))

    result = oracle.oracle_review(board_md, page_text, _SCHEMA_SUMMARY)

    assert result["approve"] is False
    assert any("stm32" in i.lower() for i in result["issues"])
