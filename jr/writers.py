"""EspAtlas Jr — recipe writer (jr/writers.py): one cited recipe per resolved board, additive.

Phase 4 (SPEC-firmware-boards.md §3 provenance, PLAN §3.4 data model): a firmware's board edge
is a RECIPE (`data/recipes/<board>__<firmware>/recipe.md`), never a `boards` list on the
firmware record. This module turns jr/derive.resolve()'s output — {atlas_id: [signals…]} — into
recipes, and says which socs the firmware is now shown to build for.

Rules, all deterministic:

- **Additive.** An existing recipe dir is never rewritten or removed (G2: no record deletion
  until the guard exists; and a human may have upgraded `status`). Only missing recipes are
  written, `status: unverified`.
- **Cite the signal.** Every recipe carries `sources[]`: `field: '*'` → the firmware repo, and
  `field: board` → the exact URL (asset, manifest, platformio.ini line, workflow) that names the
  board. `notes` quotes the token as the repo wrote it. `flash` is filled only from a signal
  that proves it: a rank-1 `.bin` asset → `method: release-bin, bin_url`; a rank-2 env →
  `env: <name>` (the PlatformIO env to build). Otherwise no `flash` block (cite-or-omit).
- **Chip from the board record**, never from the signal: `chip_family = tools.board_soc(board)`,
  which the validator cross-checks. A signal whose own chip disagrees with the board's is
  refused here even if the resolver let it through.
- **Never collapse `socs`.** `socs_for()` returns the cited union: every written/existing
  recipe board's soc plus chip-only signals. The caller (the tick's stage) merges that into the
  firmware record textually; this module does not touch firmware.md.

`root` is the tree to write in (the tick's worktree; tmp_path in tests). Returns what it did,
with paths relative to `root`, so the publisher can stage exactly those.
"""
from __future__ import annotations

from pathlib import Path

import tools

RANK_KIND = {1: "release", 2: "platformio.ini", 3: "CI matrix", 4: "build target"}


def _yaml_scalar(s: str) -> str:
    """Double-quoted YAML scalar: safe for tokens with quotes, colons or non-ASCII."""
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _best(signals: list[dict]) -> dict:
    return sorted(signals, key=lambda s: (s["rank"], s["token"]))[0]


def _flash_from(signal: dict) -> dict | None:
    if signal["rank"] == 1 and signal["kind"] == "asset" and str(signal.get("url", "")).lower().endswith((".bin", ".bin.gz")):
        return {"method": "release-bin", "bin_url": signal["url"]}
    if signal["rank"] == 2 and signal.get("extra", {}).get("env"):
        return {"env": signal["extra"]["env"]}
    return None


def render_recipe(recipe_id: str, board: str, firmware: str, chip_family: str, firmware_url: str,
                  signals: list[dict], today: str) -> str:
    """The recipe.md text for one board, from its signals (best rank first). Pure."""
    best = _best(signals)
    urls: list[str] = []
    for s in sorted(signals, key=lambda s: (s["rank"], s["token"])):
        if s.get("url") and s["url"] not in urls:
            urls.append(s["url"])
    flash = _flash_from(best)
    what = RANK_KIND.get(best["rank"], "signal")
    note = f"{firmware} names this board as {best['token']!s} in its {what}"
    if best.get("extra", {}).get("env"):
        note += f" (env {best['extra']['env']})"
    if best.get("extra", {}).get("release"):
        note += f" (release {best['extra']['release']})"
    note += "; derived from the repo's own build files, not verified on hardware."
    lines = ["---", f"id: {recipe_id}", "type: recipe", f"board: {board}", f"firmware: {firmware}",
             "status: unverified", f"chip_family: {chip_family}"]
    if flash:
        lines.append("flash:")
        for k, v in flash.items():
            lines.append(f"  {k}: {_yaml_scalar(v) if k == 'env' else v}")
    lines.append(f"notes: {_yaml_scalar(note)}")
    lines.append("sources:")
    lines += [f"- field: '*'", f"  url: {firmware_url}", f"  verified: '{today}'"]
    for u in urls:
        lines += ["- field: board", f"  url: {u}", f"  verified: '{today}'"]
    lines.append("---")
    body = [f"# {board} x {firmware}", "",
            f"`{firmware}` declares `{best['token']}` in its {what}; that name resolves to the catalogued board "
            f"`{board}` ({chip_family}). Status `unverified` until someone with the hardware confirms it.", ""]
    for s in sorted(signals, key=lambda s: (s["rank"], s["token"])):
        body.append(f"- rank {s['rank']} {s['kind']}: `{s['token']}` — {s['url']}")
    return "\n".join(lines) + "\n\n" + "\n".join(body) + "\n"


