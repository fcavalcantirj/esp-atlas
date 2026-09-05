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
    admitted: int = 0
    rejects: dict = field(default_factory=dict)       # reason -> count
    memory: dict = field(default_factory=dict)        # {"expired", "merged", "rejected", "removed"}
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
    return (f"🤖 {head} {stamp}: boards {_pct(r.boards_pct)} (overall {_pct(r.overall_pct)}) · "
            f"{r.allocation or 'allocation n/a'} · admitted {r.admitted} · rejects {rej} · "
            f"{mem_txt}{guard_txt}{reval} · {pr_txt}{warn} · {r.budget}").rstrip(" ·")


def render_pr_body(r: TickReport) -> str:
    """Deterministic PR body: base commit, gauge, allocation, each stage's summary and paths,
    memory deltas, guard verdict. Ends with the standing 'bot proposes, CI disposes' line."""
    lines = [f"EspAtlas Jr tick — {r.when.strftime('%Y-%m-%d %H:%M UTC')}", ""]
    lines.append(f"Base: `{r.base_sha or 'origin/main'}` · boards {_pct(r.boards_pct)} · overall {_pct(r.overall_pct)}")
    if r.allocation:
        lines.append(f"Allocation: {r.allocation}")
    lines.append("")
    if r.stages:
        lines.append("### Changes")
        for s in r.stages:
            flag = " ⚠️ needs a human" if s.get("needs_human") else ""
            lines.append(f"- **{s.get('name', 'stage')}** — {s.get('summary', '')}{flag}")
            for p in s.get("paths", []):
                lines.append(f"  - `{p}`")
        lines.append("")
    if r.rejects:
        lines.append("### Rejected this tick")
        for k, v in sorted(r.rejects.items()):
            lines.append(f"- {k}: {v}")
        lines.append("")
    mem = r.memory or {}
    lines.append(f"Memory: expired {mem.get('expired', 0)}, merged {mem.get('merged', 0)}, "
                 f"rejected {mem.get('rejected', 0)}, removed {mem.get('removed', 0)} (ledger committed with this PR).")
    if r.guard is not None:
        lines.append("Guard: " + ("green" if r.guard.get("ok") else "RED"))
    lines.append(f"Budget: {r.budget}")
    lines += ["", "**Bot proposes, CI disposes, a human may veto.** Every path above is additive; "
                  "no record is deleted by a tick until the G2 guard is in CI.", "",
              "— 🤖 EspAtlas Jr · hourly tick"]
    return "\n".join(lines)
