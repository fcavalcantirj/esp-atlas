"""EspAtlas Jr — the device-build evidence gate (jr/device_evidence.py).

A firmware record says "you flash this onto an ESP". Popularity, dedup and the library/demo noise
gates never checked that; rebelthor/warble (a Go server for Linux/macOS that talks to stock
xiaozhi-esp32 over WebSocket) was admitted as ESP32-S3 firmware on its GitHub topics alone
(review finding 3, 2026-11-04). So before ANY firmware record is authored — launcher, topics and
submission paths alike — the repo must show at least one device-build signal:

  arduino_sketch   a `*.ino` anywhere in the tree                         (tree only)
  idf_component    an `idf_component.yml` anywhere in the tree            (tree only)
  release_bin      a non-draft release carrying a `.bin`/`.bin.gz`/`.uf2` (derive._has_bins)
  platformio       a `platformio.ini` whose `platform` names espressif32  (derive.parse_ini)
  idf_project      a `CMakeLists.txt` that includes ESP-IDF's `project.cmake`

A repo with none is `not_device_firmware` (memory.NO_BUILD_SIGNAL_DAYS). An endpoint that failed
for any reason other than 404 is not a fact about the repo: the answer is unknown (`ok=None`,
`device_evidence_unreadable`, retried after memory.UNRESOLVED_REJECT_DAYS), never a rejection.

Network effects are injected (`api`, `raw`) exactly as in jr/derive.py and charged through its
_Calls, so tests run offline and `max_calls` bounds one check. The tick's BudgetExceeded passes
through untouched. Read-only: this module writes nothing.
"""
from __future__ import annotations

import re

import derive
import memory

NOT_DEVICE_FIRMWARE = "not_device_firmware"
EVIDENCE_UNREADABLE = "device_evidence_unreadable"
MAX_CALLS = 8                  # tree + releases + MAX_BUILD_FILES platformio.ini + MAX_BUILD_FILES CMakeLists.txt
MAX_BUILD_FILES = 3            # per build-file kind, shallowest first (the project root wins)

_PROJECT_CMAKE = re.compile(r"^\s*include\s*\(.*project\.cmake", re.I)
_TTLS = {NOT_DEVICE_FIRMWARE: memory.NO_BUILD_SIGNAL_DAYS, EVIDENCE_UNREADABLE: memory.UNRESOLVED_REJECT_DAYS}


def _found(kind: str, url: str, calls, notes: list[str]) -> dict:
    return {"ok": True, "kind": kind, "url": url, "calls": calls.n, "notes": notes}


def _shallowest(tree: list[str] | None, name: str, truncated: bool) -> list[str]:
    """Up to MAX_BUILD_FILES paths named `name`, root first. No (or a truncated) listing still
    tries the root file, the one place a project's own build file must live."""
    paths = sorted((p for p in (tree or []) if p.rsplit("/", 1)[-1] == name), key=lambda p: (p.count("/"), p))
    if (tree is None or truncated) and name not in paths:
        paths.insert(0, name)
    return paths[:MAX_BUILD_FILES]


def _tree_signal(tree: list[str], blob: str) -> tuple[str, str] | None:
    for p in tree:
        if p.lower().endswith(".ino"):
            return "arduino_sketch", blob + p
    for p in tree:
        if p.rsplit("/", 1)[-1] == "idf_component.yml":
            return "idf_component", blob + p
    return None


def _release_bin(owner_repo: str, calls) -> str | None:
    rels = calls.get_api(f"repos/{owner_repo}/releases?per_page=10")
    for rel in rels if isinstance(rels, list) else []:
        if isinstance(rel, dict) and not rel.get("draft") and derive._has_bins(rel):
            asset = next(a for a in rel["assets"] if isinstance(a, dict)
                         and str(a.get("name", "")).lower().endswith((".bin", ".bin.gz", ".uf2")))
            return asset.get("browser_download_url") or f"https://github.com/{owner_repo}/releases/tag/{rel.get('tag_name')}"
    return None


def _espressif_platform_line(text: str) -> int | None:
    """The line of the first `platform =` option (any section) naming espressif32 — the official
    platform, a pinned `espressif32@x`, or a fork URL such as pioarduino's platform-espressif32."""
    hits = [opt["line"] for opts in derive.parse_ini(text).values() for key, opt in opts.items()
            if key == "platform" and any("espressif32" in v.lower() for v in opt["values"])]
    return min(hits) if hits else None


def _project_cmake_line(text: str) -> int | None:
    return next((n for n, line in enumerate(text.split("\n"), 1) if _PROJECT_CMAKE.match(line)), None)


def check(owner_repo: str, *, api=derive.default_api, raw=derive.default_raw, ref: str | None = None,
          max_calls: int = MAX_CALLS) -> dict:
    """{"ok": True|False|None, "kind", "url", "calls", "notes"} for `owner/repo` at `ref` (default
    HEAD, the default branch). Cheapest evidence first; stops at the first signal."""
    ref = ref or "HEAD"
    calls, notes = derive._Calls(api, raw, max_calls), []
    blob = f"https://github.com/{owner_repo}/blob/{ref}/"
    base_raw = f"https://raw.githubusercontent.com/{owner_repo}/{ref}/"
    tree_doc = calls.get_api(f"repos/{owner_repo}/git/trees/{ref}?recursive=1")
    tree, truncated = None, False
    if isinstance(tree_doc, dict) and isinstance(tree_doc.get("tree"), list):
        tree = [t["path"] for t in tree_doc["tree"] if isinstance(t, dict) and t.get("type") == "blob" and t.get("path")]
        truncated = bool(tree_doc.get("truncated"))
        if truncated:
            notes.append("tree listing truncated by GitHub")
        hit = _tree_signal(tree, blob)
        if hit:
            return _found(*hit, calls, notes)
    url = _release_bin(owner_repo, calls)
    if url:
        return _found("release_bin", url, calls, notes)
    for kind, name, line_of in (("platformio", "platformio.ini", _espressif_platform_line),
                                ("idf_project", "CMakeLists.txt", _project_cmake_line)):
        for p in _shallowest(tree, name, truncated):
            text = calls.get_raw(base_raw + p)
            line = line_of(text) if text else None
            if line:
                return _found(kind, f"{blob}{p}#L{line}", calls, notes)
    if calls.exhausted:
        notes.append(f"call budget exhausted at {max_calls}")
    notes += calls.failures
    unknown = calls.errors > 0 or calls.exhausted
    return {"ok": None if unknown else False, "kind": None, "url": None, "calls": calls.n, "notes": notes}


def reject_reason(result: dict) -> str:
    """The ledger/report reason for a result that is not ok (`<key>: <detail>`)."""
    if result.get("ok") is None:
        return f"{EVIDENCE_UNREADABLE}: {'; '.join(result.get('notes') or ['endpoint unavailable'])[:120]}"
    return (f"{NOT_DEVICE_FIRMWARE}: no espressif32 platformio.ini, ESP-IDF project, "
            "Arduino sketch or release .bin")


def ttl_days(reason: str) -> int:
    """Memory TTL for a reject_reason(): no build signal re-checks in NO_BUILD_SIGNAL_DAYS, an
    unreadable repo in UNRESOLVED_REJECT_DAYS."""
    return _TTLS.get(reason.split(":")[0], memory.SEEN_TTL_DAYS)
