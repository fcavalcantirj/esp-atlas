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
BACKFILL_FIELDS = ("download_mode", "usb_serial", "getting_started", "images")


# ─────────────────────────── URL construction ───────────────────────────

def chip_seg(soc: str) -> str:
    """The docs.espressif.com path segment for a soc: the soc id with hyphens removed
    (esp32-c5 -> esp32c5, esp32-s3 -> esp32s3, esp32 -> esp32)."""
    return (soc or "").replace("-", "").lower()


def board_user_guide_url(board_id: str, soc: str) -> str:
    """The board's OFFICIAL Espressif user-guide URL, constructed deterministically from
    its soc-derived chip segment and its board-dir name."""
    return f"{USER_GUIDE_BASE}/{chip_seg(soc)}/{board_id}/user_guide.html"


# ─── per-board doc-URL overrides (multi-doc-tree resolution) ──────────────────
# The single USER_GUIDE_BASE template only covers boards whose esp-dev-kits slug is
# `<chipseg>/<board_id>/user_guide.html`. A handful of boards live at a DIFFERENT path —
# either in another Espressif doc TREE (audio boards → esp-adf, not esp-dev-kits) or with a
# version-suffixed filename (`user_guide.html` 404s; the real file is `user_guide_v1.2.html`).
# Each URL below was fetched and verified 200 on 2026-09-10; the extracted content is cited
# to it. A per-board map is used (not a suffix-guesser) because the version suffix is
# board-specific and MUST be an exact, human-verified URL — never a constructed guess.
# If Espressif bumps a version and one of these 404s, that board falls back to the default
# template (also likely 404) and stays SKIPPED as doc-unreachable — never invented.
DOC_URL_OVERRIDES: dict[str, str] = {
    # ESP32-LyraT is an AUDIO board: its user guide is in the esp-adf project's
    # multimedia-boards tree, NOT esp-dev-kits. (The esp-dev-kits/design-guide paths are
    # meta-refresh redirect stubs that urllib can't follow — this is the real content page.)
    "esp32-lyrat": ("https://docs.espressif.com/projects/esp-adf/en/latest/"
                    "multimedia-boards/dev-boards/get-started-esp32-lyrat.html"),
    # esp-dev-kits guides whose filename carries a version suffix (user_guide.html 404s).
    "esp32-s2-saola-1": (f"{USER_GUIDE_BASE}/esp32s2/esp32-s2-saola-1/user_guide_v1.2.html"),
    "esp32-s3-devkitc-1": (f"{USER_GUIDE_BASE}/esp32s3/esp32-s3-devkitc-1/user_guide_v1.1.html"),
}


def doc_url_candidates(board_id: str, soc: str) -> list[str]:
    """User-guide URLs to try, in order. A verified per-board override (a different doc tree
    or a version-suffixed filename) is tried FIRST when present. Then the default template;
    then — because Espressif drops the revision suffix from some doc slugs
    (esp32-devkitc-v4 → .../esp32-devkitc/) — the `-v<N>`-stripped slug as a fallback. Only
    the `-v<N>` form is stripped (verified safe); a bare trailing -<N> is NOT (it can be a
    real board variant → wrong doc)."""
    candidates: list[str] = []
    override = DOC_URL_OVERRIDES.get(board_id)
    if override:
        candidates.append(override)
    slugs = [board_id]
    stripped = re.sub(r"-v\d+$", "", board_id)
    if stripped != board_id:
        slugs.append(stripped)
    for s in slugs:
        u = board_user_guide_url(s, soc)
        if u not in candidates:
            candidates.append(u)
    return candidates


