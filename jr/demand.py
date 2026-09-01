"""EspAtlas Jr — read-only demand miner (SPEC-jr-demand-driven.md §3, Phase 1 — §12).

Pulls GSC query-gap demand (D1 `[query]`, D4 `[query,page]`) and attempts GA4 on-site
search (D2 `searchTerm`) via **Composio** — reusing `telemetry.py`'s exact auth pattern
(same `KEY`/`ENTITY`/`GA4_PROPERTY`/`GSC_SITE`, same `_ex()` executor; not forked here, see
`_pull_live()`). Normalizes, floor-filters, dedups/merges, weights (a pure versioned
formula), resolves each term to a catalog entity by REUSING `scorer.py`'s `device_map` /
`capability_map` (zero LLM, no new guessing — SPEC §4), and classifies the gap against the
current atlas (`data/firmware/`, `data/recipes/` — the same ground truth `tools.py` already
reads) into one of UNCOVERED / RANKS_POORLY / COVERED_OK / UNRESOLVED.

**READ-ONLY.** This module never authors a record, opens a PR, or touches `main`. It writes
a git-tracked snapshot (`docs/demand/<date>.json`) and a Telegram digest — that's it. See
SPEC §12 Phase 1.

The only network-touching function is `_pull_live()` — every other function in this module
is a pure function over plain dicts/lists, so `test_demand.py` runs entirely offline.

Run with the composio venv:  ~/.composio-venv/bin/python demand.py
"""
from __future__ import annotations
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import notify  # stdlib-only
import tools
from capability_map import capabilities_from_text
from device_map import device_from_text

JR_DIR = Path(__file__).resolve().parent
REPO = JR_DIR.parent
DEMAND_DIR = REPO / "docs" / "demand"

# ─────────────────────────── versioned constants (SPEC §3) ───────────────────────────
WEIGHT_FORMULA_VERSION = "v1"
WINDOW_DAYS = 28                        # §3.1 / ⟨Q6⟩ — wider than the digest's 7d, beats k-anonymity
MIN_IMPRESSIONS = 10                    # D1/D4 floor — rows below this are statistically thin (§3.3)
MIN_EVENTS = 5                          # D2/D3 floor
FIRST_PARTY_WEIGHT_MULTIPLIER = 2.0     # D2/D3 = purest intent, weighted above D1/D4 (§3.6)
ZERO_RESULT_MULTIPLIER = 1.5            # a first-party search that returned NOTHING is the strongest signal

# RANKS_POORLY thresholds (§4) — "high-impression + low-CTR + weak-position" made concrete
RANKS_POORLY_MIN_IMPRESSIONS = 50
RANKS_POORLY_MAX_CTR = 0.02
RANKS_POORLY_MIN_POSITION = 15.0

GAP_UNCOVERED = "UNCOVERED"
GAP_RANKS_POORLY = "RANKS_POORLY"
GAP_COVERED_OK = "COVERED_OK"
GAP_UNRESOLVED = "UNRESOLVED"

# generic words that are never themselves a firmware identity — excluded from firmware-token
# matching so e.g. "esp32" doesn't false-match every catalogued id that happens to start with it
_STOPWORDS = {"esp32", "esp", "firmware", "board", "device", "for", "the", "and", "on", "with", "a"}
_WS_RE = re.compile(r"\s+")
_TOKEN_RE = re.compile(r"[a-z0-9]+")


# ═══════════════════════════ normalize / tokenize ═══════════════════════════

def normalize_term(text: str | None) -> str:
    """Lowercase, strip, collapse whitespace — the one normalization every term goes through
    before anything else (§3.4). Device-alias canonicalization happens implicitly via
    `resolve_entity()` + entity-keyed dedup (§4), not by rewriting the text here."""
    return _WS_RE.sub(" ", (text or "").strip().lower())


