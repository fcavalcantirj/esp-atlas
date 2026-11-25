#!/usr/bin/env python3
"""Every quoted sentence in a record must appear on a page the record cites (scripts/check_quotes.py).

The motto is "100% of esp-atlas info is verified and verifiable": a hard spec is quoted verbatim from a
cited page or omitted. Until 2026-11-17 the verbatim part was checked by a human reading the page during
review (the Freenove ESP32-WROVER review, #1800, was exactly that). This script is that reading, made
mechanical, so Jr's own demand PRs can be judged by a machine:

  1. the records: every `data/**/*.md` the PR adds or changes (`git diff <base>...HEAD`), or the whole
     catalog with `--all`;
  2. the quotes: every double-quoted span of at least MIN_QUOTE characters EMBEDDED in a frontmatter
     string value (straight or curly quotes), in any field but `sources`. A YAML scalar that is merely
     written with double quotes (`name: "ESP32-WROVER"`) is not a quote: values are read after
     yaml.safe_load, so the delimiters are gone;
  3. the pages: every `sources[].url` of the record, fetched once per run (a GitHub `blob` URL is read
     raw; a PDF is read with pypdf when it is installed), reduced to text and normalized the same way
     as the quote: curly quotes and dashes straightened, "×" read as "x", a table "|" as a space, soft
     hyphens dropped, every whitespace removed, case folded. A quote with an elision ("...") is its
     fragments, each of which must appear, in order;
  4. the verdict per quote: PASS when a readable cited page contains it; FAIL when every cited page was
     readable and none contains it; INCONCLUSIVE when at least one cited page could not be read (a
     timeout, 403 bot wall, 429, 5xx, a PDF with no reader) and no readable page contains it. As in
     check_sources_live.py, a server that will not answer is never evidence against a citation.

A record FAILs when any of its quotes FAILs. Exit 0: no FAIL. Exit 1: at least one FAIL. Exit 2: the
diff could not be taken. The receipt (one line per quote: verdict, URL, the quote) is the job log.

    python3 scripts/check_quotes.py                 # records changed vs origin/$GITHUB_BASE_REF or origin/main
    python3 scripts/check_quotes.py --all           # the whole catalog (the baseline measurement)
    python3 scripts/check_quotes.py data/boards/freenove/freenove-esp32-wrover/board.md
"""
from __future__ import annotations

import argparse
import html
import io
import os
import re
import subprocess
import sys
import time
import unicodedata
from dataclasses import dataclass, field

import yaml
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "apps" / "core" / "src"))

try:
    import httpx
except ImportError:  # the offline paths (tests, --help) never need it
    httpx = None

from esp_atlas_core.frontmatter import iter_data_files, parse_frontmatter  # noqa: E402

MIN_QUOTE = 12
TIMEOUT_SECONDS = 15.0
MAX_RETRIES = 3
BACKOFF_SECONDS = 2.0
MAX_BACKOFF_SECONDS = 30.0
MAX_BYTES = 25 * 1024 * 1024
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
PASS, FAIL, INCONCLUSIVE = "PASS", "FAIL", "INCONCLUSIVE"
# a span that FAILs today but is already in the record on main: drift that predates this PR. Reported, never
# counted against the PR (the approved merge rule of 2026-11-21 judges the fields a PR adds); `--all` and an
# explicit path list judge every span as before.
KNOWN = "KNOWN-DRIFT"
_MARKS = {PASS: "✓", FAIL: "✗", INCONCLUSIVE: "?", KNOWN: "~"}

# a curly-quoted span ("\u201c...\u201d") is explicit; straight quotes are paired in order (see quotes_in)
_CURLY = re.compile(r"\u201c([^\u201c\u201d\n]+)\u201d")
_CODE = re.compile(r"`[^`\n]*`")
_GITHUB_BLOB = re.compile(r"^https?://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)$")
_TAGS = re.compile(r"<(script|style)[^>]*>.*?</\1>|<[^>]+>", re.S | re.I)
_TRANSLATE = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-", "−": "-",
    " ": " ", " ": " ", " ": " ", "​": "", "­": "",
    "×": "x", "|": " ",        # a dimension's multiplication sign; a table separator a note kept
})


_ELLIPSIS = re.compile(r"\s*(?:\.\.\.|\u2026)\s*")


