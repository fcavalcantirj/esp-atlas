"""EspAtlas Jr — build-target facts from PlatformIO's own config semantics (jr/claims_pio.py).

Jr redesign plan, step 4 (2026-11-22; Codex-reviewed SOUND at revision 12). Jr records only a configuration fact:
"At commit S, PlatformIO V resolves env E of repo R to the board option B". This module turns a project tree (the
repo's files at one pinned commit, materialized in a directory) into such facts, or into named refusals:

  resolve_project(dir)  PlatformIO's ProjectConfig (parse_extra=True) in a SUBPROCESS with a clean environment
                        (no inherited variables, HOME in a temp dir), so `${sysenv.*}`, PLATFORMIO_* variables and
                        the caller's ~/.platformio never reach the result. It returns the loaded files, every env's
                        effective board / platform / identity options, its contributing sections and their raw
                        values, and the project's boards_dir / core_dir.
  judge(resolved, platform_index)
                        applies the refusals below, then compares the env's effective identity options with the
                        definition's own manifest from the pinned platform package. `platform_index(spec, board)`
                        returns {"package_digest", "manifest": bytes | None} for an allowed, pinned spec, or None.

Refusals (no fact; the rule is recorded): no-platform, no-board, external-input (an env-, time- or caller-dependent
interpolation reaches board/platform/extends/an identity option), platform-not-pinned (bare `espressif32`, a range),
platform-not-allowed (anything but an exact official registry version or a pioarduino release zip),
order-dependent (two loaded files set the same option of a contributing section), shadowed-definition (the project's
boards_dir / core_dir holds a manifest with the same id), unknown-definition (the pinned package has no such board),
identity-override (the env's effective mcu / variant / arduino variant keys differ from the manifest's).

Measured 2026-11-22 on NightDriverStrip at 971c066b: `heltecv3demo` sets board_build.mcu = esp32s3, the same as the
heltec_wifi_kit_32_V3 manifest, so it is a fact; `m5plusdemo` inherits board = m5stick-c but sets
board_build.variant = m5stack_stickc_plus2, not the manifest's variant, so it is refused.
"""
from __future__ import annotations

import configparser
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

IDENTITY = ("board_build.mcu", "board_mcu", "board_build.variant")
IDENTITY_PREFIX = "board_build.arduino."
_OFFICIAL = re.compile(r"^(?:platformio/)?espressif32@(\d+\.\d+\.\d+)$")
_OFFICIAL_ANY = re.compile(r"^(?:platformio/)?espressif32(?:@.*)?$")
_PIOARDUINO = re.compile(r"^https://github\.com/pioarduino/platform-espressif32/releases/download/([\w.\-]+)/platform-espressif32\.zip$")
_EXTERNAL = re.compile(r"\$\{(?:sysenv\.|this\.__env__|platformio\.(?:workspace|build|core|home)_dir)")
_REF = re.compile(r"\$\{([^}.:]+(?::[^}.]+)?)\.[^}]+\}")