def _words(term: str) -> list[str]:
    """Deduped tokens of a normalized term, in first-seen order (deterministic matching)."""
    return list(dict.fromkeys(_TOKEN_RE.findall(term)))


# ═══════════════════════════ entity resolution (SPEC §4) ═══════════════════════════

def _firmware_id_parts(fid: str) -> list[str]:
    return [p for p in re.split(r"[-_]", fid) if len(p) >= 4]


def _firmware_token_match(words: list[str], firmware_ids: set[str]) -> str | None:
    """First word (>=4 chars, not a stopword) that identifies a catalogued firmware id, tried in
    two tiers per id: (1) EXACT match against one of the id's `-`/`_`-separated parts (>=4
    chars) — e.g. word 'nemo' == a part of 'm5stick-nemo'. (2) substring match against the
    WHOLE id, but ONLY when that id has no separator to split on at all (e.g. word 'marauder'
    in the fused id 'esp32marauder', which can't be tokenized any finer). Tier 2 deliberately
    does NOT apply to hyphenated ids: without it, a generic board-name fragment like 'stick'
    (part of the word 'm5stick' but not equal to it) would substring-match 'm5stick-nemo' and
    misresolve an unrelated board query (e.g. 'm5 stick s3') to the nemo firmware — a real
    false positive caught running this miner live against esp-atlas.com's actual GSC data.
    Matches ONLY against ALREADY-catalogued ids: this is a parser over the existing atlas,
    never a guess at a firmware that doesn't exist yet (that's exactly why a genuinely-new
    firmware name can only ever land in UNRESOLVED in Phase 1 — see classify_gap's docstring)."""
    ids_sorted = sorted(firmware_ids)
    for word in words:
        if len(word) < 4 or word in _STOPWORDS:
            continue
        for fid in ids_sorted:
            if word in _firmware_id_parts(fid):
                return fid
            if "-" not in fid and "_" not in fid and word in fid:
                return fid
    return None


def _chip_from_term(term: str) -> str | None:
    """A specific ESP32 chip-family token named in the term (e.g. 'esp32-c6'), reusing the same
    regex the scorer already trusts (`tools._page_chip_families`). A bare 'esp32' mention with
    no specific variant present is still reported (generic chip interest), lowest priority."""
    families = tools._page_chip_families(term)
    if not families:
        return None
    specific = families - {"esp32"}
    if specific:
        return sorted(specific)[0]
    return "esp32" if "esp32" in families else None


def resolve_entity(term: str, firmware_ids: set[str]) -> dict:
    """Term -> entity candidates, PARSING ONLY via the scorer's existing maps (§4.1): no new
    intelligence, no LLM. `board` via `device_map.device_from_text` (only ever a catalogued
    board id, by construction). `chip` from the board's ground-truth soc if a board matched,
    else any specific chip family named directly in the term. `firmware_token` via substring
    match against catalogued firmware ids. `capability` via `capability_map`'s controlled
    vocabulary. Any of these may be None/[] — the caller decides what that means (classify_gap)."""
    board = device_from_text(term)
    chip = tools.board_soc(board) if board else _chip_from_term(term)
    firmware_token = _firmware_token_match(_words(term), firmware_ids)
    capability = capabilities_from_text(term)
    return {"board": board, "chip": chip, "firmware_token": firmware_token, "capability": capability}


def _dedup_key(term: str, resolved: dict) -> tuple:
    """Merge key for §3.5 dedup — SAME resolved entity, however it was worded, becomes ONE
    item. Only `firmware_token`/`board` are concrete enough entities to merge different wordings
    on (a shared bare `chip` token is NOT — two otherwise-unrelated terms that both merely
    mention 'esp32' must stay separate items, not collapse into one bucket). Falls back to the
    normalized term itself in every other case (nothing to merge on but the exact text)."""
    if resolved.get("firmware_token"):
        return ("fw", resolved["firmware_token"], resolved.get("board") or "")
    if resolved.get("board"):
        return ("board", resolved["board"])
    return ("term", term)


