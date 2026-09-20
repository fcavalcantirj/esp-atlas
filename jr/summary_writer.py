"""EspAtlas Jr — firmware.md summary/translation persistence (jr/summary_writer.py).

Pure rewrite helpers used by jr/backfill_summary.py's one-shot pass and, later, reusable by the
tick's own per-admission enrichment step. Mirrors jr/backfill_popularity.py's own
_split/_render/update_* shape: a full YAML round-trip, a verified idempotent no-op, one
sources[] entry for the cited field.

    readme_sha256(text)            -> sha256 hex digest of a fetched README — the change-
                                       detection key a re-run compares against the frontmatter's
                                       own stored `readme_sha` before ever calling Groq again.
    update_summary(md_text, ...)   -> {"text", "changed", "reason"|None} — writes `summary`,
                                       `readme_lang`, `readme_sha` into frontmatter, plus one
                                       `field: summary` sources[] entry (replaced, never
                                       duplicated, so its `verified` date tracks the last
                                       successful enrichment).
    write_readme_en(dir, text)     -> writes <dir>/readme.en.md (plain markdown, kept OUT of
                                       frontmatter so a long README doesn't bloat every read of
                                       the record); returns the path written.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import yaml


def _split(md_text: str) -> tuple[dict, str]:
    """firmware.md text -> (frontmatter dict, body string INCLUDING its leading blank line(s)).
    Mirrors jr/backfill_popularity.py's own `_split` convention."""
    if not md_text.startswith("---"):
        return {}, md_text
    _, front, body = md_text.split("---", 2)
    return (yaml.safe_load(front) or {}), body


def _render(fm: dict, body: str) -> str:
    front = yaml.safe_dump(fm, sort_keys=False, default_flow_style=False).strip()
    return f"---\n{front}\n---{body}"


def readme_sha256(readme_markdown: str) -> str:
    """sha256 hex digest of the fetched README text."""
    return hashlib.sha256((readme_markdown or "").encode("utf-8")).hexdigest()


def update_summary(md_text: str, *, summary: str, readme_lang: str, readme_sha: str,
                    readme_url: str, today: str) -> dict:
    """Pure rewrite of one firmware.md's text with an enrichment result.

    `summary` must be non-empty — an empty/unusable README's enrichment is the caller's problem
    to skip, not this function's (reason "no_summary"). Returns
    {"text": <md, rewritten or original>, "changed": bool, "reason": str|None}. `reason` is set
    (and `changed` False, `text` the untouched original) whenever nothing was written:
    "no_summary" (empty `summary`), or "up_to_date" (frontmatter's summary/readme_lang/
    readme_sha already match — the idempotent no-op a re-run against an unchanged README hits).
    """
    if not (summary or "").strip():
        return {"text": md_text, "changed": False, "reason": "no_summary"}

    fm, body = _split(md_text)
    if (fm.get("summary") == summary and fm.get("readme_lang") == readme_lang
            and fm.get("readme_sha") == readme_sha):
        return {"text": md_text, "changed": False, "reason": "up_to_date"}

    fm = dict(fm)
    fm["summary"] = summary
    fm["readme_lang"] = readme_lang
    fm["readme_sha"] = readme_sha
    sources = [s for s in (fm.get("sources") or [])
               if not (isinstance(s, dict) and s.get("field") == "summary")]
    sources.append({"field": "summary", "url": readme_url, "verified": today})
    fm["sources"] = sources
    return {"text": _render(fm, body), "changed": True, "reason": None}


def write_readme_en(firmware_dir: Path, readme_en: str) -> Path:
    """Write the cached English translation to <firmware_dir>/readme.en.md. Plain markdown, no
    frontmatter. Returns the path written."""
    firmware_dir = Path(firmware_dir)
    firmware_dir.mkdir(parents=True, exist_ok=True)
    path = firmware_dir / "readme.en.md"
    text = readme_en if readme_en.endswith("\n") else readme_en + "\n"
    path.write_text(text, encoding="utf-8")
    return path
