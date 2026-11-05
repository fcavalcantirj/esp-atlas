"""EspAtlas Jr — declared-board source extractors (jr/board_declared.py).

SPEC-firmware-board-mapping.md §3.1 (manifest tree) and §3.3 (README device table): read the
RAW supported-board references a firmware repo itself declares, so board_resolver.resolve_boards
can map them to the catalog. Two source types, one driver (extract_declared_boards):

  1. manifest tree — a `boards/`, `variants/` or `targets/` directory with one subdir per board
     (ESP-IDF / esp-claw style); the vendor is the parent path segment, the board is the leaf dir
     name. Read from a repo's git-tree listing via derive.py's own `default_api` (`gh api
     repos/OWNER/REPO/git/trees/REF?recursive=1`) — the same call jr/derive.py already makes for
     `platformio_signals`/`ci_signals`; no new HTTP client.
  2. README table — an HTML `<table>` or a markdown table/bullet list under a heading matching
     Supported|Compatible|Devices|Hardware (evil-m5project style). Read via tools.fetch_github_readme
     (`gh api repos/OWNER/REPO/readme --jq .content`) — again, no new HTTP client.

Every extracted raw ref keeps its source URL + source type for provenance (SPEC §3). Mapping a
raw ref to a catalog board id is entirely board_resolver's job (SPEC §4) — this module only reads
what a repo declares, and never writes.
"""
from __future__ import annotations

import html
import re

import board_resolver
import derive
import tools

# --- source 1: manifest tree (SPEC §3.1) ---------------------------------------------------------

_MANIFEST_DIR_RE = re.compile(r"(?:^|/)(boards|variants|targets)/([^/]+)/([^/]+)/")

# A manifest dir under one of these segments belongs to a vendored / third-party / study copy of
# someone else's tree, not to the firmware's own build (SPEC §3.1 — NucleoOS's
# `reference/esp-claw/.../boards` is "study material only"). Matched case-insensitively, as whole
# path segments, and only BEFORE the manifest dir (after it, the segment is the vendor slot).
_VENDORED_SEGMENTS = frozenset({
    "reference", "references", "third_party", "third-party", "thirdparty", "vendor", "vendored",
    "external", "extern", "deps", "managed_components",
})


def _is_vendored(root: str) -> bool:
    return any(seg.lower() in _VENDORED_SEGMENTS for seg in root.split("/")[:-1])


def manifest_tree_refs(tree_paths: list[str]) -> dict:
    """Raw board leaf-dir names from the firmware's OWN `boards/`/`variants/`/`targets/` manifest
    trees in `tree_paths` (a flat blob-path listing, e.g. from a git-trees API call). A manifest
    dir may sit at any depth (esp-claw's lives at `application/edge_agent/boards/...`), but one
    under a vendored / third-party / study segment (_VENDORED_SEGMENTS) is skipped. Vendor is the
    parent path segment; only the leaf dir name is returned as the raw ref — the bare name is
    what board_resolver.resolve() expects (its own oracle keys off e.g. 'm5stack_cores3', not
    'm5stack/m5stack_cores3'). Returns {"refs": [...] (first-seen order, deduped),
    "roots": [<manifest dir path, e.g. 'application/edge_agent/boards'>, ...] (first-seen order),
    "ref_roots": {ref: <the root it was first found under>}, "root": roots[0] | None}."""
    refs: list[str] = []
    roots: list[str] = []
    ref_roots: dict[str, str] = {}
    for path in tree_paths:
        m = _MANIFEST_DIR_RE.search(path)
        if not m:
            continue
        root = path[: m.end(1)]
        if _is_vendored(root):
            continue
        board = m.group(3)
        if board in ref_roots:
            continue
        if root not in roots:
            roots.append(root)
        refs.append(board)
        ref_roots[board] = root
    return {"refs": refs, "root": roots[0] if roots else None, "roots": roots, "ref_roots": ref_roots}


