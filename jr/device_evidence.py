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
  release_bin   a non-draft release `.bin` that jr/esp_image.py validates offline as a whole ESP
                image: a chip the pinned esptool parser knows, every segment walked, checksum and
                appended SHA-256 recomputed and matched (chip target + integrity, never authorship).
                The asset is fetched by jr/safe_fetch.py (https only, redirects re-validated per
                hop, public addresses only, 16 MB cap while streaming, timeouts) and validated in
                jr/image_sandbox.py's restricted child (no credentials, network or serial)

Whose evidence. A signal counts only when it belongs to the project being classified: found at the
repo root, or in the project's declared build directory — any non-vendored dir when the root holds
no project of its own (a host manifest such as go.mod / package.json / pyproject.toml, or a generic
build file such as CMakeLists.txt / Makefile; a truncated listing counts as one), else only a dir
the root README or build file points to (`cd firmware`, `pio run -d firmware`, `firmware/platformio.ini`).
A signal found ONLY under a vendored or example tree (examples/, test/, third_party/, vendor/,
lib/, managed_components/, node_modules/, .pio/, build/, a git submodule …) is needs_review with
`vendored_or_example_only`; one only in a host repo's undeclared subdir is needs_review with
`undeclared_project_dir`. Neither is ever esp_target: a server that vendors an ESP example is not
ESP firmware, and when unsure a human decides.

Three verdicts. `esp_target`: one signal above holds (ok=True). `needs_review`: only the ambiguous
half of one was found — project.cmake with no stated target, a bare .ino, a .bin the validator
sends to review (merged, truncated, corrupt, unknown chip, not an image), a .bin whose fetch was
refused, timed out or overflowed the cap, a validator child that crashed, timed out or printed
garbage, a .uf2 / .bin.gz, an idf_component.yml with no project — so a human decides (ok=False,
reason `needs_review_target`). `not_device_firmware`: nothing at all (ok=False). Both rejects are
remembered memory.NO_BUILD_SIGNAL_DAYS. An endpoint that failed for any reason other than 404 is
not a fact about the repo: the answer is unknown (ok=None, `device_evidence_unreadable`, retried
after memory.UNRESOLVED_REJECT_DAYS), never a rejection.

Network effects are injected (`api`, `raw`, `fetch`) exactly as in jr/derive.py and charged through
its _Calls, so tests run offline and `max_calls` bounds one check. The tick's BudgetExceeded passes
through untouched. Read-only: this module writes nothing.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import cached_property

import derive
import esp_image
import image_sandbox
import memory
import safe_fetch
from budget import BudgetExceeded

ESP_TARGET = "esp_target"
NOT_DEVICE_FIRMWARE = "not_device_firmware"
NEEDS_REVIEW = "needs_review"
NEEDS_REVIEW_TARGET = "needs_review_target"     # the ledger/report reason key of a needs_review result
EVIDENCE_UNREADABLE = "device_evidence_unreadable"
DEFERRED = "device_evidence_deferred"   # not checked this tick (budget): neither remembered nor answered
VENDORED_OR_EXAMPLE_ONLY = "vendored_or_example_only"   # a needs_review why: the signal is another project's
UNDECLARED_PROJECT_DIR = "undeclared_project_dir"       # a needs_review why: a host repo's subdir nothing points to
OWN = "own"
MAX_BUILD_FILES = 3            # per file kind, the project's own first, then shallowest (the root wins)
# tree + releases + one asset GET + MAX_BUILD_FILES each of platformio.ini, CMakeLists.txt, IDF target
# and Arduino board files + .gitmodules, the root README and one root build file (whose evidence).
# A platformio.ini's extra_configs share the same cap, so a repo with many can exhaust it: then an
# ambiguous signal already found goes to review, and none at all is unknown.
MAX_CALLS = 6 + 4 * MAX_BUILD_FILES
MAX_IMAGE_BYTES = safe_fetch.MAX_BYTES     # the owner's 16 MB cap on a release asset
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
_FQBN = re.compile(r"[\w.-]+:[\w.-]+:[\w.,=:-]+")
_SKETCH_PATHS = re.compile(r"^(\s*)-?\s*sketch-paths\s*:\s*(.*)$")
_ROOT_DOT = re.compile(r"(?<![\w./-])\./?(?![\w./-])")
_ARCHITECTURES = re.compile(r"^\s*architectures\s*=\s*(.*)$")
# Trees that hold OTHER projects' code (PlatformIO lib/, Arduino libraries/, IDF components, vendored
# deps): their sketches and compatibility claims say nothing about what this repo targets.
_VENDORED = re.compile(r"(^|/)(lib|libs|libraries|\.pio|managed_components|components|vendor|third_party|external)/", re.I)
# Trees that hold another project's or an example's code, for platformio / ESP-IDF / Arduino board
# evidence. components/ itself is an IDF project's own; its components/<name>/examples are not.
# A dir merely NAMED like an example (esp32-example/, my_demo/) is one too: when unsure, review.
_VENDORED_OR_EXAMPLE = re.compile(
    r"(^|/)(tests?|third[-_]?party|3rd[-_]?party|vendor|vendored|external|extern|deps|contrib|libs?|libraries|"
    r"managed_components|node_modules|\.pio|build|(?:[\w.]+[-_])?(?:examples?|samples?|demos?)(?:[-_][\w.]+)?)/", re.I)
