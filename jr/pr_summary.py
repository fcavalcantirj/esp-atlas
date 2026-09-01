"""EspAtlas Jr — best-effort LLM smart-summary for the catalog-drain PR DESCRIPTION only.

This module writes PROSE for the top of a drain PR body. It NEVER writes into any data/ file,
source, firmware.md, recipe, or the cited list — the deterministic drain (jr/drain.py) and the
guard stay 100% LLM-free. Everything here is strictly additive to the PR description and strictly
best-effort: if GROQ_API_KEY is unset, the groq/httpx client isn't importable, the call errors,
or it exceeds a short timeout, `summarize()` returns None and drain_pr.py falls back to its terse
cited template. The drain PR MUST always open — nothing here may block, crash, or slow it.

The summary is derived ONLY from the deterministic facts the drain already authored (id, name,
category, url, capabilities, board, and optional stars). The LLM writes ONLY the natural-language
headline; the category breakdown, the notable picks, and — most importantly — the "Review these"
low-confidence flags are computed deterministically here so Jr can flag its OWN uncertain category
calls without an LLM ever inventing firmware, versions, or claims.

Interface mirrors esp_atlas_core.llm.GroqClient: any injected `client` must expose
`.complete(system_prompt, user_prompt, temperature=0) -> str` — tests inject a fake, so no real
network call is ever made under pytest.
"""
from __future__ import annotations

import os
from collections import Counter

# The FAST/cheap model matches the rest of Jr's LLM-shaped work; kept as a plain constant so this
# module needs no import from esp_atlas_core at load time (that import is guarded, best-effort).
FAST_MODEL = "openai/gpt-oss-20b"
DEFAULT_TIMEOUT_SECONDS = 8.0

# Deterministic low-confidence rules — Jr flagging its OWN uncertain category calls. Each keyword,
# if it appears in an entry's name/capabilities, makes the listed categories look wrong for it.
# These are heuristics for a human to double-check, never a hard gate on the cited data.
_MEDIA_TOYS = (
    "radio", "mp3", "wav", "audio", "music", "player", "media", "sound", "podcast",
    "fm-radio", "mixer", "synth", "clock", "toy", "game", "weather", "speaker", "mic",
)
_MEDIA_TOYS_WRONG = {"home", "pentest"}
_FACTORY_DEMO = ("factory", "demo", "hello-world", "helloworld", "example", "sample", "template", "boilerplate")
_FACTORY_DEMO_WRONG = {"multi"}

SYSTEM_PROMPT = (
    "You are EspAtlas Jr, a firmware-catalog bot. Given a batch of firmware entries that were "
    "already authored deterministically, write ONE short, punchy headline line summarising the "
    "batch for a human reviewer. Use ONLY the facts given. Never invent firmware, versions, star "
    "counts, or claims. No markdown, no bullet points, no newlines — a single plain sentence."
)


def _tokens(entry: dict) -> str:
    """Lowercased haystack of the human-meaningful fact fields for keyword matching."""
    caps = entry.get("capabilities") or []
    caps_txt = " ".join(str(c) for c in caps)
    return f"{entry.get('name', '')} {entry.get('id', '')} {caps_txt}".lower()


def _review_flags(facts: list[dict]) -> list[dict]:
    """Entries whose assigned category looks low-confidence given their name/capabilities — Jr's
    own uncertain calls, surfaced for a human to double-check. Deterministic; derived only from
    the provided facts."""
    flagged = []
    for e in facts:
        category = str(e.get("category", "")).lower()
        hay = _tokens(e)
        reason = None
        if category in _MEDIA_TOYS_WRONG and any(k in hay for k in _MEDIA_TOYS):
            reason = "looks like media/audio/toy"
        elif category in _FACTORY_DEMO_WRONG and any(k in hay for k in _FACTORY_DEMO):
            reason = "looks like a factory/demo"
        if reason:
            flagged.append({"id": e.get("id", ""), "name": e.get("name", ""), "category": category, "reason": reason})
    return flagged


