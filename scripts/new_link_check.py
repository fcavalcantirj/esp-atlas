#!/usr/bin/env python3
"""Check on the links a PR ADDS or CHANGES (scripts/new_link_check.py).

Owner rule: a confirmed 404 or 410 on a link the PR adds or changes fails this check. Nothing
else does. It runs as a pull_request-only step of the REQUIRED `schema` CI check, so that
failure blocks merge. Timeouts, DNS and TLS failures, 429, 5xx, a 403 from a bot wall and any
other odd status are INCONCLUSIVE -- the server declined to answer, which says nothing about
the link -- and exit 0.
Links already broken on main are never looked at here (they sit on lines the PR did not
touch); the non-blocking `sources-live` job tracks those.

How:
  1. `git diff <base>...HEAD -- data/` (the merge base, so main moving on is not the PR's doing);
  2. every URL on an added or changed line of a data text file (.md frontmatter fields and
     sources, body links, .json/.yml cited-source fields), de-duplicated ignoring #fragments.
     The URL checked is the one the author wrote: JSON/YAML/markdown escapes are decoded first
     (https:\\/\\/x is https://x), and punctuation inside quotes, a markdown (target) or an
     <autolink> is kept, as is the whole of an unquoted YAML value that is the URL
     (`url: https://x/a!` in a .yml/.yaml file or in .md frontmatter, read at HEAD); only a
     bare URL in prose drops trailing sentence punctuation;
  3. each checked once: HEAD, then GET when HEAD is not a clean yes; a 404/410 GET is asked
     again after a short pause and is DEAD only if it says so twice. Short timeout, small
     concurrency cap, a User-Agent that says who we are.

    python3 scripts/new_link_check.py              # base origin/$GITHUB_BASE_REF or origin/main

Exit 0: no dead link · 1: at least one confirmed dead link · 2: the diff could not be taken.
Stdlib only, so the CI job needs no installs.
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TIMEOUT_SECONDS = 10.0
RECHECK_DELAY_SECONDS = 2.0
CONCURRENCY = 4
USER_AGENT = "esp-atlas-new-link-check/1.0 (+https://github.com/fcavalcantirj/esp-atlas)"
DEAD_STATUS_CODES = {404, 410}
DATA_PREFIX = "data/"
TEXT_SUFFIXES = (".md", ".json", ".yml", ".yaml")

ALIVE, DEAD, INCONCLUSIVE = "alive", "dead", "inconclusive"

_BARE = re.compile(r"https?:(?:\\?/){2}[^\s<>\"`\[\]{}|^]+")  # https:\/\/ too: a JSON-escaped scheme
_TOKEN = re.compile(r"\"|'(?=https?:)|<(?=https?:)|\]\(|https?:(?:\\?/){2}")
_DOUBLE_QUOTED = re.compile(r'"((?:[^"\\]|\\.)*)"')
_SINGLE_QUOTED = re.compile(r"'((?:[^']|'')*)'")
_AUTOLINK = re.compile(r"<(https?://[^\s<>]*)>")
_WHOLE_URL = re.compile(r"https?://\S+")
_TRAILING = ".,;:!?*'"
_ESCAPED = re.compile(r"\\([!-/:-@\[-`{-~])")  # markdown/JSON backslash escapes: my\_repo, \/
_UNICODE_ESCAPE = re.compile(r"\\u([0-9a-fA-F]{4})")
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
_YAML_PLAIN_URL = re.compile(r"[ \t]*(?:(?:-[ \t]+)+(?:[\w.-]+:[ \t]+)?|[\w.-]+:[ \t]+)(?=https?://)")
_YAML_COMMENT = re.compile(r"[ \t]#")
YAML_SUFFIXES = (".yml", ".yaml")
FRONTMATTER_FENCES = ("---", "...")


# --- what the PR added ---------------------------------------------------------------------

def _is_checked_file(path: str | None) -> bool:
    return bool(path) and path.startswith(DATA_PREFIX) and path.endswith(TEXT_SUFFIXES)


def added_lines(diff_text: str) -> list[tuple[str, int, str]]:
    """(path, new-file line number, text) for every added line of a data text file.

    A `+++ b/<path>` line is a file header only before the first hunk of a file; inside a hunk
    it is content that happens to start with '++'."""
    out, path, line_no, in_hunk = [], None, 0, False
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            path, in_hunk = None, False
        elif not in_hunk and line.startswith("+++ "):
            target = line[4:].strip().strip('"')
            path = target[2:] if target.startswith("b/") else None
        elif m := _HUNK.match(line):
            in_hunk, line_no = True, int(m.group(1))
        elif in_hunk and line.startswith("+"):
            if _is_checked_file(path):
                out.append((path, line_no, line[1:]))
            line_no += 1
        elif in_hunk and line.startswith(" "):
            line_no += 1
    return out


def _trim(url: str) -> str:
    """Drop sentence punctuation and a closing paren that belongs to the prose, not the URL."""
    while url:
        if url[-1] in _TRAILING:
            url = url[:-1]
        elif url[-1] == ")" and url.count(")") > url.count("("):
            url = url[:-1]
        else:
            break
    return url


def _unescape(text: str) -> str:
    return _ESCAPED.sub(r"\1", text)


def _json_string(raw: str) -> str:
    """A "..." body decoded as JSON (also right for YAML double quotes); unknown escapes such as
    markdown's my\\_repo fall back to dropping the backslash, \\uXXXX still decoded."""
    try:
        return json.loads(f'"{raw}"')
    except ValueError:
        return _unescape(_UNICODE_ESCAPE.sub(lambda m: chr(int(m.group(1), 16)), raw))


