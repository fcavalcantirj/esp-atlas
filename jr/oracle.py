"""EspAtlas Jr — the oracle-review quality gate.

A STRONGER model (JR_ORACLE_MODEL, default openrouter:z-ai/glm-5.2:free — free tier)
fact-checks a drafted board record against its own cited source page BEFORE it is proposed.
This is an ADDITIONAL quality gate — tools.board_triple_validate remains the FINAL,
deterministic authority; the oracle never replaces it (SPEC: the guard is sovereign). It was
added after a live run authored the Adafruit MagTag (real chip: ESP32-S2) with
module: esp32-wrover-e — a classic dual-core ESP32, wrong chip family entirely.

Split out of tools.py (file-size ceiling) — re-exported there as tools.oracle_review so
run.py's call sites don't change.
"""
from __future__ import annotations
import json
import os
import re

import requests

import models

ORACLE_SYSTEM_PROMPT = (
    "You are a hardware-datasheet fact-checker. Given this proposed board record and the text "
    "of its official source page, list any field that is (a) not supported by the page, (b) the "
    "WRONG chip family/module, or (c) mis-cited.\n\n"
    "The record's soc/module value is a CANONICAL catalog identifier — it is NOT expected to "
    "appear literally on the page. Treat the soc/module as correct if the page names the SAME "
    "chip FAMILY semantically: a page that says \"ESP32-S2\" or \"ESP32-S2 module\" or \"ESP32-S2 "
    "wireless module\" fully supports soc: esp32-s2 (or an esp32-s2-* module). Do NOT reject just "
    "because the exact hyphenated identifier string is absent from the page — no vendor product "
    "page ever spells out the literal catalog id.\n\n"
    "Only flag a chip mismatch when the page names a DIFFERENT family (e.g. page says ESP32-S3 "
    "but the record says esp32-s2), or a spec VALUE (flash, psram, usb, display, dimensions, "
    "extras) that the page does not support. Stay strict on spec-value support and wrong-family "
    "mismatches — loosen ONLY on identifier-string literalism.\n\n"
    "Approve ONLY if every hard spec is backed by the page and the soc/module's chip family "
    "matches the family named on the page. Respond with ONLY a JSON object, no prose, no markdown "
    'fences: {"approve": true|false, "issues": ["..."], "notes": "..."}.'
)


def _parse_oracle_json(text: str) -> dict | None:
    """Tolerate a code-fenced JSON blob (```json ... ``` or bare ``` ... ```) around the verdict.
    None means the model didn't return a valid {"approve": bool, ...} object — oracle_review
    treats that as fail-closed, never a pass-through."""
    if not isinstance(text, str):
        return None
    body = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", body, re.DOTALL)
    if fence:
        body = fence.group(1).strip()
    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(parsed, dict) or not isinstance(parsed.get("approve"), bool):
        return None
    return {
        "approve": parsed["approve"],
        "issues": [str(x) for x in (parsed.get("issues") or [])],
        "notes": str(parsed.get("notes") or ""),
    }


def oracle_review(board_md_text: str, page_text: str, schema_summary: str) -> dict:
    """Calls the configured JR_ORACLE_MODEL via a plain OpenAI-compatible chat/completions POST
    (no Agno framework needed for a single one-shot judgment call). Returns
    {"approve": bool, "issues": [...], "notes": str}; ANY failure — network error, bad status,
    unparseable JSON, wrong shape — fails CLOSED (approve=False) rather than silently waving a
    draft through."""
    spec = os.environ.get("JR_ORACLE_MODEL", models.DEFAULT_ORACLE_MODEL)
    cfg = models.client_config(spec)
    payload = {
        "model": cfg["model_id"],
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": ORACLE_SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"SCHEMA (allowed shape):\n{schema_summary}\n\n"
                f"PROPOSED BOARD RECORD:\n{board_md_text}\n\n"
                f"OFFICIAL SOURCE PAGE TEXT:\n{page_text}"
            )},
        ],
    }
    no_usage = {"prompt_tokens": 0, "completion_tokens": 0}
    try:
        resp = requests.post(
            f"{cfg['base_url']}/chat/completions",
            headers={"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"},
            json=payload, timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
    except Exception as e:
        return {"approve": False, "issues": [f"oracle request failed: {type(e).__name__}: {e}"],
                "notes": "", "usage": no_usage}

    usage = data.get("usage") or {}
    usage = {"prompt_tokens": usage.get("prompt_tokens", 0) or 0,
             "completion_tokens": usage.get("completion_tokens", 0) or 0}

    verdict = _parse_oracle_json(content)
    if verdict is None:
        return {"approve": False, "issues": ["oracle response unparseable"], "notes": str(content)[:500],
                "usage": usage}
    verdict["usage"] = usage
    return verdict
