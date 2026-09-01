"""EspAtlas Jr — Track A: grounded board-field backfill (SPEC-data-completion.md).

DETERMINISTIC, GROUNDED, cite-or-omit backfill of the FINITE board ground. For every
Espressif board missing any of `download_mode`, `usb_serial`, or `getting_started`, it
fetches that board's OFFICIAL Espressif dev-kit user-guide page, extracts ONLY
explicitly-stated fields via plain text/regex over the fetched doc, and writes them into
the board's frontmatter — each quote-and-cited to that URL. Anything it cannot ground is
OMITTED, never guessed.

This is SAFETY-CRITICAL: a wrong download-mode instruction can leave a user unable to
flash (or brick) their board. So the rule is strictly cite-or-omit — when the doc does
not explicitly state a field, the field is left absent.

NO LLM and NO API KEY anywhere here: the extraction is regex/text over the fetched page.
Every side effect (network fetch, git, gh) is injected behind a function so tests use
fakes and the real fetch only runs on an actual run.

Scope v1 = ESPRESSIF boards only (docs.espressif.com dev-kit user guides are structured
and consistent). Non-Espressif boards are OUT of scope and are only LISTED as
"needs doc URL" — never modified.

    python3 jr/board_backfill.py            # real run (opens a PR); do NOT run in CI
"""
from __future__ import annotations

import html
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent           # the esp-atlas repo root

# esp_atlas_core lives under apps/core/src — make the module self-contained (mirrors
# scripts/data_completion.py) so it imports with or without PYTHONPATH set.
_CORE_SRC = REPO / "apps" / "core" / "src"
if str(_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_CORE_SRC))
from esp_atlas_core.frontmatter import parse_frontmatter  # noqa: E402,F401 (re-exported for tests)
from esp_atlas_core.paths import DATA_DIR  # noqa: E402

USER_GUIDE_BASE = "https://docs.espressif.com/projects/esp-dev-kits/en/latest"
FETCH_USER_AGENT = "esp-atlas-jr/0.1 (+https://esp-atlas.com; board-backfill bot)"

# The fields this backfill can ground, in write order (also the frontmatter order).
BACKFILL_FIELDS = ("download_mode", "usb_serial", "getting_started")


# ─────────────────────────── URL construction ───────────────────────────

def chip_seg(soc: str) -> str:
    """The docs.espressif.com path segment for a soc: the soc id with hyphens removed
    (esp32-c5 -> esp32c5, esp32-s3 -> esp32s3, esp32 -> esp32)."""
    return (soc or "").replace("-", "").lower()


def board_user_guide_url(board_id: str, soc: str) -> str:
    """The board's OFFICIAL Espressif user-guide URL, constructed deterministically from
    its soc-derived chip segment and its board-dir name."""
    return f"{USER_GUIDE_BASE}/{chip_seg(soc)}/{board_id}/user_guide.html"


def resolve_soc(fm: dict, data_root: Path) -> str | None:
    """The board's effective soc id: its own `soc`, or its `module`'s `soc` (resolved
    through data/modules/<module>/module.md). None when neither resolves."""
    if fm.get("soc"):
        return fm["soc"]
    module = fm.get("module")
    if module:
        mpath = Path(data_root) / "modules" / module / "module.md"
        if mpath.exists():
            try:
                mfm, _ = parse_frontmatter(mpath)
            except (ValueError, OSError):
                return None
            return (mfm or {}).get("soc")
    return None


# ─────────────────────────── fetch (injected on real runs) ───────────────────────────