_RESOLVER = r'''
import json, os, sys
from platformio.project.config import ProjectConfig
root = sys.argv[1]
os.chdir(root)
cfg = ProjectConfig(os.path.join(root, "platformio.ini"), parse_extra=True)
P = cfg._parser
def raw(sec, opt):
    try:
        return P.get(sec, opt, raw=True)
    except Exception:
        return None
def sections_of(env):
    seen, todo = [], ["env:" + env, "env"]
    while todo:
        s = todo.pop(0)
        if s in seen or not P.has_section(s):
            continue
        seen.append(s)
        ext = raw(s, "extends")
        if ext:
            todo += [x.strip() for x in ext.replace(",", "\n").split("\n") if x.strip()]
        for o in P.options(s):
            v = raw(s, o) or ""
            import re
            for m in re.finditer(r"\$\{([^}.:]+(?::[^}.]+)?)\.[^}]+\}", v):
                if m.group(1) not in ("sysenv", "this", "platformio"):
                    todo.append(m.group(1))
    return seen
out = {"loaded": [os.path.relpath(p, root) for p in cfg._parsed], "envs": {},
       "boards_dir": cfg.get("platformio", "boards_dir", None), "core_dir": cfg.get("platformio", "core_dir", None)}
for env in cfg.envs():
    sec = "env:" + env
    def eff(o):
        try:
            return cfg.get(sec, o, None)
        except Exception as e:
            return {"error": str(e)}
    names = [k for k, _v in cfg.items(env=env)]
    contrib = sections_of(env)
    out["envs"][env] = {
        "board": eff("board"), "platform": eff("platform"),
        "identity": {k: eff(k) for k in names if k in ("board_build.mcu", "board_mcu", "board_build.variant") or k.startswith("board_build.arduino.")},
        "sections": contrib,
        "raw": {s: {o: raw(s, o) for o in P.options(s)} for s in contrib},
    }
print(json.dumps(out))
'''


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def resolve_project(project_dir: Path, python: str | None = None, timeout: int = 120) -> dict:
    """PlatformIO's own resolution of every env in `project_dir`, hermetic. Raises RuntimeError on failure."""
    project_dir = Path(project_dir).resolve()
    with tempfile.TemporaryDirectory(prefix="claims-pio-home-") as home:
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": home, "LANG": "C.UTF-8",
               "PLATFORMIO_CORE_DIR": str(Path(home) / ".platformio")}
        p = subprocess.run([python or sys.executable, "-c", _RESOLVER, str(project_dir)], capture_output=True, text=True,
                           env=env, cwd=home, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"platformio could not resolve {project_dir}: {p.stderr.strip()[-400:]}")
    out = json.loads(p.stdout)
    out["root"] = str(project_dir)
    out["file_options"] = _file_options(project_dir, out["loaded"])
    out["section_lines"] = _section_lines(project_dir, out["loaded"])
    return out


def _file_options(root: Path, loaded: list[str]) -> dict:
    """{file: [[section, option], ...]} as each loaded file itself writes them (raw, no interpolation)."""
    out = {}
    for rel in loaded:
        cp = configparser.ConfigParser(strict=False, interpolation=None, inline_comment_prefixes=(";", "#"))
        cp.read_string((root / rel).read_text(encoding="utf-8", errors="replace"))
        out[rel] = [[s, o] for s in cp.sections() for o in cp.options(s) if o in cp._sections.get(s, {})]
    return out