def _breakdown(facts: list[dict]) -> str:
    counts = Counter(str(e.get("category", "") or "uncategorized").lower() for e in facts)
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return " · ".join(f"{cat} {n}" for cat, n in ordered)


def _notable(facts: list[dict], limit: int = 3) -> list[dict]:
    """2-4 standout entries: by GitHub stars if any fact carries them, else stable by name."""
    has_stars = any(e.get("stars") is not None for e in facts)
    if has_stars:
        ranked = sorted(facts, key=lambda e: (-(e.get("stars") or 0), str(e.get("name", ""))))
    else:
        ranked = sorted(facts, key=lambda e: str(e.get("name", "")).lower())
    return ranked[:limit]


def _build_user_prompt(facts: list[dict], breakdown: str) -> str:
    lines = [f"{len(facts)} new firmware this batch.", f"Category breakdown: {breakdown}.", "", "Entries:"]
    for e in facts:
        caps = ", ".join(str(c) for c in (e.get("capabilities") or [])) or "—"
        board = e.get("board") or "—"
        star = f", {e['stars']}★" if e.get("stars") is not None else ""
        lines.append(f"- {e.get('name', e.get('id', '?'))} [{e.get('category', '?')}] board={board} caps={caps}{star}")
    lines += ["", "Write the one-line headline now."]
    return "\n".join(lines)


def _resolve_client(client, env):
    """Return a client exposing .complete(...), or None if we can't/shouldn't make a real call.
    An injected client is always used as-is (tests). For a real call we require GROQ_API_KEY and
    an importable GroqClient — either missing means best-effort no-op."""
    if client is not None:
        return client
    if not (env.get("GROQ_API_KEY") or "").strip():
        return None
    try:  # Prefer the repo's real client if it's on sys.path; never hard-depend on it.
        from esp_atlas_core.llm import GroqClient  # type: ignore
    except Exception:
        return None
    try:
        return GroqClient(model=FAST_MODEL)
    except Exception:
        return None


def _call_headline(client, system_prompt: str, user_prompt: str, timeout: float):
    """Run client.complete in a worker thread with a hard timeout. Any error, timeout, or empty
    result yields None — the whole summary is best-effort and must never block the drain."""
    import concurrent.futures

    def _work():
        return client.complete(system_prompt, user_prompt, temperature=0)

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            raw = ex.submit(_work).result(timeout=timeout)
    except Exception:
        return None
    if not raw or not str(raw).strip():
        return None
    # One clean line only, even if the model returned prose/markdown.
    return str(raw).strip().splitlines()[0].strip().lstrip("#").strip()


def summarize(facts: list[dict], *, client=None, timeout: float = DEFAULT_TIMEOUT_SECONDS, env=None):
    """Return a markdown smart-summary string for the drain PR body, or None (best-effort).

    `facts` is the batch's deterministic facts: a list of {id, name, category, url, capabilities,
    board} (optional `stars`). The category breakdown, notable picks, and low-confidence "Review
    these" flags are computed here deterministically; the LLM writes only the headline. Returns
    None whenever no headline could be produced (no key, no client, error, timeout, empty) so the
    caller falls back to the terse cited template. Never raises."""
    try:
        if not facts:
            return None
        env = os.environ if env is None else env
        breakdown = _breakdown(facts)

        resolved = _resolve_client(client, env)
        if resolved is None:
            return None
        headline = _call_headline(resolved, SYSTEM_PROMPT, _build_user_prompt(facts, breakdown), timeout)
        if not headline:
            return None

        parts = [headline, "", f"**Categories:** {breakdown}"]

        notable = _notable(facts)
        if notable:
            picks = " · ".join(f"`{e.get('id', '')}` ({e.get('category', '?')})" for e in notable)
            parts += ["", f"**Notable:** {picks}"]

        flags = _review_flags(facts)
        if flags:
            parts += ["", "**⚠️ Review these** — Jr's own low-confidence category calls, please double-check:"]
            for f in flags:
                parts.append(f"- `{f['id']}` — labeled `{f['category']}`, but {f['reason']}")

        return "\n".join(parts)
    except Exception:
        # Absolute belt-and-braces: nothing in this module may ever escape to the drain.
        return None