# ─── m5stack doc-URL resolver (SPEC-board-backfill-vendors.md, Slice 2) ──────────
# Every m5stack product doc lives at `docs.m5stack.com/en/core/<ProductName>` — CONFIRMED
# by a live fetch on 2026-09-10 (m5stick-s3, m5cardputer, m5stack-core2 all returned 200,
# and their HTML is saved as the Slice-2 fixtures). The <ProductName> path segment is
# board-specific and NOT derivable from the board id (m5stack-core2 → core2,
# m5atom-lite → ATOM%20Lite, m5stamp-c3 → Stamp_C3), so — exactly like DOC_URL_OVERRIDES —
# a per-board map of human-verified paths is used, never a constructed guess. Each path here
# was taken from the board's already-cited `docs.m5stack.com` source URL and reconfirmed
# live. If m5stack renames a page and one 404s, that board stays SKIPPED (doc-unreachable),
# never invented. All 13 boards live under the single `core/` family (there is no separate
# stick/atom/stamp doc tree on docs.m5stack.com — the product name alone selects the page).
M5STACK_DOC_PATHS: dict[str, str] = {
    "m5cardputer": "core/Cardputer",
    "m5stack-core2": "core/core2",
    "m5stack-cores3": "core/CoreS3",
    "m5stack-papers3": "core/papers3",
    "m5stick-s3": "core/StickS3",
    "m5stick-cplus2": "core/M5StickC%20PLUS2",
    "m5dial": "core/M5Dial",
    "m5atom-lite": "core/ATOM%20Lite",
    "m5atoms3": "core/AtomS3",
    "m5atoms3-lite": "core/AtomS3%20Lite",
    "m5nanoc6": "core/M5NanoC6",
    "m5stamp-c3": "core/Stamp_C3",
    "m5stamp-s3": "core/StampS3",
}

M5STACK_DOC_BASE = "https://docs.m5stack.com/en"


def m5stack_doc_candidates(board_id: str, soc: str) -> list[str]:
    """Ordered candidate official doc URLs for an m5stack board on docs.m5stack.com. Returns
    the single verified `core/<ProductName>` product page for a known board, or [] for an
    unmapped id (→ the board is SKIPPED doc-unreachable, never guessed). `soc` is accepted for
    a uniform resolver signature but unused: m5stack pages are keyed by product, not chip."""
    path = M5STACK_DOC_PATHS.get(board_id)
    return [f"{M5STACK_DOC_BASE}/{path}"] if path else []


# ─── adafruit doc-URL resolver (SPEC-board-backfill-vendors.md, Slice 3) ─────────
# Every adafruit board has a Learn guide at `learn.adafruit.com/<guide-slug>` — CONFIRMED by
# a live fetch on 2026-09-10 (all 11 boards' guides returned 200 with no redirect; the
# feather-v2, qt-py-esp32-c3 and matrixportal-s3 pages are saved as the Slice-3 fixtures).
# The <guide-slug> is board-specific and NOT derivable from the board id
# (adafruit-feather-esp32-v2 → adafruit-esp32-feather-v2, adafruit-qt-py-esp32-c3 →
# adafruit-qt-py-esp32-c3-wifi-dev-board), so — exactly like M5STACK_DOC_PATHS — a per-board
# map of human-verified slugs is used, never a constructed guess. Each slug here was taken
# from the board's already-cited `learn.adafruit.com` source URL and reconfirmed live. If
# adafruit renames a guide and one 404s, that board stays SKIPPED (doc-unreachable), never
# invented. The resolved 200 overview page IS the getting_started link; usb_serial and
# download_mode ground where the overview text states them (CP2102N/USB-Serial-JTAG,
# auto-reset), else are OMITTED (cite-or-omit).
#
# 10 of the 11 adafruit boards are mapped. adafruit-feather-esp32-s2 is DELIBERATELY OMITTED:
# its Learn overview page cross-links an unrelated "CircuitPython Libraries on any Computer
# with FT232H" guide, on which the shared usb_serial extractor false-positives to "other" —
# but the S2 Feather is a native-USB board (no FTDI bridge). Mapping it would write a WRONG
# flash-critical field, so it is left unmapped (→ skipped doc-unreachable, honest) pending a
# usb_serial extractor that ignores cross-links. Follow-up, not forced.
ADAFRUIT_DOC_PATHS: dict[str, str] = {
    "adafruit-feather-esp32-s3": "adafruit-esp32-s3-feather",
    "adafruit-feather-esp32-s3-reverse-tft": "esp32-s3-reverse-tft-feather",
    "adafruit-feather-esp32-v2": "adafruit-esp32-feather-v2",
    "adafruit-huzzah32-esp32-feather": "adafruit-huzzah32-esp32-feather",
    "adafruit-itsybitsy-esp32": "adafruit-itsybitsy-esp32",
    "adafruit-matrixportal-s3": "adafruit-matrixportal-s3",
    "adafruit-metro-esp32-s3": "adafruit-metro-esp32-s3",
    "adafruit-qt-py-esp32-c3": "adafruit-qt-py-esp32-c3-wifi-dev-board",
    "adafruit-qt-py-esp32-s2": "adafruit-qt-py-esp32-s2",
    "adafruit-qt-py-esp32-s3": "adafruit-qt-py-esp32-s3",
}