def _delimited(value: str) -> list[str]:
    """A quoted value that IS a URL is taken exactly -- its punctuation is the author's; a value
    that merely contains one is prose."""
    if _WHOLE_URL.fullmatch(value.strip()):
        return [value.strip()]
    return _scan(value)


def _read_double_quoted(text: str, at: int):
    m = _DOUBLE_QUOTED.match(text, at)
    return (_delimited(_json_string(m.group(1))), m.end()) if m else ([], at + 1)


def _read_single_quoted(text: str, at: int):
    """YAML single quotes: no backslash escapes; a literal ' is written ''."""
    m = _SINGLE_QUOTED.match(text, at)
    return (_delimited(m.group(1).replace("''", "'")), m.end()) if m else ([], at + 1)


def _read_autolink(text: str, at: int):
    m = _AUTOLINK.match(text, at)
    return ([m.group(1)], m.end()) if m else ([], at + 1)


def _read_link_target(text: str, at: int):
    """[text](target "title"): the target runs to the matching paren, backslash escapes aside."""
    depth, i = 1, at + 2
    while i < len(text) and depth:
        depth += {"(": 1, ")": -1}.get(text[i], 0)
        i += 2 if text[i] == "\\" else 1
    if depth:
        return [], at + 2
    inner = text[at + 2:i - 1].strip()
    target = inner[1:].split(">", 1)[0] if inner.startswith("<") else (inner.split() or [""])[0]
    target = _unescape(target)
    return ([target] if _WHOLE_URL.fullmatch(target) else []), i


def _read_bare(text: str, at: int):
    m = _BARE.match(text, at)
    return ([_trim(_unescape(m.group()))], m.end()) if m else ([], at + 1)


_READERS = {'"': _read_double_quoted, "'": _read_single_quoted, "<": _read_autolink,
            "]": _read_link_target, "h": _read_bare}


def _scan(text: str) -> list[str]:
    urls, pos = [], 0
    while m := _TOKEN.search(text, pos):
        found, pos = _READERS[m.group()[0]](text, m.start())
        urls.extend(found)
    return urls


def _yaml_scan(line: str) -> list[str]:
    """A plain (unquoted) YAML value -- `url: x`, `- url: x`, `- x` -- that is the whole URL is
    taken exactly: YAML has no escapes there and no sentence to end. A ` #` comment after it,
    and every other shape (quoted, flow, a value that is prose), reads as anywhere else."""
    m = _YAML_PLAIN_URL.match(line)
    if not m:
        return _scan(line)
    value, *comment = _YAML_COMMENT.split(line[m.end():], 1)
    return _delimited(value) + _scan("".join(comment))