def extract_manifest_tree(owner_repo: str, ref: str, api=derive.default_api) -> dict:
    """Fetch `owner_repo`@`ref`'s git tree and run manifest_tree_refs over it. `api` defaults to
    derive.default_api (`gh api <path>`, authenticated) — the injected callable tests replace with
    a fake. Returns {"refs": [...], "source_url": <first root's github tree URL> | None,
    "source_type": "manifest_tree", "source_urls": {root: <that root's github tree URL>},
    "ref_roots": {ref: root}}; cite a ref via source_urls[ref_roots[ref]] (ref_source_url), never
    via `source_url`, which is kept only for back-compat and names just the first root.
    `source_url` is None (and everything else empty) when the repo has no first-party manifest dir."""
    tree_doc = api(f"repos/{owner_repo}/git/trees/{ref}?recursive=1")
    paths = [
        t["path"] for t in (tree_doc.get("tree") or [])
        if isinstance(t, dict) and t.get("type") == "blob" and t.get("path")
    ] if isinstance(tree_doc, dict) else []
    found = manifest_tree_refs(paths)
    source_urls = {root: f"https://github.com/{owner_repo}/tree/{ref}/{root}" for root in found["roots"]}
    return {
        "refs": found["refs"],
        "source_url": source_urls.get(found["root"]),
        "source_type": "manifest_tree",
        "source_urls": source_urls,
        "ref_roots": found["ref_roots"],
    }


def ref_source_url(source: dict, raw: str) -> str | None:
    """The URL that cites `raw` within an extractor result: its own manifest root's URL when the
    source carries per-ref roots (extract_manifest_tree), else the source's single `source_url`."""
    root = (source.get("ref_roots") or {}).get(raw)
    return (source.get("source_urls") or {}).get(root) or source["source_url"]


# --- source 2: README device table (SPEC §3.3) ---------------------------------------------------

_ATX_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_HTML_HEADING_RE = re.compile(r"<h[1-6][^>]*>(.*?)</h[1-6]>", re.I)
_SECTION_KEYWORD_RE = re.compile(r"supported|compatible|devices|hardware", re.I)
_TABLE_RE = re.compile(r"<table\b[^>]*>(.*?)</table>", re.I | re.S)
_ROW_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.I | re.S)
_TD_RE = re.compile(r"<td\b[^>]*>(.*?)</td>", re.I | re.S)
_TH_RE = re.compile(r"<th\b", re.I)
_BULLET_RE = re.compile(r"^\s*[-*]\s+(.*)$")
_ACCESSORY_RE = re.compile(r"\b(module|unit|base|hat|kit|sensor)\b", re.I)
_VERSION_SUFFIX_RE = re.compile(r"\bv\d+(\.\d+)*$", re.I)


def _clean_cell(raw: str) -> str:
    """A table/list cell's device NAME, not the surrounding annotation: strips tags, a leading
    tree marker (`↳ GPS Module`), a leading label before a colon (`Better one : M5Cardputer` ->
    `M5Cardputer`), and a trailing parenthetical (`M5AtomS3 (GPS needed)` -> `M5AtomS3`)."""
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw)).strip()
    text = re.sub(r"^[↳\-\*\s]+", "", text)
    if ":" in text:
        text = text.rsplit(":", 1)[1].strip()
    text = re.sub(r"\s*\([^)]*\)\s*$", "", text).strip()
    return text


def _html_table_refs(block: str) -> list[str]:
    out: list[str] = []
    for table in _TABLE_RE.findall(block):
        for row in _ROW_RE.findall(table):
            if _TH_RE.search(row):
                continue                            # header row
            cells = _TD_RE.findall(row)
            name = _clean_cell(cells[0]) if cells else ""
            if name:
                out.append(name)
    return out


