# SPEC — Analytics Crossing 🔀 (GA4 × Search Console, joined on landing page)

> Status: **DRAFT — implemented, first cut (2026-09-27).** Extends `jr/telemetry.py`
> (§3d growth telemetry). Depends on the same Composio OAuth calling convention
> `telemetry.py` already uses — no new credentials, no new pip deps.

---

## 0. The gap this closes

`jr/telemetry.py` reports GA4 and GSC as two disconnected numbers: "X users this week" and
"Y search impressions this week." Neither tells Jr **which page** a search query landed on,
nor **what that visitor did next**. Today's telemetry cannot answer the one question that
actually drives the 1,000,000-user north-star:

> For query Q, which lands on page P — did the visitor convert, or did P leak them?

This module (`jr/analytics_cross.py`) joins GA4 pagePath data with GSC page data **on the
landing page URL** to expose the acquisition → activation funnel: **query → page →
conversion**, per page, with the page's top queries attached.

---

## 1. Data sources (reuse `jr/telemetry.py`'s Composio convention EXACTLY)

Same `_ex()` helper, same `GA4_PROPERTY`, `GSC_SITE`, `ENTITY`, `~/.composio-venv` OAuth —
no new auth path. Four calls, all read-only, all already-authorized scopes:

| # | Source | Composio slug | Dimensions | Metrics |
|---|--------|---------------|------------|---------|
| 1 | GA4 | `GOOGLE_ANALYTICS_RUN_REPORT` | `pagePath` | `screenPageViews`, `activeUsers`, `sessions` |
| 2 | GA4 | `GOOGLE_ANALYTICS_RUN_REPORT` | `pagePath`, `eventName` | `eventCount` |
| 3 | GSC | `GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS_QUERY` | `page` | (clicks/impressions/ctr/position are always returned) |
| 4 | GSC | `GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS_QUERY` | `query`, `page` | (same) |

Pull #2 is filtered (client-side, after the call) to the three activation-funnel event
names confirmed live in `apps/web/lib/analytics.ts` / `PartViewTracker.tsx` /
`FirmwareViewTracker.tsx` / `FlashAction.tsx` / GA4 enhanced measurement:

- `page_view` — GA4's own auto-collected enhanced-measurement event (not a custom
  `track()` call; esp-atlas never disables enhanced measurement, so every pagePath in
  pull #1 already implies a `page_view`). Modeled here as `screenPageViews` from pull #1
  rather than re-derived from pull #2, since GA4 does not reliably let a `RUN_REPORT`
  dimension-filter isolate `page_view` from other auto events in the same report.
- `part_view` — fired by `PartViewTracker`/`FirmwareViewTracker` on board/firmware detail
  pages. Real event name, confirmed in source, not assumed.
- `flash_open` — fired by `FlashAction.open()` when the Flash Wizard panel expands. Real
  event name, confirmed in source, not assumed.

**Network fetch layer is thin and untested-by-oracle on purpose**: `fetch_ga_pages()`,
`fetch_ga_events()`, `fetch_gsc_pages()`, `fetch_gsc_queries()` each wrap one `_ex()` call
and return its raw `rows` (or `None` on failure). All join/scoring logic lives in the pure
function below, which is what the golden-oracle tests exercise.

---

## 2. The `FunnelTable` shape