def write_recipes(firmware_id: str, firmware_url: str, resolved: dict, *, root: Path, today: str,
                  board_soc=None) -> dict:
    """Write the missing recipes for `firmware_id` under `root`. Returns
    {"written": [recipe_id…], "paths": [relative dir…], "existing": [recipe_id…],
     "refused": [(atlas_id, why)…], "socs": sorted cited union}."""
    board_soc = board_soc or tools.board_soc
    written, paths, existing, refused, socs = [], [], [], [], set()
    for atlas_id, signals in sorted(resolved.get("boards", {}).items()):
        soc = board_soc(atlas_id)
        if not soc:
            refused.append((atlas_id, "board has no catalogued soc"))
            continue
        clash = [s for s in signals if s.get("soc") and s["soc"] != soc]
        if clash:
            refused.append((atlas_id, f"signal chip {clash[0]['soc']} disagrees with the board's {soc}"))
            continue
        rid = f"{atlas_id}__{firmware_id}"
        rdir = root / "data" / "recipes" / rid
        socs.add(soc)
        if (rdir / "recipe.md").exists():
            existing.append(rid)
            continue
        rdir.mkdir(parents=True, exist_ok=True)
        (rdir / "recipe.md").write_text(render_recipe(rid, atlas_id, firmware_id, soc, firmware_url, signals, today), encoding="utf-8")
        written.append(rid)
        paths.append(str((rdir).relative_to(root)))
    for soc in resolved.get("socs", {}):
        socs.add(soc)
    return {"written": written, "paths": paths, "existing": existing, "refused": refused, "socs": sorted(socs)}


def socs_for(firmware_id: str, root: Path, board_soc=None) -> list[str]:
    """The cited union of socs the firmware's recipes prove today (existing recipes only)."""
    board_soc = board_soc or tools.board_soc
    out = set()
    for rdir in (root / "data" / "recipes").glob(f"*__{firmware_id}"):
        board = rdir.name[: -(len(firmware_id) + 2)]
        soc = board_soc(board)
        if soc:
            out.add(soc)
    return sorted(out)


def merge_socs(firmware_md: Path, socs: list[str], source_url: str, today: str) -> bool:
    """Textually widen the firmware record's `socs:` list to include `socs` (never narrow it —
    a narrower derivation is reported, not applied), citing `source_url` under `field: socs`.
    Returns True when the file changed. No YAML round-trip: the `socs:` block and one appended
    source entry are the only lines touched."""
    text = firmware_md.read_text(encoding="utf-8")
    head, sep, rest = text.partition("\n---\n")
    if not text.startswith("---\n") or not sep:
        raise ValueError(f"{firmware_md}: no frontmatter")
    lines = head.split("\n")
    # current socs block
    i = next((k for k, l in enumerate(lines) if l.startswith("socs:")), None)
    current: list[str] = []
    if i is not None:
        inline = lines[i][len("socs:"):].strip()
        if inline.startswith("[") and inline.endswith("]"):
            current = [x.strip().strip("'\"") for x in inline[1:-1].split(",") if x.strip()]
            end = i + 1
        else:
            end = i + 1
            while end < len(lines) and lines[end].startswith("- "):
                current.append(lines[end][2:].strip().strip("'\""))
                end += 1
    else:
        end = None
    merged = sorted(set(current) | set(socs))
    if set(merged) == set(current):
        return False
    block = ["socs:"] + [f"- {s}" for s in merged]
    if i is None:
        name_idx = next(k for k, l in enumerate(lines) if l.startswith("name:"))
        lines[name_idx + 1:name_idx + 1] = block
    else:
        lines[i:end] = block
    src_idx = next((k for k, l in enumerate(lines) if l.startswith("sources:")), None)
    entry = ["- field: socs", f"  url: {source_url}", f"  verified: '{today}'"]
    if src_idx is None:
        lines += ["sources:"] + entry
    else:
        e = src_idx + 1
        while e < len(lines) and (lines[e].startswith("- ") or lines[e].startswith("  ")):
            e += 1
        lines[e:e] = entry
    firmware_md.write_text("\n".join(lines) + "\n---\n" + rest, encoding="utf-8")
    return True
