"""EspAtlas Jr — per-vendor board IMAGE extractors (SPEC-vendor-image-grounding.md).

Grounds a board's `images.photo` (visual identification) and `images.pinout` (the diagram a
maker wires from) from each vendor's product/doc page by HTML CONTEXT — deterministic, offline,
cite-or-omit. Split out of `board_backfill.py` (which re-exports these names and the
`IMAGE_EXTRACTORS` registry unchanged) once that file neared the ~900-line ceiling.

SAFETY (this is flash-/wiring-critical): `pinout` is high-confidence-or-omit — an image is
grounded as the pinout diagram ONLY under an explicit vendor-specific signal (a PinMap/Pinout
section it sits inside, or alt/title text saying pinout). A merely plausible product image is
NEVER promoted to pinout (a wrong wiring diagram can fry a board). `photo` is cite-or-omit and
grounded only from the vendor's OWN domain/CDN. When in doubt → OMIT.

NO LLM, NO network: every extractor takes `(raw_html, doc_url)` and is tested against the real
committed fixtures under jr/fixtures/board_backfill/.
"""
from __future__ import annotations

import re
from typing import Callable
from urllib.parse import urljoin, urlparse


# ─────────────────────────── espressif (filename heuristic) ───────────────────────────

_IMG_SRC = re.compile(r'<img[^>]+src="([^"]+)"', re.I)


def extract_images(raw: str, doc_url: str) -> dict | None:
    """The official pinout diagram + a board photo from the doc's <img> tags, resolved to
    absolute URLs. cite-or-omit: only what the page actually links. A pinout DIAGRAM is the
    safe (no mis-map) way to convey wiring; an annotated/isometric photo lets a maker
    visually IDENTIFY the board. Needs the RAW html (visible-text stripping drops <img>).

    This is the ESPRESSIF entry of IMAGE_EXTRACTORS and the fallback for brands with no
    dedicated extractor: on docs.espressif.com it grounds by filename; on a non-Espressif CDN
    (opaque names) it matches nothing → returns None (omit, no regression, no bad data)."""
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


# ─── adafruit image extractor (SPEC-vendor-image-grounding.md, Slice 2) ───────────
# adafruit Learn OVERVIEW pages (the committed fixtures adafruit-feather-esp32-v2 / -qt-py-esp32-c3
# / -matrixportal-s3) serve every image from the cdn-learn.adafruit.com CDN with opaque names
# (FV2_top_angle.jpg, 5778-06.gif, …), so the Espressif filename heuristic grounds nothing. We key
# off HTML CONTEXT instead:
#
#   PHOTO — the per-board identifying hero shot is the guide's Open Graph image, marked
#     `<meta property="og:image" content="https://cdn-learn.adafruit.com/guides/images/…">`. It is
#     distinct per guide and points at the board's product shot (Feather V2 → FV2_top_angle.jpg,
#     etc.). The page BODY's <img> tags are a RELATED-GUIDES carousel (class="image-preview", alt
#     text naming OTHER boards) — never the subject board — so og:image is the sole reliable photo.
#     We ground ONLY when og:image is on adafruit's own CDN (foreign og:image is ignored — safety).
#
#   PINOUT — high-confidence-or-omit (a wrong wiring diagram can fry a board). adafruit's pinout
#     DIAGRAMS live on a SEPARATE `/pinouts` sub-page of each Learn guide, NOT the overview page
#     these fixtures capture. The overview carries only a `<a href="…/pinouts">Pinouts</a>` TOC
#     LINK (not an image). So pinout is OMITTED for adafruit in this slice — we NEVER promote the
#     hero photo or a carousel image to pinout, and never mistake the /pinouts link for a diagram.
#     Reaching adafruit's /pinouts sub-page (following that link, then grounding the diagram there)
#     is a documented FOLLOW-UP, out of scope for this offline-testable slice.
_ADA_OG_IMAGE = re.compile(
    r'<meta[^>]*\bproperty=["\']og:image["\'][^>]*\bcontent=["\']([^"\']+)["\']', re.I)
_ADA_CDN = "cdn-learn.adafruit.com"