```python
FunnelRow = {
    "page": str,                       # GA4 pagePath, e.g. "/firmware/minigotchi-esp32"
    "impressions": int | None,         # GSC. None only if the GSC page axis is UNAVAILABLE
                                        # (fetch failed); 0 if the axis loaded but this page
                                        # had no matching row (a real, reportable zero).
    "clicks": int | None,              # same None-vs-0 rule as impressions
    "ctr": float | None,               # 0..1, GSC's own ctr. None only if axis unavailable
                                        # OR the page has no GSC row (ctr is undefined at 0 impressions)
    "avg_position": float | None,      # None only if axis unavailable or page has no GSC row
    "page_views": int | None,          # GA4 screenPageViews. None only if the GA4 page axis
                                        # is UNAVAILABLE; 0 if loaded but this page had no row.
    "active_users": int | None,        # same None-vs-0 rule as page_views
    "sessions": int | None,            # same None-vs-0 rule as page_views
    "part_view": int | None,           # GA4 eventCount for part_view. None only if the GA4
                                        # events axis is UNAVAILABLE; 0 if loaded but this
                                        # page/event combo had no row (GA4 omits zero-count rows).
    "flash_open": int | None,          # same None-vs-0 rule as part_view
    "conv_view_to_part": float | None, # part_view / page_views. None if either is None
                                        # (axis unavailable) or page_views == 0 (undefined rate).
                                        # 0.0 is a valid, real value (page_views > 0, part_view == 0).
    "conv_part_to_flash": float | None,# flash_open / part_view, same None-vs-0.0 rule
    "top_queries": list[{"query": str, "impressions": int, "clicks": int, "position": float}],
    "demand": None,                    # RESERVED for a future Google Trends axis (§7) — always None today
    "striking_distance": bool,         # True if ANY attributed query has 8 <= avg_position <= 20 and impressions > 0
    "leak_flag": bool,                 # True if demand+rank are healthy but conversion is weak (§5)
}

FunnelTable = {
    "rows": list[FunnelRow],           # sorted by (impressions if not None else -1) desc,
                                        # tie-broken by (page_views if not None else -1) desc —
                                        # deterministic even when one or both axes are unavailable
    "unavailable": list[str],          # subset of {"ga_pages", "ga_events", "gsc_pages", "gsc_queries"} — which source axes failed
    "generated_from": {                # echoes what was actually joined, for debugging degraded runs
        "ga_pages": int,               # row count consumed, 0 if unavailable
        "ga_events": int,
        "gsc_pages": int,
        "gsc_queries": int,
    },
}
```

A page appears in `rows` if it exists in **either** the GA4 page axis or the GSC page axis
(union, not intersection) — a page that ranks in Google but has zero GA4 traffic, and a
page GA4 sees but Search Console has never indexed, are both real states Jr needs to see,
not silently dropped.

---

## 3. Page-URL normalization contract (the tricky correctness bit)

GSC returns **absolute URLs** (`https://esp-atlas.com/firmware/minigotchi-esp32?ref=x`);
GA4 returns **paths** (`/firmware/minigotchi-esp32`). The join key is the normalized path.
`normalize_page(url_or_path: str) -> str` applies, in order:

1. If the value is an absolute URL (has a scheme), strip scheme + host, keep path + query.
2. Drop the query string and fragment entirely (`?utm_source=...`, `#section`) — GA4's
   `pagePath` dimension does the same by default for this property.
3. Percent-decode the path (`%20` → space, `%2D` → `-`, etc.) via `urllib.parse.unquote`.
4. Strip a single trailing slash, UNLESS the path is exactly `/` (the home page keeps its
   slash).
5. Collapse to lowercase is **NOT** applied — esp-atlas paths are already lowercase-slug by
   convention and GA4/GSC both preserve case; forcing lowercase would hide a real
   case-mismatch bug instead of surfacing it.

Edge cases explicitly under test (`test_analytics_cross.py`):
- `/firmware/minigotchi-esp32/` (GSC, trailing slash) joins `/firmware/minigotchi-esp32`
  (GA4, no trailing slash).
- `https://esp-atlas.com/firmware/area512?ref=hn` (GSC, query string) joins
  `/firmware/area512` (GA4).
- `https://esp-atlas.com/parts/m5cardputer%2Dv2` (GSC, percent-encoded) joins
  `/parts/m5cardputer-v2` (GA4).
- A GSC page with no GA4 counterpart at all (e.g. a page GA4 never saw, or GA4 data still
  processing) → row emitted with `page_views`/`active_users`/`sessions`/`part_view`/
  `flash_open`/conversion rates all `None`, GSC fields populated.
- A GA4 page with no GSC counterpart (never indexed, or zero-impression) → row emitted with
  `impressions`/`clicks`/`ctr`/`avg_position`/`top_queries` all `None`/`[]`, GA4 fields
  populated.
- Root path `/` never gets its trailing slash stripped into empty string.

---

## 4. Per-page metrics

- `page_views`, `active_users`, `sessions` — from GA4 pull #1, keyed by normalized
  `pagePath`; `0` for a page present in the axis but absent from pull #1's rows, `None` for
  every page if pull #1 itself is unavailable.
