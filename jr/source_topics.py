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
import subprocess
import urllib.parse

# Seeded with the device/tool topics Felipe named — the GitHub topics real ESP32 hacking-tool
# repos self-tag with (device family: cardputer/m5stack/m5stack-cardputer; specific well-known
# tools: esp32-marauder/bruce).
DEFAULT_TOPICS = ["cardputer", "m5stack", "m5stack-cardputer", "esp32-marauder", "bruce"]


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