# Root files of a project of its own — a host-side manifest (go.mod, a Cargo.toml: not read to tell an
# esp-rs firmware from a host crate, so unsure) or a generic build file: with one present, ESP evidence
# in a subdir must be pointed to by the root README / build file.
_ROOT_PROJECT_FILES = frozenset({"go.mod", "Cargo.toml", "package.json", "pyproject.toml", "setup.py", "setup.cfg",
                                 "requirements.txt", "Gemfile", "pom.xml", "build.gradle", "build.gradle.kts",
                                 "composer.json", "mix.exs", "Package.swift", "deno.json", "CMakeLists.txt", "Makefile",
                                 "makefile", "GNUmakefile", "meson.build", "build.zig", "SConstruct", "configure.ac",
                                 "WORKSPACE", "MODULE.bazel"})
_READMES = ("README.md", "README.rst", "README.txt", "README", "readme.md", "Readme.md")
_ROOT_BUILD_FILES = ("Makefile", "makefile", "GNUmakefile", "justfile", "Justfile", "Taskfile.yml", "CMakeLists.txt")
_SUBMODULE_PATH = re.compile(r"^\s*path\s*=\s*(.+?)\s*$")
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


def default_fetch(url: str) -> safe_fetch.Fetched:
    """The whole release asset under jr/safe_fetch.py's policy, capped at MAX_IMAGE_BYTES."""
    return safe_fetch.fetch_capped(url, max_bytes=MAX_IMAGE_BYTES)