def _recipe_pairs() -> set[str]:
    """`{board}__{firmware}` dir names under data/recipes/ — the ground truth for 'does this
    board×firmware pairing already exist' (§4's UNCOVERED-via-board-gap case)."""
    d = REPO / "data" / "recipes"
    return {p.name for p in d.iterdir() if p.is_dir()} if d.exists() else set()


def _rank_or_covered(metrics: dict) -> str:
    imp = metrics.get("impressions") or 0
    ctr = metrics.get("ctr")
    pos = metrics.get("position")
    if (imp >= RANKS_POORLY_MIN_IMPRESSIONS and ctr is not None and ctr <= RANKS_POORLY_MAX_CTR
            and pos is not None and pos >= RANKS_POORLY_MIN_POSITION):
        return GAP_RANKS_POORLY
    return GAP_COVERED_OK


def classify_gap(resolved: dict, firmware_ids: set[str], recipe_pairs: set[str], metrics: dict) -> str:
    """§4 gap classification — the crux of the miner.

    A `firmware_token` is the required anchor for anything but UNRESOLVED: with zero-LLM,
    reuse-only resolution, `board`/`chip`/`capability` alone never identify a SPECIFIC missing
    catalog entity (a board-only match is by construction an ALREADY-catalogued board —
    device_map only maps to those — so it can't signal a gap; a bare chip or capability token
    is too generic to say what's missing). Those partial-signal terms are exactly what §4 means
    by UNRESOLVED: "high-volume unresolved clusters are a signal to Felipe" for possible new
    categories, never an authoring target.

    Given a `firmware_token`:
    - not in `firmware_ids` -> UNCOVERED (defensive: in the live pipeline the token universe
      IS `firmware_ids`, so this can't fire today, but classify_gap is a pure function tested
      on its own contract, not just the live pipeline's reachable paths).
    - `board` given and `{board}__{firmware_token}` has no recipe -> UNCOVERED (the firmware is
      catalogued, but not for this board — a genuine populate/pairing gap, §6).
    - otherwise the entity already exists -> RANKS_POORLY or COVERED_OK by the D1 metrics
      (§4's high-impression/low-CTR/weak-position test, `_rank_or_covered`)."""
    firmware_token = resolved.get("firmware_token")
    if not firmware_token:
        return GAP_UNRESOLVED
    if firmware_token not in firmware_ids:
        return GAP_UNCOVERED
    board = resolved.get("board")
    if board and f"{board}__{firmware_token}" not in recipe_pairs:
        return GAP_UNCOVERED
    return _rank_or_covered(metrics)


# ═══════════════════════════ weight (SPEC §3.6) — pure, versioned ═══════════════════════════

def position_penalty(position: float | None) -> float:
    """Worse (higher) position -> bigger multiplier, i.e. impressions we rank badly for count
    more toward demand weight. v1: linear, position/10, clamped to [1, 100] so a missing or
    wild position never zeroes out or blows up the score."""
    if position is None:
        return 1.0
    return min(max(position, 1.0), 100.0) / 10.0


def gsc_weight(impressions: int, clicks: int, ctr: float | None, position: float | None) -> float:
    """impressions * (1 - ctr) * position_penalty(position) — high impressions we're NOT
    capturing (low ctr) at a bad rank count the most (§3.6)."""
    if not impressions:
        return 0.0
    if ctr is None:
        ctr = (clicks / impressions) if impressions else 0.0
    return impressions * (1 - ctr) * position_penalty(position)


def firstparty_weight(events: int, zero_result: bool) -> float:
    """First-party (D2/D3) demand is purest intent — weighted above D1/D4 (§3.6); a zero-result
    site search is the single strongest catalog-gap signal available, weighted higher still."""
    if not events:
        return 0.0
    return events * FIRST_PARTY_WEIGHT_MULTIPLIER * (ZERO_RESULT_MULTIPLIER if zero_result else 1.0)


