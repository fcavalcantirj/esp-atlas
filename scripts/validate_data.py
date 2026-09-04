#!/usr/bin/env python3
"""Whole-data semantic validator for esp-atlas firmware entries.

For every data/firmware/<id>/firmware.md, cross-checks the hand-authored
`category` against the SAME deterministic classifier jr/scorer.py uses when it
authors a new entry (_category_from_purpose, falling back to
_category_from_capabilities) -- reused verbatim, never reimplemented, so
hand-authored data and jr's own authoring path can never silently drift apart.
Also flags data holes: empty capabilities, missing url, missing sources.

    python3 scripts/validate_data.py            # miscategorizations + holes
    python3 scripts/validate_data.py --links     # + dead/broken source URLs

Exits non-zero only when a MISCATEGORIZATION is found. Holes (and, with
--links, dead source URLs) are reported as warnings and never affect the
exit code on their own -- scripts/check_sources_live.py is the dedicated,
already-existing gate for dead links.
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# apps/core/src MUST go on sys.path before `import scorer`: scorer imports tools, which imports
# normalize, which imports esp_atlas_core. jr/normalize.py only ever inserts jr/ itself, so on a
# clean checkout (no `pip install -e apps/core`) importing scorer first dies with
# ModuleNotFoundError: esp_atlas_core. It worked locally only because the package happened to be
# installed. Order is load-bearing; do not "tidy" these two blocks back together.
_CORE_SRC = REPO_ROOT / "apps" / "core" / "src"
if str(_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_CORE_SRC))
from esp_atlas_core.frontmatter import parse_frontmatter  # noqa: E402

_JR_DIR = REPO_ROOT / "jr"
if str(_JR_DIR) not in sys.path:
    sys.path.insert(0, str(_JR_DIR))
import scorer  # noqa: E402

FIRMWARE_GLOB = "firmware/*/firmware.md"


def iter_firmware_files(data_dir):
    """Yield every data/firmware/<id>/firmware.md Path under `data_dir`, sorted for
    deterministic report ordering."""
    return sorted(Path(data_dir).glob(FIRMWARE_GLOB))


def expected_category(name, capabilities, body_text):
    """The category jr/scorer.py's own classifier would pick for this entry.

    Mirrors jr/scorer.score_entry()'s own `category = _category_from_purpose(...)
    or _category_from_capabilities(...)` line exactly, just fed from an authored
    firmware.md instead of a fresh launcher-catalog entry + live repo_meta: `name`
    plays the entry name, and the firmware.md body plays both repo_meta's
    description and its readme_title (scorer only ever joins the three into one
    lowercased keyword pool, so which of the two body-text slots it lands in
    makes no difference). Returns (category, signal) where signal is "purpose"
    when a name/body keyword drove the decision, or "capabilities" when it fell
    back to the stored capability tokens.
    """
    purpose_category = scorer._category_from_purpose(name, body_text, None)
    if purpose_category is not None:
        return purpose_category, "purpose"
    return scorer._category_from_capabilities(capabilities or []), "capabilities"


def check_entry(path):
    """Parse one firmware.md and return (miscategorization_or_None, [hole, ...])."""
    fm, body = parse_frontmatter(path)
    entry_id = fm.get("id") or path.parent.name
    stored_category = fm.get("category")
    capabilities = fm.get("capabilities") or []
    name = fm.get("name") or ""

    expected, signal = expected_category(name, capabilities, body)

    miscategorization = None
    if stored_category != expected:
        miscategorization = {
            "id": entry_id,
            "stored": stored_category,
            "expected": expected,
            "signal": signal,
        }

    holes = []
    if not capabilities:
        holes.append({"id": entry_id, "reason": "empty capabilities list"})
    if not fm.get("url"):
        holes.append({"id": entry_id, "reason": "missing url"})
    if not fm.get("sources"):
        holes.append({"id": entry_id, "reason": "missing sources"})

    return miscategorization, holes


def _collect_source_urls(paths):
    """{url: [firmware_id, ...]} for every sources[].url across `paths`."""
    urls = {}
    for path in paths:
        fm, _body = parse_frontmatter(path)
        entry_id = fm.get("id") or path.parent.name
        for source in fm.get("sources") or []:
            url = source.get("url")
            if url:
                urls.setdefault(url, []).append(entry_id)
    return urls


def check_links(paths):
    """Reuse scripts/check_sources_live.py's own HTTP-checking logic (never
    reimplemented) to flag dead/broken source URLs among `paths`. Returns a list
    of {id, url, status, detail} for every URL that isn't ALIVE."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import check_sources_live as csl  # noqa: E402

    urls = _collect_source_urls(paths)
    broken = []
    with csl.httpx.Client(timeout=csl.TIMEOUT_SECONDS, headers={"User-Agent": csl.USER_AGENT}) as client:
        for url in sorted(urls):
            status, detail = csl.check_url(client, url)
            if status != "ALIVE":
                for entry_id in urls[url]:
                    broken.append({"id": entry_id, "url": url, "status": status, "detail": detail})
    return broken


_SIGNAL_LABELS = {
    "purpose": "purpose keyword in name/body text",
    "capabilities": "capability fallback (stored capabilities)",
}


def run(data_dir, check_links_too=False):
    """Validate every firmware.md under `data_dir` and return a report dict:
    {miscategorizations: [...], holes: [...], broken_links: [...], exit_code: int}.
    A missing/empty `data_dir` simply yields an empty, all-clear report."""
    paths = iter_firmware_files(data_dir)

    miscategorizations = []
    holes = []
    for path in paths:
        miscategorization, entry_holes = check_entry(path)
        if miscategorization:
            miscategorizations.append(miscategorization)
        holes.extend(entry_holes)

    broken_links = check_links(paths) if check_links_too else []

    return {
        "miscategorizations": miscategorizations,
        "holes": holes,
        "broken_links": broken_links,
        "exit_code": 1 if miscategorizations else 0,
    }


def print_report(report):
    miscategorizations = report["miscategorizations"]
    holes = report["holes"]
    broken_links = report["broken_links"]

    print("MISCATEGORIZATIONS:")
    if miscategorizations:
        for m in miscategorizations:
            print(f"  ✗ {m['id']}: stored={m['stored']!r} expected={m['expected']!r} "
                  f"(signal: {_SIGNAL_LABELS[m['signal']]})")
    else:
        print("  none")

    print("\nDATA HOLES (warnings only):")
    if holes:
        for h in holes:
            print(f"  ⚠ {h['id']}: {h['reason']}")
    else:
        print("  none")

    if broken_links:
        print("\nBROKEN SOURCE LINKS (warnings only):")
        for b in broken_links:
            print(f"  ⚠ {b['id']}: {b['status']} ({b['detail']}) {b['url']}")

    summary = (f"\n{len(miscategorizations)} miscategorization(s), {len(holes)} hole(s)")
    if report.get("broken_links") or broken_links:
        summary += f", {len(broken_links)} broken link(s)"
    print(summary)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", default=None,
                         help="override the data/ root to scan (mainly for tests); "
                              "defaults to <repo root>/data")
    parser.add_argument("--links", action="store_true",
                         help="also run scripts/check_sources_live.py's checks and "
                              "include dead/broken source URLs in the report")
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir) if args.data_dir else (REPO_ROOT / "data")
    report = run(data_dir, check_links_too=args.links)
    print_report(report)
    return report["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