class _Calls(derive._Calls):
    """derive's call counter plus the capped GET of a release asset."""

    def __init__(self, api, raw, fetch, max_calls: int):
        super().__init__(api, raw, max_calls)
        self.fetch = fetch

    def get_asset(self, url: str) -> safe_fetch.Fetched | None:
        """The fetch's answer, or None when it was not charged or says nothing about the asset (an
        outage — counted, so the check is unknown, never a verdict)."""
        if not self._charge():
            return None
        try:
            got = self.fetch(url)
        except BudgetExceeded:
            raise
        except Exception as e:  # noqa: BLE001 — a refusal comes back as Fetched; a raise is an outage
            self._fail(f"fetch {url}", e)
            return None
        if got.reason == safe_fetch.UNAVAILABLE:
            self._fail(f"fetch {url}", RuntimeError(got.detail))
            return None
        return got


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
    gitlinks: tuple[str, ...] = ()      # submodule paths the tree lists (type "commit")
    texts: dict[str, str | None] = field(default_factory=dict, repr=False)    # each file read (charged) once

    def read(self, path: str) -> str | None:
        if path not in self.texts:
            self.texts[path] = self.calls.get_raw(f"https://raw.githubusercontent.com/{self.owner_repo}/{self.ref}/{path}")
        return self.texts[path]

    def cite(self, path: str, line: int | None = None) -> str:
        return f"https://github.com/{self.owner_repo}/blob/{self.ref}/{path}" + (f"#L{line}" if line else "")

    def listed(self, keep) -> list[str]:
        """Tree paths `keep(path)` accepts, shallowest first."""
        return sorted((p for p in (self.tree or []) if keep(p)), key=lambda p: (p.count("/"), p))

    def shallowest(self, name: str) -> list[str]:
        """Up to MAX_BUILD_FILES paths named `name`, the project's own first, then root first. No (or
        a truncated) listing still tries the root file, the one place a project's own build file must live."""
        return self.with_fallbacks(self.own_first(self.listed(lambda p: _base(p) == name)), [name])

    def own_first(self, paths: list[str], place=None) -> list[str]:
        """OWN, then UNDECLARED_PROJECT_DIR, then vendored paths, by `place` (default self.place)."""
        rank = {OWN: 0, UNDECLARED_PROJECT_DIR: 1, VENDORED_OR_EXAMPLE_ONLY: 2}
        return sorted(paths, key=lambda p: rank[(place or self.place)(p)])

    def place(self, path: str) -> str:
        """Whose file `path` is: OWN (the root, or the project's declared build directory),
        VENDORED_OR_EXAMPLE_ONLY (a vendored, example or submodule tree) or UNDECLARED_PROJECT_DIR
        (a subdir of a host-side repo that the root README / build file never points to)."""
        d = _dir(path)
        if not d:
            return OWN
        if self.vendored(path):
            return VENDORED_OR_EXAMPLE_ONLY
        if not self._root_project or self._points_to(d.rstrip("/")):
            return OWN
        return UNDECLARED_PROJECT_DIR

    def vendored(self, path: str, below: str = "") -> bool:
        """`path` sits in a vendored/example tree (below the dir `below`) or in a git submodule."""
        return bool(_VENDORED_OR_EXAMPLE.search(_dir(path[len(below):]))) or self.in_submodule(path)

    def in_submodule(self, path: str) -> bool:
        return any(path.startswith(s) for s in self._submodules)

    @cached_property
    def _submodules(self) -> tuple[str, ...]:
        paths = list(self.gitlinks)
        if ".gitmodules" in (self.tree or []):
            text = self.read(".gitmodules") or ""
            paths += [m.group(1) for m in map(_SUBMODULE_PATH.match, text.split("\n")) if m]
        return tuple(p.strip("/") + "/" for p in paths if p.strip("/"))

    @cached_property
    def _root_project(self) -> bool:
        """The root holds a project of its own. A truncated listing cannot prove it does not."""
        return self.truncated or any("/" not in p and (p in _ROOT_PROJECT_FILES or p.endswith((".csproj", ".sln")))
                                     for p in self.tree or [])

    @cached_property
    def _pointer_text(self) -> str:
        """The root README and first root build file: where a repo declares its project directory."""
        root = set(self.tree or [])
        picks = [next((f for f in names if f in root), None) for names in (_READMES, _ROOT_BUILD_FILES)]
        return "\n".join(self.read(f) or "" for f in picks if f)

    def _points_to(self, d: str) -> bool:
        """The pointer text builds or links `d`: `cd d`, make/idf.py/pio `-C|-d|--project-dir d`,
        `add_subdirectory(d)`, a markdown link to the dir itself `](d)`, or a path to its build file (`d/platformio.ini`,
        `d/CMakeLists.txt`, `d/sdkconfig…`, `d/<x>.ino`). A bare `d/` in prose is not one."""
        return bool(_pointer(d).search(self._pointer_text))

    def with_fallbacks(self, paths: list[str], fallbacks: list[str]) -> list[str]:
        if self.tree is None or self.truncated:
            paths = [f for f in fallbacks if f not in paths] + paths
        return paths[:MAX_BUILD_FILES]