def _markdown_table_refs(lines: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(lines):
        if not lines[i].lstrip().startswith("|"):
            i += 1
            continue
        block = []
        while i < len(lines) and lines[i].lstrip().startswith("|"):
            block.append(lines[i])
            i += 1
        for row in block[2:]:                       # skip header row + `|---|---|` separator
            cells = [c.strip() for c in row.strip().strip("|").split("|")]
            name = _clean_cell(cells[0]) if cells and cells[0] else ""
            if name:
                out.append(name)
    return out


def _bullet_list_refs(lines: list[str]) -> list[str]:
    out = []
    for line in lines:
        m = _BULLET_RE.match(line)
        if m:
            name = _clean_cell(m.group(1))
            if name:
                out.append(name)
    return out


def readme_table_refs(text: str) -> list[str]:
    """Device names from README tables/bullet lists under a heading matching Supported|Compatible
    |Devices|Hardware (case-insensitive). A heading is a markdown ATX line (`## ...`) OR a single
    inline HTML `<h1-6>...</h1-6>` (evil-m5project nests one inside a matching markdown section) —
    either kind closes the PRECEDING section, so a table under a non-matching heading (e.g. a
    "🧪 In Beta" table sitting right after a matching "🧱 M5Stack Devices" one) is never pulled in
    just because it is a markdown descendant. Prose paragraphs are never scanned — only fenced
    HTML tables, markdown tables, and markdown bullet lists. First-seen order, deduped.

    Two hardening rules apply to every row/cell, regardless of which heading it sits under:
      - an accessory/module name (contains Module/Unit/Base/Hat/Kit/Sensor as a whole word, e.g.
        "GPS Module", "LLM Module") is never emitted as a device ref — it names a peripheral you
        attach to a board, not a board;
      - a version-suffixed device row (e.g. "M5Stick v1.1", "M5Stick v2") IS captured even under a
        heading that doesn't match the Supported/Compatible/Devices/Hardware keywords — firmware
        READMEs often park still-supported hardware under a non-matching heading like "In Beta",
        and a trailing "vN[.N...]" is a strong enough device-row signal on its own to pull it in
        without inheriting that heading's noise (a name with no version suffix under a non-matching
        heading, e.g. "CYD2USB", is still left alone)."""
    lines = text.splitlines()
    headings: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        m = _ATX_HEADING_RE.match(line)
        if m:
            headings.append((i, m.group(2)))
            continue
        m = _HTML_HEADING_RE.search(line)
        if m:
            headings.append((i, html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()))

    refs: list[str] = []
    for idx, (line_no, heading_text) in enumerate(headings):
        matches_heading = bool(_SECTION_KEYWORD_RE.search(heading_text))
        start = line_no + 1
        end = headings[idx + 1][0] if idx + 1 < len(headings) else len(lines)
        section_lines = lines[start:end]
        section_text = "\n".join(section_lines)
        for name in (_html_table_refs(section_text) + _markdown_table_refs(section_lines)
                    + _bullet_list_refs(section_lines)):
            if _ACCESSORY_RE.search(name):
                continue                                 # accessory/module, never a board ref
            if not matches_heading and not _VERSION_SUFFIX_RE.search(name):
                continue                                 # non-matching heading, no version signal
            if name not in refs:
                refs.append(name)
    return refs


def extract_readme_table(owner_repo: str, fetch=None) -> dict:
    """Fetch `owner_repo`'s README and run readme_table_refs over it. `fetch` defaults to
    tools.fetch_github_readme with a generous max_chars (the default 3500 truncates mid-table on
    evil-m5project's own README) — the injected callable tests replace with a fake. Returns
    {"refs": [...], "source_url": <github readme anchor>, "source_type": "readme_table"}."""
    if fetch is None:
        fetch = lambda url: tools.fetch_github_readme(url, max_chars=20000)  # noqa: E731
    repo_url = f"https://github.com/{owner_repo}"
    text = fetch(repo_url) or ""
    return {"refs": readme_table_refs(text), "source_url": repo_url + "#readme", "source_type": "readme_table"}


# --- driver ----------------------------------------------------------------------------------------

def extract_declared_boards(owner_repo: str, ref: str | None = None, *,
                            manifest_api=derive.default_api, readme_fetch=None) -> dict:
    """Run every applicable declared-board source for `owner_repo`, union the raw refs (each kept
    with the source that first named it), resolve through board_resolver.resolve_boards, and
    return {"resolved": {board_id: {"source_url", "source_type"}}, "unresolved": [raw, ...],
    "socs": [...]} — the union of the resolved boards' chip families (tools.board_soc), never a
    SoC pulled from an unresolved raw ref (SPEC §4: resolve to a board first, never guess a chip
    for a name the catalog doesn't carry). `ref` defaults to the repo's default branch."""
    if ref is None:
        meta = manifest_api(f"repos/{owner_repo}")
        ref = (meta.get("default_branch") if isinstance(meta, dict) else None) or "main"

    manifest = extract_manifest_tree(owner_repo, ref, api=manifest_api)
    readme = extract_readme_table(owner_repo, fetch=readme_fetch)

    source_of: dict[str, dict] = {}
    ordered_raws: list[str] = []
    for source in (manifest, readme):
        for raw in source["refs"]:
            if raw not in source_of:
                source_of[raw] = {"source_url": ref_source_url(source, raw), "source_type": source["source_type"]}
                ordered_raws.append(raw)

    result = board_resolver.resolve_boards(ordered_raws)
    resolved = {board_id: source_of[raw] for raw, board_id in result["resolved"].items()}
    socs = sorted({soc for board_id in resolved for soc in [tools.board_soc(board_id)] if soc})
    return {"resolved": resolved, "unresolved": result["unresolved"], "socs": socs}
