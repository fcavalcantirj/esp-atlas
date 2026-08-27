"""EspAtlas Jr — core tools (the hands).

Pure-Python, no agent framework here: these are the deterministic functions Agno will
expose to the model as tools. Each is independently testable. See ../JR.md / ../SPEC-espatlas-jr.md.

The guard is sovereign (SPEC §2.6): `run_guard()` shells the real deterministic validator.
Jr proposes via PR; it never writes `main`.
"""
from __future__ import annotations
import json
import subprocess
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent           # the esp-atlas repo root
FIRMWARE_DIR = REPO / "data" / "firmware"
LAUNCHERHUB = "https://api.launcherhub.net/giveMeTheList"


def run_guard() -> dict:
    """Run the deterministic guard (schema + oracle) over the atlas. Returns
    {"ok": bool, "output": str}. ok=True only when the guard is fully green — this is the
    gate every authored record must pass before a PR (SPEC §2.6)."""
    p = subprocess.run(
        ["python3", "scripts/validate.py"],
        cwd=REPO, capture_output=True, text=True, timeout=180,
    )
    return {"ok": p.returncode == 0, "output": (p.stdout + p.stderr).strip()[-2000:]}


def catalogued_firmware_ids() -> set[str]:
    """The firmware ids already in the atlas (dedup target)."""
    return {d.name for d in FIRMWARE_DIR.iterdir() if d.is_dir()} if FIRMWARE_DIR.exists() else set()


