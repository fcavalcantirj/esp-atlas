"""EspAtlas Jr — is a stale tick PR nothing but superseded GitHub metrics? (jr/superseded_metrics.py)

GitHub star/fork counts are published by the separate runtime JSON publisher
(jr/runtime_popularity.py), so the hourly tick no longer writes them into the catalog. A tick PR
the retired jr/stage_popularity_refresh left open edits ONLY the popularity block (and its
`popularity` / `popularity.*` citations) of firmware records that are already catalogued. Such a
PR carries nothing a later run cannot recompute, and closing it records no rejection: its ids are
`merged`, and jr/memory.reconcile_prs only settles `proposed` ones.

`is_metrics_only` answers that from the PR's ACTUAL diff against its merge base, read through
read-only gh calls (pr view --json, the compare API, the raw contents API). Every changed path must
be bookkeeping (modified or added) or a MODIFIED data/firmware/<id>/firmware.md whose text differs
only inside the popularity block and popularity source items; each such id must still be
catalogued on the base branch tip and `merged` in the tip's jr/proposed_ledger.json. Anything else
— a new record, a recipe, a rename, a non-popularity field (even a comment or re-quoting), a file
list that disagrees, a diff or ledger it cannot read — answers False and the PR stays stuck for a
human. Only read/parse errors are absorbed; the tick's own aborts (budget, SIGTERM) propagate.
"""
from __future__ import annotations

import json
import re

import yaml

import review_routing

FIRMWARE_RECORD_RE = re.compile(r"^data/firmware/([^/]+)/firmware\.md$")
LEDGER_PATH = "jr/proposed_ledger.json"
POPULARITY_KEY = "popularity"
COMPARE_JQ = "{merge_base: .merge_base_commit.sha, files: [.files[] | {filename, status}]}"
RAW_ACCEPT = "Accept: application/vnd.github.raw"   # the file itself; base64 `.content` stops at 1 MB
BOOKKEEPING_STATUSES = ("modified", "added")
_TOP_KEY_RE = re.compile(r"^[A-Za-z_][\w-]*:")
_ITEM_RE = re.compile(r"^(\s*)- ")


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


def _top_blocks(fm_text: str) -> list[tuple[str | None, list[str]]]:
    """The frontmatter text cut at its top-level keys: [(key, lines)], lines kept verbatim."""
    blocks: list[tuple[str | None, list[str]]] = []
    for line in fm_text.splitlines(keepends=True):
        m = _TOP_KEY_RE.match(line)
        if m:
            blocks.append((m.group(0)[:-1], [line]))
        elif blocks:
            blocks[-1][1].append(line)
        else:
            blocks.append((None, [line]))
    return blocks


def _source_lines(lines: list[str]) -> list[str]:
    """A `sources:` block's lines minus every popularity source item. A block that is not a plain
    block list keeps every line, so any edit in it reads as a non-popularity change."""
    head, rest = lines[:1], lines[1:]
    first = next((_ITEM_RE.match(line) for line in rest if line.strip()), None)
    if first is None:
        return lines
    items: list[list[str]] = []
    for line in rest:
        m = _ITEM_RE.match(line)
        if (m and m.group(1) == first.group(1)) or not items:
            items.append([line])
        else:
            items[-1].append(line)
    kept = list(head)
    for item in items:
        try:
            parsed = yaml.safe_load("".join(item))
        except yaml.YAMLError:
            parsed = None
        if not (isinstance(parsed, list) and len(parsed) == 1 and _is_popularity_source(parsed[0])):
            kept += item
    return kept


def _text_skeleton(fm_text: str) -> str:
    """The frontmatter text with the popularity block and popularity source items removed."""
    out = []
    for key, lines in _top_blocks(fm_text):
        if key == POPULARITY_KEY:
            continue
        out += _source_lines(lines) if key == "sources" else lines
    return "".join(out)


def _frontmatter_text(text: str) -> tuple[str, str]:
    _, fm_text, body = text.split("---", 2)
    return fm_text, body


def popularity_only(old: str | None, new: str | None) -> bool:
    """True when two texts of one firmware record differ ONLY inside `popularity` and its
    `popularity` / `popularity.*` source items: every other frontmatter line and the body are
    byte-equal, and both parse to the same non-popularity values."""
    before, after = review_routing._parse(old), review_routing._parse(new)
    if before is None or after is None:
        return False
    old_rest, new_rest = _without_popularity(before[0]), _without_popularity(after[0])
    if old_rest is None or old_rest != new_rest:
        return False
    (old_fm, old_body), (new_fm, new_body) = _frontmatter_text(old), _frontmatter_text(new)
    return old_body == new_body and _text_skeleton(old_fm) == _text_skeleton(new_fm)


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
    p = gh("api", f"repos/{slug}/contents/{path}?ref={ref}", "-H", RAW_ACCEPT)
    out = getattr(p, "stdout", "") or ""
    if getattr(p, "returncode", 1) != 0 or not out.strip():
        raise ValueError(f"{path}@{ref} unreadable")
    return out


def _all_merged(gh, slug: str, ref: str, ids: list[str]) -> bool:
    """Every id `merged` in the ledger at `ref`: reconcile_prs can then never reject it."""
    by_id = json.loads(_content(gh, slug, LEDGER_PATH, ref)).get("by_id") or {}
    return all(isinstance(by_id.get(fid), dict) and by_id[fid].get("status") == "merged" for fid in ids)


def is_metrics_only(gh, slug: str | None, number, paths: list[str]) -> bool:
    """True only when PR `number`'s diff against its merge base touches nothing but bookkeeping and
    the popularity of firmware records that are catalogued and `merged` on the base branch tip.
    Read/parse failures → False; anything else (the tick's budget, SIGTERM) propagates."""
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
        records = [p for p in paths if FIRMWARE_RECORD_RE.match(p)]
        if any(status[p] not in BOOKKEEPING_STATUSES for p in paths if p not in records):
            return False
        if any(status[p] != "modified" for p in records):
            return False
        for path in records:
            _content(gh, slug, path, base)                # still catalogued on the base tip
            if not popularity_only(_content(gh, slug, path, merge_base), _content(gh, slug, path, head)):
                return False
        return _all_merged(gh, slug, base, [FIRMWARE_RECORD_RE.match(p).group(1) for p in records])
    except (ValueError, KeyError, TypeError, AttributeError):   # incl. JSON/UTF-8 decode errors
        return False