def _pointer(d: str) -> re.Pattern:
    q = re.escape(d)
    tool = (r"(?:\bcd\s+|\b(?i:make|idf\.py|pio|platformio)\b[^\n]*?\s(?:-C|-d|--project-dir|--directory)\s*=?\s*"
            r"|add_subdirectory\s*\(\s*)")
    return re.compile(rf"{tool}(?:\./)?{q}(?![\w.-])|\]\(\s*(?:\./)?{q}/?\s*\)"
                      rf"|(?<![\w./-])(?:\./)?{q}/(?:platformio\.ini|CMakeLists\.txt|sdkconfig[\w.]*|[\w.-]+\.ino)\b")


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
    held = None
    for p in repo.shallowest("platformio.ini"):
        hit = _platformio_hit(repo, p)
        if not hit:
            continue
        where, why = repo.place(p), f"platformio.ini platform espressif32 ({hit[0]})"
        if where == OWN:
            return _Hit(ESP_TARGET, "platformio", repo.cite(*hit), why)
        held = held or _Hit(NEEDS_REVIEW, "platformio", repo.cite(*hit), _not_own(where, why))
    return held


def _not_own(where: str, what: str) -> str:
    if where == VENDORED_OR_EXAMPLE_ONLY:
        return f"{where}: {what} is in a vendored, example or submodule tree, not this repo's project"
    return f"{where}: {what} is in a subdir of a host-side repo that its README / build file never points to"


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


def _project_target_file(repo: _Repo, project_dir: str, path: str) -> bool:
    """`path` states the target of the project at `project_dir`: sdkconfig* and dependencies.lock in
    that directory (where ESP-IDF reads them), an idf_component.yml in any of its own component
    dirs — never a vendored, example or submodule tree's (managed_components/ is a dependency)."""
    if _base(path) not in _TARGET_FILES or not path.startswith(project_dir) or repo.vendored(path, project_dir):
        return False
    return _base(path) == "idf_component.yml" or _dir(path) == project_dir


def _idf_target(repo: _Repo, project_dir: str) -> tuple[str, int, str] | None:
    """(file, line, target) of an ESP target the project states, its own directory first."""
    listed = sorted(repo.listed(lambda p: _project_target_file(repo, project_dir, p)),
                    key=lambda p: (p.count("/"), _TARGET_FILES.index(_base(p)), p))
    fallbacks = [project_dir + f for f in ("sdkconfig.defaults", "main/idf_component.yml", "dependencies.lock")]
    for p in repo.with_fallbacks(listed, fallbacks):
        stated = _stated_target(_base(p), repo.read(p) or "")
        if stated:
            return p, stated[0], stated[1]
    return None


def _idf_project(repo: _Repo) -> _Hit | None:
    held = None
    for p in repo.shallowest("CMakeLists.txt"):
        line = next((n for n, ln in enumerate((repo.read(p) or "").split("\n"), 1) if _PROJECT_CMAKE.match(ln)), None)
        if not line:
            continue
        where = repo.place(p)
        if where != OWN:
            held = held or _Hit(NEEDS_REVIEW, "idf_project", repo.cite(p, line), _not_own(where, f"ESP-IDF project.cmake ({p})"))
            continue
        target = _idf_target(repo, _dir(p))
        if target:
            return _Hit(ESP_TARGET, "idf_project", repo.cite(target[0], target[1]),
                        f"ESP-IDF project ({p}) targeting {target[2]} ({target[0]})")
        return _Hit(NEEDS_REVIEW, "idf_project", repo.cite(p, line),
                    "ESP-IDF project.cmake but no ESP target stated (sdkconfig.defaults CONFIG_IDF_TARGET, "
                    "idf_component.yml targets, dependencies.lock target)")
    return held or _idf_component(repo)