ADAFRUIT_DOC_BASE = "https://learn.adafruit.com"


def adafruit_doc_candidates(board_id: str, soc: str) -> list[str]:
    """Ordered candidate official doc URLs for an adafruit board on learn.adafruit.com.
    Returns the single verified `<guide-slug>` Learn overview page for a mapped board, or []
    for an unmapped id (→ the board is SKIPPED doc-unreachable, never guessed). `soc` is
    accepted for a uniform resolver signature but unused: adafruit guides are keyed by
    product, not chip."""
    slug = ADAFRUIT_DOC_PATHS.get(board_id)
    return [f"{ADAFRUIT_DOC_BASE}/{slug}"] if slug else []


# ─── lilygo doc-URL resolver (SPEC-board-backfill-vendors.md, Slice 4) ───────────
# Every lilygo board has a product page at `lilygo.cc/products/<slug>` — CONFIRMED by a live
# fetch on 2026-09-10 (all 10 boards' pages returned 200 with NO redirect under the bot UA, and
# each page's og:title named the right product). NOTE the canonical host is the bare `lilygo.cc`:
# `www.lilygo.cc` 301-redirects to it, so the resolver uses lilygo.cc (a clean 200, no redirect).
# The <slug> is board-specific and NOT derivable from the board id (lilygo-t5-epaper-s3-pro →
# t5-e-paper-s3-pro), so — exactly like the m5stack/adafruit maps — a per-board map of
# human-verified slugs is used, never a constructed guess. Nine slugs were taken from the
# board's already-cited `lilygo.cc` source URL; the tenth (t5-e-paper-s3-pro, cited only via
# GitHub) was live-verified 200 and og:title-confirmed. If lilygo renames a page and one 404s,
# that board stays SKIPPED (doc-unreachable), never invented.
#
# GROUNDING on these Shopify product pages is LIMITED: the resolved 200 page IS the
# getting_started link (grounds for all 10), but usb_serial is GATED OFF (see
# VENDOR_UNGROUNDABLE_FIELDS) — every page carries an identical site-wide "Driver of CH9102"
# nav link, so the shared usb_serial extractor false-positives to ch9102 off site chrome, not
# the product's real bridge. download_mode and images are not stated on the product pages
# (extractors return None). So lilygo grounds getting_started only — an honest 0→1 per board.
LILYGO_DOC_PATHS: dict[str, str] = {
    "lilygo-t-beam": "t-beam",
    "lilygo-t-deck": "t-deck",
    "lilygo-t-display": "t-display",
    "lilygo-t-display-s3": "t-display-s3",
    "lilygo-t-display-s3-amoled": "t-display-s3-amoled",
    "lilygo-t-dongle-s3": "t-dongle-s3",
    "lilygo-t-embed": "t-embed",
    "lilygo-t-qt-pro": "t-qt-pro",
    "lilygo-t-watch-s3": "t-watch-s3",
    "lilygo-t5-epaper-s3-pro": "t5-e-paper-s3-pro",
}

LILYGO_DOC_BASE = "https://lilygo.cc/products"