def _section_lines(root: Path, loaded: list[str]) -> dict:
    """{section: [[file, line], ...]}: where each section header appears (1-based lines)."""
    out: dict = {}
    for rel in loaded:
        for n, line in enumerate((root / rel).read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            m = re.match(r"^\s*\[([^\]]+)\]\s*(?:[;#].*)?$", line)
            if m:
                out.setdefault(m.group(1).strip(), []).append([rel, n])
    return out


def platform_status(spec) -> str | None:
    """None when the spec is an allowed, pinned platform; otherwise the refusal rule."""
    if not isinstance(spec, str) or not spec.strip():
        return "no-platform"
    s = spec.strip()
    if _OFFICIAL.match(s) or _PIOARDUINO.match(s):
        return None
    if _OFFICIAL_ANY.match(s):
        return "platform-not-pinned"
    return "platform-not-allowed"


def _norm_mcu(v) -> str:
    return str(v or "").strip().lower().replace("-", "")


def identity_differences(identity: dict, manifest: dict) -> list[str]:
    """The env's effective identity options that differ from the definition manifest's own values."""
    build = manifest.get("build") or {}
    diffs = []
    for key, value in sorted((identity or {}).items()):
        if key in ("board_build.mcu", "board_mcu"):
            if _norm_mcu(value) != _norm_mcu(build.get("mcu")):
                diffs.append(f"{key}={value!r} vs manifest mcu {build.get('mcu')!r}")
        elif key == "board_build.variant":
            if str(value).strip() != str(build.get("variant") or "").strip():
                diffs.append(f"{key}={value!r} vs manifest variant {build.get('variant')!r}")
        elif key.startswith(IDENTITY_PREFIX):
            sub = key[len(IDENTITY_PREFIX):]
            have = (build.get("arduino") or {}).get(sub)
            if str(value).strip() != str(have if have is not None else "").strip():
                diffs.append(f"{key}={value!r} vs manifest arduino.{sub} {have!r}")
    return diffs


_ANY_REF = re.compile(r"\$\{([^}.]+)\.([^}]+)\}")


def _external(env_info: dict) -> list[str]:
    """Every env-, time- or caller-dependent interpolation that REACHES board, platform, extends or an identity
    option: those options in every contributing section, then every option their raw values reference
    (${section.option}, ${this.option}), transitively. Review BLOCK on #1998: board = X${common.suffix} with
    suffix = ${sysenv.SUFFIX} must be refused like a direct ${sysenv.*}."""
    raw = env_info.get("raw") or {}
    own = (env_info.get("sections") or ["env:?"])[0]
    todo = [(sec, opt) for sec, opts in raw.items() for opt in (opts or {})
            if opt in ("board", "platform", "extends") or opt in IDENTITY or opt.startswith(IDENTITY_PREFIX)]
    seen, hits = set(), []
    while todo:
        sec, opt = todo.pop()
        if (sec, opt) in seen:
            continue
        seen.add((sec, opt))
        val = (raw.get(sec) or {}).get(opt)
        if not isinstance(val, str):
            continue
        if _EXTERNAL.search(val):
            hits.append(f"[{sec}] {opt} = {val}")
        for ref_sec, ref_opt in _ANY_REF.findall(val):
            if ref_sec in ("sysenv", "platformio"):
                continue
            todo.append((own if ref_sec == "this" else ref_sec, ref_opt))
    return sorted(hits)


def _order_conflicts(resolved: dict, sections: list[str]) -> list[str]:
    owners: dict = {}
    for rel, pairs in (resolved.get("file_options") or {}).items():
        for sec, opt in pairs:
            if sec in sections:
                owners.setdefault((sec, opt), set()).add(rel)
    return sorted(f"[{s}] {o} in {sorted(f)}" for (s, o), f in owners.items() if len(f) > 1)


def _shadowed(resolved: dict, board: str) -> list[str]:
    root = Path(resolved["root"])
    hits = []
    for d in (resolved.get("boards_dir"), os.path.join(resolved.get("core_dir") or "", "boards") if resolved.get("core_dir") else None,
              str(root / "boards")):
        if not d:
            continue
        p = Path(d) if os.path.isabs(d) else root / d
        if (p / f"{board}.json").is_file():
            hits.append(str(p.relative_to(root)) if p.is_relative_to(root) else str(p))
    return sorted(set(hits))


def judge(resolved: dict, platform_index) -> tuple[list[dict], list[dict]]:
    """(facts, refusals) for every env. A fact: {env, board_id, platform{spec, package_digest, manifest_digest},
    sections[{name, file, line}]}. A refusal: {env, rule, detail}."""
    facts, refusals = [], []
    for env, info in sorted((resolved.get("envs") or {}).items()):
        def refuse(rule, detail=""):
            refusals.append({"env": env, "rule": rule, "detail": detail})
        board, spec = info.get("board"), info.get("platform")
        if isinstance(spec, dict) or isinstance(board, dict):
            refuse("unresolvable", json.dumps({"board": board, "platform": spec})[:200]); continue
        if not spec:
            refuse("no-platform"); continue
        if not board:
            refuse("no-board"); continue
        ext = _external(info)
        if ext:
            refuse("external-input", "; ".join(ext)[:300]); continue
        st = platform_status(spec)
        if st:
            refuse(st, str(spec)[:200]); continue
        conflicts = _order_conflicts(resolved, info.get("sections") or [])
        if conflicts:
            refuse("order-dependent", "; ".join(conflicts)[:300]); continue
        shadow = _shadowed(resolved, board)
        if shadow:
            refuse("shadowed-definition", ", ".join(shadow)); continue
        pkg = platform_index(spec, board)
        if pkg is None:
            refuse("platform-not-allowed", f"no verified package for {spec}"); continue
        if not pkg.get("manifest"):
            refuse("unknown-definition", f"{board} is not in {spec}"); continue
        manifest = json.loads(pkg["manifest"])
        diffs = identity_differences(info.get("identity") or {}, manifest)
        if diffs:
            refuse("identity-override", "; ".join(diffs)[:300]); continue
        lines = resolved.get("section_lines") or {}
        sections = [{"name": s, "file": f, "line": n} for s in info.get("sections") or [] for f, n in lines.get(s, [])]
        facts.append({"env": env, "board_id": board,
                      "platform": {"spec": spec, "package_digest": pkg["package_digest"], "manifest_digest": sha256(pkg["manifest"])},
                      "sections": sections})
    return facts, refusals