def default_fetch(url: str) -> dict:
    """Plain GET of an official user-guide page with a short timeout. Returns
    {"ok": True, "status": 200, "text": <raw html>} on 200, else {"ok": False, ...}.
    A 404 or ANY failure is a clean miss (ok=False) so the caller SKIPS the board and
    records it 'doc-unreachable' — never inventing. No crawling, no JS, one request."""
    if not url or not url.startswith(("http://", "https://")):
        return {"ok": False, "status": None, "error": f"not an http(s) url: {url!r}"}
    req = urllib.request.Request(url, headers={"User-Agent": FETCH_USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            charset = r.headers.get_content_charset() or "utf-8"
            raw = r.read(2_000_000).decode(charset, "ignore")
            return {"ok": True, "status": getattr(r, "status", 200), "text": raw}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "error": f"HTTP {e.code}"}
    except Exception as e:  # noqa: BLE001 — any fetch failure = clean miss, board skipped
        return {"ok": False, "status": None, "error": f"{type(e).__name__}: {e}"}


# ─────────────────────────── extraction (regex/text, NO LLM) ───────────────────────────

def _visible_text(raw: str) -> str:
    """Strip scripts/styles/tags and unescape entities to readable page text; collapse
    whitespace so sentence-splitting is stable. Idempotent on already-plain text."""
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw or "")
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _sentences(text: str) -> list[str]:
    """Split page text into trimmed sentences on ./!/? boundaries."""
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def extract_download_mode(text: str) -> dict | None:
    """Grounded download-mode extraction (SPEC cite-or-omit):

      * MANUAL — a single sentence that explicitly names the button sequence: it
        contains "Download mode" AND "Boot" AND "Reset" (case-insensitive), e.g.
        "Holding down Boot and then pressing Reset initiates Firmware Download mode".
        -> {"mode": "manual", "steps": <that exact sentence>}.
      * AUTO — a sentence that explicitly states auto-reset / automatic download.
        -> {"mode": "auto"}.
      * Neither found -> None (OMIT). NEVER guessed — a wrong step can brick a board."""
    for s in _sentences(text):
        low = s.lower()
        if "download mode" in low and "boot" in low and "reset" in low:
            return {"mode": "manual", "steps": s.rstrip(".")}
    for s in _sentences(text):
        low = s.lower()
        if "download" in low and ("automatic" in low or "auto-reset" in low
                                  or "auto reset" in low or "automatically" in low):
            return {"mode": "auto"}
    return None


# Most-specific token first so cp2102n is never miscounted as cp2102.
_BRIDGE_TOKENS = (
    ("cp2102n", "cp2102n"),
    ("cp2102", "cp2102"),
    ("ch9102", "ch9102"),
    ("ch343", "ch343"),
    ("ch340", "ch340"),
)


def extract_usb_serial(text: str) -> str | None:
    """Grounded usb_serial extraction: the bridge chip the page NAMES
    (cp2102n/cp2102/ch343/ch340/ch9102), or native USB-Serial-JTAG if the page states
    it. Bridge chip takes precedence (it's the default flashing path on Espressif
    devkits). Nothing named -> None (OMIT)."""
    low = (text or "").lower()
    for token, enum in _BRIDGE_TOKENS:
        if token in low:
            return enum
    if "usb-serial-jtag" in low or "usb serial jtag" in low or "usb_serial_jtag" in low:
        return "native-usb-serial-jtag"
    return None


# ─────────────────────────── per-board backfill ───────────────────────────

def _is_present(value) -> bool:
    """Mirror scripts/data_completion.py: present + non-empty counts as already-filled."""
    if value is None:
        return False
    if isinstance(value, (str, list, dict)):
        return len(value) > 0
    return True


def _missing_fields(fm: dict) -> list[str]:
    return [f for f in BACKFILL_FIELDS if not _is_present(fm.get(f))]


def _extract_for(text: str, url: str, missing: list[str]) -> dict:
    """The groundable subset of `missing`, each mapped to its extracted value. Only
    fields the doc explicitly states are included (cite-or-omit); getting_started is
    always groundable once the doc resolved 200 (the link is real)."""
    out: dict = {}
    if "download_mode" in missing:
        dm = extract_download_mode(text)
        if dm is not None:
            out["download_mode"] = dm
    if "usb_serial" in missing:
        us = extract_usb_serial(text)
        if us is not None:
            out["usb_serial"] = us
    if "getting_started" in missing:
        out["getting_started"] = url
    return out