def lilygo_doc_candidates(board_id: str, soc: str) -> list[str]:
    """Ordered candidate official doc URLs for a lilygo board on lilygo.cc. Returns the single
    verified `products/<slug>` page for a mapped board, or [] for an unmapped id (→ the board
    is SKIPPED doc-unreachable, never guessed). `soc` is accepted for a uniform resolver
    signature but unused: lilygo product pages are keyed by product, not chip."""
    slug = LILYGO_DOC_PATHS.get(board_id)
    return [f"{LILYGO_DOC_BASE}/{slug}"] if slug else []


# ─── vendor doc-URL resolver registry (SPEC-board-backfill-vendors.md, Slice 1) ──
# A resolver maps a board to the ORDERED candidate official doc URLs to try (best-first) on
# that vendor's own domain. Espressif's existing `doc_url_candidates` logic IS the
# "espressif" resolver — a behaviour-preserving refactor (identical URLs, identical output).
# `run()` and `backfill_board()` are driven off this registry's keys, so no brand is
# hardcoded: a brand with no registered resolver is never touched (skipped "no-resolver").
# New vendors are added by registering a resolver here (a future slice) — nothing else moves.
from typing import Callable  # noqa: E402

VENDOR_DOC_RESOLVERS: dict[str, Callable[[str, str], list[str]]] = {
    "espressif": doc_url_candidates,
    "m5stack": m5stack_doc_candidates,
    "adafruit": adafruit_doc_candidates,
    "lilygo": lilygo_doc_candidates,
}


# ─── per-vendor UNGROUNDABLE fields (cite-or-omit field gate) ─────────────────────
# A field a vendor's doc source structurally CANNOT ground because a shared/global element on
# every one of that vendor's pages false-positives the (flash-critical) extractor. Such a field
# is excluded from extraction for that vendor and honestly reported as OMITTED — never written.
# lilygo: every lilygo.cc product page carries an identical site-wide "Driver of CH9102" nav
# link, so extract_usb_serial reads "ch9102" off site chrome, not the product's actual bridge
# (many lilygo boards are not CH9102). That is the adafruit-feather-s2/FT232H trap at SITE scale
# — writing it would set a WRONG flash-critical field, so usb_serial is gated OFF for lilygo.
# (getting_started still grounds — it's just the resolved 200 URL.) A future slice that strips
# site chrome before extraction could lift this gate. Empty by default → no effect on any other
# vendor's extraction.
VENDOR_UNGROUNDABLE_FIELDS: dict[str, frozenset[str]] = {
    "lilygo": frozenset({"usb_serial"}),
}


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
    for s in _sentences(text):
        if _AUTO_DOWNLOAD_RE.search(s.lower()):
            return {"mode": "auto"}
    return None


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


_IMG_SRC = re.compile(r'<img[^>]+src="([^"]+)"', re.I)


def extract_images(raw: str, doc_url: str) -> dict | None:
    """The official pinout diagram + a board photo from the doc's <img> tags, resolved to
    absolute URLs. cite-or-omit: only what the page actually links. A pinout DIAGRAM is the
    safe (no mis-map) way to convey wiring; an annotated/isometric photo lets a maker
    visually IDENTIFY the board. Needs the RAW html (visible-text stripping drops <img>)."""
    from urllib.parse import urljoin
    found: dict = {}
    for src in _IMG_SRC.findall(raw or ""):
        low = src.lower()
        is_pinout = re.search(r"pin[-_]?layout|pinout", low) is not None
        if "pinout" not in found and is_pinout:
            found["pinout"] = urljoin(doc_url, src)
        # A board photo lets a maker IDENTIFY the board: newer devkits ship an
        # "isometric"/"annotated-photo"; older boards (WROVER-KIT, Ethernet-Kit, LyraT) only
        # link a labelled board "layout-front"/"-overview" shot. `not is_pinout` guards the
        # pin-layout filename (a diagram, not a photo) out of the photo slot.
        if ("photo" not in found and not is_pinout
                and re.search(r"annotated-photo|isometric|-photo|layout-front|-overview", low)):
            found["photo"] = urljoin(doc_url, src)
    return found or None


