"""EspAtlas Jr — the deterministic, ZERO-LLM firmware scorer/author.

Promoted from jr/spike/ (2026-08-31) after: (1) a 12/12 spike proof against a curated golden set
beat the LLM agent's historical record of 0/6 clean autonomous PRs (DECISION-LOG.md,
2026-08-27), then (2) an at-scale run of score_entry() over the ENTIRE real live launcher
catalog (2671 entries) surfaced real bugs beyond the curated 12 — noise/junk firmware, a
wrong-chip-via-device-name-lookalike, a fused device-name spelling, a capability-keyword
false-positive spanning a word boundary, a non-fork "described port" of a catalogued repo, and a
malformed with-code gate — all fixed and locked in by 17 new hard golden cases (29 total; see
golden_set.json and test_scorer.py). Still ADDITIVE and NOT wired into jr's live authoring path
(agent.py/run.py) or jr-daily — see DECISION-LOG.md for the resume decision.

Every decision below traces to one of: the GitHub API (fork/source/stars), the device->board map
(device_map.py), the board record's own soc (tools.board_soc — ground truth), and a fixed
capability-keyword map (capability_map.py). No network calls happen here — score_entry() is a
pure function over a catalog entry + a frozen repo_meta dict, so tests are fast and offline (the
golden fixture embeds real, previously-fetched `gh api` responses).

Reused from tools.py: board_soc (ground-truth chip per catalogued board), capability_vocab (the
controlled token set), and _page_chip_families (the chip-family regex the board-authoring path
already trusts, reused here for the chip_family_mismatch cross-check).
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

_JR_DIR = Path(__file__).resolve().parent
if str(_JR_DIR) not in sys.path:
    sys.path.insert(0, str(_JR_DIR))
import tools  # noqa: E402
from capability_map import capabilities_from_text  # noqa: E402
from device_map import device_from_category, device_from_text  # noqa: E402

FIRMWARE_CATEGORY_ENUM = ("pentest", "mesh", "badusb", "display", "home", "multi")

# Popularity floor (SPEC-firmware-floor.md). A drain candidate is authored only if it clears
# EITHER of two GitHub signals (OR-gated): stars >= STAR_FLOOR, OR forks >= FORK_FLOOR. Forks are
# a stronger "actually built-on" signal than stars (a star is a bookmark; a fork is a
# derivative), so a heavily-forked but under-starred utility still clears. Below BOTH → the drain
# skips it as filler. Downloads are NOT a signal — a launcher/M5Burner download count is not a
# citable, stable metric and is never used to gate or store popularity. One place, tunable;
# consumed by drain.score_candidates via clears_popularity_floor(). Gates NEW drain authoring
# only, never catalogued.
# The floor lives in ONE place: esp_atlas_core.floor. These names are re-exported so existing
# callers (scorer.STAR_FLOOR, scorer.clears_popularity_floor) keep working, but the values are
# no longer defined here -- scripts/firmware_floor_audit.py used to re-type them by hand, and
# hand-sync is how the CI gate and the drain came to disagree about what qualifies.
from esp_atlas_core.floor import (  # noqa: E402
    FORK_FLOOR,
    STAR_FLOOR,
    clears_popularity_floor,
)



# capability tokens that signal each firmware_category enum value, checked in this priority
# order (a record with both "wifi" and "mesh" tokens is a mesh firmware first — mesh is the
# more specific claim). "home"/"display"-only firmware fall through to those buckets; anything
# left with no capability signal at all defaults to "multi" (never invented, always the safest
# guess when the evidence doesn't single out one category). This is the WEAK FALLBACK, only
# consulted when _category_from_purpose() below found no purpose keyword — wifi/ble are
# deliberately absent (see _category_from_purpose's docstring: wifi/ble are ubiquitous, not
# evidence of a hacking tool; nfc/rfid-nfc/sub-ghz/subghz are narrow enough radio protocols to
# stay a weak pentest hint).
_CATEGORY_SIGNALS = (
    ("mesh", {"mesh"}),
    ("badusb", {"badusb"}),
    ("pentest", {"nfc", "rfid-nfc", "sub-ghz", "subghz"}),
    ("display", {"display"}),
    ("home", {"mqtt", "ota", "on-device-web-ui", "ethernet", "artnet", "e131", "ddp"}),
)

# Purpose keywords checked BEFORE any capability signal, in the same mesh > badusb > pentest >
# display > home priority as _CATEGORY_SIGNALS. This is the PRIMARY classifier: wifi and ble are
# ubiquitous radios present in an internet radio, an mp3 streamer, or a brainwave generator just
# as much as in an actual hacking tool — their mere presence is not evidence of intent. Only an
# explicit offensive-security/mesh/badusb/display/home-automation keyword in the entry's own name
# or its repo_meta description/README title counts as evidence; everything else falls through to
# the weak capability fallback above, and ultimately to "multi" if nothing matches at all.
_PURPOSE_SIGNALS = (
    ("mesh", ("mesh", "meshtastic", "meshcore")),
    ("badusb", ("badusb", "ducky", "rubber-ducky", "hid-attack", "keystroke-injection")),
    ("pentest", ("marauder", "deauth", "deauther", "sniff", "sniffer", "pwn", "pwnagotchi",
                 "evil-portal", "evilportal", "wardriv", "jammer", "spoof", "nemo", "ghost",
                 "pcap", "handshake", "packet-monitor", "rogue", "bruce")),
    ("display", ("clock", "badge")),
    ("home", ("esphome", "home-assistant", "mqtt sensor", "smart-home", "thermostat")),
)

# Games/emulators/platforms — not atlas firmware. A NARROWER list than tools.uncatalogued_with_code()'s
# inline NOISE (that one also drops "demo"/"test"/" game"/"hello world", which at-scale proved too
# blunt HERE: "GroveNFC Demo for AtomS3" and M5Stack's own official "M5Dial-UserDemo"/"CoreS3
# UserDemo" factory firmware are real, legitimate entries that happen to say "demo" — a false-skip
# on real firmware is worse than a slipped-through generic-sounding one). Kept as unambiguous
# junk categories only: retro-game/emulator ROMs and the UIFlow/MicroPython block-programming
# platform (not a single firmware, and every board variant re-lists it separately in the catalog).
# Found at-scale: with the FULL production list this would false-skip real firmware; with THIS
# narrower list, dozens of genuine Tetris/Doom/emulator/UIFlow entries the earlier scorer draft
# wrongly "authored" are now correctly excluded (see the at-scale report for exact counts).
NOISE_TOKENS = ("doom", "gameboy", "game boy", "emulator", "tetris", "pacman", "pac-man", "snake",
                "nes", "snes", "pokemon", "arduboy", "chip-8", "chip8", "uiflow", "micropython",
                "tamagotchi", "flappy", "2048")

_GITHUB_REPO_RE = re.compile(r"^https?://github\.com/[^/\s]+/[^/\s]+")
_GITHUB_MENTION_RE = re.compile(r"github\.com/([\w.-]+/[\w.-]+)", re.IGNORECASE)


def _owner_repo(github_url: str) -> str:
    fn = (github_url or "").split("?", 1)[0].split("#", 1)[0]
    fn = fn.rstrip("/").replace("https://github.com/", "").lower()
    return "/".join(fn.split("/")[:2])


def _repo_name_from_url(github_url: str) -> str:
    """The bare repo NAME (not owner/repo) a launcher-catalog github url points at — the path
    segment immediately after the owner. `_owner_repo` already keeps only the first two path
    segments, so any trailing sub-page (/releases, /releases/latest, /tree/<branch>, /blob/...,
    /archive/...) is dropped generically, not special-cased per suffix — a url pointing at a
    repo's /releases page must still slug to the REPO, e.g. github.com/sosprz/meshcore-cardputer
    -adv/releases -> 'meshcore-cardputer-adv', never the bare last path segment 'releases' (the
    real garbage-id bug this fixes)."""
    owner_repo = _owner_repo(github_url)
    repo = owner_repo.split("/")[-1] if owner_repo else ""
    return re.sub(r"\.git$", "", repo)


_MARKETING_NOISE_RE = re.compile(r"\s*\([^)]*\)")


def _clean_marketing(text: str) -> str:
    """Strip parenthetical marketing/feature asides (e.g. '(BLE Fix)', '( load 2000+ songs)')
    from a catalog entry's display name — noise that pollutes both the shown name and any slug
    derived from it, not a signal that this is actually a different board/variant."""
    return re.sub(r"\s+", " ", _MARKETING_NOISE_RE.sub("", text or "")).strip()


def _slug(repo_name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", _clean_marketing(repo_name).lower()).strip("-")
    return s[:40]


def _category_from_purpose(name: str, repo_description: str | None,
                            readme_title: str | None) -> str | None:
    """Purpose-first classifier: an offensive-security/mesh/badusb/display/home-automation
    keyword in the entry name or repo_meta's own description/README title, checked BEFORE any
    capability token. Returns None (never "pentest" or anything else) when no keyword matches —
    the caller falls back to the weak capability signals, and ultimately to "multi"."""
    pool = " ".join(t for t in (name, repo_description, readme_title) if t).lower()
    if not pool:
        return None
    pool = f" {pool} "
    for category, keywords in _PURPOSE_SIGNALS:
        if any(keyword in pool for keyword in keywords):
            return category
    return None


def _category_from_capabilities(capabilities: list[str]) -> str:
    caps = set(capabilities)
    for category, signals in _CATEGORY_SIGNALS:
        if caps & signals:
            return category
    return "multi"


def score_entry(entry: dict, repo_meta: dict, catalogued_repos: set[str],
                catalogued_tokens: set[str]) -> dict:
    """Score ONE launcher-catalog entry. Returns either
      {"decision": "authored", "record": {...}}
    or
      {"decision": "skip", "reason": "..."}
    `repo_meta` is the frozen GitHub API shape: {full_name, fork, source_full_name, stars,
    description, license, readme_title}. `catalogued_repos`/`catalogued_tokens` mirror
    tools._catalogued_repos_and_tokens() (dedup fingerprint of what's already in the atlas)."""
    github = (entry.get("github") or "").strip()
    if not _GITHUB_REPO_RE.match(github):
        return {"decision": "skip", "reason": "no_github: with-code gate failed "
                "(no citable github.com/owner/repo URL — not a github link, or owner with no repo path)"}

    owner_repo = _owner_repo(github)
    if not repo_meta or repo_meta.get("error"):
        return {"decision": "skip", "reason": f"repo_unresolved: {github}"}

    source = (repo_meta.get("source_full_name") or repo_meta.get("full_name") or "").lower()
    if repo_meta.get("fork") and source and source != owner_repo:
        if source in catalogued_repos or source.split("/")[0] in catalogued_repos:
            return {"decision": "skip", "reason": f"fork_of_catalogued: source={source}"}
        return {"decision": "skip", "reason": f"fork_of_uncatalogued: source={source}"}

    if owner_repo in catalogued_repos or owner_repo.split("/")[0] in catalogued_repos:
        return {"decision": "skip", "reason": f"already_catalogued: {owner_repo} is already in the atlas"}

    name = entry.get("name") or ""
    name_tokens = {t for t in re.split(r"[-_\s]", name.lower()) if len(t) >= 4}
    if name_tokens & catalogued_tokens:
        return {"decision": "skip", "reason": "name_token_matches_catalogued: likely a port/variant"}

    # A repo that isn't a git fork of a catalogued one can still openly describe itself as a
    # derivative ("Updated version of M5Stickc-NEMO https://github.com/n0xa/m5stick-nemo.") — a
    # literal github.com/<catalogued-owner>/<catalogued-repo> link in either description is a
    # deterministic (if conservative) signal that this is a described port, not new firmware.
    for text in (entry.get("description"), repo_meta.get("description")):
        for mentioned in _GITHUB_MENTION_RE.findall(text or ""):
            mentioned_lower = mentioned.lower().rstrip("/.,;)")   # trailing sentence punctuation, not repo name
            if mentioned_lower != owner_repo and mentioned_lower in catalogued_repos:
                return {"decision": "skip",
                        "reason": f"described_port_of_catalogued: description links {mentioned_lower}"}

    name_low = f" {name.lower()} "
    if any(t in name_low for t in NOISE_TOKENS):
        return {"decision": "skip", "reason": "noise_non_firmware: name matches a game/emulator/platform token"}

    board = device_from_text(name, repo_meta.get("description"), repo_meta.get("readme_title"))
    if not board:
        board = device_from_category(entry.get("category"))
    if not board:
        return {"decision": "skip", "reason": "no_board_evidence: no catalogued device named"}

    chip = tools.board_soc(board)   # GROUND TRUTH — never taken from entry["esp"] (noisy/user-submitted)
    if not chip:
        return {"decision": "skip", "reason": f"board '{board}' has no known soc"}

    # A device-name match (e.g. "M5 Dial") can name a catalogued board's product line while the
    # REPO is actually for unrelated generic hardware (e.g. fbiego/esp32-c3-mini, an ESP32-C3
    # round-display clone board, not an M5Stack Dial) — the #71 wrong-chip class arriving via a
    # different route. Cross-check any SPECIFIC ESP32 family token named in the repo's own
    # full_name/description against the derived chip (reusing tools._page_chip_families, the
    # same regex the board-authoring path already trusts for this). A bare generic "esp32"
    # mention is never a conflict (too common/loose a term to mean a specific silicon variant);
    # only a different SPECIFIC variant (esp32-s3, esp32-c3, ...) is treated as real evidence.
    chip_text = " ".join(filter(None, (repo_meta.get("full_name"), repo_meta.get("description"))))
    mentioned_specific = tools._page_chip_families(chip_text) - {"esp32"}
    if mentioned_specific and chip not in mentioned_specific:
        return {"decision": "skip",
                "reason": f"chip_family_mismatch: repo names {sorted(mentioned_specific)}, "
                          f"but board '{board}' is {chip}"}

    text_pool = (name, entry.get("description"), repo_meta.get("description"))
    vocab = tools.capability_vocab()
    capabilities = [c for c in capabilities_from_text(*text_pool) if c in vocab]
    category = (_category_from_purpose(name, repo_meta.get("description"), repo_meta.get("readme_title"))
                or _category_from_capabilities(capabilities))

    firmware_id = _slug(_repo_name_from_url(github))

    record = {
        "id": firmware_id,
        "name": _clean_marketing(name),
        "url": f"https://github.com/{repo_meta.get('full_name', owner_repo)}",
        "category": category,
        "board": board,
        "chip": chip,
        "capabilities": capabilities,
        "maintainer": owner_repo.split("/")[0],
    }
    return {"decision": "authored", "record": record}
