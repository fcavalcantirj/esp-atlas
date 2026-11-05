#!/usr/bin/env python3
"""G2 destructive-operation guard (scripts/g2_guard.py, SPEC-firmware-boards.md §4).

A deleted firmware record that is curated-exempt, floor-passing, or ≥1000 stars fails the
PR unless `jr/overrides/<id>.json` is in the same change (the explicit, logged override —
a human saying "yes, delete this on purpose"). A deleted recipe fails unless its firmware
is also deleted under an override, OR an audited edge correction
`jr/overrides/<firmware>__edges.json` ADDED OR MODIFIED in the same change lists that exact
recipe path while the firmware itself stays (the false-edge fix: the firmware is real, one of
its board edges was not). Everything else (below-floor, unstamped, unlisted records) stays
deletable: G2 protects high-signal rows, not every row.

Offline and deterministic: the deleted record is read from the BASE ref (`git show
<base>:<path>`), so the check judges what was actually removed, not what remains. The
floor comes from apps/core/src/esp_atlas_core/floor.py (imported, never re-typed) and the
curated-exempt list from scripts/firmware_floor_audit.py (imported, never re-typed).

Usage in CI (a dedicated `g2-guard` job with fetch-depth: 0):
    python3 scripts/g2_guard.py                      # base origin/main (or $GITHUB_BASE_REF)

Locally:
    python3 scripts/g2_guard.py --base <sha-or-ref>  # e.g. origin/main, a tag, a commit

Exit 0 when every deletion is guarded or harmless; exit 1 with ::error:: lines otherwise.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "apps" / "core" / "src"))

import yaml  # noqa: E402
from esp_atlas_core.floor import clears_popularity_floor  # noqa: E402
from firmware_floor_audit import CURATED_EXEMPT  # noqa: E402

# A firmware with this many stored stars is high-signal no matter what the floors say
# (today every stars>=1000 record also clears the floor; this clause survives floor edits).
G2_STAR_GUARD = 1000

FIRMWARE_PREFIX = "data/firmware/"
FIRMWARE_SUFFIX = "/firmware.md"
RECIPE_PREFIX = "data/recipes/"
RECIPE_SUFFIX = "/recipe.md"
OVERRIDE_PREFIX = "jr/overrides/"
EDGE_OVERRIDE_SUFFIX = "__edges.json"
EDGE_ACTION = "edge_correction"
EDGE_TEXT_FIELDS = ("classification", "directed_by")
GIT_SHA = re.compile(r"[0-9a-f]{7,40}")
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def firmware_id_of(path: str) -> str | None:
    """<id> from data/firmware/<id>/firmware.md, else None."""
    if path.startswith(FIRMWARE_PREFIX) and path.endswith(FIRMWARE_SUFFIX):
        rest = path[len(FIRMWARE_PREFIX):-len(FIRMWARE_SUFFIX)]
        return rest or None
    return None


def recipe_firmware_id(path: str) -> str | None:
    """The firmware id from data/recipes/<board>__<firmware>/recipe.md, else None."""
    if path.startswith(RECIPE_PREFIX) and path.endswith(RECIPE_SUFFIX):
        dirname = path[len(RECIPE_PREFIX):-len(RECIPE_SUFFIX)]
        if "__" in dirname:
            _board, fid = dirname.split("__", 1)
            return fid or None
    return None


def edge_override_firmware_id(path: str) -> str | None:
    """<firmware> from jr/overrides/<firmware>__edges.json, else None."""
    if path.startswith(OVERRIDE_PREFIX) and path.endswith(EDGE_OVERRIDE_SUFFIX):
        fid = path[len(OVERRIDE_PREFIX):-len(EDGE_OVERRIDE_SUFFIX)]
        if fid and "/" not in fid:
            return fid
    return None


def _paths_with_status(diff_text: str, statuses: tuple[str, ...]) -> list[str]:
    out = []
    for line in diff_text.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0] in statuses:
            out.append(parts[1])
    return out


def deleted_paths(diff_text: str) -> list[str]:
    """Paths with status D from `git diff --name-status --no-renames` output."""
    return _paths_with_status(diff_text, ("D",))


def changed_paths(diff_text: str) -> list[str]:
    """Paths added (A) or modified (M) by the change — the only place an edge-correction
    override can come from: one merely present at HEAD and untouched authorizes nothing."""
    return _paths_with_status(diff_text, ("A", "M"))


def protection_reasons(fid: str, fm: dict) -> list[str]:
    """Why deleting this firmware record is refused (empty when deletable). Judged from the
    record as it was BEFORE deletion: curated-exempt, floor-passing stored popularity (stars,
    forks, or the fourth signal — a persisted launcher download count, SPEC-firmware-floor.md;
    there is no live homepage check here, same as before), or ≥1000 stored stars. Unstamped
    records (no popularity block) clear nothing and pass."""
    reasons = []
    if fid in CURATED_EXEMPT:
        reasons.append("curated-exempt")
    pop = fm.get("popularity") if isinstance(fm, dict) else None
    pop = pop if isinstance(pop, dict) else {}
    stars, forks, downloads = pop.get("stars") or 0, pop.get("forks") or 0, pop.get("downloads") or 0
    if clears_popularity_floor(pop.get("stars"), pop.get("forks"), downloads=pop.get("downloads")):
        reasons.append(f"floor-passing (stars={stars} forks={forks} downloads={downloads})")
    if (pop.get("stars") or 0) >= G2_STAR_GUARD:
        reasons.append(f"stars>={G2_STAR_GUARD}")
    return reasons


def _is_https_url(value) -> bool:
    if not isinstance(value, str):
        return False
    url = urlparse(value)
    return url.scheme == "https" and bool(url.netloc)


def _is_text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_iso_date(value) -> bool:
    if not isinstance(value, str) or not ISO_DATE.fullmatch(value):
        return False
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _parse_edge_override(raw: bytes | None) -> tuple[dict | None, str | None]:
    """(record, None) or (None, why it is unreadable)."""
    if raw is None:
        return None, "unreadable at HEAD"
    try:
        record = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, f"malformed JSON ({exc})"
    if not isinstance(record, dict):
        return None, "must be a JSON object"
    return record, None


def _edge_field_problems(record: dict, name_fid: str) -> list[str]:
    """Shape of the audit record itself: every required field present and well-formed."""
    problems = []
    if record.get("firmware") != name_fid:
        problems.append(f"'firmware' must be '{name_fid}' (the file name), got {record.get('firmware')!r}")
    if record.get("action") != EDGE_ACTION:
        problems.append(f"'action' must be '{EDGE_ACTION}'")
    for field in EDGE_TEXT_FIELDS:
        if not _is_text(record.get(field)):
            problems.append(f"'{field}' must be a non-empty string")
    sources = record.get("sources")
    if not isinstance(sources, list) or not sources or not all(_is_https_url(u) for u in sources):
        problems.append("'sources' must be a non-empty list of https URLs")
    sha = record.get("historical_parent_sha")
    if not isinstance(sha, str) or not GIT_SHA.fullmatch(sha):
        problems.append("'historical_parent_sha' must be a 7-40 char lowercase hex git sha")
    if not _is_iso_date(record.get("date")):
        problems.append("'date' must be a YYYY-MM-DD date")
    deletes = record.get("deletes")
    if not isinstance(deletes, list) or not deletes or not all(isinstance(p, str) for p in deletes):
        problems.append("'deletes' must be a non-empty list of recipe paths")
    if not isinstance(record.get("originals"), dict):
        problems.append("'originals' must map each deleted path to its full original text")
    return problems


def _edge_path_problems(record: dict, fid: str, deleted: set[str], show_base_bytes) -> list[str]:
    """Each listed path is one of THIS firmware's recipes, is really deleted by the change,
    and has its BASE text preserved byte-for-byte in `originals` (and nothing else is)."""
    problems = []
    deletes, originals = record["deletes"], record["originals"]
    for path in deletes:
        if recipe_firmware_id(path) != fid:
            problems.append(f"'{path}' is not a data/recipes/<board>__{fid}/recipe.md path")
        elif path not in deleted:
            problems.append(f"'{path}' is listed but not deleted in this change")
        elif not isinstance(originals.get(path), str):
            problems.append(f"'{path}' has no original text in 'originals'")
        elif originals[path].encode("utf-8") != show_base_bytes(path):
            problems.append(f"'{path}' original text does not byte-match the BASE revision")
    for path in originals:
        if path not in deletes:
            problems.append(f"'originals' carries '{path}', which 'deletes' does not list")
    return problems


def edge_override_problems(path: str, raw: bytes | None, deleted: set[str],
                           show_base_bytes, head_has) -> list[str]:
    """Why the edge-correction override at `path` (HEAD bytes `raw`) is invalid — empty when
    it may authorize its `deletes`. Fail-closed: any problem voids the whole override."""
    fid = edge_override_firmware_id(path)
    record, unreadable = _parse_edge_override(raw)
    if record is None:
        return [unreadable]
    problems = _edge_field_problems(record, fid)
    if problems:
        return problems
    firmware_path = f"{FIRMWARE_PREFIX}{fid}{FIRMWARE_SUFFIX}"
    if firmware_path in deleted:
        return [f"firmware '{fid}' is deleted in this change — an edge correction is only for a "
                f"firmware that stays (use jr/overrides/{fid}.json for a firmware removal)"]
    if not head_has(firmware_path):
        return [f"firmware '{fid}' does not exist at HEAD ({firmware_path})"]
    return _edge_path_problems(record, fid, deleted, show_base_bytes)


def edge_authorized_recipes(edge_overrides: dict, deleted: set[str], show_base_bytes,
                            head_has) -> tuple[set[str], list[str]]:
    """(recipe paths authorized by valid edge overrides of this change, error lines)."""
    authorized, errors = set(), []
    for path, raw in sorted(edge_overrides.items()):
        problems = edge_override_problems(path, raw, deleted, show_base_bytes, head_has)
        for problem in problems:
            errors.append(f"::error file={path}::G2 guard: edge-correction override invalid: {problem}")
        if not problems:
            authorized.update(json.loads(raw.decode("utf-8"))["deletes"])
    return authorized, errors


def check(deleted: list[str], show_file, head_has, edge_overrides: dict | None = None,
          show_base_bytes=None) -> list[str]:
    """The pure gate: `deleted` repo-relative paths; `show_file(base, path)` returns the base
    file text or None; `head_has(path)` says whether the path exists in HEAD. Returns error
    lines (empty when the change is guarded or harmless).

    A recipe deletion rides along with its firmware's deletion: it passes when the firmware
    is deleted in the same change AND that firmware deletion itself passes this gate (below
    floor with no override, or guarded by an override). A recipe deleted while its firmware
    stays always fails — that is the two-step orphaning move (strip the evidence, then take
    the firmware as "unused") — unless a valid edge-correction override in `edge_overrides`
    (path -> HEAD bytes, only overrides ADDED OR MODIFIED by the change) lists that exact path;
    `show_base_bytes(path)` returns the BASE file bytes for the byte-exact `originals` check."""
    errors = []
    edge_authorized, edge_errors = edge_authorized_recipes(
        edge_overrides or {}, set(deleted), show_base_bytes or (lambda _path: None), head_has)
    errors.extend(edge_errors)
    firmware_removed_cleanly = set()
    for path in deleted:
        fid = firmware_id_of(path)
        if fid is None:
            continue
        text = show_file(path)
        if text is None:
            continue
        try:
            fm = yaml.safe_load(text.split("---")[1])
        except (yaml.YAMLError, IndexError):
            fm = {}
        if not isinstance(fm, dict):
            fm = {}
        reasons = protection_reasons(fid, fm)
        if not reasons:
            firmware_removed_cleanly.add(fid)
            continue
        if head_has(f"{OVERRIDE_PREFIX}{fid}.json"):
            firmware_removed_cleanly.add(fid)
            continue
        errors.append(f"::error file={path}::G2 guard: deleting firmware '{fid}' "
                      f"({', '.join(reasons)}) without jr/overrides/{fid}.json in this change")
    for path in deleted:
        fid = recipe_firmware_id(path)
        if fid is None:
            continue
        if fid in firmware_removed_cleanly or path in edge_authorized:
            continue
        errors.append(f"::error file={path}::G2 guard: deleting recipe '{path}' whose firmware "
                      f"'{fid}' is not deleted under an override in this change, nor listed by a "
                      f"valid jr/overrides/{fid}{EDGE_OVERRIDE_SUFFIX} added or modified in it")
    return errors


def _git(*args: str, cwd: Path, text: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=text, timeout=60)


def _git_bytes(rev_path: str, cwd: Path) -> bytes | None:
    """`git show <rev>:<path>` as raw bytes (no newline translation), None when absent."""
    p = _git("show", rev_path, cwd=cwd, text=False)
    return p.stdout if p.returncode == 0 else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=None,
                    help="base ref for the diff (default: origin/$GITHUB_BASE_REF, else origin/main)")
    ap.add_argument("--repo", type=Path, default=REPO)
    args = ap.parse_args(argv)
    base = args.base or (f"origin/{os.environ['GITHUB_BASE_REF']}" if os.environ.get("GITHUB_BASE_REF") else "origin/main")
    diff = _git("diff", "--name-status", "--no-renames", f"{base}...HEAD", cwd=args.repo)
    if diff.returncode != 0:
        print(f"::error::G2 guard: cannot diff {base}...HEAD: {(diff.stderr or '').strip()[:200]}")
        return 1

    def show_file(path: str) -> str | None:
        p = _git("show", f"{base}:{path}", cwd=args.repo)
        return p.stdout if p.returncode == 0 else None

    def head_has(path: str) -> bool:
        return _git("show", f"HEAD:{path}", cwd=args.repo).returncode == 0

    edge_overrides = {path: _git_bytes(f"HEAD:{path}", args.repo)
                      for path in changed_paths(diff.stdout) if edge_override_firmware_id(path)}
    errors = check(deleted_paths(diff.stdout), show_file, head_has, edge_overrides=edge_overrides,
                   show_base_bytes=lambda path: _git_bytes(f"{base}:{path}", args.repo))
    for line in errors:
        print(line)
    if errors:
        print(f"G2 GUARD FAILED: {len(errors)} unguarded deletion(s)", file=sys.stderr)
        return 1
    print("G2 guard green: no unguarded deletions of high-signal firmware")
    return 0


if __name__ == "__main__":
    sys.exit(main())