# ─── m5stack image extractor (SPEC-vendor-image-grounding.md, Slice 1) ────────────
# m5stack serves every product/doc image from an Aliyun OSS CDN with OPAQUE filenames
# (K150-stickS3_main-products_01.webp, core2_01.jpg, …), so the Espressif FILENAME heuristic
# grounds nothing here. Instead we key off the HTML CONTEXT of docs.m5stack.com pages, which
# is uniform across the real fixtures (m5stick-s3 / m5stack-core2 / m5cardputer / papers3):
#
#   PHOTO — the identifying hero shot is the FIRST carousel image, marked
#     `<div class="carousel-container"> … <img src="…" alt="Preview">`. It is per-board
#     distinct (the product's own gallery) and appears on every fixture → a reliable photo.
#
#   PINOUT — high-confidence-or-omit (a wrong wiring diagram can fry a board). Every page has
#     one explicit section heading `<h2 id="pinmap" data-id="PinMap">PinMap</h2>`. We ground
#     `pinout` ONLY to an <img> the author embedded INSIDE that PinMap section (from the
#     heading to the next <h2>). The section context IS the vendor signal that the image is
#     the pin map — we never promote a gallery/hero image to pinout. On the real fixtures this
#     grounds ONLY m5stack-core2 (whose PinMap section embeds a GPIO diagram); m5stick-s3,
#     m5cardputer and m5stack-papers3 render their pin maps as HTML TABLES with no image, so
#     pinout is correctly OMITTED for them. m5stack pages carry NO og:image and an identical
#     generic <meta name="description"> across boards, so neither is usable for grounding.
_M5_PINMAP_H2 = re.compile(r'<h2[^>]*\bid="pinmap"[^>]*>', re.I)
_M5_NEXT_H2 = re.compile(r"<h2[ >]", re.I)
_M5_CAROUSEL_PREVIEW = re.compile(
    r'<div[^>]*class="[^"]*carousel-container[^"]*".*?<img[^>]+src="([^"]+)"[^>]*\balt="Preview"',
    re.I | re.S,
)


def extract_images_m5stack(raw: str, doc_url: str) -> dict | None:
    """Ground m5stack `{photo?, pinout?}` by docs.m5stack.com HTML CONTEXT, absolute URLs.

    photo  = the first carousel `<img alt="Preview">` (the product hero shot).
    pinout = an `<img>` embedded inside the explicit `<h2 id="pinmap">PinMap</h2>` section
             ONLY — the section heading is the vendor signal it is the pin map. A merely
             plausible product image is NEVER promoted to pinout (safety: cite-or-omit,
             high-confidence-or-omit). Returns None when neither is found."""
    from urllib.parse import urljoin
    raw = raw or ""
    found: dict = {}

    hero = _M5_CAROUSEL_PREVIEW.search(raw)
    if hero:
        found["photo"] = urljoin(doc_url, hero.group(1))

    h = _M5_PINMAP_H2.search(raw)
    if h:
        section = raw[h.end():]
        nxt = _M5_NEXT_H2.search(section)
        if nxt:
            section = section[: nxt.start()]
        img = _IMG_SRC.search(section)
        if img:
            found["pinout"] = urljoin(doc_url, img.group(1))

    return found or None


# ─── per-vendor image-extractor registry (SPEC-vendor-image-grounding.md) ─────────
# Mirrors VENDOR_DOC_RESOLVERS: keyed by brand, each entry grounds the `images` field
# ({photo?, pinout?} absolute URLs, or None) from that vendor's page structure. The
# "espressif" entry IS the existing filename heuristic, UNCHANGED (behaviour-preserving).
# A brand with no entry falls back to the Espressif heuristic, which finds nothing on a
# non-Espressif CDN → images omitted, no regression, no bad data.
IMAGE_EXTRACTORS: dict[str, Callable[[str, str], dict | None]] = {
    "espressif": extract_images,
    "m5stack": extract_images_m5stack,
}


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