# ═══════════════════════════ row parsing (raw Composio shapes -> plain rows) ═══════════════════════════

def _parse_gsc_rows(rows: list[dict], has_page: bool) -> list[dict]:
    """Raw `GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS_QUERY` rows -> plain dicts. `has_page`
    selects D1 (`dimensions=['query']`) vs D4 (`dimensions=['query','page']`) key shape."""
    out = []
    for r in rows or []:
        keys = r.get("keys") or []
        if not keys:
            continue
        raw_query = keys[0]
        term = normalize_term(raw_query)
        if not term:
            continue
        page = keys[1] if has_page and len(keys) > 1 else None
        out.append({
            "raw_term": raw_query, "term": term, "page": page,
            "impressions": int(r.get("impressions") or 0),
            "clicks": int(r.get("clicks") or 0),
            "ctr": r.get("ctr"),
            "position": r.get("position"),
        })
    return out


def parse_ga4_searchterm_rows(raw_rows: list[dict]) -> tuple[list[dict], bool]:
    """Raw `GOOGLE_ANALYTICS_RUN_REPORT` (dim `searchTerm`, metric `eventCount`) rows -> plain
    dicts + a `d2_available` flag. **KNOWN ISSUE (SPEC ⟨Q1⟩ resolved 2026-08-31):** the
    `searchTerm` dimension value currently comes back EMPTY upstream (term-capture not
    configured — a site-code fix, not Jr's). Rows with a blank/whitespace-only term are
    dropped, never raised; if EVERY row is blank (today's live reality) or there are no rows at
    all, `d2_available` is False and the miner runs on D1/D4 only (§8: 'no silent degradation')."""
    parsed = []
    for r in raw_rows or []:
        dims = r.get("dimensionValues") or []
        raw_term = (dims[0].get("value") if dims else "") or ""
        term = normalize_term(raw_term)
        if not term:
            continue
        metrics = r.get("metricValues") or []
        try:
            events = int(float((metrics[0] or {}).get("value", 0))) if metrics else 0
        except (TypeError, ValueError):
            events = 0
        parsed.append({"term": term, "events": events, "zero_result": bool(r.get("zero_result"))})
    return parsed, bool(parsed)


def _floor_filter_impressions(rows: list[dict], min_impressions: int = MIN_IMPRESSIONS) -> list[dict]:
    return [r for r in rows if r["impressions"] >= min_impressions]


def _floor_filter_events(rows: list[dict], min_events: int = MIN_EVENTS) -> list[dict]:
    return [r for r in rows if r["events"] >= min_events]


def _landing_pages_by_term(d4_rows: list[dict]) -> dict[str, str]:
    """Per normalized term, the D4 page with the most impressions — the 'which page does this
    query already land on' signal (§4)."""
    best: dict[str, tuple[str, int]] = {}
    for row in d4_rows:
        term, page, imp = row["term"], row["page"], row["impressions"]
        if not page:
            continue
        if term not in best or imp > best[term][1]:
            best[term] = (page, imp)
    return {term: page for term, (page, _imp) in best.items()}


# ═══════════════════════════ the pure pipeline ═══════════════════════════

def _new_group(resolved: dict) -> dict:
    return {"resolved": resolved, "raw_terms": set(), "source": set(),
            "impressions": 0, "clicks": 0, "_pos_weighted": 0.0, "events": 0,
            "zero_result": False, "landing_page": None, "display_term": None}


