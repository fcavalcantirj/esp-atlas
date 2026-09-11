"""EspAtlas Jr — vendor doc-URL resolver layer (extracted from board_backfill.py).

A resolver maps a board to the ORDERED candidate official doc URLs to try (best-first) on
that vendor's own domain. This module holds every per-vendor resolver, its verified
per-board URL/slug maps, the VENDOR_DOC_RESOLVERS registry that keys them by brand, and the
VENDOR_UNGROUNDABLE_FIELDS gate. It was split out of board_backfill.py once that file neared
the ~900-line ceiling; board_backfill.py re-imports every name here UNCHANGED, so all
existing behaviour (identical URLs, identical output) and all existing tests keep passing.

NO LLM, NO API KEY, NO network here: these are pure string builders over a board id + soc.
"""
from __future__ import annotations

import re
from typing import Callable

USER_GUIDE_BASE = "https://docs.espressif.com/projects/esp-dev-kits/en/latest"


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


# ─── heltec doc-URL resolver (SPEC-board-backfill-vendors.md, Slice 5) ───────────
# Every heltec ESP32 board has an official doc page at
# `docs.heltec.org/en/node/esp32/<name>/index.html`. UNLIKE the m5stack/adafruit/lilygo maps,
# heltec's slug is a clean DETERMINISTIC rule — CONFIRMED by a live fetch on 2026-09-11 (all 5
# boards returned 200 and each page described the correct V3/ESP32-S3 board; their HTML is the
# Slice-5 fixtures): strip the `heltec-` prefix, strip a trailing `-v3`, replace `-` with `_`.
# All 5 board ids fit the rule exactly, so none is hardcoded (if one ever failed to fit it would
# go in a small verified override map rather than forcing the rule). The resolver only claims
# `heltec-`-prefixed ids; anything else yields [] (→ skipped doc-unreachable, never a guessed
# URL). Grounding on these Sphinx-style doc pages: getting_started grounds for all 5 (the
# resolved 200 page IS the link); usb_serial grounds only where the page NAMES the bridge
# (wifi-kit-32-v3 / wifi-lora-32-v3 → cp2102; the other three name none → omitted);
# download_mode and images are not stated (extractors return None → omitted). `soc` is accepted
# for a uniform resolver signature but unused: heltec's slug derives from the board id alone.
HELTEC_DOC_BASE = "https://docs.heltec.org/en/node/esp32"


def heltec_doc_candidates(board_id: str, soc: str) -> list[str]:
    """Ordered candidate official doc URLs for a heltec board on docs.heltec.org. Returns the
    single deterministic-rule `<name>/index.html` doc page for a `heltec-`-prefixed id, or []
    for any other id (→ the board is SKIPPED doc-unreachable, never guessed)."""
    if not board_id.startswith("heltec-"):
        return []
    name = re.sub(r"-v3$", "", board_id[len("heltec-"):]).replace("-", "_")
    return [f"{HELTEC_DOC_BASE}/{name}/index.html"]


# ─── seeed doc-URL resolver (SPEC-board-backfill-vendors.md, Slice 6) ────────────
# The 3 Seeed XIAO ESP32 boards each have an official getting-started page on
# wiki.seeedstudio.com. UNLIKE heltec's clean deterministic rule, the Seeed wiki slugs are NOT
# case-uniform: the C3 page is CamelCase (`XIAO_ESP32C3_Getting_Started`) while the C6/S3 pages
# are lowercase (`xiao_esp32c6_getting_started`). A single naive rule can't yield all three, so —
# like the m5stack/adafruit/lilygo maps — this resolver is a small EXPLICIT per-board map: only
# URLs CONFIRMED live=200 on 2026-09-11 (each page's main content describes the matching chip;
# their HTML is the Slice-6 fixtures) are ever emitted — never a guessed case variant. The
# resolver claims only the 3 mapped XIAO ids; any other id yields [] (→ SKIPPED doc-unreachable,
# never a guessed URL). Grounding on these wiki pages: getting_started grounds for all 3 (the
# resolved 200 page IS the link); usb_serial / download_mode / images are not groundable on the
# page text (extractors return None → omitted, cite-or-omit). `soc` is accepted for a uniform
# resolver signature but unused: the map is keyed by board id.
SEEED_DOC_URLS = {
    "xiao-esp32c3": "https://wiki.seeedstudio.com/XIAO_ESP32C3_Getting_Started/",
    "xiao-esp32c6": "https://wiki.seeedstudio.com/xiao_esp32c6_getting_started/",
    "xiao-esp32s3": "https://wiki.seeedstudio.com/xiao_esp32s3_getting_started/",
}