def extract_images_adafruit(raw: str, doc_url: str) -> dict | None:
    """Ground adafruit `{photo?}` by learn.adafruit.com HTML CONTEXT, absolute URLs.

    photo  = the guide's `<meta property="og:image">` hero (the identifying board shot), grounded
             ONLY when it is on adafruit's own cdn-learn CDN (a foreign og:image is ignored).
    pinout = ALWAYS omitted here: adafruit pinout diagrams live on a separate `/pinouts` sub-page,
             not the overview page. Never promote a photo/carousel image to pinout (safety:
             high-confidence-or-omit). Returns None when no adafruit-CDN og:image is present."""
    found: dict = {}

    m = _ADA_OG_IMAGE.search(raw or "")
    if m:
        photo = urljoin(doc_url, m.group(1))
        if urlparse(photo).netloc.endswith(_ADA_CDN):
            found["photo"] = photo

    return found or None


# ─── lilygo image extractor (SPEC-vendor-image-grounding.md, Slice 3) ─────────────
# lilygo product pages are a Shopify store (Dawn theme) at lilygo.cc/products/<slug>. They carry
# NO og:image and NO JSON-LD Product schema, and every image is on an opaque-named CDN
# (…/cdn/shop/products/H579-T-QT-Pro_2.jpg), so the Espressif filename heuristic grounds nothing.
# We key off the Dawn theme's product-media-gallery HTML CONTEXT, uniform across the real fixtures
# (lilygo-t-qt-pro, lilygo-t5-epaper-s3-pro):
#
#   PHOTO — the identifying board hero is the FIRST gallery slide, the one Dawn marks active:
#     `<li … class="product__media-item … is-active …"> … <img src="//lilygo.cc/cdn/shop/…">`.
#     That first-slide <img> is the product's own main shot (T-QT-Pro → H579-T-QT-Pro_2.jpg;
#     T5 → T5-4_7.jpg). We take that <img>'s src, resolve it absolute, strip the ?v=…&width=…
#     Shopify variant query to the canonical image, and ground it ONLY when it is on lilygo's
#     OWN domain (…lilygo.cc). A foreign-domain image in the slot is ignored (safety, mirrors
#     the adafruit own-CDN gate). No active slide → photo omitted.
#
#   PINOUT — OMITTED for lilygo (high-confidence-or-omit; a wrong wiring diagram can fry a board).
#     The only pinout-ish signal on either fixture is a loose `<p><strong>1. Pin Diagram</strong>`
#     bold label inside T-QT-Pro's marketing description blob — NOT a semantic section/anchor
#     (unlike m5stack's `<h2 id="pinmap">`), the image after it has empty alt and a product-shot
#     filename (T-QT-Pro-Lilygo_600x600.jpg, no pin/gpio/diagram token), and the T5 fixture has no
#     pinout marker at all. That is below the confidence bar, so we NEVER promote any image to
#     pinout. (Following a marked pinout diagram, if lilygo ever adds one, is a future slice.)
_LILYGO_ACTIVE_SLIDE = re.compile(
    r'<li[^>]*class="[^"]*\bproduct__media-item\b[^"]*\bis-active\b[^"]*"', re.I)
_LILYGO_SLIDE_END = re.compile(r"</li>", re.I)


def _is_lilygo_domain(netloc: str) -> bool:
    """True only for lilygo's own domain (lilygo.cc or a *.lilygo.cc subdomain/CDN) — a foreign
    host (e.g. an embedded third-party image) is rejected so it never becomes the board photo."""
    return netloc == "lilygo.cc" or netloc.endswith(".lilygo.cc")


def extract_images_lilygo(raw: str, doc_url: str) -> dict | None:
    """Ground lilygo `{photo?}` by lilygo.cc (Shopify Dawn) HTML CONTEXT, absolute URLs.

    photo  = the <img> in the FIRST product-gallery slide (`product__media-item … is-active`),
             resolved absolute with the Shopify variant query stripped to the canonical image,
             grounded ONLY when it is on lilygo's own domain (foreign hosts ignored — safety).
    pinout = ALWAYS omitted for lilygo: no page embeds a semantically-marked pinout diagram, so
             we never promote a product image to pinout (safety: high-confidence-or-omit).
    Returns None when no own-domain active-slide hero is found."""
    raw = raw or ""
    found: dict = {}

    m = _LILYGO_ACTIVE_SLIDE.search(raw)
    if m:
        rest = raw[m.end():]
        end = _LILYGO_SLIDE_END.search(rest)
        slide = rest[: end.start()] if end else rest
        img = _IMG_SRC.search(slide)
        if img:
            photo = urljoin(doc_url, img.group(1)).split("?")[0]
            if _is_lilygo_domain(urlparse(photo).netloc):
                found["photo"] = photo

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
    "adafruit": extract_images_adafruit,
    "lilygo": extract_images_lilygo,
}
