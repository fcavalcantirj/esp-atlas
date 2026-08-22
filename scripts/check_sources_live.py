#!/usr/bin/env python3
"""Check every cited source URL in data/**/*.md is still reachable.

Collects every sources[].url across the dataset, de-duplicates identical
URLs, and HTTP-checks each exactly once with a browser User-Agent, a ~10s
timeout, and up to 2 retries. Some vendor sites 403 bots while the page is
perfectly reachable in a browser, so 200/301/302/403 all count as ALIVE;
only DNS failure, connection error, 404, and 410 count as DEAD. Run locally:

    python3 scripts/check_sources_live.py

Exits non-zero and lists only the DEAD URLs when any are found.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "core" / "src"))

import httpx  # noqa: E402

from esp_atlas_core.frontmatter import iter_data_files, parse_frontmatter  # noqa: E402
from esp_atlas_core.paths import REPO_ROOT  # noqa: E402

TIMEOUT_SECONDS = 10.0
MAX_RETRIES = 2
ALIVE_STATUS_CODES = {200, 301, 302, 403}
DEAD_STATUS_CODES = {404, 410}
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def collect_urls():
    """Return {url: [rel_path, ...]} for every sources[].url in the dataset."""
    urls = {}
    for _kind, path in iter_data_files():
        fm, _body = parse_frontmatter(path)
        rel = str(path.relative_to(REPO_ROOT))
        for source in fm.get("sources") or []:
            url = source.get("url")
            if url:
                urls.setdefault(url, []).append(rel)
    return urls


def check_url(client, url):
    """Return (status, detail) where status is 'ALIVE' or 'DEAD'."""
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.get(url, follow_redirects=False)
        except httpx.RequestError as e:
            last_error = e
            if attempt < MAX_RETRIES:
                continue
            return "DEAD", f"{type(e).__name__}: {e}"

        if response.status_code in DEAD_STATUS_CODES:
            return "DEAD", f"HTTP {response.status_code}"
        if response.status_code in ALIVE_STATUS_CODES:
            return "ALIVE", f"HTTP {response.status_code}"
        # Anything else (5xx, other 3xx/4xx) is retried, then treated as dead.
        last_error = f"HTTP {response.status_code}"
        if attempt < MAX_RETRIES:
            continue
        return "DEAD", last_error

    return "DEAD", str(last_error)


def main():
    urls = collect_urls()
    dead = []

    with httpx.Client(timeout=TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT}) as client:
        for url in sorted(urls):
            status, detail = check_url(client, url)
            print(f"  {'✓' if status == 'ALIVE' else '✗'} {status:5s} {detail:20s} {url}")
            if status == "DEAD":
                dead.append(url)

    print(f"\n{len(urls) - len(dead)}/{len(urls)} URLs alive, {len(dead)} dead")

    if dead:
        print("\nDEAD sources (fix or remove the citing entry):")
        for url in dead:
            for rel in urls[url]:
                print(f"  ✗ {url}  <-  {rel}")

    sys.exit(1 if dead else 0)


if __name__ == "__main__":
    main()