def seeed_doc_candidates(board_id: str, soc: str) -> list[str]:
    """Ordered candidate official doc URLs for a Seeed XIAO board on wiki.seeedstudio.com.
    Returns the single live-verified getting-started page for a mapped board id, or [] for any
    other id (→ the board is SKIPPED doc-unreachable, never guessed). `soc` is accepted for a
    uniform resolver signature but unused: the map is keyed by board id (the wiki slugs are not
    case-uniform, so no rule derives them)."""
    url = SEEED_DOC_URLS.get(board_id)
    return [url] if url else []


# ─── lolin (wemos) doc-URL resolver (SPEC-board-backfill-vendors.md, Slice 7) ────
# Every LOLIN (wemos) ESP32 board has an official doc page on `www.wemos.cc`. LIKE heltec's
# clean deterministic rule — CONFIRMED by a live fetch on 2026-09-11 (all 6 boards returned 200
# and each page described the correct chip; their HTML is the Slice-7 fixtures): strip the
# `lolin-` prefix, replace `-` with `_` → `<name>`; the family folder is `<name>` up to the
# first `_` (`c3_mini`→`c3`, `d32_pro`→`d32`, `s2_mini`→`s2`, `s3`→`s3`); then
# `https://www.wemos.cc/en/latest/<family>/<name>.html`. All 6 board ids fit the rule exactly,
# so none is hardcoded (if one ever failed to fit it would go in a small verified override map
# rather than forcing the rule). The resolver only claims `lolin-`-prefixed ids; anything else
# yields [] (→ skipped doc-unreachable, never a guessed URL). Grounding on these Sphinx-style
# doc pages: getting_started grounds for all 6 (the resolved 200 page IS the link); usb_serial
# grounds only where the page NAMES the bridge (d32 / d32_pro → ch340; the other four name none
# → omitted); download_mode and images are not stated (extractors return None → omitted). `soc`
# is accepted for a uniform resolver signature but unused: lolin's slug derives from the board
# id alone.
LOLIN_DOC_BASE = "https://www.wemos.cc/en/latest"


def lolin_doc_candidates(board_id: str, soc: str) -> list[str]:
    """Ordered candidate official doc URLs for a lolin (wemos) board on www.wemos.cc. Returns
    the single deterministic-rule `<family>/<name>.html` doc page for a `lolin-`-prefixed id, or
    [] for any other id (→ the board is SKIPPED doc-unreachable, never guessed)."""
    if not board_id.startswith("lolin-"):
        return []
    name = board_id[len("lolin-"):].replace("-", "_")
    family = name.split("_")[0]
    return [f"{LOLIN_DOC_BASE}/{family}/{name}.html"]


# ─── unexpected-maker doc-URL resolver (SPEC-board-backfill-vendors.md, Slice 8) ─
# Every Unexpected Maker ESP32-S3 board has an official doc page on `esp32s3.com`. LIKE heltec /
# lolin's clean DETERMINISTIC rule — CONFIRMED by a live fetch on 2026-09-11 (all 4 boards
# returned 200 and each page described the correct ESP32-S3 board with a USB-C connector; their
# HTML is the Slice-8 fixtures): strip the `um-` prefix → `<name>`, then
# `https://esp32s3.com/<name>.html` (um-tinys3→tinys3, um-pros3→pros3, um-nanos3→nanos3,
# um-feathers3→feathers3). All 4 board ids fit the rule exactly, so none is hardcoded (if one ever
# failed to fit it would go in a small verified override map rather than forcing the rule). The
# resolver only claims `um-`-prefixed ids; anything else yields [] (→ skipped doc-unreachable,
# never a guessed URL). The frontmatter `brand` for these boards is exactly `unexpected-maker`, so
# it registers under that key. Grounding on these pages: getting_started grounds for all 4 (the
# resolved 200 page IS the link); usb_serial grounds for all 4 (each page states "Native USB +
# USB Serial JTAG" → native-usb-serial-jtag); download_mode is not stated (no Boot+Reset sentence
# → omitted); images is GATED OFF for the vendor (see VENDOR_UNGROUNDABLE_FIELDS — the espressif
# filename heuristic mis-grounds a cross-board pinout on nanos3). `soc` is accepted for a uniform
# resolver signature but unused: the slug derives from the board id alone.
UM_DOC_BASE = "https://esp32s3.com"


def unexpected_maker_doc_candidates(board_id: str, soc: str) -> list[str]:
    """Ordered candidate official doc URLs for an Unexpected Maker board on esp32s3.com. Returns
    the single deterministic-rule `<name>.html` doc page for a `um-`-prefixed id, or [] for any
    other id (→ the board is SKIPPED doc-unreachable, never guessed)."""
    if not board_id.startswith("um-"):
        return []
    name = board_id[len("um-"):]
    return [f"{UM_DOC_BASE}/{name}.html"]