- `part_view`, `flash_open` — GA4 pull #2 filtered to those two `eventName` values, keyed by
  normalized `pagePath`; `eventCount` summed if a page/event pair somehow repeats (defensive,
  GA4 report rows are already unique per dimension combo); same 0-vs-None rule as above,
  keyed off pull #2's availability.
- `impressions`, `clicks` — from GSC pull #3, keyed by normalized `page`; same 0-vs-None
  rule, keyed off pull #3's availability. `ctr`, `avg_position` are `None` whenever the page
  has no GSC row at all (undefined, not zero) even if the axis itself is available.
- `conv_view_to_part = part_view / page_views` when both are non-`None` and `page_views > 0`;
  `None` if either side is `None` (axis unavailable) or `page_views == 0` (rate undefined,
  never divide by zero). `part_view == 0` with `page_views > 0` is a real `0.0`, not `None`.
- `conv_part_to_flash = flash_open / part_view`, same rule against `part_view`.
- `top_queries` — every GSC pull #4 row whose normalized `page` matches this row's page,
  sorted by `impressions` desc, capped at 10.

---

## 5. Flags

- **`striking_distance`** — `True` if any of the page's `top_queries` has
  `8 <= avg_position <= 20` and `impressions > 0` (Jr's classic "one push from page 1" SEO
  signal — reused verbatim from the position band `SPEC-jr-demand-driven.md` already treats
  as actionable).
- **`leak_flag`** — `True` if the page has **healthy demand+rank** (`impressions` is present
  and `>= 10`, and `avg_position` is present and `<= 20`) **but** `conv_view_to_part` is
  present and `< 0.05` (fewer than 1 in 20 visitors even opens the part view) — i.e. Google
  is sending qualified traffic and the page is losing it. Both `impressions`/`avg_position`
  and `conv_view_to_part` must be non-`None` to raise this flag; a page missing either axis
  is not flagged (§6 graceful degradation — no flag fabricated from partial data).

---

## 6. Graceful degradation contract

Each of the four source calls (`fetch_ga_pages`, `fetch_ga_events`, `fetch_gsc_pages`,
`fetch_gsc_queries`) can fail independently (quota, transient API error, `_ex()` returning
`None`). `build_funnel()` never raises on a missing/`None`/empty input for any single axis:

- The failing axis's name is added to `FunnelTable["unavailable"]`.
- Every row's fields sourced from that UNAVAILABLE axis are `None` (numeric fields) or `[]`
  (`top_queries`), never fabricated, never defaulted to `0`. (An *available* axis that
  simply has no row for a given page still yields a real `0` — see §2/§4 — that is not
  degradation, that is a fact.)
- Conversion rates that need a `None` field are `None`, not skipped-with-an-exception.
- Flags (`striking_distance`, `leak_flag`) default to `False` when the data needed to
  evaluate them is missing — a flag is a positive claim, and an unavailable axis cannot
  support one.
- If **all four** axes fail, `rows` is `[]` and `unavailable` lists all four — a valid,
  non-crashing empty table, not an exception.

`build_funnel()` takes already-fetched raw rows (`ga_pages`, `ga_events`, `gsc_pages`,
`gsc_queries` — each `None` or a `list[dict]` in the shape `_ex()` returns), so it is a pure,
network-free function with zero I/O — fully oracle-testable without mocking HTTP.

---

## 7. Reserved: future Google Trends axis

`FunnelRow["demand"]` is reserved for a future Google Trends interest-over-time score for
the page's top query (0–100 relative interest). **Not wired in this run** — Trends has no
Composio action today and pulling it needs a decision on keyword-vs-page granularity that's
out of scope here. The field exists now, always `None`, so the row shape doesn't change
(and downstream consumers don't need a migration) the day Trends is added.

---

## 8. Non-goals this run

- No Telegram digest / snapshot-writer wiring — `jr/telemetry.py`'s existing weekly digest
  is untouched. A future spec can fold `build_funnel()`'s output into it.
- No Google Trends call (§7).
- No persistence — `build_funnel()` returns a `FunnelTable` in memory; callers decide what
  to do with it.