def urls_in(line: str, yaml: bool = False) -> list[str]:
    """Every URL on a line, exactly as its author wrote it.

    Structured escapes are decoded before discovery (JSON/YAML "https:\\/\\/x", markdown
    my\\_repo, YAML 'it''s'). Punctuation inside an explicit delimiter -- a quoted value that is
    the whole URL, a markdown (target) or an <autolink> -- belongs to the URL, and so does a
    plain YAML value that is the whole URL when the line is YAML; only a bare URL in prose
    loses trailing sentence punctuation."""
    found = _yaml_scan(line) if yaml else _scan(line)
    return [url for url in found if _WHOLE_URL.fullmatch(url)]


def frontmatter_span(text: str) -> range:
    """Line numbers (1-based) between a markdown file's opening --- and its closing ---/...;
    empty when the file has no closed frontmatter."""
    lines = text.splitlines()
    if not lines or lines[0].rstrip() != FRONTMATTER_FENCES[0]:
        return range(0)
    for line_no, line in enumerate(lines[1:], start=2):
        if line.rstrip() in FRONTMATTER_FENCES:
            return range(2, line_no)
    return range(0)


def _at_head(repo: Path, path: str) -> str:
    """The file as the PR leaves it (the side the diff's line numbers count); "" when git cannot
    show it, so its lines read as prose -- never a reason to fail the check."""
    try:
        shown = subprocess.run(["git", "show", f"HEAD:{path}"], cwd=repo, capture_output=True,
                               text=True, errors="replace", timeout=60)
    except (subprocess.TimeoutExpired, OSError):
        return ""
    return shown.stdout if shown.returncode == 0 else ""


def yaml_lines(repo: Path, lines) -> set[tuple[str, int]]:
    """(path, line) of every added line that is YAML: all of a .yml/.yaml file, and the
    frontmatter of a .md file -- its body is prose, however YAML-shaped a line looks."""
    spans: dict[str, range] = {}
    out = set()
    for path, line_no, _ in lines:
        if path.endswith(".md") and path not in spans:
            spans[path] = frontmatter_span(_at_head(repo, path))
        if path.endswith(YAML_SUFFIXES) or line_no in spans.get(path, ()):
            out.add((path, line_no))
    return out


def extract_urls(lines, yaml=frozenset()) -> dict[str, list[tuple[str, int]]]:
    """{url without #fragment: [(path, line), ...]} in first-seen order; `yaml` holds the
    (path, line) pairs to read as YAML."""
    found: dict[str, list[tuple[str, int]]] = {}
    for path, line_no, text in lines:
        for url in urls_in(text, yaml=(path, line_no) in yaml):
            found.setdefault(url.split("#", 1)[0], []).append((path, line_no))
    return found


# --- is it alive? --------------------------------------------------------------------------

def _request(url: str, method: str, timeout: float) -> tuple[int | None, str]:
    """(HTTP status, detail); status None when the server never answered -- or was never asked,
    because the URL is too malformed to build a request from (http://[ is a ValueError)."""
    try:
        req = urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, f"HTTP {response.status}"
    except urllib.error.HTTPError as e:
        return e.code, f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return None, f"{type(e.reason).__name__}"
    except (TimeoutError, OSError, http.client.HTTPException, ValueError) as e:
        return None, type(e).__name__


def _ok(status: int | None) -> bool:
    return status is not None and 200 <= status < 400


def check_url(url: str, timeout: float = TIMEOUT_SECONDS, recheck_delay: float = RECHECK_DELAY_SECONDS,
              sleep=time.sleep) -> tuple[str, str]:
    """(alive|dead|inconclusive, detail). Dead takes two 404/410 GETs in a row."""
    status, detail = _request(url, "HEAD", timeout)
    if _ok(status):
        return ALIVE, detail
    status, detail = _request(url, "GET", timeout)
    if _ok(status):
        return ALIVE, detail
    if status not in DEAD_STATUS_CODES:
        return INCONCLUSIVE, detail
    sleep(recheck_delay)
    again, again_detail = _request(url, "GET", timeout)
    if again in DEAD_STATUS_CODES:
        return DEAD, f"HTTP {status}, then {again}"
    if _ok(again):
        return ALIVE, f"HTTP {status}, then {again}"
    return INCONCLUSIVE, f"HTTP {status}, then {again_detail}"