# ─── dfrobot doc-URL resolver (SPEC-board-backfill-vendors.md, Slice 9) ──────────
# The 6 DFRobot ESP32 boards each have an official wiki page at wiki.dfrobot.com/dfrXXXX, where
# dfrXXXX is the product's SKU. UNLIKE heltec/lolin's clean deterministic rule, the SKU is NOT
# derivable from the board id (beetle-esp32-c3 → dfr0868, beetle-esp32-c6 → dfr1117 — adjacent
# boards, non-adjacent SKUs), so — exactly like the seeed SEEED_DOC_URLS map — this resolver is
# a small EXPLICIT per-board map: only URLs CONFIRMED live=200 on 2026-09-11 (each page's <title>
# content-matches OUR board record — dfr0975 is the S3 N16R8 16MB/8MB-PSRAM variant, NOT dfr1145
# the N4 4MB variant; dfr0478 is the original FireBeetle ESP32, not a "FireBeetle 2"; their HTML
# is the Slice-9 fixtures) are ever emitted — never an invented/guessed SKU. The resolver claims
# only the 6 mapped ids; any other id yields [] (→ SKIPPED doc-unreachable, never a guessed URL).
# The frontmatter `brand` for these boards is exactly `dfrobot`, so it registers under that key.
# Grounding on these wiki pages: getting_started grounds for all 6 (the resolved 200 page IS the
# link); usb_serial grounds ch340 only where the page NAMES the bridge in product prose
# (firebeetle-2-esp32-e / firebeetle-esp32 → ch340; the other four label only a JTAG debug PIN,
# not the USB-Serial-JTAG flashing peripheral → omitted); download_mode is not stated and the
# default image heuristic finds nothing (both → omitted, cite-or-omit; no image gate needed).
# `soc` is accepted for a uniform resolver signature but unused: the map is keyed by board id.
DFROBOT_DOC_URLS = {
    "beetle-esp32-c3": "https://wiki.dfrobot.com/dfr0868",
    "beetle-esp32-c6": "https://wiki.dfrobot.com/dfr1117",
    "firebeetle-2-esp32-c6": "https://wiki.dfrobot.com/dfr1075",
    "firebeetle-2-esp32-e": "https://wiki.dfrobot.com/dfr0654",
    "firebeetle-2-esp32-s3": "https://wiki.dfrobot.com/dfr0975",
    "firebeetle-esp32": "https://wiki.dfrobot.com/dfr0478",
}


def dfrobot_doc_candidates(board_id: str, soc: str) -> list[str]:
    """Ordered candidate official doc URLs for a DFRobot board on wiki.dfrobot.com. Returns the
    single live-verified `dfrXXXX` wiki page for a mapped board id, or [] for any other id (→ the
    board is SKIPPED doc-unreachable, never guessed). `soc` is accepted for a uniform resolver
    signature but unused: the map is keyed by board id (the SKU number is not derivable)."""
    url = DFROBOT_DOC_URLS.get(board_id)
    return [url] if url else []


# ─── vendor doc-URL resolver registry (SPEC-board-backfill-vendors.md, Slice 1) ──
# A resolver maps a board to the ORDERED candidate official doc URLs to try (best-first) on
# that vendor's own domain. Espressif's existing `doc_url_candidates` logic IS the
# "espressif" resolver — a behaviour-preserving refactor (identical URLs, identical output).
# `run()` and `backfill_board()` are driven off this registry's keys, so no brand is
# hardcoded: a brand with no registered resolver is never touched (skipped "no-resolver").
# New vendors are added by registering a resolver here (a future slice) — nothing else moves.
VENDOR_DOC_RESOLVERS: dict[str, Callable[[str, str], list[str]]] = {
    "espressif": doc_url_candidates,
    "m5stack": m5stack_doc_candidates,
    "adafruit": adafruit_doc_candidates,
    "lilygo": lilygo_doc_candidates,
    "heltec": heltec_doc_candidates,
    "seeed": seeed_doc_candidates,
    "lolin": lolin_doc_candidates,
    "unexpected-maker": unexpected_maker_doc_candidates,
    "dfrobot": dfrobot_doc_candidates,
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
# site chrome before extraction could lift this gate.
# unexpected-maker: on esp32s3.com the per-board pinout diagrams are `images/pins_<board>.jpg`
# (which the espressif filename heuristic's pinout regex does NOT match), while a cross-linked
# generic `images/tiny_pinout_matrix.jpg` DOES match — and the nanos3 page carries BOTH its own
# nanos3_pinout_matrix.jpg AND tiny_pinout_matrix.jpg, so the heuristic grounds the WRONG (tinys3)
# pinout first in DOM order. A wrong wiring diagram can fry a board (the lilygo trap at cross-board
# scale), so images is gated OFF for the vendor and reported OMITTED. A future dedicated
# unexpected-maker image extractor (keying on the per-board pins_<name>.jpg) could lift this gate.
# Empty by default → no effect on any other vendor's extraction.
VENDOR_UNGROUNDABLE_FIELDS: dict[str, frozenset[str]] = {
    "lilygo": frozenset({"usb_serial"}),
    "unexpected-maker": frozenset({"images"}),
}
