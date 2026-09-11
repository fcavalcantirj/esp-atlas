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

FETCH_USER_AGENT = "esp-atlas-jr/0.1 (+https://esp-atlas.com; board-backfill bot)"

# The fields this backfill can ground, in write order (also the frontmatter order).
BACKFILL_FIELDS = ("download_mode", "usb_serial", "getting_started", "images")


# ─── vendor doc-URL resolver layer (moved to jr/board_doc_resolvers.py) ────────
# The per-vendor doc-URL resolvers, their verified per-board URL/slug maps, the
# VENDOR_DOC_RESOLVERS registry and the VENDOR_UNGROUNDABLE_FIELDS gate were split into
# board_doc_resolvers.py once this file neared the ~900-line ceiling. They are re-imported
# here UNCHANGED so board_backfill.chip_seg / board_user_guide_url / USER_GUIDE_BASE /
# doc_url_candidates / <vendor>_doc_candidates / VENDOR_DOC_RESOLVERS / etc. resolve exactly
# as before (behaviour-preserving; identical URLs, identical output). backfill_board() and
# run() below drive off VENDOR_DOC_RESOLVERS / VENDOR_UNGROUNDABLE_FIELDS from this import.
from board_doc_resolvers import (  # noqa: E402,F401
    ADAFRUIT_DOC_BASE,
    ADAFRUIT_DOC_PATHS,
    DFROBOT_DOC_URLS,
    DOC_URL_OVERRIDES,
    HELTEC_DOC_BASE,
    LILYGO_DOC_BASE,
    LILYGO_DOC_PATHS,
    LOLIN_DOC_BASE,
    M5STACK_DOC_BASE,
    M5STACK_DOC_PATHS,
    SEEED_DOC_URLS,
    SPARKFUN_DOC_URLS,
    UM_DOC_BASE,
    USER_GUIDE_BASE,
    VENDOR_DOC_RESOLVERS,
    VENDOR_UNGROUNDABLE_FIELDS,
    adafruit_doc_candidates,
    board_user_guide_url,
    chip_seg,
    dfrobot_doc_candidates,
    doc_url_candidates,
    heltec_doc_candidates,
    lilygo_doc_candidates,
    lolin_doc_candidates,
    m5stack_doc_candidates,
    seeed_doc_candidates,
    sparkfun_doc_candidates,
    unexpected_maker_doc_candidates,
)


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

      * MANUAL — a single sentence that explicitly names the button sequence: it names the
        Firmware Download / upload mode AND the Boot button AND the second button, which
        Espressif docs write as either "Reset" or "EN" (EN is the ESP32 reset/enable pin),
        e.g. "Holding down Boot and then pressing Reset initiates Firmware Download mode" or
        "...pressing EN initiates Firmware Download mode". Audio (esp-adf) boards phrase the
        same act as "...initiates the firmware upload mode" — treated as equivalent.
        -> {"mode": "manual", "steps": <that exact sentence>}.
      * MANUAL (m5stack family) — those docs state download mode in a different grammar with
        NO "Boot" sequence: under a "Download Mode" label / binding a physical button action
        to entering it (PaperS3/StickS3 "...press and hold the reset button..."). Grounds the
        CONCISE instruction sentence only — it must name "download mode" AND carry an
        imperative AFFIRMATIVE ENGAGE action (press/hold/long-press/connect/plug) in the SAME
        sentence, so a result-only confirmation ("When the internal green LED flashes, the
        device has successfully entered download mode") is NOT captured, a bare-"release" half-
        instruction (m5cardputer's tail, whose hold-G0 precondition is stranded in a spec
        table) is NOT captured, and a flattened spec-table blob (over _M5_STEPS_MAX chars,
        which also contains the words "download mode") is skipped. -> {"mode": "manual",
        "steps": <that exact instruction sentence>}. Runs only after the Espressif branch, so
        Espressif boards are byte-identical.
      * AUTO — a sentence that explicitly BINDS an auto-word to a flashing verb: `auto-reset`,
        or `automatic(ally)` sitting next to download/flash/bootloader (in either order). The
        auto-word MUST be tied to the flashing act, not merely co-occur in the sentence — some
        vendor pages say "automatic port recognition" (the OS auto-detecting the serial PORT),
        which is NOT an auto-download claim and MUST NOT ground (m5stack PaperS3). -> {"mode": "auto"}.
      * Neither found -> None (OMIT). NEVER guessed — a wrong step can brick a board.
      `\\bEN\\b` is matched with word boundaries so it only catches the standalone EN button,
      never the fragment inside "then"/"when"/"enter"."""
    for s in _sentences(text):
        low = s.lower()
        names_mode = "download mode" in low or "firmware upload mode" in low
        second_button = "reset" in low or re.search(r"\ben\b", low) is not None
        if names_mode and "boot" in low and second_button:
            return {"mode": "manual", "steps": s.rstrip(".")}
    for s in _sentences(text):  # m5stack-family manual phrasing (no Boot sequence)
        low = s.lower()
        if "download mode" not in low or len(s) > _M5_STEPS_MAX:
            continue
        if _M5_MANUAL_ACTION_RE.search(low):
            return {"mode": "manual", "steps": s.rstrip(".")}
    for s in _sentences(text):
        if _AUTO_DOWNLOAD_RE.search(s.lower()):
            return {"mode": "auto"}
    return None


# m5stack manual download-mode: an imperative AFFIRMATIVE ENGAGE action bound (same
# sentence) to entering download mode. Matches press / press-and-hold / long press / hold /
# connect / plug. Deliberately NOT bare "flash(es)"/"enter(ed)" (a result-only confirmation
# line must not ground), and deliberately NOT "release": a release presupposes a prior HOLD,
# so a sentence whose only action is "release" is a HALF-instruction (it tells the user to
# let go of a button they were never told to hold) — worse than an omission on a flash-
# critical field. m5cardputer's tail sentence ("...release the button, and the device will
# enter download mode") is exactly that fragment; its hold-G0 precondition survives only
# inside a flattened >_M5_STEPS_MAX spec table, so cardputer correctly OMITS (cite-or-omit).
_M5_MANUAL_ACTION_RE = re.compile(
    r"\b(?:press(?:ing)?|hold(?:ing)?|connect|plug)\b", re.I)
# Concise-instruction guard: genuine m5stack instruction sentences are short; a flattened
# spec/feature table (which also contains the words "download mode") runs to hundreds of
# chars — never quote one as `steps`.
_M5_STEPS_MAX = 300


# Auto-download only grounds when an auto-word is BOUND to a flashing verb — not merely
# present in a (table-flattened) sentence. `auto[- ]?reset` is unambiguous; otherwise
# `automatic(ally)` must sit within two words of download/flash/bootloader (either order).
# This deliberately EXCLUDES "automatic port recognition" (serial-port auto-detect, not
# auto-flash) so a wrong download-mode claim is never written (cite-or-omit, flash-critical).
_AUTO_DOWNLOAD_RE = re.compile(
    r"auto[- ]?reset"
    r"|automatic(?:ally)?\s+(?:\w+\s+){0,2}(?:download|flash(?:ing)?|bootloader)"
    r"|(?:download|flash(?:ing)?|bootloader)(?:\s+\w+){0,3}\s+automatic(?:ally)?",
    re.I,
)


# Most-specific token first so cp2102n is never miscounted as cp2102 (and ft2232h → ft2232).
_BRIDGE_TOKENS = (
    ("cp2102n", "cp2102n"),
    ("cp2102", "cp2102"),
    ("ch9102", "ch9102"),
    ("ch343", "ch343"),
    ("ch340", "ch340"),
    ("ft2232", "other"),    # FTDI (e.g. ESP-WROVER-KIT's FT2232HL) — no dedicated enum value yet,
    ("ft232", "other"),     # so map to the schema-valid "other" (never emit a value outside the
)                           # usb_serial enum, or the guard rejects the board and the tick aborts)


# Espressif user guides that DON'T name the part number still state, verbatim in the
# components table, that the board carries a dedicated bridge: "Single USB-to-UART bridge
# chip provides transfer rates up to 3 Mbps" / "Integrated USB-UART Bridge Chip". That is an
# explicit, citeable claim that a USB-UART bridge exists — which the schema has a dedicated
# enum for: "usb-uart-bridge-unspecified". We require the words "bridge chip" (not a bare
# "USB-to-UART bridge") so a passing mention of a UART interface is NOT mistaken for a chip.
_UNSPEC_BRIDGE_RE = re.compile(r"usb[- ]?(?:to[- ]?)?uart bridge chip", re.I)


def extract_usb_serial(text: str) -> str | None:
    """Grounded usb_serial extraction, most-specific first (every branch returns a value in
    the schema's usb_serial enum, never outside it):

      1. the bridge chip the page NAMES (cp2102n/cp2102/ch343/ch340/ch9102, or FTDI → other);
      2. native USB-Serial-JTAG, if the page states it;
      3. an explicitly-stated but UNNAMED "USB-to-UART bridge chip" -> usb-uart-bridge-unspecified.

    A named chip takes precedence (it's the default flashing path on Espressif devkits).
    Nothing stated -> None (OMIT). This is flash-critical: only ever emit what the doc says."""
    low = (text or "").lower()
    for token, enum in _BRIDGE_TOKENS:
        if token in low:
            return enum
    if any(t in low for t in ("usb-serial-jtag", "usb serial jtag", "usb_serial_jtag",
                              "usb serial/jtag", "usb-serial/jtag")):
        return "native-usb-serial-jtag"
    if _UNSPEC_BRIDGE_RE.search(low):
        return "usb-uart-bridge-unspecified"
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


# ─── per-vendor image extractors (moved to jr/board_image_extractors.py) ──────
# The image extractors and the IMAGE_EXTRACTORS registry were split into
# board_image_extractors.py once this file neared the ~900-line ceiling. They are re-imported
# here UNCHANGED so board_backfill.extract_images / _m5stack / _adafruit / _lilygo and
# IMAGE_EXTRACTORS resolve exactly as before (behaviour-preserving; the espressif entry is the
# same filename heuristic, same function object). The registry drives images grounding in
# _extract_for below, keyed by brand, falling back to the espressif heuristic for any brand
# with no dedicated extractor.
from board_image_extractors import (  # noqa: E402,F401
    IMAGE_EXTRACTORS,
    extract_images,
    extract_images_adafruit,
    extract_images_lilygo,
    extract_images_m5stack,
)


def _extract_for(text: str, url: str, missing: list[str], raw: str | None = None,
                 brand: str = "espressif") -> dict:
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
    if "images" in missing:
        extractor = IMAGE_EXTRACTORS.get(brand, extract_images)
        imgs = extractor(raw or "", url)
        if imgs is not None:
            out["images"] = imgs
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

    # Vendor-doc resolver selected by the board's brand. A brand with no registered
    # resolver is left COMPLETELY unmodified (matches today's behaviour where non-Espressif
    # brands are never touched) — reported skipped/no-resolver, not backfilled.
    resolver = VENDOR_DOC_RESOLVERS.get(brand)
    if resolver is None:
        return {**base, "status": "skipped", "reason": "no-resolver", "url": None}

    missing = _missing_fields(fm)
    if not missing:
        return {**base, "status": "complete"}

    soc = resolve_soc(fm, data_root)
    if not soc:
        return {**base, "status": "skipped", "reason": "no-soc", "url": None}

    candidates = resolver(board_id, soc)
    if not candidates:  # resolver has no verified URL for this board — skip, never guess
        return {**base, "status": "skipped", "reason": "doc-unreachable", "url": None}
    res, url = None, candidates[-1]
    for u in candidates:
        r = fetch(u)
        if r.get("ok"):
            res, url = r, u          # cite the slug that actually resolved
            break
    if res is None:
        return {**base, "status": "skipped", "reason": "doc-unreachable", "url": url}

    raw = res.get("text", "")
    text = _visible_text(raw)
    # Fields this vendor's doc source cannot reliably ground (a shared page element false-
    # positives the extractor) are excluded from extraction — never written — but kept in
    # `missing` so they surface honestly as OMITTED below (cite-or-omit).
    gated = VENDOR_UNGROUNDABLE_FIELDS.get(brand, frozenset())
    extracted = _extract_for(text, url, [f for f in missing if f not in gated], raw=raw,
                             brand=brand)
    if not extracted:
        return {**base, "status": "skipped", "reason": "nothing-groundable", "url": url}

    _write_fields(path, fm, body, extracted, url, today)
    written = [f for f in BACKFILL_FIELDS if f in extracted]
    omitted = [f for f in missing if f not in extracted]
    return {**base, "status": "backfilled", "url": url, "written": written,
            "omitted": omitted, "partial": bool(omitted), "modified": True}


# ─────────────────────────── run (worklist over espressif) ───────────────────────────

def run(data_root: Path | None = None, fetch=default_fetch, today: str | None = None) -> dict:
    """Backfill every board whose brand has a REGISTERED vendor doc resolver
    (VENDOR_DOC_RESOLVERS) and is missing any backfill field. Brands with no resolver yet
    are LISTED (needs_doc_url) and never touched. Today only "espressif" is registered, so
    the processed set is identical to the v1 espressif-only worklist. Returns {backfilled,
    skipped, needs_doc_url, today}."""
    root = Path(data_root) if data_root is not None else DATA_DIR
    today = today or datetime.now(timezone.utc).date().isoformat()
    boards_dir = root / "boards"

    report: dict = {"backfilled": [], "skipped": [], "needs_doc_url": [], "today": today}

    for brand_dir in sorted(p for p in boards_dir.glob("*") if p.is_dir()):
        if brand_dir.name in VENDOR_DOC_RESOLVERS:
            for path in sorted(brand_dir.glob("*/board.md")):
                entry = backfill_board(path, root, fetch, today)
                if entry["status"] == "backfilled":
                    report["backfilled"].append(entry)
                elif entry["status"] == "skipped":
                    report["skipped"].append(entry)
                # "complete" boards are intentionally silent (not on the worklist)
        else:
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