def build_demand_items(
    gsc_query_rows: list[dict],
    gsc_query_page_rows: list[dict] | None = None,
    ga4_searchterm_raw_rows: list[dict] | None = None,
    firmware_ids: set[str] | None = None,
    recipe_pairs: set[str] | None = None,
    today: str | None = None,
    prior_first_seen: dict[str, str] | None = None,
) -> list[dict]:
    """The pure miner (§3): normalize -> floor-filter -> resolve -> dedup/merge -> weight ->
    classify -> emit a ranked `List[DemandItem]` (schema §9), NO network. `gsc_query_rows` /
    `gsc_query_page_rows` / `ga4_searchterm_raw_rows` are the raw Composio row shapes (see
    `_pull_live`) — pass realistic fixtures here for offline testing."""
    firmware_ids = firmware_ids if firmware_ids is not None else set()
    recipe_pairs = recipe_pairs if recipe_pairs is not None else set()
    today = today or dt.date.today().isoformat()
    prior_first_seen = prior_first_seen or {}

    d1_rows = _floor_filter_impressions(_parse_gsc_rows(gsc_query_rows or [], has_page=False))
    d4_rows = _parse_gsc_rows(gsc_query_page_rows or [], has_page=True)
    landing_pages = _landing_pages_by_term(d4_rows)

    ga4_parsed, _d2_available = parse_ga4_searchterm_rows(ga4_searchterm_raw_rows or [])
    ga4_parsed = _floor_filter_events(ga4_parsed)

    groups: dict[tuple, dict] = {}

    for row in d1_rows:
        resolved = resolve_entity(row["term"], firmware_ids)
        key = _dedup_key(row["term"], resolved)
        g = groups.setdefault(key, _new_group(resolved))
        g["raw_terms"].add(row["raw_term"])
        g["source"].add("gsc_query")
        g["impressions"] += row["impressions"]
        g["clicks"] += row["clicks"]
        g["_pos_weighted"] += (row["position"] or 0) * row["impressions"]
        g["display_term"] = g["display_term"] or row["term"]
        page = landing_pages.get(row["term"])
        if page:
            g["landing_page"] = page

    for row in ga4_parsed:
        resolved = resolve_entity(row["term"], firmware_ids)
        key = _dedup_key(row["term"], resolved)
        g = groups.setdefault(key, _new_group(resolved))
        g["raw_terms"].add(row["term"])
        g["source"].add("ga4_sitesearch")
        g["events"] += row["events"]
        g["zero_result"] = g["zero_result"] or bool(row.get("zero_result"))
        g["display_term"] = g["display_term"] or row["term"]

    items = []
    for g in groups.values():
        impressions, clicks = g["impressions"], g["clicks"]
        ctr = round(clicks / impressions, 4) if impressions else None
        position = round(g["_pos_weighted"] / impressions, 1) if impressions else None
        events = g["events"]
        weight = round(
            gsc_weight(impressions, clicks, ctr, position) + firstparty_weight(events, g["zero_result"]), 2)
        gap = classify_gap(g["resolved"], firmware_ids, recipe_pairs,
                           {"impressions": impressions, "ctr": ctr, "position": position})
        term = g["display_term"]
        resolved_out = g["resolved"] if any(g["resolved"].values()) else None
        items.append({
            "term": term,
            "raw_terms": sorted(g["raw_terms"]),
            "source": sorted(g["source"]),
            "impressions": impressions or None, "clicks": clicks or None, "ctr": ctr, "position": position,
            "events": events or None, "zero_result": g["zero_result"] if events else None,
            "weight": weight,
            "resolved": resolved_out,
            "gap": gap,
            "landing_page": g["landing_page"],
            "first_seen": prior_first_seen.get(term, today),
            "last_seen": today,
        })
    items.sort(key=lambda it: it["weight"], reverse=True)
    return items


# ═══════════════════════════ the ONE network-touching function ═══════════════════════════

