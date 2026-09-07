"""EspAtlas Jr — board-signal derivation (jr/derive.py): read what a firmware repo DECLARES.

SPEC-firmware-boards.md §1: a firmware's supported boards are a fact the source repo already
states in machine-readable form. Read it; do not infer it. Ranked by trust:

  1  release assets      `*.bin` per board on GitHub Releases, and a release manifest
                         (Meshtastic `firmware-<ver>.json` targets / esp-web-tools `builds`)
  2  platformio.ini      `[env:*] board = <id>`, resolved the way PlatformIO does: every
                         `extra_configs` file merged into ONE config, `extends` with the LAST
                         listed parent winning, `[env]` defaults, `${section.option}`
                         interpolation, case-insensitive option names
  3  CI build matrix     `.github/workflows/*.yml` `strategy.matrix` string values
  4  Arduino / IDF       in-repo `boards.txt` ids, `idf_component.yml` targets,
                         `sdkconfig.defaults[.<target>]` CONFIG_IDF_TARGET (chip family only)

This module ONLY extracts signals, each with the URL (and line) that proves it; it writes
nothing and never fetches an asset body (Meshtastic's latest release is ~1.85 GB). Mapping a
signal's token to a catalogued board is jr/board_alias.resolve_token's job (`resolve()` below
does exactly that). Rank 5 (README prose, LLM) is deliberately absent.

Determinism and budget: every network effect is an injected callable (`api`, `raw`), fixture
tests run offline, `max_calls` caps the calls one derivation may make (hitting it is a note,
never an exception), and every cap that drops input is reported in `notes`. The tick's own
BudgetExceeded is the one exception that passes through untouched.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

import board_alias
from budget import BudgetExceeded

MAX_CALLS = 60
MAX_EXTRA_CONFIG_FILES = 40
MAX_WORKFLOWS = 10
MAX_MANIFEST_BYTES = 64 * 1024
IGNORED_ENVS = {"native"}
ESP_PLATFORMS = {"esp32", "esp32s2", "esp32s3", "esp32c2", "esp32c3", "esp32c5", "esp32c6", "esp32c61", "esp32h2", "esp32p4"}
GENERIC_BIN_STEMS = {"bootloader", "partitions", "partition-table", "boot_app0", "firmware", "merged", "merged-firmware",
                     "factory", "app", "ota", "spiffs", "littlefs", "otadata"}
_RUNNER = re.compile(r"^(ubuntu|windows|macos)-|^(latest|self-hosted)$", re.I)
_VERSIONISH = re.compile(r"^v?\d+([._]\d+)*$|^\d{6,}$", re.I)           # CI matrix noise: '3.11', '20240101'
_STAMP = re.compile(r"^v?\d+([._]\d+)+$|^\d{6,}$", re.I)                   # a dotted/underscored version or a date
_MULTIPART_SUFFIX = re.compile(r"[-_](bootloader|partition[-_]?table|partitions|boot_app0)$", re.I)   # the other parts of a 3-part image


@dataclass
class Signal:
    rank: int
    kind: str                 # asset | manifest | platformio | ci | idf | boards_txt
    token: str                # the string as the repo wrote it (version/date stamps removed for assets)
    url: str                  # where a reader can see it
    soc: str | None = None    # chip family when the signal itself says so
    line: int | None = None
    extra: dict = field(default_factory=dict)


_MISSING = re.compile(r"\b404\b|not found", re.I)


def _is_missing(exc: BaseException) -> bool:
    """A 404 is a fact about the repo (no releases, no such file); anything else — 403 rate limit,
    5xx, network — is an endpoint we could not read, and the derivation must say so."""
    return bool(_MISSING.search(str(exc)))


class _Calls:
    def __init__(self, api, raw, max_calls: int):
        self.api, self.raw, self.max_calls, self.n, self.exhausted = api, raw, max_calls, 0, False
        self.errors = 0                  # endpoints that failed for a reason other than 404
        self.failures: list[str] = []    # the first few, for the notes

    def _charge(self) -> bool:
        if self.n >= self.max_calls:
            self.exhausted = True
            return False
        self.n += 1
        return True

    def _fail(self, what: str, exc: BaseException) -> None:
        if _is_missing(exc):
            return
        self.errors += 1
        if len(self.failures) < 5:
            self.failures.append(f"{what} unavailable: {type(exc).__name__}: {str(exc)[:100]}")

    def get_api(self, path: str):
        if not self._charge():
            return None
        try:
            return self.api(path)
        except BudgetExceeded:
            raise                      # the tick's abort signal must never be swallowed here
        except Exception as e:  # noqa: BLE001 — a missing endpoint is a fact; anything else is counted
            self._fail(f"api {path}", e)
            return None

    def get_raw(self, url: str) -> str | None:
        if not self._charge():
            return None
        try:
            return self.raw(url)
        except BudgetExceeded:
            raise
        except Exception as e:  # noqa: BLE001
            self._fail(f"raw {url}", e)
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

def _stem(name: str) -> str:
    for ext in (".bin.gz", ".bin", ".uf2", ".elf", ".zip", ".hex"):
        if name.lower().endswith(ext):
            return name[: -len(ext)]
    return name


def common_prefix(names: list[str]) -> str:
    """Longest common prefix of ≥ 2 asset stems, cut back to a separator, and ONLY when it carries
    a digit (a version/date stamp such as `esp32_marauder_v1_15_1_20260824_`). A digit-free shared
    stem is a vendor/family name (`xiao-` in `xiao-esp32c3` / `xiao-esp32c6`) and stays: stripping
    it would leave chip-only tokens."""
    if len(names) < 2:
        return ""
    p = os.path.commonprefix(names)
    cut = max(p.rfind("_"), p.rfind("-"), p.rfind("."))
    p = p[:cut + 1] if cut >= 0 else ""
    # `esp32_marauder_v1_15_1_20260824_` carries a stamp; `esp32-s3-` and `xiao-` do not
    segs = [x for x in re.split(r"[-_]", p) if x]
    return p if any(_STAMP.match(x) for x in segs) or re.search(r"v\d+_\d+", p) else ""


def clean_token(stem: str) -> str:
    """Drop version/date segments from an asset stem (`firmware-tbeam-2.5.3` → `firmware-tbeam`,
    `mini_v3` stays because `v3` is a board revision, not a dotted version)."""
    parts = re.split(r"([-_])", stem)          # dots stay inside a segment: `2.5.3` is one stamp
    keep, sep = [], ""
    for i in range(0, len(parts), 2):
        seg = parts[i]
        nxt = parts[i + 1] if i + 1 < len(parts) else ""
        if seg and not _STAMP.match(seg):
            keep.append((sep, seg))
        sep = nxt
    return "".join(s + seg for s, seg in keep).lstrip("-_.")


def _has_bins(rel) -> bool:
    return isinstance(rel, dict) and any(isinstance(a, dict) and str(a.get("name", "")).lower().endswith((".bin", ".bin.gz", ".uf2"))
                                         for a in (rel.get("assets") or []))


def release_signals(owner_repo: str, calls: _Calls, notes: list[str]) -> list[Signal]:
    rel = calls.get_api(f"repos/{owner_repo}/releases/latest")
    if isinstance(rel, dict) and not _has_bins(rel):
        # `latest` with no binaries (a tag-only release, or assets still uploading — draftling's
        # v1.0.2 over its v1.0.1 binaries): the newest release that carries them is the evidence.
        rels = calls.get_api(f"repos/{owner_repo}/releases?per_page=10")
        newer = next((r for r in (rels if isinstance(rels, list) else []) if _has_bins(r) and not r.get("draft")), None)
        if newer is not None:
            notes.append(f"latest release {rel.get('tag_name')} has no binaries; read {newer.get('tag_name')} instead")
            rel = newer
    if not isinstance(rel, dict) or not isinstance(rel.get("assets"), list):
        return []
    out: list[Signal] = []
    assets = [a for a in rel["assets"] if isinstance(a, dict) and a.get("name")]
    bins = [a for a in assets if str(a["name"]).lower().endswith((".bin", ".bin.gz", ".uf2"))]
    stems = [_stem(a["name"]) for a in bins]
    prefix = common_prefix(stems)
    repo_prefix = re.compile(r"^" + re.escape(owner_repo.split("/")[-1]) + r"[-_.]", re.I)   # `draftling-m5stack_papers3`
    for a, stem in zip(bins, stems):
        token = stem[len(prefix):] if prefix and stem.startswith(prefix) else stem
        token = repo_prefix.sub("", token)
        if _MULTIPART_SUFFIX.search(token):
            continue                        # `<board>-bootloader` / `-partition-table`: the app image carries the board
        token = clean_token(token)
        if not token or token.lower() in GENERIC_BIN_STEMS:
            continue
        soc = board_alias.chip_only(token)
        out.append(Signal(1, "asset", token, a.get("browser_download_url") or "", soc=soc,
                          extra={"asset": a["name"], "release": rel.get("tag_name")}))
    for a in assets:
        name = str(a["name"])
        if name.lower().endswith(".json") and (a.get("size") or 0) <= MAX_MANIFEST_BYTES and a.get("browser_download_url"):
            text = calls.get_raw(a["browser_download_url"])
            if text is None:
                continue
            try:
                doc = json.loads(text)
            except json.JSONDecodeError:
                notes.append(f"manifest {name}: not JSON")
                continue
            out += manifest_signals(doc, a["browser_download_url"], rel.get("tag_name"))
    return out


def manifest_signals(doc, url: str, release: str | None) -> list[Signal]:
    """Meshtastic: {targets: [{board, platform}]} — ESP32 platforms only. esp-web-tools:
    {name, builds: [{chipFamily, parts: [...]}]} — the board identity is the manifest `name`
    (parts are bootloader/partitions/firmware), chip from chipFamily. Any other shape → []."""
    if not isinstance(doc, dict):
        return []
    out: list[Signal] = []
    targets = doc.get("targets")
    for t in (targets if isinstance(targets, list) else []):
        if not isinstance(t, dict):
            continue
        plat = str(t.get("platform") or "").lower().replace("-", "")
        if plat in ESP_PLATFORMS and t.get("board"):
            out.append(Signal(1, "manifest", str(t["board"]), url, soc=board_alias.chip_only(plat),
                              extra={"platform": plat, "release": release}))
    builds = doc.get("builds")
    if isinstance(builds, list) and builds:
        name = str(doc.get("name") or "").strip()
        for b in builds:
            if not isinstance(b, dict):
                continue
            chip = str(b.get("chipFamily") or "").replace(" ", "")
            soc = board_alias.chip_only(chip)
            token = str(b.get("name") or name).strip()
            if token and not board_alias.chip_only(token):
                out.append(Signal(1, "manifest", token, url, soc=soc, extra={"chipFamily": b.get("chipFamily"), "release": release}))
            elif soc:
                out.append(Signal(1, "manifest", chip, url, soc=soc, extra={"chipFamily": b.get("chipFamily"), "release": release}))
    return out


# --- rank 2: platformio.ini — a faithful-enough model of PlatformIO's project config ---------------

_SECTION = re.compile(r"^\[([^\]]+)\]\s*(?:[;#].*)?$")
_KV = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*=\s*(.*)$")
_INTERP = re.compile(r"\$\{([^}]+)\}")


def _strip_comment(s: str) -> str:
    if s.lstrip().startswith((";", "#")):
        return ""
    return re.split(r"\s+[;#]", s, 1)[0].strip()


def parse_ini(text: str, file: str = "platformio.ini") -> dict[str, dict]:
    """{section: {option(lowercased): {"values": [...], "line": n, "file": file}}}. Multi-line values
    (continuation lines indented) are joined; commented items are dropped; the first assignment of
    an option within one file wins; cross-file override is merge_ini's job."""
    sections: dict[str, dict] = {}
    section, collecting = None, None
    for n, raw in enumerate(text.split("\n"), 1):
        line = raw.rstrip("\r")
        m = _SECTION.match(line)
        if m:
            section = m.group(1).strip()
            sections.setdefault(section, {})
            collecting = None
            continue
        if collecting is not None and (line.startswith(" ") or line.startswith("\t")):
            item = _strip_comment(line.strip())
            if item:
                collecting.extend(x for x in re.split(r"[,\s]+", item) if x)
            continue
        collecting = None
        if section is None or not line.strip() or line.lstrip().startswith((";", "#")):
            continue
        kv = _KV.match(line)
        if not kv:
            continue
        key, rest = kv.group(1).lower(), _strip_comment(kv.group(2))
        if key in sections[section]:
            continue
        values = [x for x in re.split(r"[,\s]+", rest) if x] if rest else []
        sections[section][key] = {"values": values, "line": n, "file": file}
        collecting = values
    return sections


