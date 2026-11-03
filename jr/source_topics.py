"""EspAtlas Jr — the GitHub-topics firmware SOURCE (jr/source_topics.py).

A THIRD candidate source alongside the Launcher/M5Burner catalog (jr/drain.py, SPEC-espatlas-jr.
md §3b) and the awesome-list source (jr/source_awesome.py) — added for the same reason: the
launcher pool is ~98% drained (DECISION-LOG.md). Instead of scraping curated markdown lists, this
module queries GitHub's own topic search (`gh api search/repositories?q=topic:TOPIC`) for
repositories that self-tag with a topic like `cardputer` or `esp32-marauder`, sorted by stars
descending. Its only job is to turn that search into a flat, deduped list of candidate
{name, github, source} dicts shaped exactly like a launcher-catalog entry, so it can be handed to
the SAME admission gate (jr/drain.score_candidates -> jr/scorer.score_entry) the launcher drain
already uses — popularity floor and firmware-evidence rules unchanged, because THAT gate is what
has to separate real firmware from a topic search's library/tool noise, not this module. See
jr/ingest_topics.py for the read-only driver that runs candidates through it.

The search client is injected — this module makes no network call unless the caller passes the
real `default_search_topic`.
"""
from __future__ import annotations
import json
import re
import subprocess
import urllib.parse
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# The seed list is VERSIONED: bump SEED_VERSION whenever CURATED_TOPICS or the catalog-derivation
# rule changes, so a tick report line ("topics=v1:...") says which list produced an admit.
SEED_VERSION = 1

# Curated ecosystem topics (Felipe, 2026-11-03 jr-fixes G1a): the SoC families, toolchains, device
# families and well-known firmware/tool projects ESP32 repos self-tag with. The original five
# (cardputer, m5stack, m5stack-cardputer, esp32-marauder, bruce) had been searched dry — m5stack
# now arrives through the catalog-derived half (data/boards/m5stack).
CURATED_TOPICS = [
    "esp32", "esp32-s3", "esp32-c3", "esp32-c6", "esp32-c5", "esp32-h2", "esp32-p4", "esp-idf",
    "arduino-esp32", "platformio", "m5stickc", "m5stack-core2", "atoms3", "m5stack-cardputer",
    "cardputer", "lilygo", "t-deck", "t-display", "heltec", "meshtastic", "meshcore", "wled",
    "esphome", "tasmota", "esp32-marauder", "bruce", "flipper-zero", "wardriving", "xiaozhi",
]

_GITHUB_TOPIC_MAX = 50   # GitHub's own topic length limit


def normalize_topic(raw: str) -> str:
    """A catalog id/dir name in GitHub topic form: lowercase, runs of anything but [a-z0-9]
    collapsed to one hyphen, no leading/trailing hyphen, at most 50 chars. "" when nothing is
    left."""
    topic = re.sub(r"[^a-z0-9]+", "-", (raw or "").strip().lower()).strip("-")
    return topic[:_GITHUB_TOPIC_MAX].rstrip("-")


def catalog_topics(root: Path = REPO) -> list[str]:
    """Topics derived from the catalog itself: every SoC id (data/socs/<id>/) and every brand dir
    (data/boards/<brand>/), normalized, sorted, deduped. A missing catalog dir yields nothing."""
    names = []
    for sub in ("socs", "boards"):
        d = Path(root) / "data" / sub
        if d.is_dir():
            names += [p.name for p in d.iterdir() if p.is_dir()]
    return sorted({t for t in map(normalize_topic, names) if t})


def seed_topics(root: Path = REPO) -> list[str]:
    """The versioned seed list: CURATED_TOPICS in order, then catalog_topics(root), first
    occurrence wins — no duplicates."""
    return list(dict.fromkeys(CURATED_TOPICS + catalog_topics(root)))


def hour_index(now: datetime) -> int:
    """Whole hours since the Unix epoch — the hourly tick's rotation index."""
    return int(now.timestamp() // 3600)


def topics_for_tick(topics, hour: int, per_tick: int) -> list[str]:
    """The `per_tick` topics this hour searches: a window of `topics` starting at
    (hour * per_tick) mod N, wrapping. Consecutive hours tile consecutive windows, so every topic
    is searched within ceil(N / per_tick) ticks, and the same hour always gets the same slice."""
    topics = list(topics)
    k = min(max(per_tick, 0), len(topics))
    if not k:
        return []
    start = (hour * k) % len(topics)
    return [topics[(start + i) % len(topics)] for i in range(k)]


# The one-shot drivers (jr/author_topics.py, jr/ingest_topics.py) scan the whole seed list; the
# hourly stage (jr/stage_admit_topics.py) rotates through it via topics_for_tick.
DEFAULT_TOPICS = seed_topics()


def default_search_topic(topic: str, per_page: int = 100) -> list[dict]:  # pragma: no cover — real network call
    """Real GitHub topic-search client (`gh api search/repositories?q=topic:TOPIC&sort=stars&
    order=desc&per_page=N`, authed through `gh` for a higher rate limit) — the one network-
    touching implementation in this module, used only by a live run. Returns the raw `items` list
    (each item at least carrying `full_name`) or [] on any failure/empty result."""
    query = urllib.parse.quote(f"topic:{topic}", safe=":")
    p = subprocess.run(
        ["gh", "api", f"search/repositories?q={query}&sort=stars&order=desc&per_page={per_page}"],
        capture_output=True, text=True, timeout=30,
    )
    if p.returncode != 0:
        return []
    try:
        data = json.loads(p.stdout)
    except json.JSONDecodeError:
        return []
    items = data.get("items") if isinstance(data, dict) else None
    return items if isinstance(items, list) else []


def fetch_topic_repos(topics, search=default_search_topic, per_topic: int = 100) -> list[dict]:
    """Query `search(topic, per_page) -> [{full_name, ...}, ...]` (GitHub search/repositories'
    own `items` shape) for every topic in `topics`, and turn every distinct repo surfaced across
    ALL of them into a candidate dict shaped like a launcher-catalog entry so jr/drain.py's scorer
    path can consume it unmodified: {name (the repo name), github (the canonical
    https://github.com/OWNER/REPO url), source (e.g. "topic:cardputer" — the FIRST topic this
    repo was seen under, when it carries more than one of `topics`)}. A malformed item (no
    `full_name`, or one without an owner/repo path) is skipped, never raising — one bad item must
    not abort the rest. A blank topic is skipped without ever calling `search`."""
    candidates: list[dict] = []
    seen: set[str] = set()
    for topic in topics:
        topic = (topic or "").strip()
        if not topic:
            continue
        for item in search(topic, per_topic) or []:
            full_name = (item.get("full_name") or "").strip()
            if not full_name or "/" not in full_name:
                continue
            key = full_name.lower()
            if key in seen:
                continue
            seen.add(key)
            _, repo = full_name.split("/", 1)
            candidates.append({
                "name": repo,
                "github": f"https://github.com/{full_name}",
                "source": f"topic:{topic}",
                # Carry the repo's own description so scorer's library/demo keyword filter has text
                # to read (a topic candidate has no submitter description); without it, keyword-only
                # libraries/demos like meloncookie/RemotePy and esp-idf-mpu6050-dmp slip the gate.
                "description": item.get("description"),
            })
    return candidates