def _pull_live(days: int = WINDOW_DAYS) -> dict:
    """Pulls D1/D4 (GSC) and attempts D2 (GA4 searchTerm) via **Composio**, reusing
    `telemetry.py`'s auth VERBATIM (same `KEY`/`ENTITY`/`GA4_PROPERTY`/`GSC_SITE`, same `_ex()`
    executor — not forked). This is the ONLY function in this module that touches the network;
    everything else (`build_demand_items` and everything it calls) is pure. Imported lazily so
    importing `demand.py` never requires a composio key/package to be present (keeps
    `test_demand.py` fully offline, per SPEC Phase 1)."""
    import telemetry

    end = dt.date.today()
    start = end - dt.timedelta(days=days)
    S, E = start.isoformat(), end.isoformat()

    gsc_query = telemetry._ex("GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS_QUERY",
        {"siteUrl": telemetry.GSC_SITE, "startDate": S, "endDate": E,
         "dimensions": ["query"], "rowLimit": 500})
    gsc_query_page = telemetry._ex("GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS_QUERY",
        {"siteUrl": telemetry.GSC_SITE, "startDate": S, "endDate": E,
         "dimensions": ["query", "page"], "rowLimit": 500})
    ga4_searchterm = telemetry._ex("GOOGLE_ANALYTICS_RUN_REPORT",
        {"property": telemetry.GA4_PROPERTY, "dateRanges": [{"startDate": S, "endDate": E}],
         "dimensions": [{"name": "searchTerm"}], "metrics": [{"name": "eventCount"}]})

    return {
        "window": {"start": S, "end": E},
        "gsc_query_rows": (gsc_query or {}).get("rows") or [],
        "gsc_query_page_rows": (gsc_query_page or {}).get("rows") or [],
        "ga4_searchterm_raw_rows": (ga4_searchterm or {}).get("rows") or [],
    }


# ═══════════════════════════ snapshot + digest (SPEC §9 / §12) ═══════════════════════════

def _latest_prior_snapshot(demand_dir: Path = DEMAND_DIR) -> list[dict]:
    """The most recent dated snapshot's items (for carrying `first_seen` forward), or []."""
    if not demand_dir.exists():
        return []
    files = sorted(p for p in demand_dir.glob("*.json") if p.stem != "unresolved")
    if not files:
        return []
    try:
        data = json.loads(files[-1].read_text())
    except Exception:
        return []
    return data.get("items") or []


def _prior_first_seen_map(prior_items: list[dict]) -> dict[str, str]:
    return {it["term"]: it["first_seen"] for it in prior_items if it.get("term") and it.get("first_seen")}


def write_snapshot(items: list[dict], d2_available: bool, window: dict,
                   today: str | None = None, demand_dir: Path = DEMAND_DIR) -> Path:
    """Git-tracked, auditable, diffable — `docs/demand/<date>.json` (§9)."""
    today = today or dt.date.today().isoformat()
    demand_dir.mkdir(parents=True, exist_ok=True)
    path = demand_dir / f"{today}.json"
    payload = {
        "date": today, "window": window, "weight_formula_version": WEIGHT_FORMULA_VERSION,
        "d2_available": d2_available, "count": len(items), "items": items,
    }
    path.write_text(json.dumps(payload, indent=1))
    return path


def write_unresolved(items: list[dict], demand_dir: Path = DEMAND_DIR) -> Path:
    """`docs/demand/unresolved.json` — high-volume UNRESOLVED clusters for Felipe, a review
    list (§4/§9). Never an authoring input."""
    unresolved = sorted((it for it in items if it["gap"] == GAP_UNRESOLVED),
                        key=lambda it: it["weight"], reverse=True)
    demand_dir.mkdir(parents=True, exist_ok=True)
    path = demand_dir / "unresolved.json"
    path.write_text(json.dumps({"count": len(unresolved), "items": unresolved}, indent=1))
    return path


_GAP_EMOJI = {GAP_UNCOVERED: "🆕", GAP_RANKS_POORLY: "📉", GAP_COVERED_OK: "✅", GAP_UNRESOLVED: "❓"}