def merge_ini(files: list[tuple[str, str]]) -> dict[str, dict]:
    """All files into ONE config, in read order; a later file's option overrides an earlier one's
    (ConfigParser.read semantics, what PlatformIO does with extra_configs)."""
    merged: dict[str, dict] = {}
    for path, text in files:
        for sec, opts in parse_ini(text, path).items():
            merged.setdefault(sec, {}).update(opts)
    return merged


def _interpolate(values: list[str], sections: dict, depth: int = 0) -> list[str]:
    """Resolve `${section.option}` references; a value still carrying `${` after 4 levels, or
    referencing an unknown option, is dropped (it is not a board id)."""
    out: list[str] = []
    for v in values:
        if "${" not in v:
            out.append(v)
            continue
        if depth > 4:
            continue
        m = _INTERP.fullmatch(v)
        if m and "." in m.group(1):
            sec, opt = m.group(1).rsplit(".", 1)
            ref = sections.get(sec, {}).get(opt.lower())
            if ref:
                out += _interpolate(ref["values"], sections, depth + 1)
            continue

        def sub(mm):
            if "." not in mm.group(1):
                return ""
            sec, opt = mm.group(1).rsplit(".", 1)
            ref = sections.get(sec, {}).get(opt.lower())
            return " ".join(_interpolate(ref["values"], sections, depth + 1)) if ref else ""
        s = _INTERP.sub(sub, v).strip()
        if s and "${" not in s:
            out.append(s)
    return out