def check_all(urls, concurrency: int = CONCURRENCY, **kwargs) -> dict[str, tuple[str, str]]:
    unique = list(dict.fromkeys(urls))
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        return dict(zip(unique, pool.map(lambda u: check_url(u, **kwargs), unique)))


# --- report --------------------------------------------------------------------------------

_MARKS = {ALIVE: "✓", DEAD: "✗", INCONCLUSIVE: "?"}
_ORDER = {DEAD: 0, INCONCLUSIVE: 1, ALIVE: 2}


def render_table(found, results) -> str:
    rows = sorted(found, key=lambda u: (_ORDER[results[u][0]], u))
    width = max([len(results[u][1]) for u in rows] + [len("DETAIL")])
    lines = [f"  {'STATUS':14s} {'DETAIL':{width}s}  URL  <-  WHERE"]
    for url in rows:
        status, detail = results[url]
        where = ", ".join(f"{p}:{n}" for p, n in found[url])
        lines.append(f"  {_MARKS[status]} {status.upper():12s} {detail:{width}s}  {url}  <-  {where}")
    return "\n".join(lines)


def _diff(repo: Path, base: str) -> subprocess.CompletedProcess:
    """Bytes that are not UTF-8 are replaced, never fatal: only a dead link may fail the check."""
    return subprocess.run(["git", "-c", "core.quotePath=false", "diff", "--no-color", "--no-ext-diff",
                           "-M", "--unified=0", f"{base}...HEAD", "--", DATA_PREFIX],
                          cwd=repo, capture_output=True, text=True, errors="replace", timeout=120)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=None, help="base ref (default origin/$GITHUB_BASE_REF, else origin/main)")
    ap.add_argument("--repo", type=Path, default=REPO)
    ap.add_argument("--timeout", type=float, default=TIMEOUT_SECONDS)
    ap.add_argument("--recheck-delay", type=float, default=RECHECK_DELAY_SECONDS)
    ap.add_argument("--concurrency", type=int, default=CONCURRENCY)
    args = ap.parse_args(argv)
    base = args.base or (f"origin/{os.environ['GITHUB_BASE_REF']}" if os.environ.get("GITHUB_BASE_REF") else "origin/main")

    try:
        diff = _diff(args.repo, base)
    except subprocess.TimeoutExpired:
        print(f"::error::git diff against {base} timed out")
        return 2
    if diff.returncode != 0:
        print(f"::error::git diff against {base} failed: {diff.stderr.strip()[:200]}")
        return 2
    lines = added_lines(diff.stdout)
    found = extract_urls(lines, yaml=yaml_lines(args.repo, lines))
    if not found:
        print(f"new-link check: no added or changed URLs under {DATA_PREFIX} (base {base})")
        return 0

    results = check_all(found, concurrency=args.concurrency, timeout=args.timeout, recheck_delay=args.recheck_delay)
    print(render_table(found, results))
    counts = {s: sum(1 for v in results.values() if v[0] == s) for s in (ALIVE, DEAD, INCONCLUSIVE)}
    print(f"\nnew-link check: {len(found)} URL(s) on added/changed lines (base {base}) — "
          f"{counts[ALIVE]} alive, {counts[DEAD]} dead, {counts[INCONCLUSIVE]} inconclusive")
    for url, (status, detail) in results.items():
        if status == DEAD:
            for path, line_no in found[url]:
                print(f"::error file={path},line={line_no}::Dead link ({detail}, confirmed): {url}")
    if counts[INCONCLUSIVE]:
        print("Inconclusive links never block (timeout, rate limit, 5xx, bot wall): worth a manual look.")
    return 1 if counts[DEAD] else 0


if __name__ == "__main__":
    sys.exit(main())