def _write_fields(path: Path, fm: dict, body: str, extracted: dict, url: str, today: str) -> None:
    """Add ONLY the extracted (missing) fields to the frontmatter, each with its own
    {field, url, verified} source entry appended (the exact shape the C5 uses). Existing
    fields and their existing citations are preserved untouched; `sources` is kept last."""
    sources = fm.pop("sources", None) or []
    for field in BACKFILL_FIELDS:  # deterministic order
        if field not in extracted:
            continue
        if _is_present(fm.get(field)):  # belt-and-suspenders: never overwrite a filled field
            continue
        fm[field] = extracted[field]
        sources.append({"field": field, "url": url, "verified": today})
    fm["sources"] = sources
    front = yaml.safe_dump(fm, sort_keys=False, default_flow_style=False, allow_unicode=True).strip()
    path.write_text(f"---\n{front}\n---\n\n{body.strip()}\n")


def backfill_board(path: Path, data_root: Path, fetch, today: str) -> dict:
    """Backfill ONE board.md. Returns a report entry with `status`:
      * "complete"    — nothing was missing (not part of the worklist).
      * "skipped"     — doc-unreachable / no-soc / nothing-groundable; NOT modified.
      * "backfilled"  — >=1 missing field grounded and written; `written`/`omitted` list
                        which; `partial` is True when some missing field was omitted."""
    fm, body = parse_frontmatter(path)
    board_id = fm.get("id") or path.parent.name
    brand = fm.get("brand") or path.parent.parent.name
    base = {"board_id": board_id, "brand": brand, "path": path, "modified": False}

    missing = _missing_fields(fm)
    if not missing:
        return {**base, "status": "complete"}

    soc = resolve_soc(fm, data_root)
    if not soc:
        return {**base, "status": "skipped", "reason": "no-soc", "url": None}

    url = board_user_guide_url(board_id, soc)
    res = fetch(url)
    if not res.get("ok"):
        return {**base, "status": "skipped", "reason": "doc-unreachable", "url": url}

    text = _visible_text(res.get("text", ""))
    extracted = _extract_for(text, url, missing)
    if not extracted:
        return {**base, "status": "skipped", "reason": "nothing-groundable", "url": url}

    _write_fields(path, fm, body, extracted, url, today)
    written = [f for f in BACKFILL_FIELDS if f in extracted]
    omitted = [f for f in missing if f not in extracted]
    return {**base, "status": "backfilled", "url": url, "written": written,
            "omitted": omitted, "partial": bool(omitted), "modified": True}


# ─────────────────────────── run (worklist over espressif) ───────────────────────────

def run(data_root: Path | None = None, fetch=default_fetch, today: str | None = None) -> dict:
    """Backfill every Espressif board missing any backfill field. Non-Espressif boards
    are LISTED (needs_doc_url) and never touched. Returns {backfilled, skipped,
    needs_doc_url, today}."""
    root = Path(data_root) if data_root is not None else DATA_DIR
    today = today or datetime.now(timezone.utc).date().isoformat()
    boards_dir = root / "boards"

    report: dict = {"backfilled": [], "skipped": [], "needs_doc_url": [], "today": today}

    esp_dir = boards_dir / "espressif"
    for path in sorted(esp_dir.glob("*/board.md")):
        entry = backfill_board(path, root, fetch, today)
        if entry["status"] == "backfilled":
            report["backfilled"].append(entry)
        elif entry["status"] == "skipped":
            report["skipped"].append(entry)
        # "complete" boards are intentionally silent (not on the worklist)

    for brand_dir in sorted(p for p in boards_dir.glob("*") if p.is_dir()):
        if brand_dir.name == "espressif":
            continue
        for path in sorted(brand_dir.glob("*/board.md")):
            report["needs_doc_url"].append(f"{brand_dir.name}/{path.parent.name}")

    return report


# ─────────────────────────── orchestration (git/gh injected) ───────────────────────────

def default_git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)


def default_gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], cwd=REPO, capture_output=True, text=True)


def branch_name(now: datetime | None = None) -> str:
    """jr-board-backfill-YYYYMMDD-HHMM in UTC — one branch per backfill run."""
    now = now or datetime.now(timezone.utc)
    return f"jr-board-backfill-{now.strftime('%Y%m%d-%H%M')}"


