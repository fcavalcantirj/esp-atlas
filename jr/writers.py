"""EspAtlas Jr — recipe writer (jr/writers.py): one cited recipe per resolved board, additive.

Phase 4 (SPEC-firmware-boards.md §3 provenance, PLAN §3.4 data model): a firmware's board edge
is a RECIPE (`data/recipes/<board>__<firmware>/recipe.md`), never a `boards` list on the
firmware record. This module turns jr/derive.resolve()'s output — {atlas_id: [signals…]} — into
recipes, and says which socs the firmware is now shown to build for.

Rules, all deterministic:

- **Additive.** An existing recipe dir is never rewritten or removed (G2: no record deletion
  until the guard exists; and a human may have upgraded `status`). Only missing recipes are
  written, `status: unverified`.
- **Cite where a reader can SEE it.** Every recipe carries `sources[]`: `field: '*'` → the
  firmware repo, and `field: board` → the page that names the board: a release asset cites its
  release page (`/releases/tag/<tag>`, where the asset list is readable — the download URL is a
  binary), a manifest / platformio.ini line / workflow / build target cites its own URL. `notes`
  quotes the token as the repo wrote it.
- **`flash` only from a signal that proves it.** A rank-1 `.bin` asset proves a release binary
  exists → `method: release-bin` and nothing more: whether that file is a merged image flashable
  at 0x0 is a hardware fact no filename proves, so `bin_url` (which makes the site serve an
  install manifest) is a HUMAN promotion after a hardware check (SPEC-flash-catalog §5). A
  rank-2 env → `env: <name>` cited under `field: flash.env`. Otherwise no `flash` block.
- **Chip from the board record**, never from the signal: `chip_family = board_soc(board)`,
  which the validator cross-checks. A signal whose own chip disagrees with the board's is
  refused here even if the resolver let it through.
- **Never collapse `socs`.** `socs_for()` returns the cited union: every written/existing
  recipe board's soc plus chip-only signals. The caller (the tick's stage) merges that into the
  firmware record with `merge_socs`, which widens only, cites one `field: socs` entry per proving
  URL, and verifies its own rewrite by re-parsing before it writes.

`root` is the tree to write in (the tick's worktree; tmp_path in tests). Returns what it did,
with paths relative to `root`, so the publisher can stage exactly those.

`render_firmware` (Track A admission) renders a scorer record as a firmware.md: exactly the
scorer's record fields — id/name/url/category, `socs` from the record's chip, capabilities,
maintainer — plus the given `sources[]`, and a one-line admission note as the prose. No free
prose, no capabilities beyond what the scorer already filtered through
tools.capability_vocab(). It returns text; the caller writes it.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

import tools

RANK_KIND = {0: "repository name/description", 1: "release", 2: "platformio.ini", 3: "CI matrix", 4: "build target"}
KIND_WHAT = {"submission": "submission issue"}          # kinds whose evidence is not a rank: the page where the claim appears

_ASSET_URL = re.compile(r"^(https://github\.com/[^/\s]+/[^/\s]+)/releases/download/([^/\s]+)/[^\s]+$")


def _yaml_scalar(s: str) -> str:
    """Double-quoted YAML scalar: safe for tokens with quotes, colons or non-ASCII."""
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _best(signals: list[dict]) -> dict:
    return sorted(signals, key=lambda s: (s["rank"], s["token"]))[0]


def evidence_url(signal: dict) -> str:
    """Where a reader can SEE the token. A release asset's download URL is a binary, so a rank-1
    asset cites its release page (the asset names are listed there); everything else cites its
    own URL (manifest JSON, platformio.ini#L<n>, workflow file, build target file)."""
    url = str(signal.get("url") or "")
    if signal.get("kind") == "asset":
        m = _ASSET_URL.match(url)
        if m:
            return f"{m.group(1)}/releases/tag/{m.group(2)}"
    return url


def _flash_from(signal: dict) -> dict | None:
    if signal["rank"] == 1 and signal["kind"] == "asset" and str(signal.get("url", "")).lower().endswith(".bin"):
        return {"method": "release-bin"}          # a binary exists; bin_url/offset need a hardware check (human)
    if signal["rank"] == 2 and signal.get("extra", {}).get("env"):
        return {"env": signal["extra"]["env"]}
    return None


def render_recipe(recipe_id: str, board: str, firmware: str, chip_family: str, firmware_url: str,
                  signals: list[dict], today: str) -> str:
    """The recipe.md text for one board, from its signals (best rank first). Pure."""
    ordered = sorted(signals, key=lambda s: (s["rank"], s["token"]))
    best = ordered[0]
    urls: list[str] = []
    for s in ordered:
        u = evidence_url(s)
        if u and u not in urls:
            urls.append(u)
    flash = _flash_from(best)
    what = KIND_WHAT.get(best.get("kind") or "", RANK_KIND.get(best["rank"], "signal"))
    note = f"{firmware} names this board as {best['token']!s} in its {what}"
    if best.get("extra", {}).get("env"):
        note += f" (env {best['extra']['env']})"
    if best.get("extra", {}).get("asset"):
        note += f" (asset {best['extra']['asset']})"
    if best.get("extra", {}).get("release"):
        note += f" (release {best['extra']['release']})"
    kind = best.get("kind")
    note += ("; named by the submitter, not verified on hardware." if kind == "submission"
             else "; named in the repository itself, not verified on hardware." if kind == "repo"
             else "; derived from the repo's own build files, not verified on hardware.")
    lines = ["---", f"id: {recipe_id}", "type: recipe", f"board: {board}", f"firmware: {firmware}",
             "status: unverified", f"chip_family: {chip_family}"]
    if flash:
        lines.append("flash:")
        for k, v in flash.items():
            lines.append(f"  {k}: {_yaml_scalar(v) if k == 'env' else v}")
    lines.append(f"notes: {_yaml_scalar(note)}")
    lines.append("sources:")
    lines += [f"- field: '*'", f"  url: {firmware_url}", f"  verified: '{today}'"]
    if flash and "env" in flash:
        lines += ["- field: flash.env", f"  url: {best['url']}", f"  verified: '{today}'"]
    for u in urls:
        lines += ["- field: board", f"  url: {u}", f"  verified: '{today}'"]
    lines.append("---")
    verb = "was submitted for" if best.get("kind") == "submission" else "declares"
    body = [f"# {board} x {firmware}", "",
            f"`{firmware}` {verb} `{best['token']}` in its {what}; that name resolves to the catalogued board "
            f"`{board}` ({chip_family}). Status `unverified` until someone with the hardware confirms it.", ""]
    for s in ordered:
        body.append(f"- rank {s['rank']} {s['kind']}: `{s['token']}` — {s['url']}")
    return "\n".join(lines) + "\n\n" + "\n".join(body) + "\n"


def write_recipes(firmware_id: str, firmware_url: str, resolved: dict, *, root: Path, today: str,
                  board_soc=None) -> dict:
    """Write the missing recipes for `firmware_id` under `root`. Returns
    {"written": [recipe_id…], "paths": [relative dir…], "existing": [recipe_id…],
     "refused": [(atlas_id, why)…], "socs": sorted cited union}.
    `board_soc` defaults to reading `root`'s own board records."""
    board_soc = board_soc or (lambda b: tools.board_soc(b, repo=root))
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
    board_soc = board_soc or (lambda b: tools.board_soc(b, repo=root))
    out = set()
    for rdir in (root / "data" / "recipes").glob(f"*__{firmware_id}"):
        board = rdir.name[: -(len(firmware_id) + 2)]
        soc = board_soc(board)
        if soc:
            out.add(soc)
    return sorted(out)


# --- firmware.md: widen `socs`, textually, verified ------------------------------------------------

_FENCE = re.compile(r"\A---\n(.*?)\n---(?:\n|\Z)", re.S)


def _key_line(lines: list[str], key: str) -> int | None:
    return next((k for k, l in enumerate(lines) if re.match(rf"^{re.escape(key)}:", l)), None)


def _block_span(lines: list[str], i: int) -> tuple[int, str]:
    """(end, item_indent) of the block-list items that follow the `key:` line at `i`. Items share
    the first item's indent; deeper-indented lines belong to the item above them. Stops at the
    first line that is neither (a comment or blank ends the block too — never guessed past)."""
    ind: str | None = None
    end = i + 1
    while end < len(lines):
        l = lines[end]
        m = re.match(r"^(\s*)- ", l)
        if m and ind is None:
            ind = m.group(1)
        elif m and m.group(1) == ind:
            pass
        elif ind is not None and l.strip() and l.startswith(ind + " "):
            pass
        else:
            break
        end += 1
    return end, ("" if ind is None else ind)


def merge_socs(firmware_md: Path, socs: list[str], source_urls: list[str] | str, today: str) -> bool:
    """Widen the firmware record's `socs:` list to include `socs` (never narrow it — a narrower
    derivation is reported, not applied), appending one `field: socs` source per URL in
    `source_urls` (the pages that prove the added chips). Returns True when the file changed.

    The current list comes from a real YAML parse; the text edit touches only the `socs:` block
    and the tail of `sources:` (keeping their indentation), and the result is re-parsed and
    checked — socs == the merged list, every other key byte-identical, the new sources at the
    end — BEFORE anything is written. Any doubt raises ValueError; the file is left untouched."""
    urls = [source_urls] if isinstance(source_urls, str) else list(dict.fromkeys(u for u in source_urls if u))
    with open(firmware_md, encoding="utf-8", newline="") as f:      # keep \r\n visible: refused, never normalised
        text = f.read()
    m = _FENCE.match(text)
    if not m:
        raise ValueError(f"{firmware_md}: no frontmatter fence")
    head, rest = m.group(1), text[m.end():]
    old_fm = yaml.safe_load(head)
    if not isinstance(old_fm, dict):
        raise ValueError(f"{firmware_md}: frontmatter is not a mapping")
    current = old_fm.get("socs") or []
    if not isinstance(current, list) or not all(isinstance(s, str) for s in current):
        raise ValueError(f"{firmware_md}: socs is not a list of strings")
    merged = sorted(set(current) | set(socs))
    if set(merged) == set(current):
        return False
    if not urls:
        raise ValueError(f"{firmware_md}: socs widening without a source URL (cite-or-omit)")

    lines = head.split("\n")
    # --- socs block --------------------------------------------------------------------------
    i = _key_line(lines, "socs")
    if i is None:
        anchor = _key_line(lines, "name")
        anchor = _key_line(lines, "id") if anchor is None else anchor
        at = len(lines) if anchor is None else anchor + 1
        lines[at:at] = ["socs:"] + [f"- {s}" for s in merged]
    else:
        after = lines[i][len("socs:"):]
        if re.match(r"^\s*(#.*)?$", after):                                   # block form
            end, ind = _block_span(lines, i)
            lines[i:end] = ["socs:"] + [f"{ind}- {s}" for s in merged]
        elif re.match(r"^\s*\[.*\]\s*(#.*)?$", after):                        # one-line flow list
            lines[i] = "socs: [" + ", ".join(merged) + "]"
        else:
            raise ValueError(f"{firmware_md}: socs written in a form this writer will not touch: {lines[i]!r}")
    # --- sources tail --------------------------------------------------------------------------
    s = _key_line(lines, "sources")
    if s is None:
        ind = ""
        lines += ["sources:"]
        at = len(lines)
    else:
        after = lines[s][len("sources:"):]
        if re.match(r"^\s*(#.*)?$", after):
            at, ind = _block_span(lines, s)
        elif re.match(r"^\s*\[\s*\]\s*(#.*)?$", after):
            lines[s] = "sources:"
            at, ind = s + 1, ""
        else:
            raise ValueError(f"{firmware_md}: sources written in a form this writer will not touch: {lines[s]!r}")
    entries = []
    for u in urls:
        entries += [f"{ind}- field: socs", f"{ind}  url: {u}", f"{ind}  verified: '{today}'"]
    lines[at:at] = entries
    new_head = "\n".join(lines)
    # --- verify before writing -------------------------------------------------------------------
    try:
        new_fm = yaml.safe_load(new_head)
    except yaml.YAMLError as e:
        raise ValueError(f"{firmware_md}: rewrite would not parse: {e}") from None
    expected_tail = [{"field": "socs", "url": u, "verified": today} for u in urls]
    old_sources = old_fm.get("sources") or []
    ok = (isinstance(new_fm, dict)
          and new_fm.get("socs") == merged
          and set(new_fm.get("socs") or []) >= set(current)
          and new_fm.get("sources") == list(old_sources) + expected_tail
          and {k: v for k, v in new_fm.items() if k not in ("socs", "sources")}
              == {k: v for k, v in old_fm.items() if k not in ("socs", "sources")})
    if not ok:
        raise ValueError(f"{firmware_md}: rewrite verification failed; file left untouched")
    firmware_md.write_text("---\n" + new_head + "\n---\n" + rest, encoding="utf-8")
    return True


_FIRMWARE_ID_RE = re.compile(r"^[a-z0-9-]+$")   # schema/firmware.schema.json's id pattern


def render_firmware(record: dict, sources: list[dict], today: str,
                    needs_human: bool = False, popularity: dict | None = None) -> str:
    """Render a scorer record as a complete firmware.md (frontmatter + prose). Pure: returns
    text, writes nothing. Exactly the scorer's record fields — id/name/url/category, `socs`
    from the record's chip, capabilities, maintainer — plus `sources[]` (each stamped
    `verified: today`), and one admission note as the prose. Refuses a non-schema id."""
    fid = record.get("id") or ""
    if not _FIRMWARE_ID_RE.match(fid):
        raise ValueError(f"render_firmware: id {fid!r} is not a schema firmware id")
    fm: dict = {
        "id": fid,
        "type": "firmware",
        "name": record.get("name") or fid,
        "url": record.get("url"),
        "category": record.get("category"),
        "socs": [record.get("chip")],
        "sources": [{"field": s["field"], "url": s["url"], "verified": today} for s in sources],
    }
    if record.get("maintainer"):
        fm["maintainer"] = record["maintainer"]
    if record.get("capabilities"):
        fm["capabilities"] = list(record["capabilities"])
    if popularity and isinstance(popularity.get("stars"), int) and isinstance(popularity.get("forks"), int):
        # The dated snapshot SPEC-firmware-floor.md asks for, so scripts/firmware_floor_audit.py
        # enforces the floor on Jr's own records in CI, offline — the gate, not a reader, checks.
        fm["popularity"] = {"stars": int(popularity["stars"]), "forks": int(popularity["forks"]), "as_of": today}
    front = yaml.safe_dump(fm, sort_keys=False, default_flow_style=False).strip()
    detail = "needs_human" if needs_human else "authored"
    return f"---\n{front}\n---\n\nAdmitted by jr/scorer.py rule {detail}.\n"
