"""EspAtlas Jr — Groq-powered README enrichment (jr/groq_enrich.py).

One grounded call per firmware: given its README verbatim, ask Groq for (1) a one-to-two
sentence English synopsis derived ONLY from what the README states, and (2) — when the README
isn't already English — a full English translation that preserves code blocks, shell commands,
URLs, and API-key/env-var names verbatim. Never invents capabilities beyond the README's own
text; that grounding lives in SYSTEM_PROMPT, not in any code-side filtering here.

The real HTTP call (`default_client`) reads GROQ_API_KEY from the environment only — never
hardcoded, never passed a default — and is used purely as an injectable callable
`(system_prompt, user_prompt) -> raw content string`, mirroring jr/derive.py's own
`api`/`raw` injection convention. Every test in jr/test_groq_enrich.py passes a fake callable,
so this module makes zero network calls under pytest.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
# Overridable via GROQ_MODEL; default is the strongest model enabled on Jr's key
# (llama-3.3-70b-versatile is NOT provisioned — verified against /v1/models, 2026-09-20).
MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

SYSTEM_PROMPT = (
    "You are EspAtlas Jr's README enrichment engine. You are given one firmware project's "
    "README verbatim. Using ONLY what the README itself states — never invent capabilities, "
    "boards, versions, or claims the README does not make — do two things:\n"
    "1. Write a grounded one-to-two sentence English synopsis of what the firmware is/does.\n"
    "2. Detect the README's primary language as an ISO 639-1 code ('en' if it is already "
    "English). If it is NOT English, translate the FULL README to English. In the translation, "
    "preserve code blocks, shell commands, URLs, and API-key/environment-variable names "
    "verbatim — translate prose only, never identifiers.\n"
    "Return ONLY a single JSON object with exactly these keys, no prose outside it:\n"
    '{"summary": "<synopsis>", "source_lang": "<code>", "readme_en": "<translation or null>"}\n'
    "readme_en MUST be null when source_lang is \"en\"."
)

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.I | re.M)


def default_client(system_prompt: str, user_prompt: str) -> str:  # pragma: no cover — real network call
    """Real Groq chat-completions call, OpenAI-compatible. Reads GROQ_API_KEY from the
    environment (never hardcoded); raises RuntimeError if it's unset. Never used under pytest —
    every test injects a fake `(system_prompt, user_prompt) -> str` callable instead."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set")
    payload = json.dumps({
        "model": MODEL,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }).encode("utf-8")
    req = urllib.request.Request(
        GROQ_CHAT_URL, data=payload, method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
                 "User-Agent": "esp-atlas-jr/0.1"},  # Cloudflare 403s the default Python-urllib UA
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def _parse_json_object(raw: str) -> dict:
    """Tolerate a code-fence-wrapped JSON object (```json ... ```) and/or stray prose around it —
    Groq output isn't always the bare object the prompt asks for."""
    text = _FENCE.sub("", (raw or "").strip()).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"no JSON object found in model output: {raw[:200]!r}")
    return json.loads(text[start:end + 1])


def enrich_readme(readme_markdown: str, firmware_name: str, *, client=default_client) -> dict:
    """Return {"summary": str, "source_lang": str, "readme_en": str|None} for one firmware's
    README, grounded in that README alone.

    `summary` is '' when the README is empty/whitespace-only (no call is made) or when the
    model's response can't be parsed as the requested JSON object (a bad response degrades to
    "nothing usable", never a crash — the caller decides whether that's a skip). `source_lang`
    defaults to 'en' in both of those cases. `readme_en` is populated only when `source_lang`
    isn't 'en' and the model actually returned a non-empty translation.
    """
    if not (readme_markdown or "").strip():
        return {"summary": "", "source_lang": "en", "readme_en": None}

    user_prompt = f"Firmware name: {firmware_name}\n\nREADME:\n{readme_markdown}"
    raw = client(SYSTEM_PROMPT, user_prompt)
    try:
        obj = _parse_json_object(raw)
    except (ValueError, json.JSONDecodeError):
        return {"summary": "", "source_lang": "en", "readme_en": None}

    summary = str(obj.get("summary") or "").strip()
    source_lang = (str(obj.get("source_lang") or "en").strip().lower() or "en")
    readme_en = obj.get("readme_en")
    if source_lang == "en" or not (readme_en or "").strip():
        readme_en = None
    else:
        readme_en = str(readme_en).strip()

    return {"summary": summary, "source_lang": source_lang, "readme_en": readme_en}
