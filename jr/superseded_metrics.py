"""EspAtlas Jr — is a stale tick PR nothing but superseded GitHub metrics? (jr/superseded_metrics.py)

GitHub star/fork counts are published by the separate runtime JSON publisher
(jr/runtime_popularity.py), so the hourly tick no longer writes them into the catalog. A tick PR
the retired jr/stage_popularity_refresh left open edits ONLY the popularity block (and its
`popularity` / `popularity.*` citations) of firmware records that are already catalogued. Such a
PR carries nothing a later run cannot recompute, and closing it records no rejection
(jr/memory.reconcile_prs only settles `proposed` ids; these ids are `merged`).

`is_metrics_only` answers that from the PR's ACTUAL diff against its merge base, read through
read-only gh calls (pr view --json, the compare API, the contents API). Every changed path must be
bookkeeping or a MODIFIED data/firmware/<id>/firmware.md whose frontmatter and body differ only in
popularity. Anything else — a new record, a recipe, a non-popularity field, a file list that
disagrees, a diff it cannot read — answers False, and the PR stays stuck for a human. Never raises.
"""
from __future__ import annotations

import base64
import json
import re

import review_routing

FIRMWARE_RECORD_RE = re.compile(r"^data/firmware/[^/]+/firmware\.md$")
POPULARITY_KEY = "popularity"
COMPARE_JQ = "{merge_base: .merge_base_commit.sha, files: [.files[] | {filename, status}]}"


def _is_popularity_source(source) -> bool:
    field = source.get("field") if isinstance(source, dict) else None
    return isinstance(field, str) and (field == POPULARITY_KEY or field.startswith(POPULARITY_KEY + "."))


def _without_popularity(fm: dict) -> dict | None:
    """The frontmatter minus the popularity block and its citations; None when `sources` is not a
    list (an unreadable record is never judged popularity-only)."""
    sources = fm.get("sources", [])
    if not isinstance(sources, list):
        return None
    rest = {k: v for k, v in fm.items() if k not in (POPULARITY_KEY, "sources")}
    rest["sources"] = [s for s in sources if not _is_popularity_source(s)]
    return rest


def popularity_only(old: str | None, new: str | None) -> bool:
    """True when two texts of one firmware record differ ONLY in `popularity` and its
    `popularity` / `popularity.*` source entries; body and every other field byte-equal."""
    before, after = review_routing._parse(old), review_routing._parse(new)
    if before is None or after is None:
        return False
    (old_fm, old_body), (new_fm, new_body) = before, after
    if old_body != new_body:
        return False
    old_rest, new_rest = _without_popularity(old_fm), _without_popularity(new_fm)
    return old_rest is not None and old_rest == new_rest


def candidate(paths: list[str]) -> bool:
    """Cheap path-only screen: some firmware record, and nothing but records and bookkeeping."""
    records = [p for p in paths if FIRMWARE_RECORD_RE.match(p)]
    return bool(records) and all(FIRMWARE_RECORD_RE.match(p) or review_routing.is_bookkeeping(p) for p in paths)


def _json(gh, *args) -> dict:
    p = gh(*args)
    if getattr(p, "returncode", 1) != 0:
        raise ValueError(f"gh {' '.join(args[:2])} failed")
    data = json.loads(getattr(p, "stdout", "") or "")
    if not isinstance(data, dict):
        raise ValueError("not a JSON object")
    return data


def _content(gh, slug: str, path: str, ref: str) -> str:
    p = gh("api", f"repos/{slug}/contents/{path}?ref={ref}", "-q", ".content")
    out = (getattr(p, "stdout", "") or "").strip()
    if getattr(p, "returncode", 1) != 0 or not out:
        raise ValueError(f"{path}@{ref} unreadable")
    return base64.b64decode(out).decode("utf-8")


def is_metrics_only(gh, slug: str | None, number, paths: list[str]) -> bool:
    """True only when PR `number`'s diff against its merge base touches nothing but bookkeeping and
    the popularity of existing (modified, not added) firmware records. Any failure → False."""
    if not slug or not candidate(paths):
        return False
    try:
        refs = _json(gh, "pr", "view", str(number), "--json", "baseRefName,headRefOid")
        base, head = refs["baseRefName"], refs["headRefOid"]
        cmp = _json(gh, "api", f"repos/{slug}/compare/{base}...{head}", "-q", COMPARE_JQ)
        merge_base = cmp["merge_base"]
        status = {f["filename"]: f["status"] for f in cmp["files"]}
        if not (base and head and merge_base) or set(status) != set(paths):
            return False
        for path in paths:
            if review_routing.is_bookkeeping(path):
                continue
            if status[path] != "modified":
                return False
            if not popularity_only(_content(gh, slug, path, merge_base), _content(gh, slug, path, head)):
                return False
        return True
    except Exception:  # noqa: BLE001 — an unreadable diff is never a reason to close a PR
        return False