def normalize(text: str) -> str:
    """The comparison form: NFKC, typography straightened, every whitespace and hyphen removed, case
    folded. Whitespace and hyphens are dropped altogether (not collapsed): a page writes "8MB Flash"
    and "built-in" where a note wrote "8 MB Flash" and "built in", a PDF breaks a sentence across
    lines, a table cell and its neighbour are joined by the HTML stripping. Letters, digits and the
    other punctuation must still match, in order."""
    t = unicodedata.normalize("NFKC", text or "").translate(_TRANSLATE)
    return re.sub(r"[\s-]+", "", t).casefold()


def fragments(quote: str) -> list[str]:
    """A quote with an elision ("dual core ... with native USB") is its fragments in order, each
    normalized; a plain quote is one fragment."""
    return [normalize(f) for f in _ELLIPSIS.split(quote or "") if normalize(f)]


def contains(page_text: str, quote: str) -> bool:
    """Every fragment of `quote` appears in `page_text`, in order, non-overlapping."""
    frags = fragments(quote)
    if not frags:
        return False
    at = 0
    for frag in frags:
        i = page_text.find(frag, at)
        if i < 0:
            return False
        at = i + len(frag)
    return True


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def _spans(text: str) -> list[str]:
    """The quoted spans of one string: curly pairs, then the straight quotes PAIRED IN ORDER (the 1st
    with the 2nd, the 3rd with the 4th...), so the text BETWEEN two quotes ("Specs" (Features) and
    "Pinout") is never read as a quote itself. An odd straight quote leaves its tail unpaired. Backtick
    code is removed first: `"` around a value in a command line is not a quotation."""
    text = _CODE.sub(" ", text or "")          # `code` is a command or a value, never a quotation
    out = [m.group(1) for m in _CURLY.finditer(text)]
    parts = _CURLY.sub(" ", text).split('"')
    out += [parts[i] for i in range(1, len(parts) - 1, 2)]
    return [q.strip() for q in out if "\n" not in q]


def quotes_in(frontmatter: dict) -> list[str]:
    """The quoted spans embedded in the record's string values (every field but `sources`), in order,
    de-duplicated, at least MIN_QUOTE characters."""
    out, seen = [], set()
    for key, value in (frontmatter or {}).items():
        if key == "sources":
            continue
        for s in _strings(value):
            for q in _spans(s):
                if len(q) >= MIN_QUOTE and q not in seen:
                    seen.add(q)
                    out.append(q)
    return out


def cited_urls(frontmatter: dict) -> list[str]:
    out, seen = [], set()
    for s in (frontmatter or {}).get("sources") or []:
        u = (s or {}).get("url") if isinstance(s, dict) else None
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def fetch_url(url: str) -> str:
    """A GitHub `blob` page is HTML around the file; its raw form is the file. Everything else as cited."""
    m = _GITHUB_BLOB.match(url)
    if m:
        owner, repo, ref, path = m.groups()
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"
    return url


def html_to_text(doc: str) -> str:
    return html.unescape(_TAGS.sub(" ", doc))


def pdf_to_text(data: bytes) -> str | None:
    """The PDF's text, or None when no reader is installed or the file cannot be read."""
    try:
        import pypdf  # noqa: PLC0415
    except ImportError:
        return None
    try:
        reader = pypdf.PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:  # noqa: BLE001 — an unreadable PDF is inconclusive, never a verdict
        return None


@dataclass
class Page:
    url: str
    text: str | None          # normalized text, or None when unreadable
    detail: str


def _retry_after(response, attempt):
    header = response.headers.get("retry-after")
    if header:
        try:
            return min(float(header), MAX_BACKOFF_SECONDS)
        except ValueError:
            pass
    return min(BACKOFF_SECONDS * (2 ** (attempt - 1)), MAX_BACKOFF_SECONDS)