def changed_paths(report: dict) -> list[str]:
    """The board.md paths (relative to the repo root) actually modified this run — ONLY
    the backfilled boards, nothing else in the tree."""
    paths = []
    for entry in report["backfilled"]:
        p = Path(entry["path"])
        try:
            paths.append(str(p.relative_to(REPO)))
        except ValueError:
            paths.append(str(p))
    return paths


def pr_body(report: dict) -> str:
    """Deterministic PR body: every backfilled board with which fields it got (marking
    the partial ones), plus the boards skipped (doc-unreachable / nothing groundable) and
    the non-Espressif boards still needing a doc URL. Every value read off the report —
    nothing invented."""
    lines = ["Jr's Track-A board backfill — grounded, cite-or-omit "
             f"(verified {report.get('today', '')}).", ""]
    lines.append(f"### Backfilled ({len(report['backfilled'])})")
    if not report["backfilled"]:
        lines.append("- none")
    for e in report["backfilled"]:
        tag = " · partial" if e.get("partial") else ""
        got = ", ".join(f"`{f}`" for f in e.get("written", []))
        line = f"- `{e['board_id']}` — {got}{tag} — {e.get('url', '')}"
        if e.get("omitted"):
            line += f" (omitted: {', '.join(e['omitted'])})"
        lines.append(line)

    lines += ["", f"### Skipped ({len(report['skipped'])})"]
    if not report["skipped"]:
        lines.append("- none")
    for e in report["skipped"]:
        lines.append(f"- `{e['board_id']}` — {e.get('reason', '')} — {e.get('url', '') or 'n/a'}")

    others = report.get("needs_doc_url", [])
    lines += ["", f"### Out of scope — needs doc URL ({len(others)})",
              "Non-Espressif boards are not modified in v1 (no consistent official doc "
              "template yet)."]
    for b in others:
        lines.append(f"- `{b}`")

    lines += [
        "",
        "Cite-or-omit STRICTLY: every written field carries its own `{field,url,verified}` "
        "citation to the board's official Espressif user guide; anything the doc did not "
        "explicitly state was OMITTED (a wrong download-mode step is safety-critical). "
        "No LLM, no API key — extraction is regex/text over the fetched doc.",
        "",
        "**Bot proposes, humans dispose** — skim, then merge (or drop any you don't want).",
        "",
        "— 🤖 EspAtlas Jr · Track A (finite-ground backfill)",
    ]
    return "\n".join(lines)


def open_backfill_pr(report: dict, git=default_git, gh=default_gh,
                     now: datetime | None = None) -> dict:
    """Create a fresh branch, commit ONLY the changed board.md files, and open a PR
    against main summarizing what was backfilled and skipped. Always creates+switches to
    the branch FIRST; no git call ever references `main` (the only 'main' is the
    `gh pr create --base main` API call). Returns {branch, pr_ok, pr_url}."""
    now = now or datetime.now(timezone.utc)
    branch = branch_name(now)
    paths = changed_paths(report)
    git("checkout", "-B", branch)
    git("add", *paths)
    n = len(report["backfilled"])
    subject = f"feat(boards): jr Track-A backfill of {n} board(s)"
    git("commit", "-m", subject)
    git("push", "-u", "origin", branch)
    pr = gh("pr", "create", "--base", "main", "--head", branch,
            "--title", subject, "--body", pr_body(report))
    return {"branch": branch, "pr_ok": pr.returncode == 0, "pr_url": pr.stdout.strip()}


def main(run=run, git=default_git, gh=default_gh, now: datetime | None = None,
         data_root: Path | None = None, fetch=default_fetch, today: str | None = None) -> dict:
    report = run(data_root=data_root, fetch=fetch, today=today)
    if not report["backfilled"]:
        print(f"jr-board-backfill: nothing to backfill — no board fields grounded "
              f"({len(report['skipped'])} skipped)")
        return {"report": report, "pr": None}
    pr = open_backfill_pr(report, git=git, gh=gh, now=now)
    link = pr.get("pr_url") or "(PR creation failed)"
    print(f"jr-board-backfill: {len(report['backfilled'])} board(s) backfilled — "
          f"PR {link} · branch {pr['branch']}")
    return {"report": report, "pr": pr}


if __name__ == "__main__":
    main()
