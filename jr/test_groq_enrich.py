"""EspAtlas Jr — pytest for jr/groq_enrich.py. Every client here is a hand-built fake; no test in
this file ever reaches real Groq.

Run: cd jr && python3 -m pytest test_groq_enrich.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import groq_enrich  # noqa: E402

ENGLISH_README = "# CoolFirmware\n\nA firmware that turns your ESP32 into a portable Wi-Fi scanner."
JAPANESE_README = "# クールファームウェア\n\nESP32をポータブルなWi-Fiスキャナーに変えるファームウェアです。"


def _fake_client(reply) -> callable:
    """reply: a dict (JSON-encoded before returning) or a raw string, and the calls it recorded."""
    calls = []

    def _client(system_prompt: str, user_prompt: str) -> str:
        calls.append((system_prompt, user_prompt))
        return json.dumps(reply) if isinstance(reply, dict) else reply

    _client.calls = calls
    return _client


def test_enrich_readme_english_returns_summary_and_no_translation():
    client = _fake_client({
        "summary": "CoolFirmware turns an ESP32 into a portable Wi-Fi scanner.",
        "source_lang": "en",
        "readme_en": None,
    })

    result = groq_enrich.enrich_readme(ENGLISH_README, "coolfirmware", client=client)

    assert result == {
        "summary": "CoolFirmware turns an ESP32 into a portable Wi-Fi scanner.",
        "source_lang": "en",
        "readme_en": None,
    }
    assert len(client.calls) == 1
    system_prompt, user_prompt = client.calls[0]
    assert "coolfirmware" in user_prompt.lower()
    assert ENGLISH_README in user_prompt
    assert "never invent" in system_prompt.lower()


def test_enrich_readme_japanese_returns_translation_and_source_lang():
    translated = "# Cool Firmware\n\nFirmware that turns your ESP32 into a portable Wi-Fi scanner."
    client = _fake_client({
        "summary": "Cool Firmware turns an ESP32 into a portable Wi-Fi scanner.",
        "source_lang": "ja",
        "readme_en": translated,
    })

    result = groq_enrich.enrich_readme(JAPANESE_README, "coolfirmware", client=client)

    assert result["source_lang"] == "ja"
    assert result["readme_en"] == translated
    assert result["summary"] == "Cool Firmware turns an ESP32 into a portable Wi-Fi scanner."


def test_enrich_readme_empty_input_makes_no_client_call():
    client = _fake_client({"summary": "should never be seen", "source_lang": "en", "readme_en": None})

    result = groq_enrich.enrich_readme("   ", "empty-fw", client=client)

    assert result == {"summary": "", "source_lang": "en", "readme_en": None}
    assert client.calls == []


def test_enrich_readme_tolerates_a_code_fenced_json_reply():
    client = _fake_client(
        "```json\n"
        + json.dumps({"summary": "A synopsis.", "source_lang": "en", "readme_en": None})
        + "\n```"
    )

    result = groq_enrich.enrich_readme(ENGLISH_README, "coolfirmware", client=client)

    assert result["summary"] == "A synopsis."
    assert result["source_lang"] == "en"


def test_enrich_readme_unparseable_reply_degrades_to_empty_summary():
    client = _fake_client("not json at all, sorry")

    result = groq_enrich.enrich_readme(ENGLISH_README, "coolfirmware", client=client)

    assert result == {"summary": "", "source_lang": "en", "readme_en": None}


def test_enrich_readme_forces_readme_en_to_none_when_source_lang_is_english_even_if_the_model_sent_one():
    client = _fake_client({
        "summary": "A synopsis.", "source_lang": "en",
        "readme_en": "a translation that should never have been sent for an english source",
    })

    result = groq_enrich.enrich_readme(ENGLISH_README, "coolfirmware", client=client)

    assert result["readme_en"] is None
