"""EspAtlas Jr — the tick's report (jr/report.py): one deterministic line, one PR body.

PLAN §3.2 step 11: every tick ends with ONE Telegram line, always — gauge, allocation, what was
admitted, rejects by reason, the PR link, the budget. And every tick PR carries a body that a
human can review without opening a diff. Both are rendered from the tick's own numbers, never
from a model: the Groq headline that jr/pr_summary.py could add is deliberately NOT used here
(deterministic where it matters; an LLM in the report path would make the tick's output
non-reproducible). pr_summary's deterministic pieces stay available for Phase 3 stages that
author firmware facts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class TickReport:
    """Everything the tick learned, in the order the report reads it out."""
    when: datetime
    dry_run: bool = False
    base_sha: str = ""
    boards_pct: float | None = None
    overall_pct: float | None = None
    allocation: str = ""
    stages: list = field(default_factory=list)        # [{"name", "paths", "summary", "needs_human"}]
    extra_paths: list = field(default_factory=list)    # tick-owned paths outside stages (data-trend snapshot)
    data_row: dict | None = None                       # SPEC-data-trend.md row for this tick
    data_delta: dict | None = None                     # its diff vs the prior day (None on first snapshot)
    demand_signal: dict | None = None                  # SPEC-demand-steering.md steer_signal (fresh snapshot only)
    alignment: dict | None = None                      # SPEC-demand-steering.md alignment (fresh snapshot only)
    demand_meta: dict | None = None                    # {"stale","age_days","date"} when a snapshot loaded, else None
    admitted: int = 0
    rejects: dict = field(default_factory=dict)       # reason -> count
    memory: dict = field(default_factory=dict)        # {"expired", "merged", "rejected", "removed"}
    hydrated: list = field(default_factory=list)       # firmware ids marked proposed from open Jr PRs at tick start
    revalidate: dict | None = None
    guard: dict | None = None                         # {"ok": bool, "output": str}
    publish: dict | None = None                       # PublishResult.as_dict()
    budget: str = ""
    warnings: list = field(default_factory=list)      # dry-run preflight notes, never fatal
    aborted: str = ""                                 # non-empty → the tick stopped early, why

    @property
    def paths(self) -> list[str]:
        out: list[str] = []
        for s in self.stages:
            for p in s.get("paths", []):
                if p not in out:
                    out.append(p)
        for p in self.extra_paths:
            if p not in out:
                out.append(p)
        return out

    @property
    def needs_human(self) -> bool:
        return any(s.get("needs_human") for s in self.stages)


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.1f}%"


def render_line(r: TickReport) -> str:
    """The one line. Telegram-friendly, no markdown tables, every field always present."""
    stamp = r.when.strftime("%Y-%m-%d %H:%M UTC")
    head = "jr-tick" + (" (dry-run)" if r.dry_run else "")
    if r.aborted:
        return f"🛑 {head} {stamp}: aborted — {r.aborted} · {r.budget}".rstrip(" ·")
    mem = r.memory or {}
    mem_txt = (f"memory expired {mem.get('expired', 0)} / merged {mem.get('merged', 0)} / "
               f"rejected {mem.get('rejected', 0)} / removed {mem.get('removed', 0)}")
    rej = ", ".join(f"{k} {v}" for k, v in sorted(r.rejects.items())) or "none"
    if r.publish and r.publish.get("published"):
        pr = r.publish.get("pr_url") or "(no url)"
        pr_txt = f"PR {pr}" + (" · auto-merge" if r.publish.get("auto_merge") else f" · {r.publish.get('reason') or 'human merge'}")
    elif r.publish:
        pr_txt = f"no PR ({r.publish.get('reason') or 'nothing to publish'})"
    elif r.paths:
        pr_txt = "no PR (dry-run)" if r.dry_run else "no PR"
    else:
        pr_txt = "nothing to do"
    guard_txt = "" if r.guard is None else (" · guard green" if r.guard.get("ok") else " · guard RED")
    reval = ""
    if r.revalidate:
        reval = " · revalidate " + ("ok" if r.revalidate.get("ok") else str(r.revalidate.get("status") or r.revalidate.get("skipped") or "failed"))
    warn = "".join(f" · ⚠ {w}" for w in r.warnings)
    stage_txt = "".join(f" · {s.get('name', 'stage')}: {s.get('summary', '')[:300]}" for s in r.stages if s.get("summary"))
    return (f"🤖 {head} {stamp}: boards {_pct(r.boards_pct)} (overall {_pct(r.overall_pct)}) · "
            f"{r.allocation or 'allocation n/a'} · admitted {r.admitted} · rejects {rej} · "
            f"{mem_txt}{guard_txt}{reval} · {pr_txt}{stage_txt}{warn} · {r.budget}").rstrip(" ·")


def _paren(value: str, delta, fmt) -> str:
    """`<value> (<±delta>)` when a baseline exists, else just `<value>`."""
    return value if delta is None else f"{value} ({fmt(delta)})"


def render_data_line(row: dict | None, delta: dict | None, demand: dict | None = None) -> str:
    """The ONE data-quality trend line for the PR body (SPEC-data-trend.md): finite %, the two
    lead board fields, firmware volume and compat density — each with its day-over-day delta when a
    baseline exists. Deterministic; read straight off the stored row+delta.

    `demand` (SPEC-demand-steering.md, fresh snapshot only) extends the line with the supply×demand
    alignment: `· demand: aligned XX% · N uncovered`."""
    if not row:
        return ""
    bf = row.get("board_fields", {})
    df = (delta or {}).get("board_fields", {})
    usb = bf.get("usb_serial", {}).get("count", 0)
    gs = bf.get("getting_started", {}).get("count", 0)
    sgn = lambda n: (f"+{n}" if n >= 0 else str(n))          # noqa: E731
    sgnf = lambda v, nd: (f"+{v:.{nd}f}" if v >= 0 else f"{v:.{nd}f}")  # noqa: E731
    parts = [
        "📊 data:",
        _paren(f"finite {row.get('finite_overall_pct', 0.0):g}%", (delta or {}).get("finite_overall_pct") if delta else None, lambda v: sgnf(v, 1)),
        "· " + _paren(f"usb_serial {usb}", df.get("usb_serial") if delta else None, sgn),
        "· " + _paren(f"gs {gs}", df.get("getting_started") if delta else None, sgn),
        "· " + _paren(f"firmware {row.get('firmware_count', 0)}", (delta or {}).get("firmware_count") if delta else None, sgn),
        "· " + _paren(f"compat {row.get('compat_density', 0.0):g}/bd", (delta or {}).get("compat_density") if delta else None, lambda v: sgnf(v, 2)),
    ]
    if demand:
        parts.append(f"· demand: aligned {demand.get('aligned_pct', 0)}% · {demand.get('uncovered', 0)} uncovered")
    return " ".join(parts)


def render_demand_section(r: "TickReport") -> list[str]:
    """The '### Demand alignment' section for the PR body (SPEC-demand-steering.md).

    A fresh snapshot renders the full section: the aligned-% headline, the UNCOVERED worklist
    (Jr's authoring path), and a SEPARATE RANKS_POORLY list clearly labelled as an SEO/human
    report that is NOT Jr's authoring path. A stale or missing snapshot renders ONE honest line
    instead — never a section, because the steer stood down."""
    meta = r.demand_meta
    align = r.alignment
    if align and meta and not meta.get("stale"):
        counts = align.get("counts", {})
        lines = ["### Demand alignment", ""]
        lines.append(
            f"Supply×demand: **aligned {align.get('aligned_pct', 0)}%** of demand weight · "
            f"{counts.get('UNCOVERED', 0)} uncovered · {counts.get('RANKS_POORLY', 0)} ranks-poorly (SEO) · "
            f"{counts.get('COVERED_OK', 0)} covered · snapshot {meta.get('date')} (age {meta.get('age_days')}d, "
            f"bias {(r.demand_signal or {}).get('bias', 0.0):+g})")
        lines.append("")
        worklist = [it for it in align.get("demanded_but_missing", []) if it.get("gap") == "UNCOVERED"]
        lines.append("**Demanded but missing — Jr worklist (UNCOVERED, the authoring path):**")
        if worklist:
            for it in worklist:
                res = it.get("resolved") or {}
                target = res.get("firmware_token") or res.get("part") or res.get("board") or res.get("chip") or "?"
                track = "B/firmware" if res.get("firmware_token") else "A/backfill"
                lines.append(f"- `{it.get('term')}` — w={it.get('weight')} · imp {it.get('impressions') or '?'} "
                             f"· → `{target}` (Track {track})")
        else:
            lines.append("- none")
        lines.append("")
        seo = (r.demand_signal or {}).get("ranks_poorly") \
            or [it for it in align.get("demanded_but_missing", []) if it.get("gap") == "RANKS_POORLY"]
        lines.append("**RANKS_POORLY (SEO — human, NOT Jr's authoring path):**")
        if seo:
            for it in seo[:5]:
                lines.append(f"- `{it.get('term')}` — imp {it.get('impressions') or '?'}, "
                             f"ctr {it.get('ctr')}, pos {it.get('position')}")
        else:
            lines.append("- none")
        lines.append("")
        return lines
    if meta and meta.get("stale"):
        return [f"_demand snapshot stale (age {meta.get('age_days')}d) — not steering_", ""]
    return ["_demand snapshot missing — not steering_", ""]


def _fmt_firmware_item(it: dict) -> list[str]:
    stars, forks = it.get("stars"), it.get("forks")
    pop = f"{stars if stars is not None else '?'} ★ / {forks if forks is not None else '?'} forks"
    out = [f"- **{it.get('name') or it.get('id')}** (`{it.get('id')}`) — {it.get('url')}",
           f"  - ✅ public GitHub repository, {'not a fork' if not it.get('fork') else 'a fork'}, "
           f"{'not archived' if not it.get('archived') else 'ARCHIVED'} · {pop} (floor: 25 stars or 25 forks)"
           + (f" · license {it['license']}" if it.get("license") else ""),
           "  - ✅ not already catalogued (repository, name tokens, repository id)",
           f"  - ✅ board `{it.get('board')}` ({it.get('chip')}): {it.get('evidence')} → recipe `{it.get('recipe')}`, status unverified",
           "  - ✅ schema-valid, cite-or-omit (guard green)"]
    if it.get("submission"):
        out.append(f"  - via submission #{it['submission']} (answered there)")
    if it.get("needs_human"):
        out.append("  - ⚠️ flagged needs-human: a person reviews before merge")
    return out


def _fmt_recipes_item(it: dict) -> list[str]:
    kinds = ", ".join(f"{k} {v}" for k, v in sorted((it.get("kinds") or {}).items(), key=lambda kv: (-kv[1], kv[0])))
    head = f"- **{it.get('firmware')}** — +{len(it.get('written') or [])} recipe(s)"
    if it.get("existing"):
        head += f", {it['existing']} existing kept"
    out = [head]
    for rid in it.get("written") or []:
        out.append(f"  - ✅ `{rid}` — board named in the repo's own build files, cited; status unverified")
    if it.get("socs_added"):
        out.append(f"  - ✅ socs widened: +{', '.join(it['socs_added'])} (cited)")
    out.append(f"  - evidence: {it.get('signals', 0)} signal(s){' — ' + kinds if kinds else ''}; {it.get('unresolved', 0)} token(s) name no catalogued board")
    for n in it.get("notes") or []:
        out.append(f"  - note: {n}")
    return out


def render_pr_body(r: TickReport) -> str:
    """The PR as a VERDICT a human can read top to bottom: what is proposed and which gates it
    passed (one checklist per record), what was skipped (counts only — the launcher backlog is
    hundreds of entries, remembered with TTLs, never listed), one summary line, and the raw
    stage log folded away for debugging. Deterministic; no model wrote any of it."""
    lines = [f"EspAtlas Jr tick — {r.when.strftime('%Y-%m-%d %H:%M UTC')}", ""]
    lines.append(f"Base `{r.base_sha or 'origin/main'}` · boards {_pct(r.boards_pct)} · overall {_pct(r.overall_pct)}"
                 + (f" · {r.allocation}" if r.allocation else ""))
    fresh_demand = r.alignment if (r.demand_meta and not r.demand_meta.get("stale")) else None
    data_line = render_data_line(r.data_row, r.data_delta, demand=fresh_demand)
    if data_line:
        lines.append(data_line)
    lines.append("")
    items = [(s.get("name"), it) for s in r.stages for it in (s.get("items") or [])]
    lines.append("### Proposed in this PR")
    if not items:
        lines.append("Nothing new — memory reconciliation only (the ledger records merges, vetoes and expiries).")
    n_records = n_recipes = 0
    for _stage, it in items:
        if it.get("kind") == "firmware":
            n_records += 1
            n_recipes += 1
            lines += _fmt_firmware_item(it)
        elif it.get("kind") == "recipes":
            n_recipes += len(it.get("written") or [])
            lines += _fmt_recipes_item(it)
    lines.append("")
    lines += render_demand_section(r)
    lines.append("### Skipped this tick (not in this PR; remembered with a TTL)")
    if r.rejects:
        for k, v in sorted(r.rejects.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"- {k}: {v}")
    else:
        lines.append("- none")
    lines.append("")
    mem = r.memory or {}
    guard = "n/a" if r.guard is None else ("green" if r.guard.get("ok") else "RED")
    lines.append("### Summary")
    lines.append(f"{n_records} record(s) · {n_recipes} recipe(s) · guard {guard} · memory expired {mem.get('expired', 0)} / "
                 f"merged {mem.get('merged', 0)} / rejected {mem.get('rejected', 0)} / removed {mem.get('removed', 0)} · {r.budget}")
    lines.append("")
    lines.append("**Merge = accept. Close = veto** (Jr records the veto and does not propose it again for 30 days). "
                 "Every path is additive; nothing is deleted by a tick.")
    lines.append("")
    lines.append("<details><summary>Stage log</summary>")
    lines.append("")
    for s in r.stages:
        summary = s.get("summary", "")
        if len(summary) > 1500:
            summary = summary[:1500].rstrip() + " … (truncated; the tick's stderr log has the rest)"
        flag = " ⚠️ needs a human" if s.get("needs_human") else ""
        lines.append(f"- **{s.get('name', 'stage')}** — {summary}{flag}")
        for p in s.get("paths", []):
            lines.append(f"  - `{p}`")
    lines.append("")
    lines.append("</details>")
    lines.append("")
    lines.append("— 🤖 EspAtlas Jr · hourly tick")
    return "\n".join(lines)