def build_digest(items: list[dict], d2_available: bool, window: dict, top_n: int = 10) -> str:
    """The Telegram digest (§12 Phase 1: 'ship the ranked demand snapshot to Telegram for
    Felipe to eyeball vs reality'). Surfaces top demand + gap labels + the D2-blind note.

    Gap labels (`RANKS_POORLY`, `COVERED_OK`, ...) are ALWAYS wrapped in backticks: Telegram's
    legacy Markdown `parse_mode` treats a bare `_` as an (un-escaped, unmatched) italic
    delimiter, so a raw 'RANKS_POORLY' in the message text 400s the whole send — caught by
    actually sending a live digest, not just by the offline tests. Inside a code span the
    parser doesn't look for formatting characters at all, so this is the fix, not an escape
    hack."""
    uncovered = [it for it in items if it["gap"] == GAP_UNCOVERED]
    ranks_poorly = [it for it in items if it["gap"] == GAP_RANKS_POORLY]
    unresolved = [it for it in items if it["gap"] == GAP_UNRESOLVED]

    lines = [
        f"🎯 *Jr — demand mine* (read-only, Phase 1) · {window.get('start')}→{window.get('end')}",
        f"📊 {len(items)} demand items · {len(uncovered)} `{GAP_UNCOVERED}` · "
        f"{len(ranks_poorly)} `{GAP_RANKS_POORLY}` (report) · {len(unresolved)} `{GAP_UNRESOLVED}`",
        "",
        "*Top demand* (ranked by weight):",
    ]
    for it in items[:top_n]:
        bits = [f"w={it['weight']}", f"`{it['gap']}`"]
        if it.get("impressions"):
            bits.append(f"imp {it['impressions']}")
        if it.get("events"):
            bits.append(f"events {it['events']}")
        lines.append(f"  {_GAP_EMOJI[it['gap']]} `{it['term']}` — " + " · ".join(bits))

    if ranks_poorly:
        lines += ["", f"*`{GAP_RANKS_POORLY}` — report for Felipe+us (content/SEO, never Jr's authoring path):*"]
        for it in ranks_poorly[:5]:
            lines.append(f"  📉 `{it['term']}` — imp {it['impressions']}, ctr {it['ctr']}, pos {it['position']}")

    lines.append("")
    lines.append("🔴 D2 blind: term-capture off (GA4 searchTerm empty upstream — site-code fix, ⟨Q1⟩)"
                if not d2_available else "🟢 D2 live: first-party site-search terms captured")
    return "\n".join(lines)


# ═══════════════════════════ orchestrator (READ-ONLY) ═══════════════════════════

def mine(days: int = WINDOW_DAYS, send_telegram: bool = True, demand_dir: Path = DEMAND_DIR) -> dict:
    """Pull -> build -> write snapshot -> digest. **READ-ONLY** — no authoring, no PRs, no
    catalog writes (SPEC §12 Phase 1). Does not touch `jr-daily` or `jr/scorer.py`."""
    live = _pull_live(days)
    firmware_ids = tools.catalogued_firmware_ids()
    recipe_pairs = _recipe_pairs()
    today = dt.date.today().isoformat()
    prior_first_seen = _prior_first_seen_map(_latest_prior_snapshot(demand_dir))

    ga4_raw = live["ga4_searchterm_raw_rows"]
    _, d2_available = parse_ga4_searchterm_rows(ga4_raw)

    items = build_demand_items(
        live["gsc_query_rows"], live["gsc_query_page_rows"], ga4_raw,
        firmware_ids=firmware_ids, recipe_pairs=recipe_pairs,
        today=today, prior_first_seen=prior_first_seen,
    )
    write_snapshot(items, d2_available, live["window"], today, demand_dir)
    write_unresolved(items, demand_dir)
    digest = build_digest(items, d2_available, live["window"])
    if send_telegram:
        notify.send_telegram(digest)
    return {"items": items, "digest": digest, "d2_available": d2_available}


if __name__ == "__main__":
    result = mine()
    print(result["digest"])