def board_of(sections: dict, name: str, depth: int = 0, seen: frozenset = frozenset()) -> tuple[str | None, int | None, str | None]:
    """(board id, line, file) for a section: its own `board`, else its `extends` parents with the
    LAST listed parent winning (PlatformIO pops the extends queue from the end), else None."""
    sec = sections.get(name)
    if sec is None or depth > 6 or name in seen:
        return None, None, None
    seen = seen | {name}
    b = sec.get("board")
    if b:
        vals = _interpolate(b["values"], sections)
        if vals:
            return vals[0], b["line"], b["file"]
    for parent in reversed((sec.get("extends") or {"values": []})["values"]):
        found = board_of(sections, parent, depth + 1, seen)
        if found[0]:
            return found
    return None, None, None


def envs_of(sections: dict) -> dict[str, dict]:
    """{env: {"board", "line", "file"}} for every [env:*] in the merged config; the `[env]` section
    supplies the default when neither the env nor its parents declare a board."""
    envs = {}
    for name in sections:
        if not name.startswith("env:"):
            continue
        board, line, file = board_of(sections, name)
        if board is None:
            board, line, file = board_of(sections, "env")
        envs[name[4:]] = {"board": board, "line": line, "file": file}
    return envs


def parse_platformio(text: str) -> dict:
    """Single-file view: envs + extra_configs + default_envs (the root file, and tests)."""
    sections = parse_ini(text)
    plat = sections.get("platformio", {})
    return {"envs": {k: {"board": v["board"], "line": v["line"]} for k, v in envs_of(sections).items()},
            "extra_configs": list((plat.get("extra_configs") or {"values": []})["values"]),
            "default_envs": list((plat.get("default_envs") or {"values": []})["values"])}


