#!/usr/bin/env python3
"""Check every cited source URL in data/**/*.md is still reachable.

Collects every sources[].url across the dataset, de-duplicates identical
URLs, and HTTP-checks each exactly once with a browser User-Agent and a ~10s
timeout. Some vendor sites 403 bots while the page is perfectly reachable in a
browser, so 200/301/302/403 all count as ALIVE; only 404/410 and a host that
will not resolve count as DEAD.

A third outcome matters: **INCONCLUSIVE**. A 429 or a transient 5xx is the
server declining to answer, which is no evidence at all about whether the link
is broken -- and we now cite enough URLs, many of them on github.com, that a
rate-limit is routine. Reporting that as DEAD is a false accusation against a
perfectly good citation, and a check that cries wolf is one people learn to
ignore -- which would quietly cost us the "every spec cites a live source"
guarantee this script exists to protect. Those retry with backoff (honouring
Retry-After) and, if they still will not answer, are reported separately and do
NOT fail the run.

    python3 scripts/check_sources_live.py

Exits non-zero only when a URL is genuinely DEAD.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "core" / "src"))

import httpx  # noqa: E402

from esp_atlas_core.frontmatter import iter_data_files, parse_frontmatter  # noqa: E402
from esp_atlas_core.paths import REPO_ROOT  # noqa: E402

TIMEOUT_SECONDS = 10.0
MAX_RETRIES = 3
ALIVE_STATUS_CODES = {200, 301, 302, 403}
DEAD_STATUS_CODES = {404, 410}
# The server is refusing to answer right now, not saying the page is gone.
INCONCLUSIVE_STATUS_CODES = {429, 500, 502, 503, 504}
BACKOFF_SECONDS = 2.0
MAX_BACKOFF_SECONDS = 30.0
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


def _retry_after(response, attempt):
    """How long to wait, preferring the server's own Retry-After."""
    header = response.headers.get("retry-after")
    if header:
        try:
            return min(float(header), MAX_BACKOFF_SECONDS)
        except ValueError:
            pass  # HTTP-date form; fall through to our own backoff
    return min(BACKOFF_SECONDS * (2 ** (attempt - 1)), MAX_BACKOFF_SECONDS)


def check_url(client, url, sleep=time.sleep):
    """Return (status, detail): 'ALIVE', 'DEAD', or 'INCONCLUSIVE'."""
    last_detail = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.get(url, follow_redirects=False)
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            # A timeout or a dropped connection says nothing about the page.
            last_detail = f"{type(e).__name__}"
            if attempt < MAX_RETRIES:
                sleep(min(BACKOFF_SECONDS * (2 ** (attempt - 1)), MAX_BACKOFF_SECONDS))
                continue
            return "INCONCLUSIVE", last_detail
        except httpx.RequestError as e:
            # A host that will not resolve, or a malformed URL: really broken.
            return "DEAD", f"{type(e).__name__}: {e}"

        if response.status_code in DEAD_STATUS_CODES:
            return "DEAD", f"HTTP {response.status_code}"
        if response.status_code in ALIVE_STATUS_CODES:
            return "ALIVE", f"HTTP {response.status_code}"
        if response.status_code in INCONCLUSIVE_STATUS_CODES:
            last_detail = f"HTTP {response.status_code}"
            if attempt < MAX_RETRIES:
                sleep(_retry_after(response, attempt))
                continue
            return "INCONCLUSIVE", last_detail
        # An unexpected status: report it as-is rather than guessing.
        return "INCONCLUSIVE", f"HTTP {response.status_code}"

    return "INCONCLUSIVE", str(last_detail)


_MARKS = {"ALIVE": "✓", "DEAD": "✗", "INCONCLUSIVE": "?"}


def main():
    urls = collect_urls()
    dead, inconclusive = [], []

    with httpx.Client(timeout=TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT}) as client:
        for url in sorted(urls):
            status, detail = check_url(client, url)
            print(f"  {_MARKS[status]} {status:13s} {detail:20s} {url}")
            if status == "DEAD":
                dead.append(url)
            elif status == "INCONCLUSIVE":
                inconclusive.append(url)

    alive = len(urls) - len(dead) - len(inconclusive)
    summary = f"\n{alive}/{len(urls)} URLs alive, {len(dead)} dead"
    if inconclusive:
        summary += f", {len(inconclusive)} inconclusive"
    print(summary)

    if dead:
        print("\nDEAD sources (fix or remove the citing entry):")
        for url in dead:
            for rel in urls[url]:
                print(f"  ✗ {url}  <-  {rel}")

    if inconclusive:
        print("\nINCONCLUSIVE (server would not answer — rate-limited or down; NOT a broken link):")
        for url in inconclusive:
            print(f"  ? {url}")

    sys.exit(1 if dead else 0)


if __name__ == "__main__":
    main()
