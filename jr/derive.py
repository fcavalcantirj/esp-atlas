"""EspAtlas Jr — board-signal derivation (jr/derive.py): read what a firmware repo DECLARES.

SPEC-firmware-boards.md §1: a firmware's supported boards are a fact the source repo already
states in machine-readable form. Read it; do not infer it. Ranked by trust:

  1  release assets      `*.bin` per board on GitHub Releases, and a release manifest
                         (Meshtastic `firmware-<ver>.json` targets / esp-web-tools `builds`)
  2  platformio.ini      `[env:*] board = <id>`, with `extra_configs` globs expanded
  3  CI build matrix     `.github/workflows/*.yml` `strategy.matrix` scalars
  4  Arduino / IDF       in-repo `boards.txt` ids, `idf_component.yml` targets,
                         `sdkconfig.defaults` CONFIG_IDF_TARGET  (chip family only)

This module ONLY extracts signals, each with the URL (and line) that proves it; it writes
nothing and never fetches an asset body (Meshtastic's latest release is ~1.85 GB). Mapping a
signal's token to a catalogued board is jr/board_alias.resolve_token's job (`resolve()` below
does exactly that and nothing more). Rank 5 (README prose, LLM) is deliberately absent.

Determinism and budget: every network effect is an injected callable (`api`, `raw`), fixture
tests run offline, and `max_calls` caps the number of calls one derivation may make — hitting
the cap is reported in `notes`, never raised.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import board_alias

MAX_CALLS = 60
MAX_EXTRA_CONFIG_FILES = 40
MAX_WORKFLOWS = 10
MAX_MANIFEST_BYTES = 64 * 1024
IGNORED_ENVS = {"native"}
ESP_PLATFORMS = {"esp32", "esp32s2", "esp32s3", "esp32c2", "esp32c3", "esp32c5", "esp32c6", "esp32c61", "esp32h2", "esp32p4"}


@dataclass
class Signal:
    rank: int
    kind: str                 # asset | manifest | platformio | ci | idf | boards_txt
    token: str                # the string as the repo wrote it
    url: str                  # where a reader can see it
    soc: str | None = None    # chip family when the signal itself says so
    line: int | None = None
    extra: dict = field(default_factory=dict)


class _Calls:
    def __init__(self, api, raw, max_calls: int):
        self.api, self.raw, self.max_calls, self.n, self.exhausted = api, raw, max_calls, 0, False

    def _charge(self) -> bool:
        if self.n >= self.max_calls:
            self.exhausted = True
            return False
        self.n += 1
        return True

    def get_api(self, path: str):
        if not self._charge():
            return None
        try:
            return self.api(path)
        except Exception:  # noqa: BLE001 — a missing endpoint is a fact, not a failure
            return None

    def get_raw(self, url: str) -> str | None:
        if not self._charge():
            return None
        try:
            return self.raw(url)
        except Exception:  # noqa: BLE001
            return None


# --- default network effects ---------------------------------------------------------------------

def default_api(path: str):
    """`gh api <path>` (authenticated through gh). Returns the parsed JSON or raises."""
    import subprocess
    p = subprocess.run(["gh", "api", path], capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip()[:200])
    return json.loads(p.stdout)


def default_raw(url: str) -> str | None:
    """GET a small text file. 404 → None. Never used for release asset binaries."""
    import urllib.error
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "esp-atlas-jr-derive/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read(MAX_MANIFEST_BYTES * 8).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


# --- rank 1: releases --------------------------------------------------------------------------

def common_prefix(names: list[str]) -> str:
    """Longest common prefix of the asset stems, cut back to a separator, so
    `esp32_marauder_v1_15_1_20260824_m5cardputer` → `m5cardputer`. Only meaningful with ≥ 2 names."""
    if len(names) < 2:
        return ""
    p = os.path.commonprefix(names)
    cut = max(p.rfind("_"), p.rfind("-"), p.rfind("."))
    return p[:cut + 1] if cut >= 0 else ""


def _stem(name: str) -> str:
    for ext in (".bin.gz", ".bin", ".uf2", ".elf", ".zip", ".hex"):
        if name.lower().endswith(ext):
            return name[: -len(ext)]
    return name


def release_signals(owner_repo: str, calls: _Calls, notes: list[str]) -> list[Signal]:
    rel = calls.get_api(f"repos/{owner_repo}/releases/latest")
    if not rel or not isinstance(rel, dict) or not rel.get("assets"):
        return []
    out: list[Signal] = []
    html = rel.get("html_url") or f"https://github.com/{owner_repo}/releases/tag/{rel.get('tag_name', '')}"
    bins = [a for a in rel["assets"] if a.get("name", "").lower().endswith((".bin", ".bin.gz", ".uf2"))]
    stems = [_stem(a["name"]) for a in bins]
    prefix = common_prefix(stems)
    for a, stem in zip(bins, stems):
        token = stem[len(prefix):] if prefix and stem.startswith(prefix) else stem
        if token:
            out.append(Signal(1, "asset", token, a.get("browser_download_url") or html,
                              extra={"asset": a["name"], "release": rel.get("tag_name")}))
    for a in rel["assets"]:
        name = a.get("name", "")
        if name.lower().endswith(".json") and (a.get("size") or 0) <= MAX_MANIFEST_BYTES:
            text = calls.get_raw(a.get("browser_download_url", ""))
            if text is None:
                continue
            try:
                doc = json.loads(text)
            except json.JSONDecodeError:
                notes.append(f"manifest {name}: not JSON")
                continue
            out += manifest_signals(doc, a.get("browser_download_url", ""), rel.get("tag_name"))
    return out


def manifest_signals(doc: dict, url: str, release: str | None) -> list[Signal]:
    """Meshtastic: {targets: [{board, platform}]} — ESP32 platforms only. esp-web-tools:
    {builds: [{chipFamily, parts: [{path}]}]} — chip from chipFamily, token from the part path."""
    out: list[Signal] = []
    for t in (doc.get("targets") or []):
        plat = str(t.get("platform") or "").lower()
        if plat in ESP_PLATFORMS and t.get("board"):
            out.append(Signal(1, "manifest", str(t["board"]), url, soc=board_alias.chip_only(plat),
                              extra={"platform": plat, "release": release}))
    for b in (doc.get("builds") or []):
        soc = board_alias.chip_only(str(b.get("chipFamily") or "").replace(" ", ""))
        for part in (b.get("parts") or []):
            path = str(part.get("path") or "")
            if path:
                out.append(Signal(1, "manifest", _stem(Path(path).name), url, soc=soc,
                                  extra={"chipFamily": b.get("chipFamily"), "release": release}))
    return out


# --- rank 2: platformio.ini ---------------------------------------------------------------------

# Section headers may carry trailing whitespace or a `;`/`#` comment (Bruce: `[platformio]   `,
# WLED: `[env:…] ; …`); the name is what is inside the brackets.
_ENV = re.compile(r"^\[env:([^\]]+)\]\s*(?:[;#].*)?$")
_SECTION = re.compile(r"^\[([^\]]+)\]\s*(?:[;#].*)?$")


def parse_platformio(text: str) -> dict:
    """{"envs": {name: {"board": id|None, "line": n}}, "extra_configs": [globs], "default_envs": [names]}

    PlatformIO inheritance is honoured: an `[env:x]` with no `board =` of its own takes it from
    the sections named in its `extends = a, b` (depth-first, ≤ 6 deep — Bruce's boards/*.ini
    declare `board` in a base section and every env extends it), else from the `[env]` global
    defaults. `line` is where the winning `board =` line is, in THIS file."""
    sections: dict[str, dict] = {}
    order: list[str] = []
    section, collecting = None, None
    for n, raw in enumerate(text.split("\n"), 1):
        line = raw.rstrip("\r")
        m = _SECTION.match(line)
        if m:
            section = m.group(1).strip()
            sections.setdefault(section, {})
            if section not in order:
                order.append(section)
            collecting = None
            continue
        if collecting is not None and (line.startswith(" ") or line.startswith("\t")):
            item = line.strip()
            if item and not item.startswith((";", "#")):          # commented-out entries stay out
                collecting.append(item)
            continue
        collecting = None
        if section is None or not line.strip() or line.lstrip().startswith((";", "#")):
            continue
        kv = re.match(r"^\s*([A-Za-z0-9_.-]+)\s*=\s*(.*)$", line)
        if not kv:
            continue
        key, rest = kv.group(1), kv.group(2).strip()
        rest = re.split(r"\s+[;#]", rest)[0].strip()             # trailing comment
        entry = sections[section]
        if key in entry:
            continue                                               # first assignment wins
        values = [x.strip() for x in re.split(r"[,\s]+", rest) if x.strip()] if rest else []
        entry[key] = {"values": values, "line": n}
        collecting = values          # indented lines that follow continue this value (PlatformIO)

    def board_of(name: str, depth: int = 0) -> tuple[str | None, int | None]:
        sec = sections.get(name)
        if sec is None or depth > 6:
            return None, None
        b = sec.get("board")
        if b and b["values"]:
            return b["values"][0], b["line"]
        for parent in (sec.get("extends") or {"values": []})["values"]:
            found = board_of(parent, depth + 1)
            if found[0]:
                return found
        return None, None

    envs: dict[str, dict] = {}
    for name in order:
        if not name.startswith("env:"):
            continue
        board, line = board_of(name)
        if board is None:
            board, line = board_of("env")
        envs[name[4:]] = {"board": board, "line": line}
    plat = sections.get("platformio", {})
    return {"envs": envs,
            "extra_configs": list((plat.get("extra_configs") or {"values": []})["values"]),
            "default_envs": list((plat.get("default_envs") or {"values": []})["values"])}


def platformio_signals(owner_repo: str, ref: str, calls: _Calls, notes: list[str], tree: list[str] | None) -> list[Signal]:
    base_raw = f"https://raw.githubusercontent.com/{owner_repo}/{ref}/"
    base_blob = f"https://github.com/{owner_repo}/blob/{ref}/"
    text = calls.get_raw(base_raw + "platformio.ini")
    if text is None:
        return []
    files = [("platformio.ini", text)]
    root = parse_platformio(text)
    if root["extra_configs"]:
        if tree is None:
            notes.append("extra_configs present but no tree listing; globs not expanded")
        else:
            matched = [p for g in root["extra_configs"] for p in tree if fnmatch.fnmatch(p, g)]
            matched = list(dict.fromkeys(matched))
            if len(matched) > MAX_EXTRA_CONFIG_FILES:
                notes.append(f"extra_configs matched {len(matched)} files; capped at {MAX_EXTRA_CONFIG_FILES}")
                matched = matched[:MAX_EXTRA_CONFIG_FILES]
            for p in matched:
                t = calls.get_raw(base_raw + p)
                if t is not None:
                    files.append((p, t))
                elif calls.exhausted:
                    notes.append("call budget exhausted while expanding extra_configs")
                    break
    out: list[Signal] = []
    for path, t in files:
        parsed = root if path == "platformio.ini" else parse_platformio(t)
        for env, info in parsed["envs"].items():
            if env in IGNORED_ENVS or not info["board"]:
                continue
            out.append(Signal(2, "platformio", info["board"], f"{base_blob}{path}#L{info['line']}",
                              line=info["line"], extra={"env": env, "file": path}))
    return out


# --- rank 3: CI matrix ---------------------------------------------------------------------------

def _matrix_scalars(node, out: list[str]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if k in ("include", "exclude") and isinstance(v, list):
                for item in v:
                    _matrix_scalars(item, out)
            else:
                _matrix_scalars(v, out)
    elif isinstance(node, list):
        for v in node:
            _matrix_scalars(v, out)
    elif isinstance(node, (str, int)):
        s = str(node).strip()
        if s and len(s) <= 64 and not s.startswith("${{"):
            out.append(s)


def ci_signals(owner_repo: str, ref: str, calls: _Calls, notes: list[str], tree: list[str] | None) -> list[Signal]:
    if not tree:
        return []
    try:
        import yaml
    except ImportError:  # pragma: no cover
        notes.append("pyyaml missing; CI matrix skipped")
        return []
    wfs = [p for p in tree if p.startswith(".github/workflows/") and p.endswith((".yml", ".yaml"))][:MAX_WORKFLOWS]
    out: list[Signal] = []
    for p in wfs:
        text = calls.get_raw(f"https://raw.githubusercontent.com/{owner_repo}/{ref}/{p}")
        if text is None:
            continue
        try:
            doc = yaml.safe_load(text) or {}
        except yaml.YAMLError:
            notes.append(f"{p}: unparsable YAML")
            continue
        scalars: list[str] = []
        for job in ((doc.get("jobs") or {}).values() if isinstance(doc, dict) else []):
            matrix = ((job or {}).get("strategy") or {}).get("matrix") if isinstance(job, dict) else None
            if matrix:
                _matrix_scalars(matrix, scalars)
        for s in dict.fromkeys(scalars):
            out.append(Signal(3, "ci", s, f"https://github.com/{owner_repo}/blob/{ref}/{p}", extra={"workflow": p}))
    return out


# --- rank 4: Arduino / IDF targets ------------------------------------------------------------------

def idf_signals(owner_repo: str, ref: str, calls: _Calls, notes: list[str], tree: list[str] | None) -> list[Signal]:
    out: list[Signal] = []
    base_raw = f"https://raw.githubusercontent.com/{owner_repo}/{ref}/"
    base_blob = f"https://github.com/{owner_repo}/blob/{ref}/"
    have = set(tree or [])
    if "idf_component.yml" in have or tree is None:
        t = calls.get_raw(base_raw + "idf_component.yml")
        if t:
            for n, line in enumerate(t.split("\n"), 1):
                for m in re.finditer(r"\b(esp32[a-z]?\d?\d?)\b", line.lower()):
                    soc = board_alias.chip_only(m.group(1))
                    if soc and re.search(r"targets?", t.lower()):
                        out.append(Signal(4, "idf", m.group(1), base_blob + f"idf_component.yml#L{n}", soc=soc, line=n))
    if "sdkconfig.defaults" in have or tree is None:
        t = calls.get_raw(base_raw + "sdkconfig.defaults")
        if t:
            for n, line in enumerate(t.split("\n"), 1):
                m = re.match(r'^\s*CONFIG_IDF_TARGET="?([a-z0-9]+)"?', line)
                if m and board_alias.chip_only(m.group(1)):
                    out.append(Signal(4, "idf", m.group(1), base_blob + f"sdkconfig.defaults#L{n}", soc=board_alias.chip_only(m.group(1)), line=n))
    if "boards.txt" in have:
        t = calls.get_raw(base_raw + "boards.txt")
        if t:
            for n, line in enumerate(t.split("\n"), 1):
                m = re.match(r"^([^.#=\s]+)\.name=(.*)$", line)
                if m:
                    out.append(Signal(4, "boards_txt", m.group(1), base_blob + f"boards.txt#L{n}", line=n, extra={"name": m.group(2).strip()}))
    return out


# --- driver ------------------------------------------------------------------------------------------

def derive(owner_repo: str, *, api=default_api, raw=default_raw, ref: str | None = None,
           max_calls: int = MAX_CALLS, today: str | None = None) -> dict:
    """All signals for `owner/repo` at `ref` (default: the repo's default branch), as plain dicts,
    plus the citation date, the call count and any notes. Never raises on a missing signal."""
    calls = _Calls(api, raw, max_calls)
    notes: list[str] = []
    today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if ref is None:
        meta = calls.get_api(f"repos/{owner_repo}")
        ref = (meta or {}).get("default_branch") or "main"
    tree_doc = calls.get_api(f"repos/{owner_repo}/git/trees/{ref}?recursive=1")
    tree = [t["path"] for t in (tree_doc or {}).get("tree", []) if t.get("type") == "blob"] if tree_doc else None
    if tree_doc and tree_doc.get("truncated"):
        notes.append("tree listing truncated by GitHub")
    signals: list[Signal] = []
    signals += release_signals(owner_repo, calls, notes)
    signals += platformio_signals(owner_repo, ref, calls, notes, tree)
    signals += ci_signals(owner_repo, ref, calls, notes, tree)
    signals += idf_signals(owner_repo, ref, calls, notes, tree)
    if calls.exhausted:
        notes.append(f"call budget exhausted at {max_calls}")
    return {"repo": owner_repo, "ref": ref, "fetched": today, "calls": calls.n,
            "signals": [asdict(s) for s in signals], "notes": notes}


def resolve(derived: dict) -> dict:
    """Map every signal to a catalogued board through jr/board_alias.resolve_token. Returns
    {"boards": {atlas_id: [signal, ...]}, "socs": {soc: [signal, ...]}, "unresolved": [signal, ...]}.
    A board keeps every signal that named it, highest rank first; a chip-only signal lands in
    `socs`. Nothing here decides what to write — the writer does, from the best rank per board."""
    boards: dict[str, list] = {}
    socs: dict[str, list] = {}
    unresolved: list = []
    for s in derived.get("signals", []):
        r = board_alias.resolve_token(s["token"], soc=s.get("soc"))
        if r and r.get("atlas_id"):
            boards.setdefault(r["atlas_id"], []).append({**s, "how": r["how"]})
        elif r and r.get("soc"):
            socs.setdefault(r["soc"], []).append(s)
        elif s.get("soc"):
            socs.setdefault(s["soc"], []).append(s)
            unresolved.append(s)
        else:
            unresolved.append(s)
    for sigs in boards.values():
        sigs.sort(key=lambda x: (x["rank"], x["token"]))
    return {"boards": dict(sorted(boards.items())), "socs": dict(sorted(socs.items())), "unresolved": unresolved}