def fetch_page(client, url: str, sleep=time.sleep) -> Page:
    """GET `url` (following redirects) and reduce it to normalized text; unreadable -> text None."""
    target = fetch_url(url)
    detail = ""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = client.get(target, follow_redirects=True)
        except Exception as e:  # noqa: BLE001 — timeouts, DNS, TLS: the server did not answer
            detail = type(e).__name__
            if attempt < MAX_RETRIES:
                sleep(min(BACKOFF_SECONDS * (2 ** (attempt - 1)), MAX_BACKOFF_SECONDS))
                continue
            return Page(url, None, detail)
        if r.status_code in (429, 500, 502, 503, 504):
            detail = f"HTTP {r.status_code}"
            if attempt < MAX_RETRIES:
                sleep(_retry_after(r, attempt))
                continue
            return Page(url, None, detail)
        if r.status_code != 200:
            return Page(url, None, f"HTTP {r.status_code}")
        data = r.content
        if len(data) > MAX_BYTES:
            return Page(url, None, f"{len(data)} bytes, over the {MAX_BYTES} cap")
        ctype = (r.headers.get("content-type") or "").lower()
        if "pdf" in ctype or target.lower().endswith(".pdf"):
            text = pdf_to_text(data)
            return Page(url, (normalize(text) + " " + normalize(url)) if text is not None else None,
                        "pdf" if text is not None else "pdf not readable (pypdf missing or unparsable)")
        body = r.text
        if "html" in ctype or "<html" in body[:2000].lower():
            body = html_to_text(body)
        return Page(url, normalize(body) + " " + normalize(url), f"HTTP 200 {ctype.split(';')[0] or 'text'}")
    return Page(url, None, detail or "no answer")


@dataclass
class QuoteVerdict:
    quote: str
    verdict: str
    where: str          # the URL that holds it, or why not


@dataclass
class RecordReport:
    path: str
    quotes: list[QuoteVerdict] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        vs = {q.verdict for q in self.quotes}
        return FAIL if FAIL in vs else (INCONCLUSIVE if INCONCLUSIVE in vs else PASS)


def check_record(path: Path, frontmatter: dict, pages: dict[str, Page], fetch, known: set | None = None) -> RecordReport:
    """`fetch(url) -> Page` is called once per URL per run (`pages` is the cache across records). A span in
    `known` (already in this record on main) that would FAIL is reported as KNOWN instead."""
    rel = str(Path(path).resolve().relative_to(REPO)) if Path(path).resolve().is_relative_to(REPO) else str(path)
    report = RecordReport(rel)
    urls = cited_urls(frontmatter)
    for url in urls:
        if url not in pages:
            pages[url] = fetch(url)
    for q in quotes_in(frontmatter):
        readable = [pages[u] for u in urls if pages[u].text is not None]
        hit = next((p for p in readable if contains(p.text, q)), None)
        if hit:
            report.quotes.append(QuoteVerdict(q, PASS, hit.url))
        elif len(readable) < len(urls):
            why = "; ".join(f"{pages[u].url}: {pages[u].detail}" for u in urls if pages[u].text is None)
            report.quotes.append(QuoteVerdict(q, INCONCLUSIVE, f"not on any readable cited page; unreadable: {why}"))
        elif not urls:
            report.quotes.append(QuoteVerdict(q, FAIL, "the record cites no URL"))
        elif q in (known or ()):
            report.quotes.append(QuoteVerdict(q, KNOWN, f"on none of the {len(urls)} cited page(s); already on "
                                                        "main, not written by this change"))
        else:
            report.quotes.append(QuoteVerdict(q, FAIL, f"on none of the {len(urls)} cited page(s)"))
    return report


def changed_records(base: str, repo: Path = REPO) -> list[Path] | None:
    """The data/**/*.md files the branch adds or changes against `base` (merge base), or None when
    the diff cannot be taken."""
    try:
        p = subprocess.run(["git", "diff", "--name-only", "--diff-filter=AM", f"{base}...HEAD", "--", "data/"],
                           cwd=repo, capture_output=True, text=True, timeout=120)
    except (subprocess.TimeoutExpired, OSError):
        return None
    if p.returncode != 0:
        return None
    return [repo / line for line in p.stdout.split("\n") if line.endswith(".md") and (repo / line).is_file()]


