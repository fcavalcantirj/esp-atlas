"""EspAtlas Jr — the device-build evidence gate (jr/device_evidence.py).

A firmware record says "you flash this onto an ESP". Popularity, dedup and the library/demo noise
gates never checked that; rebelthor/warble (a Go server for Linux/macOS that talks to stock
xiaozhi-esp32 over WebSocket) was admitted as ESP32-S3 firmware on its GitHub topics alone
(review finding 3, 2026-11-04). So before ANY firmware record is authored — launcher, topics and
submission paths alike — the repo must show evidence that it TARGETS an ESP chip. Owner rule: a
generic build file or binary is never enough, and an ambiguous repo goes to a human, never guessed.

  platformio    a `platformio.ini` whose `platform` names espressif32, its `extra_configs` and
                `${section.option}` references resolved (derive's ini model)
  idf_project   a `CMakeLists.txt` including ESP-IDF's `project.cmake` AND an ESP target stated:
                `CONFIG_IDF_TARGET` in sdkconfig.defaults (or a committed sdkconfig), `targets`
                in an idf_component.yml, or `target` in a dependencies.lock
  arduino_sketch  a `*.ino` AND an ESP board named: a sketch.yaml fqbn `<vendor>:esp32:<board>`,
                a build workflow compiling for one, or library.properties `architectures=esp32`
  release_bin   a non-draft release `.bin` whose first 16 bytes (one ranged GET) are an ESP image
                header: magic 0xE9 at offset 0, a known chip id (LE u16) at offset 12

Three verdicts. `esp_target`: one signal above holds (ok=True). `needs_review`: only the ambiguous
half of one was found — project.cmake with no stated target, a bare .ino, a .bin without the
header, a .uf2 / .bin.gz, an idf_component.yml with no project — so a human decides (ok=False,
reason `needs_review_target`). `not_device_firmware`: nothing at all (ok=False). Both rejects are
remembered memory.NO_BUILD_SIGNAL_DAYS. An endpoint that failed for any reason other than 404 is
not a fact about the repo: the answer is unknown (ok=None, `device_evidence_unreadable`, retried
after memory.UNRESOLVED_REJECT_DAYS), never a rejection.

Network effects are injected (`api`, `raw`, `head`) exactly as in jr/derive.py and charged through
its _Calls, so tests run offline and `max_calls` bounds one check. The tick's BudgetExceeded passes
through untouched. Read-only: this module writes nothing.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

import derive
import memory
from budget import BudgetExceeded

ESP_TARGET = "esp_target"
NOT_DEVICE_FIRMWARE = "not_device_firmware"
NEEDS_REVIEW = "needs_review"
NEEDS_REVIEW_TARGET = "needs_review_target"     # the ledger/report reason key of a needs_review result
EVIDENCE_UNREADABLE = "device_evidence_unreadable"
DEFERRED = "device_evidence_deferred"   # not checked this tick (budget): neither remembered nor answered
MAX_BUILD_FILES = 3            # per file kind, shallowest first (the project root wins)
MAX_CALLS = 3 + 4 * MAX_BUILD_FILES   # tree + releases + one ranged GET; platformio.ini, CMakeLists.txt, IDF target, Arduino board files
IMAGE_HEADER_BYTES = 16

# ESP-IDF components/bootloader_support/include/esp_app_format.h: esp_image_header_t / esp_chip_id_t.
ESP_IMAGE_MAGIC = 0xE9
ESP_CHIP_IDS = {0x0000: "ESP32", 0x0002: "ESP32-S2", 0x0005: "ESP32-C3", 0x0009: "ESP32-S3",
                0x000C: "ESP32-C2", 0x000D: "ESP32-C6", 0x0010: "ESP32-H2", 0x0012: "ESP32-P4",
                0x0014: "ESP32-C61", 0x0017: "ESP32-C5", 0x0019: "ESP32-H21", 0x001C: "ESP32-H4",
                0x0020: "ESP32-S31"}
# ESP-IDF tools/idf_py_actions/constants.py SUPPORTED_TARGETS + PREVIEW_TARGETS, less `linux`.
IDF_TARGETS = frozenset({"esp32", "esp32s2", "esp32s3", "esp32c2", "esp32c3", "esp32c5", "esp32c6", "esp32c61",
                         "esp32h2", "esp32h21", "esp32h4", "esp32p4", "esp32s31"})

_PROJECT_CMAKE = re.compile(r"^\s*include\s*\(.*project\.cmake", re.I)
_TARGET_FILES = ("sdkconfig.defaults", "sdkconfig", "dependencies.lock", "idf_component.yml")
_SDK_TARGET = re.compile(r"""^\s*CONFIG_IDF_TARGET\s*=\s*["']?([\w-]+)["']?\s*$""")
_LOCK_TARGET = re.compile(r"""^target\s*:\s*["']?([\w-]+)""")
_YML_TARGETS = re.compile(r"^targets\s*:\s*(.*)$")
_YML_ITEM = re.compile(r"""^\s*-\s*["']?([\w-]+)""")
_SKETCH_FQBN = re.compile(r"^\s*(?:default_)?fqbn\s*:\s*[\w.-]+:esp32:[\w.-]+")
_ESP_FQBN = re.compile(r"\b[\w.-]+:esp32:[\w.-]+")
_ARCHITECTURES = re.compile(r"^\s*architectures\s*=\s*(.*)$")
_NOT_AN_APP = re.compile(r"partition|boot_app0|ota_data|spiffs|littlefs|fatfs|nvs", re.I)
_TTLS = {NOT_DEVICE_FIRMWARE: memory.NO_BUILD_SIGNAL_DAYS, NEEDS_REVIEW_TARGET: memory.NO_BUILD_SIGNAL_DAYS,
         EVIDENCE_UNREADABLE: memory.UNRESOLVED_REJECT_DAYS}


def gh_api(gh):
    """api(path) -> parsed JSON over a `gh` callable (the tick's counted ctx.gh). A failed call
    raises with gh's stderr, so derive._Calls tells a 404 (a fact) from an outage (unknown)."""
    def api(path):
        p = gh("api", path)
        if getattr(p, "returncode", 1) != 0:
            raise RuntimeError((getattr(p, "stderr", "") or "gh api failed").strip()[:200])
        return json.loads(p.stdout or "null")
    return api


def default_head(url: str, nbytes: int) -> bytes | None:
    """The first `nbytes` of a release asset: ONE ranged GET (`Range: bytes=0-<n-1>`; a server that
    ignores the range is still read no further). 404 / 416 (nothing that long) -> None."""
    import urllib.error
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "esp-atlas-jr-derive/0.1",
                                               "Range": f"bytes=0-{nbytes - 1}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read(nbytes)
    except urllib.error.HTTPError as e:
        if e.code in (404, 416):
            return None
        raise


def esp_image_chip(header: bytes | None) -> str | None:
    """The chip an ESP image header names ("ESP32-S3"), or None: no 0xE9 magic, too short, or a
    chip id ESP-IDF does not define."""
    if not header or len(header) < 14 or header[0] != ESP_IMAGE_MAGIC:
        return None
    return ESP_CHIP_IDS.get(int.from_bytes(header[12:14], "little"))


class _Calls(derive._Calls):
    """derive's call counter plus the ranged GET of a release asset's header."""

    def __init__(self, api, raw, head, max_calls: int):
        super().__init__(api, raw, max_calls)
        self.head = head

    def get_head(self, url: str) -> bytes | None:
        if not self._charge():
            return None
        try:
            return self.head(url, IMAGE_HEADER_BYTES)
        except BudgetExceeded:
            raise
        except Exception as e:  # noqa: BLE001 — a missing asset is a fact; anything else is counted
            self._fail(f"head {url}", e)
            return None


@dataclass
class _Hit:
    verdict: str        # ESP_TARGET or NEEDS_REVIEW
    kind: str
    url: str
    why: str


@dataclass
class _Repo:
    owner_repo: str
    ref: str
    calls: _Calls
    tree: list[str] | None
    truncated: bool

    def read(self, path: str) -> str | None:
        return self.calls.get_raw(f"https://raw.githubusercontent.com/{self.owner_repo}/{self.ref}/{path}")

    def cite(self, path: str, line: int | None = None) -> str:
        return f"https://github.com/{self.owner_repo}/blob/{self.ref}/{path}" + (f"#L{line}" if line else "")

    def listed(self, keep) -> list[str]:
        """Tree paths `keep(path)` accepts, shallowest first."""
        return sorted((p for p in (self.tree or []) if keep(p)), key=lambda p: (p.count("/"), p))

    def shallowest(self, name: str) -> list[str]:
        """Up to MAX_BUILD_FILES paths named `name`, root first. No (or a truncated) listing still
        tries the root file, the one place a project's own build file must live."""
        return self.with_fallbacks(self.listed(lambda p: _base(p) == name), [name])

    def with_fallbacks(self, paths: list[str], fallbacks: list[str]) -> list[str]:
        if self.tree is None or self.truncated:
            paths = [f for f in fallbacks if f not in paths] + paths
        return paths[:MAX_BUILD_FILES]


def _base(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def _dir(path: str) -> str:
    return path[: path.rfind("/") + 1]


# --- platformio ------------------------------------------------------------------------------------

def _extra_configs(path: str, text: str, tree: list[str] | None) -> list[str]:
    """The tree files a platformio.ini's `extra_configs` globs match (relative to its directory),
    ESP32-named first (derive._chip_priority), at most MAX_BUILD_FILES."""
    base = _dir(path)
    globs = (derive.parse_ini(text, path).get("platformio", {}).get("extra_configs") or {"values": []})["values"]
    matched = [p for g in globs for p in (tree or [])
               if p.startswith(base) and p != path and derive.glob_to_regex(g).match(p[len(base):])]
    return sorted(dict.fromkeys(matched), key=derive._chip_priority)[:MAX_BUILD_FILES]


def _platformio_hit(repo: _Repo, path: str) -> tuple[str, int] | None:
    """(file, line) of the first `platform =` option naming espressif32 — the official platform, a
    pinned `espressif32@x`, or a fork URL such as pioarduino's platform-espressif32 — across the
    file and its extra_configs, `${section.option}` resolved the way derive models PlatformIO."""
    text = repo.read(path)
    if not text:
        return None
    files = [(path, text)]
    for extra in _extra_configs(path, text, repo.tree):
        t = repo.read(extra)
        if t:
            files.append((extra, t))
    order = {f: i for i, (f, _t) in enumerate(files)}
    sections = derive.merge_ini(files)
    hits = [(order[opt["file"]], opt["line"], opt["file"]) for opts in sections.values() for key, opt in opts.items()
            if key == "platform" and any("espressif32" in v.lower() for v in derive._interpolate(opt["values"], sections))]
    return (min(hits)[2], min(hits)[1]) if hits else None


def _platformio(repo: _Repo) -> _Hit | None:
    for p in repo.shallowest("platformio.ini"):
        hit = _platformio_hit(repo, p)
        if hit:
            return _Hit(ESP_TARGET, "platformio", repo.cite(*hit), f"platformio.ini platform espressif32 ({hit[0]})")
    return None


# --- ESP-IDF project -------------------------------------------------------------------------------

def _stated_target(name: str, text: str) -> tuple[int, str] | None:
    """(line, target) of the first ESP target a target file states, or None."""
    lines = text.split("\n")
    if name.startswith("sdkconfig"):
        found = ((n, _SDK_TARGET.match(ln)) for n, ln in enumerate(lines, 1))
    elif name == "dependencies.lock":
        found = ((n, _LOCK_TARGET.match(ln)) for n, ln in enumerate(lines, 1))
    else:
        found = _yml_targets(lines)
    return next(((n, m.group(1).lower()) for n, m in found if m and m.group(1).lower() in IDF_TARGETS), None)


def _yml_targets(lines: list[str]):
    """(line, match) per item of an idf_component.yml top-level `targets:` list, block or flow."""
    for i, ln in enumerate(lines):
        head = _YML_TARGETS.match(ln)
        if not head:
            continue
        inline = head.group(1).split("#")[0].strip()
        if inline:
            for item in inline.strip("[]").split(","):
                yield i + 1, re.match(r"""\s*["']?([\w-]+)""", item)
            return
        for n, item in enumerate(lines[i + 1:], i + 2):
            if item.strip() and not item.lstrip().startswith("#") and not item[0].isspace() and not item.startswith("-"):
                return
            yield n, _YML_ITEM.match(item)
        return


def _idf_target(repo: _Repo, project_dir: str) -> tuple[str, int, str] | None:
    """(file, line, target) of an ESP target the project states, its own directory first. A
    vendored managed_components/ manifest describes a dependency, not this project."""
    listed = sorted(repo.listed(lambda p: _base(p) in _TARGET_FILES and "managed_components/" not in p),
                    key=lambda p: (not p.startswith(project_dir), p.count("/"), _TARGET_FILES.index(_base(p)), p))
    fallbacks = [project_dir + f for f in ("sdkconfig.defaults", "main/idf_component.yml", "dependencies.lock")]
    for p in repo.with_fallbacks(listed, fallbacks):
        stated = _stated_target(_base(p), repo.read(p) or "")
        if stated:
            return p, stated[0], stated[1]
    return None


def _idf_project(repo: _Repo) -> _Hit | None:
    for p in repo.shallowest("CMakeLists.txt"):
        line = next((n for n, ln in enumerate((repo.read(p) or "").split("\n"), 1) if _PROJECT_CMAKE.match(ln)), None)
        if not line:
            continue
        target = _idf_target(repo, _dir(p))
        if target:
            return _Hit(ESP_TARGET, "idf_project", repo.cite(target[0], target[1]),
                        f"ESP-IDF project ({p}) targeting {target[2]} ({target[0]})")
        return _Hit(NEEDS_REVIEW, "idf_project", repo.cite(p, line),
                    "ESP-IDF project.cmake but no ESP target stated (sdkconfig.defaults CONFIG_IDF_TARGET, "
                    "idf_component.yml targets, dependencies.lock target)")
    component = repo.listed(lambda p: _base(p) == "idf_component.yml" and "managed_components/" not in p)
    if component:
        return _Hit(NEEDS_REVIEW, "idf_component", repo.cite(component[0]),
                    "an idf_component.yml but no ESP-IDF project (CMakeLists.txt including project.cmake)")
    return None


# --- Arduino sketch --------------------------------------------------------------------------------

def _board_files(repo: _Repo) -> list[str]:
    """Where a sketch names its board: sketch.yaml, library.properties, then build workflows."""
    sketch = repo.listed(lambda p: _base(p) in ("sketch.yaml", "sketch.yml"))
    props = repo.listed(lambda p: _base(p) == "library.properties")
    workflows = repo.listed(lambda p: p.startswith(".github/workflows/") and p.endswith((".yml", ".yaml")))
    return (sketch + props + workflows)[:MAX_BUILD_FILES]


def _esp_board_line(path: str, text: str) -> int | None:
    """The line naming an ESP board: an esp32 fqbn (sketch.yaml / workflow) or architectures=esp32."""
    for n, ln in enumerate(text.split("\n"), 1):
        if _base(path) == "library.properties":
            m = _ARCHITECTURES.match(ln)
            if m and "esp32" in [a.strip().lower() for a in m.group(1).split(",")]:
                return n
        elif (_SKETCH_FQBN if _base(path).startswith("sketch.") else _ESP_FQBN).search(ln):
            return n
    return None


def _arduino(repo: _Repo) -> _Hit | None:
    sketches = repo.listed(lambda p: p.lower().endswith(".ino"))
    if not sketches:
        return None
    for p in _board_files(repo):
        line = _esp_board_line(p, repo.read(p) or "")
        if line:
            return _Hit(ESP_TARGET, "arduino_sketch", repo.cite(p, line), f"Arduino sketch {sketches[0]} built for an ESP board ({p})")
    return _Hit(NEEDS_REVIEW, "arduino_sketch", repo.cite(sketches[0]),
                "a .ino but no ESP board named (sketch.yaml fqbn, esp32 build workflow, library.properties architectures=esp32)")


# --- release binary --------------------------------------------------------------------------------

def _release_bin(repo: _Repo) -> _Hit | None:
    rels = repo.calls.get_api(f"repos/{repo.owner_repo}/releases?per_page=10")
    rel = next((r for r in (rels if isinstance(rels, list) else []) if derive._has_bins(r) and not r.get("draft")), None)
    if rel is None:
        return None
    assets = [a for a in rel["assets"] if isinstance(a, dict) and str(a.get("name", "")).lower().endswith((".bin", ".bin.gz", ".uf2"))]
    page = f"https://github.com/{repo.owner_repo}/releases/tag/{rel.get('tag_name')}"
    bins = sorted((a for a in assets if a["name"].lower().endswith(".bin")), key=lambda a: bool(_NOT_AN_APP.search(a["name"])))
    if not bins:
        return _Hit(NEEDS_REVIEW, "release_bin", assets[0].get("browser_download_url") or page,
                    f"release ships {assets[0]['name']} only; no ESP image header to read")
    name, url = bins[0]["name"], bins[0].get("browser_download_url")
    chip = esp_image_chip(repo.calls.get_head(url)) if url else None
    if chip:
        return _Hit(ESP_TARGET, "release_bin", url, f"{name}: ESP image header for {chip}")
    return _Hit(NEEDS_REVIEW, "release_bin", url or page, f"{name} is not an ESP image (magic 0xE9 + a known chip id at offset 12)")


# --- the check -------------------------------------------------------------------------------------

_PROBES = (_platformio, _idf_project, _arduino, _release_bin)


def _listing(owner_repo: str, ref: str, calls: _Calls, notes: list[str]) -> tuple[list[str] | None, bool]:
    doc = calls.get_api(f"repos/{owner_repo}/git/trees/{ref}?recursive=1")
    if not (isinstance(doc, dict) and isinstance(doc.get("tree"), list)):
        return None, False
    if doc.get("truncated"):
        notes.append("tree listing truncated by GitHub")
    return [t["path"] for t in doc["tree"] if isinstance(t, dict) and t.get("type") == "blob" and t.get("path")], bool(doc.get("truncated"))


def _result(ok, verdict, calls, notes, hit: _Hit | None = None, ambiguous=()) -> dict:
    return {"ok": ok, "verdict": verdict, "kind": hit.kind if hit else None, "url": hit.url if hit else None,
            "calls": calls.n, "notes": notes, "ambiguous": [{"kind": a.kind, "url": a.url, "why": a.why} for a in ambiguous]}


def check(owner_repo: str, *, api=None, raw=None, head=None, ref: str | None = None, max_calls: int = MAX_CALLS) -> dict:
    """{"ok", "verdict", "kind", "url", "calls", "notes", "ambiguous"} for `owner/repo` at `ref`
    (default HEAD, the default branch). ok=True only for ESP_TARGET; NEEDS_REVIEW and
    NOT_DEVICE_FIRMWARE are ok=False; unknown is ok=None, verdict None. Stops at the first ESP
    target; a needs_review result cites its first ambiguous signal and lists them all.
    `api`/`raw`/`head` default to derive.default_api/default_raw and default_head."""
    ref = ref or "HEAD"
    calls, notes = _Calls(api or derive.default_api, raw or derive.default_raw, head or default_head, max_calls), []
    repo = _Repo(owner_repo, ref, calls, *_listing(owner_repo, ref, calls, notes))
    ambiguous = []
    for probe in _PROBES:
        hit = probe(repo)
        if hit and hit.verdict == ESP_TARGET:
            return _result(True, ESP_TARGET, calls, notes + [hit.why], hit)
        if hit:
            ambiguous.append(hit)
    if calls.exhausted:
        notes.append(f"call budget exhausted at {max_calls}")
    notes += calls.failures
    if calls.errors:          # an unread file could have stated the target: retry, never decide
        return _result(None, None, calls, notes)
    if ambiguous:
        return _result(False, NEEDS_REVIEW, calls, notes + [a.why for a in ambiguous], ambiguous[0], ambiguous)
    if calls.exhausted:
        return _result(None, None, calls, notes)
    return _result(False, NOT_DEVICE_FIRMWARE, calls, notes)


def deferred(why: str) -> dict:
    """A check that was not run (e.g. the tick cannot afford MAX_CALLS): not ok, not a fact."""
    return {"ok": None, "verdict": None, "deferred": True, "kind": None, "url": None, "calls": 0, "notes": [why], "ambiguous": []}


def reject_reason(result: dict) -> str:
    """The ledger/report reason for a result that is not ok (`<key>: <detail>`)."""
    if result.get("deferred"):
        return f"{DEFERRED}: {'; '.join(result.get('notes') or [])[:120]}"
    if result.get("ok") is None:
        return f"{EVIDENCE_UNREADABLE}: {'; '.join(result.get('notes') or ['endpoint unavailable'])[:120]}"
    if result.get("verdict") == NEEDS_REVIEW:
        return f"{NEEDS_REVIEW_TARGET}: " + "; ".join(f"{a['kind']}: {a['why']}" for a in result.get("ambiguous") or [])[:240]
    return (f"{NOT_DEVICE_FIRMWARE}: no espressif32 platformio.ini, ESP-IDF project, "
            "Arduino sketch or release .bin")


def review_note(result: dict) -> dict:
    """{"kind", "url", "why"} of a needs_review result, for the owner's list in the tick report."""
    return {"kind": result.get("kind"), "url": result.get("url"),
            "why": "; ".join(a["why"] for a in result.get("ambiguous") or [])}


def ttl_days(reason: str) -> int:
    """Memory TTL for a reject_reason(): no build signal and needs review re-check in
    NO_BUILD_SIGNAL_DAYS, an unreadable repo in UNRESOLVED_REJECT_DAYS."""
    return _TTLS.get(reason.split(":")[0], memory.SEEN_TTL_DAYS)