def _idf_component(repo: _Repo) -> _Hit | None:
    component = repo.own_first(repo.listed(lambda p: _base(p) == "idf_component.yml"))
    if not component:
        return None
    first = next((c for c in component if repo.place(c) == OWN), component[0])
    where = repo.place(first)
    why = "an idf_component.yml but no ESP-IDF project (CMakeLists.txt including project.cmake)"
    return _Hit(NEEDS_REVIEW, "idf_component", repo.cite(first), why if where == OWN else _not_own(where, f"idf_component.yml ({first})"))


# --- Arduino sketch --------------------------------------------------------------------------------

def _board_files(repo: _Repo) -> list[str]:
    """Where a sketch names its board: sketch.yaml, library.properties, then build workflows —
    never a vendored library's; the project's own first."""
    sketch = repo.listed(lambda p: _base(p) in ("sketch.yaml", "sketch.yml") and not _VENDORED.search(p))
    props = repo.listed(lambda p: _base(p) == "library.properties" and not _VENDORED.search(p))
    workflows = repo.listed(lambda p: p.startswith(".github/workflows/") and p.endswith((".yml", ".yaml")))
    return repo.own_first(sketch + props + workflows, lambda p: _board_place(repo, p))[:MAX_BUILD_FILES]


def _sketch_place(repo: _Repo, path: str) -> str:
    """repo.place, except that a root library.properties makes the repo an Arduino library whose
    top-level examples/ are its own, whatever they are named."""
    if path.startswith("examples/") and "library.properties" in (repo.tree or []) and not repo.in_submodule(path):
        return OWN
    return repo.place(path)


def _board_place(repo: _Repo, path: str) -> str:
    """A root build workflow is the repo's own CI, wherever the sketch it compiles lives."""
    return OWN if path.startswith(".github/workflows/") else _sketch_place(repo, path)


def _built_sketches(path: str, text: str, sketches: list[str], own: list[str]) -> list[str]:
    """The sketches a board file is for: a sketch.yaml its own folder's; a library.properties those
    below it; a workflow those an ESP-fqbn line of it compiles (by folder, or a root sketch by file
    name or `.`) or its compile-sketches `sketch-paths` list — naming none, every sketch when all
    are the repo's own, else the ones that are not (unsure: review)."""
    if _base(path).startswith("sketch."):
        return [s for s in sketches if _dir(s) == _dir(path)]
    if _base(path) == "library.properties":
        return [s for s in sketches if s.startswith(_dir(path))]
    lines = text.split("\n")
    built = "\n".join([_FQBN.sub(" ", ln) for ln in lines if _ESP_FQBN.search(ln)] + _sketch_paths(lines))
    named = [s for s in sketches if _names_dir(built, _dir(s).rstrip("/") if _dir(s) else s)
             or (not _dir(s) and _ROOT_DOT.search(built))]
    return named or (sketches if len(own) == len(sketches) else [s for s in sketches if s not in own])


def _sketch_paths(lines: list[str]) -> list[str]:
    """The values of arduino/compile-sketches `sketch-paths:` keys (inline, or the block below)."""
    out = []
    for i, ln in enumerate(lines):
        m = _SKETCH_PATHS.match(ln)
        if not m:
            continue
        out.append(m.group(2))
        for item in lines[i + 1:]:
            if item.strip() and len(item) - len(item.lstrip()) <= len(m.group(1)):
                break
            out.append(item)
    return out