def glob_to_regex(pattern: str) -> re.Pattern:
    """PlatformIO expands extra_configs with glob.glob(recursive=True): `*` and `?` never cross
    `/`, `**/` matches zero or more directories. Anchored to the whole path."""
    p = pattern.strip()
    while p.startswith("./"):
        p = p[2:]
    out, i = "", 0
    while i < len(p):
        if p.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif p.startswith("**", i):
            out += ".*"
            i += 2
        elif p[i] == "*":
            out += "[^/]*"
            i += 1
        elif p[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(p[i])
            i += 1
    return re.compile("^" + out + "$")


def _chip_priority(path: str) -> tuple:
    """When the extra_configs cap bites, keep files that name an ESP32 family first (Meshtastic's
    tree is 190 files, alphabetically nrf52 before esp32s3), then everything else, by path."""
    lp = path.lower()
    return (0 if "esp32" in lp else 1, path)


def platformio_signals(owner_repo: str, ref: str, calls: _Calls, notes: list[str], tree: list[str] | None) -> list[Signal]:
    base_raw = f"https://raw.githubusercontent.com/{owner_repo}/{ref}/"
    base_blob = f"https://github.com/{owner_repo}/blob/{ref}/"
    text = calls.get_raw(base_raw + "platformio.ini")
    if text is None:
        return []
    files = [("platformio.ini", text)]
    root = parse_ini(text)
    globs = list((root.get("platformio", {}).get("extra_configs") or {"values": []})["values"])
    if globs:
        if tree is None:
            notes.append("extra_configs present but no tree listing; globs not expanded")
        else:
            matched = []
            for g in globs:
                rx = glob_to_regex(g)
                matched += [p for p in tree if rx.match(p) and p != "platformio.ini"]
            matched = list(dict.fromkeys(matched))
            if len(matched) > MAX_EXTRA_CONFIG_FILES:
                matched = sorted(matched, key=_chip_priority)[:MAX_EXTRA_CONFIG_FILES]
                notes.append(f"extra_configs matched more than {MAX_EXTRA_CONFIG_FILES} files; kept the {MAX_EXTRA_CONFIG_FILES} naming an ESP32 family first")
            for p in matched:
                t = calls.get_raw(base_raw + p)
                if t is not None:
                    files.append((p, t))
                elif calls.exhausted:
                    notes.append("call budget exhausted while expanding extra_configs")
                    break
    merged = merge_ini(files)
    out: list[Signal] = []
    for env, info in envs_of(merged).items():
        if env in IGNORED_ENVS or not info["board"] or "${" in info["board"]:
            continue
        out.append(Signal(2, "platformio", info["board"], f"{base_blob}{info['file']}#L{info['line']}",
                          line=info["line"], extra={"env": env, "file": info["file"]}))
    return out


# --- rank 3: CI matrix ---------------------------------------------------------------------------

def _matrix_scalars(node, out: list[str]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "exclude" or k in ("os", "runs-on", "python-version", "node-version", "python", "node"):
                continue
            _matrix_scalars(v, out)
    elif isinstance(node, list):
        for v in node:
            _matrix_scalars(v, out)
    elif isinstance(node, str):
        s = node.strip()
        if s and len(s) <= 64 and not s.startswith("${{") and not _RUNNER.match(s) and not _VERSIONISH.match(s):
            out.append(s)


def ci_signals(owner_repo: str, ref: str, calls: _Calls, notes: list[str], tree: list[str] | None) -> list[Signal]:
    if not tree:
        return []
    try:
        import yaml
    except ImportError:  # pragma: no cover
        notes.append("pyyaml missing; CI matrix skipped")
        return []
    wfs = [p for p in tree if p.startswith(".github/workflows/") and p.endswith((".yml", ".yaml"))]
    if len(wfs) > MAX_WORKFLOWS:
        wfs = sorted(wfs, key=lambda p: (0 if re.search(r"build|firmware|release|ci", p, re.I) else 1, p))[:MAX_WORKFLOWS]
        notes.append(f"more than {MAX_WORKFLOWS} workflows; kept the {MAX_WORKFLOWS} named build/firmware/release/ci first")
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
            if isinstance(matrix, dict):
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
    if "idf_component.yml" in have:
        t = calls.get_raw(base_raw + "idf_component.yml")
        if t:
            try:
                import yaml
                doc = yaml.safe_load(t) or {}
            except Exception:  # noqa: BLE001
                doc = {}
            targets = doc.get("targets") if isinstance(doc, dict) else None
            for tg in (targets if isinstance(targets, list) else []):
                soc = board_alias.chip_only(str(tg))
                if soc:
                    line = next((n for n, l in enumerate(t.split("\n"), 1) if str(tg) in l), None)
                    url = base_blob + "idf_component.yml" + (f"#L{line}" if line else "")
                    out.append(Signal(4, "idf", str(tg), url, soc=soc, line=line))
    for p in sorted(x for x in have if x == "sdkconfig.defaults" or re.match(r"^sdkconfig\.defaults\.esp32[a-z0-9]*$", x)):
        if p != "sdkconfig.defaults":
            chip = p.split(".")[-1]
            soc = board_alias.chip_only(chip)
            if soc:
                out.append(Signal(4, "idf", chip, base_blob + p, soc=soc))     # the file name names the target
            continue
        t = calls.get_raw(base_raw + p)
        if t:
            for n, line in enumerate(t.split("\n"), 1):
                m = re.match(r'^\s*CONFIG_IDF_TARGET="?([a-z0-9]+)"?', line)
                if m and board_alias.chip_only(m.group(1)):
                    out.append(Signal(4, "idf", m.group(1), base_blob + f"{p}#L{n}", soc=board_alias.chip_only(m.group(1)), line=n))
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
    plus the citation date, the call count and notes. A failing extractor is a note, not an
    exception; only the tick's BudgetExceeded propagates."""
    calls = _Calls(api, raw, max_calls)
    notes: list[str] = []
    today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if ref is None:
        meta = calls.get_api(f"repos/{owner_repo}")
        ref = (meta.get("default_branch") if isinstance(meta, dict) else None) or "main"
        if not isinstance(meta, dict):
            notes.append("repo metadata unavailable, assumed ref=main")
    tree_doc = calls.get_api(f"repos/{owner_repo}/git/trees/{ref}?recursive=1")
    tree = None
    if isinstance(tree_doc, dict) and isinstance(tree_doc.get("tree"), list):
        tree = [t["path"] for t in tree_doc["tree"] if isinstance(t, dict) and t.get("type") == "blob" and t.get("path")]
        if tree_doc.get("truncated"):
            notes.append("tree listing truncated by GitHub")
    signals: list[Signal] = []
    for name, fn in (("release", lambda: release_signals(owner_repo, calls, notes)),
                     ("platformio", lambda: platformio_signals(owner_repo, ref, calls, notes, tree)),
                     ("ci", lambda: ci_signals(owner_repo, ref, calls, notes, tree)),
                     ("idf", lambda: idf_signals(owner_repo, ref, calls, notes, tree))):
        try:
            signals += fn()
        except BudgetExceeded:
            raise
        except Exception as e:  # noqa: BLE001 — one broken extractor must not hide the others
            notes.append(f"{name} extractor failed: {type(e).__name__}: {str(e)[:120]}")
    if calls.exhausted:
        notes.append(f"call budget exhausted at {max_calls}")
    notes += calls.failures
    return {"repo": owner_repo, "ref": ref, "fetched": today, "calls": calls.n, "errors": calls.errors,
            "signals": [asdict(s) for s in signals], "notes": notes}


_DEVKIT_ENV = re.compile(r"^esp32(?:[chsp]\d+)?dev")     # esp32dev, esp32c5dev, esp32s3dev_8MB_opi: the devkit-targeting env idiom


def _generic_base(signal: dict, atlas_id: str, atlas: dict) -> bool:
    """True when a rank-2 platformio `board =` value names an Espressif devkit but the env that
    carries it is named after some other product. Accepted as a devkit target only when the env
    name follows the devkit idiom (`esp32c5dev`), says `devkit`, or repeats the board id."""
    if signal.get("kind") != "platformio" or (atlas.get(atlas_id) or {}).get("brand") != "espressif":
        return False
    env = board_alias.compact(str((signal.get("extra") or {}).get("env") or ""))
    if not env:
        return False
    return not (_DEVKIT_ENV.match(env) or "devkit" in env or board_alias.compact(atlas_id) in env)


def resolve(derived: dict, boards: dict[str, dict] | None = None) -> dict:
    """Map every signal to a catalogued board through jr/board_alias.resolve_token. Returns
    {"boards": {atlas_id: [signal, ...]}, "socs": {soc: [signal, ...]}, "unresolved": [signal, ...]}.
    A board keeps every signal that named it, highest rank first; a chip-only signal lands in
    `socs`. Nothing here decides what to write — the writer does, from the best rank per board.
    `boards` is the atlas to resolve against (default: this clone's; the tick passes its worktree's)."""
    atlas = boards if boards is not None else board_alias.atlas_boards()
    boards: dict[str, list] = {}
    socs: dict[str, list] = {}
    unresolved: list = []
    for s in derived.get("signals", []):
        r = board_alias.resolve_token(s["token"], soc=s.get("soc"), boards=atlas)
        if r and r.get("atlas_id") and _generic_base(s, r["atlas_id"], atlas):
            # An Espressif devkit id used as the BASE of a product-specific PlatformIO env (Bruce's
            # `board = esp32-s3-devkitc1-n16r8` under env `elecrow-advance-35-s3`) proves the chip,
            # not that the firmware targets the bare devkit: chip evidence only, never a recipe.
            chip = atlas[r["atlas_id"]].get("soc")
            if chip:
                socs.setdefault(chip, []).append(s)
            unresolved.append({**s, "how": "generic_base"})
        elif r and r.get("atlas_id"):
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