def base_quotes(base: str, paths: list[Path], repo: Path = REPO) -> dict[Path, set]:
    """{path: the quoted spans the record carries at the merge base of `base` and HEAD}, only for a record that
    still cites every URL it cited there. A record that does not exist there (added by the branch), drops or
    swaps a cited URL, or cannot be read at either end knows nothing, so its spans are all judged (an
    unreadable base never excuses a quote)."""
    out = {Path(p): set() for p in paths}
    try:
        mb = subprocess.run(["git", "merge-base", base, "HEAD"], cwd=repo, capture_output=True, text=True, timeout=60)
    except (subprocess.TimeoutExpired, OSError):
        return out
    if mb.returncode != 0:
        return out
    for p in paths:
        rel = Path(p).resolve().relative_to(Path(repo).resolve()).as_posix()
        try:
            show = subprocess.run(["git", "show", f"{mb.stdout.strip()}:{rel}"], cwd=repo, capture_output=True,
                                  text=True, timeout=60)
        except (subprocess.TimeoutExpired, OSError):
            continue
        if show.returncode != 0:
            continue
        try:
            fm = yaml.safe_load(show.stdout.split("---", 2)[1]) if show.stdout.startswith("---") else None
        except (yaml.YAMLError, IndexError):
            continue
        if not isinstance(fm, dict):
            continue
        # excused only while every URL the record cited on main is still cited (review BLOCK of #2087): a PR that
        # drops or swaps a source can make an old span fail, and that failure is the PR's own
        try:
            head_fm, _ = parse_frontmatter(Path(p))
        except Exception:  # noqa: BLE001 — an unreadable head excuses nothing
            continue
        if set(cited_urls(fm)) <= set(cited_urls(head_fm or {})):
            out[Path(p)] = set(quotes_in(fm))
    return out


def default_base() -> str:
    ref = os.environ.get("GITHUB_BASE_REF")
    return f"origin/{ref}" if ref else "origin/main"


def run(paths: list[Path], fetch, out=None, known: dict | None = None) -> tuple[list[RecordReport], int]:
    out = out or sys.stdout          # resolved at call time, so a test's captured stdout is the one written
    pages: dict[str, Page] = {}
    reports = []
    for path in paths:
        fm, _body = parse_frontmatter(path)
        if not quotes_in(fm):
            continue
        rep = check_record(path, fm, pages, fetch, (known or {}).get(Path(path)))
        reports.append(rep)
        print(f"{_MARKS[rep.verdict]} {rep.verdict:12s} {rep.path}", file=out)
        for q in rep.quotes:
            print(f"    {_MARKS[q.verdict]} {q.verdict:12s} {q.where}\n      \"{q.quote}\"", file=out)
    n = {v: sum(1 for r in reports for q in r.quotes if q.verdict == v) for v in (PASS, FAIL, INCONCLUSIVE, KNOWN)}
    recs = {v: sum(1 for r in reports if r.verdict == v) for v in (PASS, FAIL, INCONCLUSIVE)}
    print(f"\n{len(reports)} record(s) with quotes: {recs[PASS]} pass, {recs[FAIL]} FAIL, {recs[INCONCLUSIVE]} inconclusive; "
          f"{sum(n.values())} quote(s): {n[PASS]} pass, {n[FAIL]} FAIL, {n[INCONCLUSIVE]} inconclusive"
          + (f", {n[KNOWN]} failing but already on main (not judged here)" if n[KNOWN] else "") + "; "
          f"{len(pages)} page(s) fetched", file=out)
    return reports, (1 if recs[FAIL] else 0)


def main(argv=None, fetch=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("paths", nargs="*", help="records to check (default: the branch's changed data/**/*.md)")
    ap.add_argument("--all", action="store_true", help="every data/**/*.md")
    ap.add_argument("--base", default=None, help="diff base (default: origin/$GITHUB_BASE_REF or origin/main)")
    args = ap.parse_args(argv)
    if args.all:
        paths = [p for _kind, p in iter_data_files()]
    elif args.paths:
        paths = [Path(p) for p in args.paths]
    known = None
    if not args.all and not args.paths:
        paths = changed_records(args.base or default_base())
        if paths is None:
            print("could not take the diff against the base", file=sys.stderr)
            return 2
        known = base_quotes(args.base or default_base(), paths)
    if fetch is None:
        if httpx is None:
            print("httpx is required to fetch the cited pages", file=sys.stderr)
            return 2
        client = httpx.Client(timeout=TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT})
        fetch = lambda url: fetch_page(client, url)  # noqa: E731
    _reports, code = run(paths, fetch, known=known)
    return code


if __name__ == "__main__":
    sys.exit(main())