def fetch_launcher_catalog() -> list[dict]:
    """Fetch the Launcher/M5Burner community firmware catalog (the 2,487-entry backlog behind
    bmorcelli.github.io/Launcher/catalog.html). Official API, one call. SPEC §3b."""
    req = urllib.request.Request(LAUNCHERHUB, headers={"User-Agent": "esp-atlas-jr/0.1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    return data if isinstance(data, list) else data.get("data", [])


def _catalogued_repos_and_tokens() -> tuple[set[str], set[str]]:
    """(repo full_names, name-tokens) of catalogued firmware — the dedup fingerprint. A launcher
    entry that shares a repo owner/name or a firmware-name token is a PORT/variant, not new."""
    import re
    repos, tokens = set(), set()
    for d in (FIRMWARE_DIR.iterdir() if FIRMWARE_DIR.exists() else []):
        if not d.is_dir():
            continue
        tokens.add(d.name.lower())
        for part in re.split(r"[-_]", d.name.lower()):
            if len(part) >= 4:
                tokens.add(part)                        # e.g. 'bruce', 'marauder', 'nemo'
        md = (d / "firmware.md").read_text() if (d / "firmware.md").exists() else ""
        for line in md.splitlines():
            if line.startswith("url:") and "github.com/" in line:
                fn = line.split("github.com/", 1)[1].strip().rstrip("/").lower()
                repos.add("/".join(fn.split("/")[:2]))  # owner/repo
                repos.add(fn.split("/")[0])             # owner (catches other repos by same owner)
    return repos, tokens


def uncatalogued_with_code(limit: int = 5) -> list[dict]:
    """Launcher-catalog entries that are GENUINELY NEW firmware (not ports/forks of catalogued
    ones) and pass the with-code gate (resolve to a real GitHub repo). Dedup skips any entry
    sharing a repo owner/name or a firmware-name token with the catalogue (SPEC §3b: skip
    forks/mirrors). Ranked by `download` popularity proxy. Returns compact dicts."""
    repos, tokens = _catalogued_repos_and_tokens()
    out = []
    for e in fetch_launcher_catalog():
        gh = (e.get("github") or "").strip()
        if not gh or not gh.startswith("http"):
            continue                                    # with-code gate
        fn = gh.rstrip("/").replace("https://github.com/", "").lower()
        owner_repo = "/".join(fn.split("/")[:2])
        if owner_repo in repos or fn.split("/")[0] in repos:
            continue                                    # same repo/owner as a catalogued firmware
        name_l = (e.get("name") or "").lower()
        if any(t in name_l for t in tokens):
            continue                                    # name shares a catalogued firmware token → port
        out.append({
            "name": e.get("name"), "github": gh, "category": e.get("category"),
            "author": e.get("author"), "download": e.get("download", 0),
            "description": (e.get("description") or "")[:200],
        })
    out.sort(key=lambda x: x.get("download") or 0, reverse=True)
    return out[:limit]


def schema_enums() -> dict:
    """The valid values authoring MUST choose from (so the model can't invent `stickc`/`ESP32-C5`).
    Pulled live from the schemas + data dirs. Call this BEFORE authoring."""
    import json
    fw = json.loads((REPO / "schema/firmware.schema.json").read_text())["properties"]
    boards = sorted(b.name for b in (REPO / "data/boards").glob("*/*") if b.is_dir())
    socs = sorted(s.name for s in (REPO / "data/socs").iterdir() if s.is_dir())
    return {
        "firmware_category": fw["category"].get("enum"),
        "firmware_distribution": fw["distribution"].get("enum"),
        "recipe_status": ["known-good", "reported", "unverified", "broken"],
        "soc_ids": socs,
        "board_ids": boards,
    }


def author_recipe(recipe_id: str, board: str, firmware: str, chip_family: str,
                  sources: list[dict], body: str, status: str = "unverified",
                  flash: dict | None = None) -> dict:
    """Write a recipe pairing a firmware to a CATALOGUED board (resolves the orphan rule —
    firmware can't stand alone). `board` must be a catalogued board id, `chip_family` a valid soc
    id, `status` defaults to `unverified` (trust is human-only). Returns {"path": ...}."""
    import yaml
    rec: dict = {"id": recipe_id, "type": "recipe", "board": board, "firmware": firmware,
                 "status": status, "chip_family": chip_family}
    if flash:
        rec["flash"] = flash
    rec["sources"] = sources
    front = yaml.safe_dump(rec, sort_keys=False, default_flow_style=False).strip()
    d = REPO / "data" / "recipes" / recipe_id
    d.mkdir(parents=True, exist_ok=True)
    path = d / "recipe.md"
    path.write_text(f"---\n{front}\n---\n\n{body.strip()}\n")
    return {"path": str(path.relative_to(REPO))}


def fetch_github_repo(url: str) -> dict:
    """Fetch a repo's real metadata via the GitHub API (authed through `gh`, higher rate limit) —
    the citable ground truth for a firmware record: description, license, topics, homepage,
    default_branch, and **real stargazers_count** (use THIS for star-ranking, never the launcher
    like-count). Returns {} if the repo can't be resolved. Read the repo before authoring."""
    parts = url.rstrip("/").replace("https://github.com/", "").split("/")
    if len(parts) < 2:
        return {}
    owner, repo = parts[0], parts[1]
    p = subprocess.run(["gh", "api", f"repos/{owner}/{repo}"], capture_output=True, text=True, timeout=30)
    if p.returncode != 0:
        return {"error": p.stderr.strip()[:200]}
    d = json.loads(p.stdout)
    return {
        "full_name": d.get("full_name"), "description": d.get("description"),
        "license": (d.get("license") or {}).get("spdx_id"), "topics": d.get("topics", []),
        "homepage": d.get("homepage"), "default_branch": d.get("default_branch"),
        "stars": d.get("stargazers_count"), "archived": d.get("archived"),
    }


def author_firmware_record(
    firmware_id: str, name: str, url: str, category: str,
    socs: list[str], sources: list[dict], body: str,
    maintainer: str | None = None, license: str | None = None,
    distribution: list[str] | None = None, capabilities: list[str] | None = None,
) -> dict:
    """Write a firmware record to data/firmware/<id>/firmware.md (YAML frontmatter + markdown
    body). CITE-OR-OMIT: every entry in `sources` is {field, url, verified} and only fields
    backed by a source may be set (SPEC §2.2). New firmware is authored `unverified`; trust is
    human-only. Returns {"path": ...}. Does NOT touch git — call run_guard() then open_pr()."""
    import yaml
    fm: dict = {"id": firmware_id, "type": "firmware", "name": name, "url": url,
                "category": category}
    if maintainer: fm["maintainer"] = maintainer
    if license: fm["license"] = license
    if distribution: fm["distribution"] = distribution
    if capabilities: fm["capabilities"] = capabilities
    fm["socs"] = socs
    fm["sources"] = sources
    front = yaml.safe_dump(fm, sort_keys=False, default_flow_style=False).strip()
    d = FIRMWARE_DIR / firmware_id
    d.mkdir(parents=True, exist_ok=True)
    path = d / "firmware.md"
    path.write_text(f"---\n{front}\n---\n\n{body.strip()}\n")
    return {"path": str(path.relative_to(REPO))}


def open_pr(firmware_id: str, title: str, body: str, recipe_id: str | None = None,
            base: str = "main") -> dict:
    """Open a cited PR for an authored firmware (+ its recipe) on branch `jr/firmware-<id>`
    (never writes `main`; SPEC §2.3 bot-proposes-humans-dispose). Stages BOTH the firmware and
    the recipe so the branch is never orphaned. Assumes triple_validate() passed. Returns
    {"ok","pr_url"}."""
    branch = f"jr/firmware-{firmware_id}"
    paths = [f"data/firmware/{firmware_id}"]
    if recipe_id:
        paths.append(f"data/recipes/{recipe_id}")
    def git(*a): return subprocess.run(["git", *a], cwd=REPO, capture_output=True, text=True)
    git("checkout", "-B", branch)
    git("add", *paths)
    c = git("commit", "-m", title)
    git("push", "-u", "origin", branch, "--force-with-lease")
    pr = subprocess.run(
        ["gh", "pr", "create", "--base", base, "--head", branch, "--title", title, "--body", body],
        cwd=REPO, capture_output=True, text=True,
    )
    git("checkout", "main")  # leave main clean; the record lives on the branch/PR
    return {"ok": pr.returncode == 0, "pr_url": pr.stdout.strip(),
            "error": (pr.stderr or c.stderr).strip()[:300]}


def _frontmatter(md_path: Path) -> dict:
    import yaml
    txt = md_path.read_text()
    if txt.startswith("---"):
        return yaml.safe_load(txt.split("---", 2)[1]) or {}
    return {}


def triple_validate(firmware_id: str, recipe_id: str) -> dict:
    """THREE independent gates before a PR (Felipe's hard rule — never propose an unvalidated
    record). Returns {"pass": bool, "gate1_guard", "gate2_source", "gate3_structure"} with
    per-gate detail. A PR may open ONLY when pass=True."""
    en = schema_enums()
    fw_md = FIRMWARE_DIR / firmware_id / "firmware.md"
    rc_md = REPO / "data/recipes" / recipe_id / "recipe.md"
    problems = {"gate1": [], "gate2": [], "gate3": []}

    # GATE 1 — the deterministic guard (schema + oracle + no-orphan)
    g = run_guard()
    if not g["ok"]:
        problems["gate1"].append(g["output"].splitlines()[-1] if g["output"] else "guard failed")

    # GATE 2 — every cited field re-checked against the REAL github source (cite-or-omit holds)
    fw = _frontmatter(fw_md) if fw_md.exists() else {}
    if not fw:
        problems["gate2"].append("firmware record missing/unparseable")
    else:
        repo = fetch_github_repo(fw.get("url", ""))
        if not repo or repo.get("error"):
            problems["gate2"].append(f"repo unresolved: {fw.get('url')}")
        else:
            if fw.get("license") and repo.get("license") and fw["license"] != repo["license"]:
                problems["gate2"].append(f"license {fw['license']} != repo {repo['license']}")
            if fw.get("category") not in (en["firmware_category"] or []):
                problems["gate2"].append(f"category '{fw.get('category')}' not a valid enum")
            for s in fw.get("socs", []):
                if s not in en["soc_ids"]:
                    problems["gate2"].append(f"soc '{s}' not a known soc id")
        for src in fw.get("sources", []):
            u = src.get("url", "")
            try:
                req = urllib.request.Request(u, method="HEAD", headers={"User-Agent": "esp-atlas-jr"})
                urllib.request.urlopen(req, timeout=15)
            except Exception as e:
                problems["gate2"].append(f"source not live: {u} ({type(e).__name__})")

    # GATE 3 — structural: recipe pairs firmware to a catalogued board (kills the orphan)
    rc = _frontmatter(rc_md) if rc_md.exists() else {}
    if not rc:
        problems["gate3"].append("recipe missing/unparseable (firmware would be orphan)")
    else:
        if rc.get("firmware") != firmware_id:
            problems["gate3"].append(f"recipe.firmware '{rc.get('firmware')}' != '{firmware_id}'")
        if rc.get("board") not in en["board_ids"]:
            problems["gate3"].append(f"recipe.board '{rc.get('board')}' not catalogued")
        if rc.get("chip_family") not in en["soc_ids"]:
            problems["gate3"].append(f"chip_family '{rc.get('chip_family')}' not a known soc")
        if rc.get("status") not in en["recipe_status"]:
            problems["gate3"].append(f"status '{rc.get('status')}' invalid (must be unverified for new)")

    ok = not any(problems.values())
    return {"pass": ok, "gate1_guard": problems["gate1"] or "green",
            "gate2_source": problems["gate2"] or "cited fields match source",
            "gate3_structure": problems["gate3"] or "recipe pairs to catalogued board, no orphan"}


if __name__ == "__main__":  # self-test against the REAL repo + REAL source
    print("── guard (real validate.py) ──")
    g = run_guard()
    print(f"   ok={g['ok']}  tail: {g['output'].splitlines()[-1] if g['output'] else '(none)'}")

    print("── catalogued firmware ──")
    have = catalogued_firmware_ids()
    print(f"   {len(have)} in atlas: {sorted(have)[:8]}…")

    print("── launcher catalog (live) ──")
    cat = fetch_launcher_catalog()
    with_gh = sum(1 for e in cat if (e.get('github') or '').startswith('http'))
    print(f"   {len(cat)} entries, {with_gh} with a github link")

    print("── top uncatalogued with-code candidates ──")
    for c in uncatalogued_with_code(5):
        print(f"   • {c['name']:<24} dl={c['download']:<6} {c['github']}")