def _names_dir(text: str, d: str) -> bool:
    return bool(re.search(rf"(?<![\w./:-])(?:\./)?{re.escape(d)}(?![\w.:-])", text))


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
    """An ESP board named by the repo's own board file for the repo's own sketch. A root
    library.properties makes the repo an Arduino library: its examples/ sketches are its own."""
    sketches = repo.listed(lambda p: p.lower().endswith(".ino") and not _VENDORED.search(p))
    if not sketches:
        return None
    own = [s for s in sketches if _sketch_place(repo, s) == OWN]
    held = None
    for p in _board_files(repo):
        text = repo.read(p) or ""
        line = _esp_board_line(p, text)
        built = _built_sketches(p, text, sketches, own) if line else []
        if not built:
            continue
        mine, where = [s for s in built if s in own], _board_place(repo, p)
        if mine and where == OWN:
            return _Hit(ESP_TARGET, "arduino_sketch", repo.cite(p, line), f"Arduino sketch {mine[0]} built for an ESP board ({p})")
        if where == OWN:
            where = _sketch_place(repo, built[0])
        held = held or _Hit(NEEDS_REVIEW, "arduino_sketch", repo.cite(p, line),
                            _not_own(where, f"an ESP board named in {p} for sketch {built[0]}"))
    return held or _Hit(NEEDS_REVIEW, "arduino_sketch", repo.cite(sketches[0]),
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
                    f"release ships {assets[0]['name']} only; no ESP image to validate")
    name, url = bins[0]["name"], bins[0].get("browser_download_url")
    got = repo.calls.get_asset(url) if url else None
    if got is None or got.reason == safe_fetch.NOT_FOUND:
        return _Hit(NEEDS_REVIEW, "release_bin", url or page,
                    f"{name} not readable ({got.detail if got else 'no download url, or the fetch failed'})")
    if not got.ok:          # refused, timed out or over the cap: never proven to be the asset
        return _Hit(NEEDS_REVIEW, "release_bin", url, f"{name} not fetched — {got.reason}: {got.detail}")
    if len(got.data) > MAX_IMAGE_BYTES:     # an injected fetch that ignored the cap
        return _Hit(NEEDS_REVIEW, "release_bin", url, f"{name} is over the 16 MB cap")
    image = image_sandbox.validate(got.data)
    if image["status"] == esp_image.ESP_TARGET:
        return _Hit(ESP_TARGET, "release_bin", url, f"{name}: {'; '.join(image['reasons'])}")
    return _Hit(NEEDS_REVIEW, "release_bin", url, f"{name} needs review: {'; '.join(image['reasons'])}")


# --- the check -------------------------------------------------------------------------------------

_PROBES = (_platformio, _idf_project, _arduino, _release_bin)


def _listing(owner_repo: str, ref: str, calls: _Calls, notes: list[str]) -> tuple[list[str] | None, bool, tuple[str, ...]]:
    """(blob paths, truncated, submodule gitlink paths) of the recursive tree, or (None, False, ())."""
    doc = calls.get_api(f"repos/{owner_repo}/git/trees/{ref}?recursive=1")
    if not (isinstance(doc, dict) and isinstance(doc.get("tree"), list)):
        return None, False, ()
    if doc.get("truncated"):
        notes.append("tree listing truncated by GitHub")
    entries = [t for t in doc["tree"] if isinstance(t, dict) and t.get("path")]
    return ([t["path"] for t in entries if t.get("type") == "blob"], bool(doc.get("truncated")),
            tuple(t["path"] for t in entries if t.get("type") == "commit"))


def _result(ok, verdict, calls, notes, hit: _Hit | None = None, ambiguous=()) -> dict:
    return {"ok": ok, "verdict": verdict, "kind": hit.kind if hit else None, "url": hit.url if hit else None,
            "calls": calls.n, "notes": notes, "ambiguous": [{"kind": a.kind, "url": a.url, "why": a.why} for a in ambiguous]}


def check(owner_repo: str, *, api=None, raw=None, fetch=None, ref: str | None = None, max_calls: int = MAX_CALLS) -> dict:
    """{"ok", "verdict", "kind", "url", "calls", "notes", "ambiguous"} for `owner/repo` at `ref`
    (default HEAD, the default branch). ok=True only for ESP_TARGET; NEEDS_REVIEW and
    NOT_DEVICE_FIRMWARE are ok=False; unknown is ok=None, verdict None. Stops at the first ESP
    target; a needs_review result cites its first ambiguous signal and lists them all.
    `api`/`raw`/`fetch` default to derive.default_api/default_raw and default_fetch."""
    ref = ref or "HEAD"
    calls, notes = _Calls(api or derive.default_api, raw or derive.default_raw, fetch or default_fetch, max_calls), []
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
    if ambiguous:             # exhaustion recurs on every retry (the repo's shape): the owner decides
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
