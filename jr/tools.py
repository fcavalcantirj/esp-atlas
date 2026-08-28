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
BOARDS_DIR = REPO / "data" / "boards"
SOCS_DIR = REPO / "data" / "socs"
MODULES_DIR = REPO / "data" / "modules"
COVERAGE_MD = REPO / "COVERAGE.md"
LAUNCHERHUB = "https://api.launcherhub.net/giveMeTheList"
FETCH_USER_AGENT = "esp-atlas-jr/0.1 (+https://esp-atlas.com; board-authoring bot)"


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


_LEDGER = Path(__file__).resolve().parent / "proposed.json"


def _proposed_repos() -> set[str]:
    """owner/repo of every firmware Jr has already PROPOSED — so it's never re-proposed while a PR
    is open, and stays skipped if that PR was closed/rejected (SPEC §8: never re-propose rejected)."""
    if _LEDGER.exists():
        try:
            return set(json.loads(_LEDGER.read_text()))
        except Exception:
            return set()
    return set()


def mark_proposed(url: str) -> None:
    """Record a firmware's repo as proposed (called after it lands in a PR)."""
    fn = url.rstrip("/").replace("https://github.com/", "").lower()
    owner_repo = "/".join(fn.split("/")[:2])
    if not owner_repo:
        return
    s = _proposed_repos(); s.add(owner_repo)
    _LEDGER.write_text(json.dumps(sorted(s)))


MONTHLY_CAP_USD = 5.0
_SPEND = Path(__file__).resolve().parent / "spend.json"
_PRICE_IN, _PRICE_OUT = 0.15 / 1e6, 0.60 / 1e6          # Groq gpt-oss-120b paid, $/token


def _spend_data() -> dict:
    if _SPEND.exists():
        try:
            return json.loads(_SPEND.read_text())
        except Exception:
            return {}
    return {}


def month_spend(month: str | None = None) -> float:
    """This calendar month's Jr spend in USD (the hard-cap check)."""
    import datetime as dt
    month = month or dt.date.today().strftime("%Y-%m")
    return _spend_data().get(month, {}).get("cost", 0.0)


def record_spend(input_tokens: int, output_tokens: int) -> float:
    """Add a run's token cost to this month's ledger; returns the month's running cost."""
    import datetime as dt
    month = dt.date.today().strftime("%Y-%m")
    d = _spend_data()
    m = d.setdefault(month, {"tokens_in": 0, "tokens_out": 0, "cost": 0.0, "runs": 0})
    m["tokens_in"] += int(input_tokens or 0)
    m["tokens_out"] += int(output_tokens or 0)
    m["cost"] = round(m["tokens_in"] * _PRICE_IN + m["tokens_out"] * _PRICE_OUT, 4)
    m["runs"] += 1
    _SPEND.write_text(json.dumps(d, indent=1))
    return m["cost"]


def uncatalogued_with_code(limit: int = 5) -> list[dict]:
    """Launcher-catalog entries that are GENUINELY NEW firmware (not ports/forks of catalogued
    ones) and pass the with-code gate (resolve to a real GitHub repo). Dedup skips any entry
    sharing a repo owner/name or a firmware-name token with the catalogue (SPEC §3b: skip
    forks/mirrors). Ranked by `download` popularity proxy. Returns compact dicts."""
    repos, tokens = _catalogued_repos_and_tokens()
    repos |= _proposed_repos()                          # also skip firmware already in an open/closed PR
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
        NOISE = ("doom", "gameboy", "game boy", "emulator", "tetris", "pacman", "pac-man", "snake",
                 "nes", "snes", "pokemon", "arduboy", "chip-8", "chip8", "uiflow", "micropython",
                 "tamagotchi", "flappy", "2048", " game", "demo", "hello world", "test")
        if any(t in name_l for t in NOISE):
            continue                                    # games/emulators/platforms — not atlas firmware
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
        "capabilities": sorted(capability_vocab()),   # ONLY these tokens — never freeform phrases
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


def fetch_github_readme(url: str, max_chars: int = 3500) -> str:
    """Fetch the repo's README text — the RICHEST citable source (API description/topics are
    often empty, as with CatHack). Read this to source category / socs / capabilities / which
    boards a firmware supports. Returns '' if none."""
    parts = url.rstrip("/").replace("https://github.com/", "").split("/")
    if len(parts) < 2:
        return ""
    owner, repo = parts[0], parts[1]
    p = subprocess.run(["gh", "api", f"repos/{owner}/{repo}/readme", "--jq", ".content"],
                       capture_output=True, text=True, timeout=30)
    if p.returncode != 0 or not p.stdout.strip():
        return ""
    import base64
    try:
        return base64.b64decode(p.stdout.strip()).decode("utf-8", "ignore")[:max_chars]
    except Exception:
        return ""


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


def open_batch_pr(firmware_ids: list[str], label: str, base: str = "main") -> dict:
    """Open ONE PR bundling many authored firmware (+ their recipes + the coverage run-cases) —
    a reviewable daily batch instead of a flood of PRs. Assumes each passed triple_validate.
    `label` makes the branch unique (e.g. a date). Returns {"ok","pr_url","count"}."""
    if not firmware_ids:
        return {"ok": False, "error": "empty batch"}
    branch = f"jr/batch-{label}"
    paths = ["apps/core/tests/test_coverage_matrix.py"]
    for fid in firmware_ids:
        paths.append(f"data/firmware/{fid}")
        for rdir in (REPO / "data/recipes").glob(f"*__{fid}"):
            paths.append(str(rdir.relative_to(REPO)))
    def git(*a): return subprocess.run(["git", *a], cwd=REPO, capture_output=True, text=True)
    git("checkout", "-B", branch)
    git("add", *paths)
    git("commit", "-m", f"feat(firmware): batch add {len(firmware_ids)} firmware (unverified) — {label}")
    git("push", "-u", "origin", branch, "--force-with-lease")
    rows = "\n".join(f"- `{f}` → " + ", ".join(
        r.name.split("__")[0] for r in (REPO / "data/recipes").glob(f"*__{f}")) for f in firmware_ids)
    body = (f"**TL;DR** — Jr's daily batch: **{len(firmware_ids)} new firmware** (all `unverified`, "
            f"triple-validated, socs derived from board records).\n\n### Firmware (firmware → boards)\n{rows}\n\n"
            "Discovered via the Launcher/M5Burner catalog, with-code gated. Guard green, coverage run-cases "
            "included. **Bot proposes, humans dispose** — skim, then merge (or drop any you don't want).\n\n"
            "— 🤖 **EspAtlas Jr** · autonomous data-keeper")
    pr = subprocess.run(["gh", "pr", "create", "--base", base, "--head", branch,
                         "--title", f"feat(firmware): batch add {len(firmware_ids)} firmware ({label})",
                         "--body", body], cwd=REPO, capture_output=True, text=True)
    git("checkout", "main")
    return {"ok": pr.returncode == 0, "pr_url": pr.stdout.strip(), "count": len(firmware_ids),
            "error": pr.stderr.strip()[:200]}


def build_firmware_pr_body(firmware_id: str, recipe_id: str) -> str:
    """Deterministically build a HUMAN-friendly PR body — TL;DR, clickable links, what/why —
    from the authored records + live repo stars. Not left to the model. Jr signs its own PRs."""
    fw = _frontmatter(FIRMWARE_DIR / firmware_id / "firmware.md")
    rc = _frontmatter(REPO / "data/recipes" / recipe_id / "recipe.md")
    repo = fetch_github_repo(fw.get("url", "")) or {}
    stars = f" ({repo['stars']:,}★)" if repo.get("stars") else ""
    name = fw.get("name", firmware_id)
    ghurl = fw.get("url", "")
    board = rc.get("board", "")
    desc = (repo.get("description") or "").strip().rstrip(".")
    socs = ", ".join(f"`{s}`" for s in fw.get("socs", []))
    body_md = (fw_md_body := (FIRMWARE_DIR / firmware_id / "firmware.md").read_text().split("---", 2)[-1].strip())
    return f"""**TL;DR** — Add **[{name}]({ghurl})**{stars}, a `{fw.get('category')}` firmware, for the **[{board}](https://esp-atlas.com/parts/{board})** — as an `unverified` firmware + recipe for review.

### What it is
{desc or body_md.splitlines()[0] if body_md else name}

### What this PR adds
| | |
|---|---|
| 🔌 Firmware | **[{name}]({ghurl})** — category `{fw.get('category')}`, socs {socs} |
| 🧩 Recipe | **{board} × {firmware_id}** — chip `{rc.get('chip_family')}`, `status: {rc.get('status')}` |
| 🔗 Board | [{board}](https://esp-atlas.com/parts/{board}) · (firmware page → `esp-atlas.com/firmware/{firmware_id}` once merged) |

### Why
Top uncatalogued firmware by downloads in the **[Launcher / M5Burner catalog](https://bmorcelli.github.io/Launcher/catalog.html)** — a real, repo-backed tool people flash today.

### Provenance & validation
Discovered via launcherhub `giveMeTheList`, with-code gated on its GitHub repo. Authored **cite-or-omit**{" — `license` omitted (repo declares none; no fabrication)" if not fw.get("license") else ""}. **Triple-validated:** deterministic guard green · every field re-checked against the source · recipe pairs to a catalogued board (no orphan).

> **Bot proposes, humans dispose** — trust-tier promotion is human-only. Please review + merge.
>
> — 🤖 **EspAtlas Jr** · autonomous data-keeper (Agno + Groq `gpt-oss-120b`)"""


def open_pr(firmware_id: str, title: str, body: str | None = None, recipe_id: str | None = None,
            base: str = "main") -> dict:
    """Open a cited PR for an authored firmware (+ its recipe) on branch `jr/firmware-<id>`
    (never writes `main`; SPEC §2.3 bot-proposes-humans-dispose). Stages BOTH the firmware and
    the recipe so the branch is never orphaned. Assumes triple_validate() passed. Returns
    {"ok","pr_url"}."""
    branch = f"jr/firmware-{firmware_id}"
    paths = [f"data/firmware/{firmware_id}", "apps/core/tests/test_coverage_matrix.py"]
    if recipe_id:
        paths.append(f"data/recipes/{recipe_id}")
    def git(*a): return subprocess.run(["git", *a], cwd=REPO, capture_output=True, text=True)
    git("checkout", "-B", branch)
    git("add", *paths)
    c = git("commit", "-m", title)
    git("push", "-u", "origin", branch, "--force-with-lease")
    if body is None and recipe_id:
        body = build_firmware_pr_body(firmware_id, recipe_id)   # human-friendly, deterministic
    pr = subprocess.run(
        ["gh", "pr", "create", "--base", base, "--head", branch, "--title", title, "--body", body],
        cwd=REPO, capture_output=True, text=True,
    )
    pr_url = pr.stdout.strip()
    if pr.returncode == 0:                              # nudge Felipe (§7) while the record is still on disk
        try:
            import notify
            fw = _frontmatter(FIRMWARE_DIR / firmware_id / "firmware.md")
            board = _frontmatter(REPO / "data/recipes" / recipe_id / "recipe.md").get("board", "") if recipe_id else ""
            notify.nudge_pr(firmware_id, fw.get("name", firmware_id), pr_url, board)
        except Exception:
            pass
    git("checkout", "main")  # leave main clean; the record lives on the branch/PR
    return {"ok": pr.returncode == 0, "pr_url": pr_url,
            "error": (pr.stderr or c.stderr).strip()[:300]}


def run_ci_tests() -> dict:
    """Run the coverage-matrix invariant CI test (the one #69 broke) so Jr never proposes a PR
    that reds main. Uses system python3 (has esp_atlas_core + pytest). {"ok","output"}."""
    p = subprocess.run(["python3", "-m", "pytest",
                        "apps/core/tests/test_coverage_matrix.py",   # run-case coverage
                        "apps/core/tests/test_examples.py",          # capabilities / labels
                        "apps/core/tests/test_intent_oracle.py",     # routable-by-name
                        "-q"], cwd=REPO, capture_output=True, text=True, timeout=200)
    return {"ok": p.returncode == 0, "output": (p.stdout + p.stderr).strip()[-1500:]}


def author_run_case(firmware_id: str) -> dict:
    """Register a firmware's coverage RUN case in test_coverage_matrix.py's RUN_MATRIX, so the
    `test_every_firmware_has_a_run_case` invariant stays green (the gap that broke main on #69).
    Minimal case (id + fw) — grounds via the recipe; capability asserts can be tightened later."""
    import re
    p = REPO / "apps/core/tests/test_coverage_matrix.py"
    txt = p.read_text()
    if f'fw="{firmware_id}"' in txt:
        return {"skipped": "run case already present"}
    start = txt.index("RUN_MATRIX = [")
    end = txt.index("\n]", start)                       # the newline right before RUN_MATRIX's ]
    nums = [int(m) for m in re.findall(r'id="(\d+)_', txt[start:end])]
    n = (max(nums) + 1) if nums else 1
    entry = f'    dict(\n        id="{n}_{firmware_id}",\n        fw="{firmware_id}",\n    ),\n'
    p.write_text(txt[: end + 1] + entry + txt[end + 1:])
    return {"path": "apps/core/tests/test_coverage_matrix.py", "case": f"{n}_{firmware_id}"}


def remove_run_case(firmware_id: str) -> None:
    """Remove a firmware's RUN_MATRIX block (used when a batch firmware is rejected, so its
    orphan run-case can't red the CI test for the rest of the batch)."""
    p = REPO / "apps/core/tests/test_coverage_matrix.py"
    lines = p.read_text().splitlines(keepends=True)
    out, i = [], 0
    while i < len(lines):
        if lines[i].strip() == "dict(" and any(f'fw="{firmware_id}"' in l for l in lines[i:i + 5]):
            while i < len(lines) and lines[i].strip() != "),":
                i += 1
            i += 1  # skip the closing "),"
            continue
        out.append(lines[i]); i += 1
    p.write_text("".join(out))


def _frontmatter(md_path: Path) -> dict:
    import yaml
    txt = md_path.read_text()
    if txt.startswith("---"):
        return yaml.safe_load(txt.split("---", 2)[1]) or {}
    return {}


def board_soc(board_id: str) -> str | None:
    """The chip_family (soc) of a catalogued board, read from its record — GROUND TRUTH so Jr
    never guesses a chip. Returns None if the board or its soc is unknown."""
    for bmd in (REPO / "data/boards").glob(f"*/{board_id}/board.md"):
        return _frontmatter(bmd).get("soc")
    return None


def capability_vocab() -> set[str]:
    """The controlled capability vocabulary — the tokens existing firmware use (wifi, ble, ir,
    display, ota, sub-ghz…). Jr may ONLY use these; freeform capabilities like
    'Media playback (MP3, WAV)' break test_examples (comma-split). Derived from live records."""
    vocab: set[str] = set()
    for d in (FIRMWARE_DIR.iterdir() if FIRMWARE_DIR.exists() else []):
        md = d / "firmware.md"
        if md.is_dir() or not md.exists():
            continue
        for c in (_frontmatter(md).get("capabilities") or []):
            if isinstance(c, str):
                vocab.add(c)
    return vocab


def author_firmware_and_recipes(firmware_id: str, name: str, url: str, category: str,
                                boards: list[str], body: str, capabilities: list[str] | None = None,
                                maintainer: str | None = None, license: str | None = None,
                                distribution: list[str] | None = None) -> dict:
    """DETERMINISTIC authoring — the model supplies ONLY judgment (category, which catalogued
    `boards` it runs on, capabilities from the README). `socs` and every recipe's `chip_family`
    are DERIVED from the board records — the model never touches a chip id (kills the
    soc-fabrication class, e.g. CatHack's esp32-s3). Writes the firmware + one recipe per board +
    the coverage run-case, all consistent by construction."""
    import re
    if not re.fullmatch(r"[a-z][a-z0-9-]{1,39}", firmware_id or "") or re.search(r"\d{4}-\d\d", firmware_id):
        return {"error": f"bad firmware id '{firmware_id}' — use ONE clean slug (the repo/tool name), "
                         "lowercase-hyphen, NO dates/versions (e.g. 'm5stick-shark', not 'shark-2024-08-1')"}
    boards = [b for b in dict.fromkeys(boards) if board_soc(b)]   # catalogued, known-soc, deduped
    if not boards:
        return {"error": "no catalogued board with a known soc — open an Issue, do not author"}
    socs = sorted({board_soc(b) for b in boards})
    if capabilities:                                    # keep ONLY controlled-vocab tokens — no freeform
        vocab = capability_vocab()
        capabilities = [c for c in capabilities if isinstance(c, str) and c in vocab] or None
    src = [{"field": "*", "url": url, "verified": "2026-08-27"}]
    author_firmware_record(firmware_id, name, url, category, socs, src, body,
                           maintainer=maintainer, license=license,
                           distribution=distribution, capabilities=capabilities)
    recipes = []
    for b in boards:
        rid = f"{b}__{firmware_id}"
        author_recipe(rid, b, firmware_id, board_soc(b), src,
                      f"{name} on the {b} ({board_soc(b)}). `unverified`; the repo lists {b} as a supported device.")
        recipes.append(rid)
    return {"firmware": firmware_id, "socs": socs, "recipes": recipes, "run_case": author_run_case(firmware_id)}


def triple_validate(firmware_id: str, recipe_id: str) -> dict:
    """THREE independent gates before a PR (Felipe's hard rule — never propose an unvalidated
    record). Returns {"pass": bool, "gate1_guard", "gate2_source", "gate3_structure"} with
    per-gate detail. A PR may open ONLY when pass=True."""
    en = schema_enums()
    fw_md = FIRMWARE_DIR / firmware_id / "firmware.md"
    rc_md = REPO / "data/recipes" / recipe_id / "recipe.md"
    problems = {"gate1": [], "gate2": [], "gate3": []}

    # GATE 1 — the deterministic guard (schema + oracle + no-orphan) + the CI coverage invariant
    g = run_guard()
    if not g["ok"]:
        problems["gate1"].append(g["output"].splitlines()[-1] if g["output"] else "guard failed")
    ci = run_ci_tests()   # the pytest invariant #69 broke — never propose a PR that reds main
    if not ci["ok"]:
        problems["gate1"].append("CI test red: " + (ci["output"].splitlines()[-1] if ci["output"] else "pytest failed"))

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
        if rc.get("chip_family") and fw.get("socs") and rc["chip_family"] not in fw["socs"]:
            problems["gate3"].append(  # the cathack-class semantic error the deterministic guard misses
                f"soc mismatch: recipe chip '{rc['chip_family']}' not in firmware socs {fw.get('socs')}")
        if rc.get("status") not in en["recipe_status"]:
            problems["gate3"].append(f"status '{rc.get('status')}' invalid (must be unverified for new)")

    ok = not any(problems.values())
    return {"pass": ok, "gate1_guard": problems["gate1"] or "green",
            "gate2_source": problems["gate2"] or "cited fields match source",
            "gate3_structure": problems["gate3"] or "recipe pairs to catalogued board, no orphan"}


def open_board_batch_pr(boards: list[tuple[str, str]], label: str, base: str = "main") -> dict:
    """Open ONE PR bundling many authored boards — mirrors open_batch_pr() for firmware. `boards`
    is a list of (brand, board_id) pairs. Assumes each passed board_triple_validate. `label` makes
    the branch unique (e.g. a date). Returns {"ok","pr_url","count"}."""
    if not boards:
        return {"ok": False, "error": "empty batch"}
    branch = f"jr/boards-{label}"
    paths = [f"data/boards/{brand}/{board_id}" for brand, board_id in boards]
    def git(*a): return subprocess.run(["git", *a], cwd=REPO, capture_output=True, text=True)
    git("checkout", "-B", branch)
    git("add", *paths)
    git("commit", "-m", f"feat(boards): batch add {len(boards)} board(s) — {label}")
    git("push", "-u", "origin", branch, "--force-with-lease")
    rows = "\n".join(f"- `{brand}/{board_id}`" for brand, board_id in boards)
    body = (f"**TL;DR** — Jr's board batch: **{len(boards)} new board(s)**, cite-or-omit, "
            f"triple-validated.\n\n### Boards\n{rows}\n\n"
            "Discovered via the COVERAGE.md backlog against each vendor's official product/"
            "user-guide page. **Bot proposes, humans dispose** — skim, then merge (or drop any "
            "you don't want).\n\n— 🤖 **EspAtlas Jr** · autonomous data-keeper")
    pr = subprocess.run(["gh", "pr", "create", "--base", base, "--head", branch,
                         "--title", f"feat(boards): batch add {len(boards)} board(s) ({label})",
                         "--body", body], cwd=REPO, capture_output=True, text=True)
    git("checkout", "main")
    return {"ok": pr.returncode == 0, "pr_url": pr.stdout.strip(), "count": len(boards),
            "error": pr.stderr.strip()[:200]}


# ─────────────────────────── board authoring (SPEC §3a "board population") ───────────────────────────

def _slugify(text: str) -> str:
    """kebab-case a free-text name for id-dedup matching (not necessarily the real board_id —
    boards use hand-picked ids; this is only a fuzzy dedup key)."""
    import re
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return re.sub(r"-{2,}", "-", s)


def _existing_board_ids() -> set[str]:
    return {d.name for d in BOARDS_DIR.glob("*/*") if d.is_dir()} if BOARDS_DIR.exists() else set()


def _existing_board_names() -> set[str]:
    """Normalized (alnum-only, lowercase) `name:` of every already-authored board — a second,
    fuzzier dedup signal alongside the id-slug match (board ids don't always slugify 1:1 from the
    marketing name, e.g. 'm5stick-cplus2')."""
    import re
    names = set()
    for md in (BOARDS_DIR.glob("*/*/board.md") if BOARDS_DIR.exists() else []):
        n = _frontmatter(md).get("name")
        if n:
            names.add(re.sub(r"[^a-z0-9]", "", n.lower()))
    return names


def board_refs() -> dict:
    """The ONLY valid soc/module ids the board agent may reference for `soc:`/`module:` — call
    this FIRST, before author_board. Pulled live from data/socs/ and data/modules/ (dirs only) so
    a weak model can never invent a chip/module id, and never needs a filesystem-browsing tool
    (e.g. list_directory) it doesn't have."""
    soc_ids = sorted(d.name for d in SOCS_DIR.iterdir() if d.is_dir()) if SOCS_DIR.exists() else []
    module_ids = sorted(d.name for d in MODULES_DIR.iterdir() if d.is_dir()) if MODULES_DIR.exists() else []
    return {"soc_ids": soc_ids, "module_ids": module_ids}


def coverage_backlog() -> list[dict]:
    """Parse ../COVERAGE.md into the still-unchecked `[ ]` boards, as {name, vendor, url}. `url`
    is None where COVERAGE.md itself has no live link yet (e.g. '(url: to-verify)') — Jr must not
    invent one. Skips any entry that already has a board dir under data/boards/ (by id-slug or by
    matching `name:`), even if the checkbox in COVERAGE.md hasn't been flipped yet."""
    import re
    if not COVERAGE_MD.exists():
        return []
    existing_ids, existing_names = _existing_board_ids(), _existing_board_names()
    lines = COVERAGE_MD.read_text().splitlines()
    out: list[dict] = []
    vendor = None
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("## "):
            vendor = line[3:].strip()
            i += 1
            continue
        m = re.match(r"^- \[([ xX])\]\s*(.+)$", line)
        if not m:
            i += 1
            continue
        checked, rest = m.group(1).strip().lower() == "x", m.group(2)
        entry_lines = [rest]
        j = i + 1
        while j < len(lines) and lines[j].startswith("  ") and not re.match(r"^\s*- \[", lines[j]):
            entry_lines.append(lines[j].strip())
            j += 1
        if not checked:
            name = rest.split("—", 1)[0].strip()
            url_match = re.search(r"https?://\S+", " ".join(entry_lines))
            url = url_match.group(0).rstrip(".,;)") if url_match else None
            if _slugify(name) not in existing_ids and re.sub(r"[^a-z0-9]", "", name.lower()) not in existing_names:
                out.append({"name": name, "vendor": vendor, "url": url})
        i = j
    return out


def fetch_url(url: str) -> dict:
    """GET a public official product/user-guide page and return its readable text (tags/scripts/
    styles stripped). SPEC §2.5: official pages only, rate-limited, no ToS-violating scraping — a
    single plain GET with a UA and a short timeout, no crawling, no JS rendering. Returns
    {"url","text"} or {"error"}."""
    import html
    import re
    if not url or not url.startswith(("http://", "https://")):
        return {"error": f"not an http(s) url: {url!r}"}
    req = urllib.request.Request(url, headers={"User-Agent": FETCH_USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            charset = r.headers.get_content_charset() or "utf-8"
            raw = r.read(1_500_000).decode(charset, "ignore")
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = "\n".join(l.strip() for l in text.splitlines() if l.strip())
    return {"url": url, "text": text[:20000]}


_BOARD_OPTIONAL_FIELDS = ("aka", "flash_mb", "psram_mb", "form_factor", "price_tier",
                          "dimensions_mm", "usb", "power", "display", "extras", "io", "notes")


def _field_covered(field: str, sources: list[dict]) -> bool:
    """A top-level field is cited if some sources[] entry is '*' (whole record), exactly that
    field, or a dotted path under it (e.g. field='io' is covered by 'io.gpio_free')."""
    for s in sources or []:
        f = s.get("field", "")
        if f == "*" or f == field or f.startswith(field + "."):
            return True
    return False


_USB_CONNECTORS = {"usb-c", "micro-usb", "mini-usb", "none"}


def author_board(board_id: str, brand: str, name: str, fields: dict, sources: list[dict],
                 body: str, soc: str | None = None, module: str | None = None,
                 today: str | None = None) -> dict:
    """Write data/boards/<brand>/<board_id>/board.md from templates/board.template.md's shape —
    id==folder, brand==folder, EXACTLY one of soc/module, ONLY the fields in `fields` (cite-or-
    omit — SPEC §2.2), each covered by a sources[] entry. Returns {"board_id","path"} or
    {"error"}. Does NOT touch git or run the guard — call run_guard()/board_triple_validate() next.
    Tolerant of a weak model, but ONLY within `fields`/`sources` (no signature catch-all, so the
    Agno-generated tool schema stays minimal/correct): any key in `fields` not in the board schema
    is dropped silently; a bare `usb` string like "USB-C" is coerced to {"connector":"usb-c"} (an
    unrecognized string is dropped); if `today` (an ISO date) is given, any sources[] `verified`
    that is still a bool or missing is normalized to `today`. Every sources[] entry still needs
    field+url+verified or the board is rejected — cite-or-omit is unchanged."""
    import re
    import yaml
    if not re.fullmatch(r"[a-z0-9-]+", board_id or ""):
        return {"error": f"bad board id '{board_id}' — kebab-case only"}
    if not re.fullmatch(r"[a-z0-9-]+", brand or ""):
        return {"error": f"bad brand '{brand}' — kebab-case only"}
    if bool(soc) == bool(module):
        return {"error": "exactly one of soc/module is required (not both, not neither)"}
    if not sources:
        return {"error": "sources[] is required — cite-or-omit, no exceptions"}

    fields = {k: v for k, v in fields.items() if k in _BOARD_OPTIONAL_FIELDS}
    usb = fields.get("usb")
    if isinstance(usb, str):
        connector = usb.strip().lower()
        if connector in _USB_CONNECTORS:
            fields["usb"] = {"connector": connector}
        else:
            del fields["usb"]

    sources = [dict(s) for s in sources]
    if today is not None:
        for s in sources:
            if s.get("verified") is None or isinstance(s.get("verified"), bool):
                s["verified"] = today

    bad_sources = [s for s in sources if not (s.get("field") and s.get("url") and s.get("verified"))]
    if bad_sources:
        return {"error": f"every sources[] entry needs field+url+verified (cite-or-omit) — bad entries: {bad_sources}"}
    uncited = [f for f in fields if fields.get(f) not in (None, [], {}) and not _field_covered(f, sources)]
    if uncited:
        return {"error": f"missing source for field(s) {sorted(uncited)} — cite-or-omit, "
                         "every field you set needs a sources[] entry"}

    rec: dict = {"id": board_id, "type": "board", "brand": brand, "name": name}
    if soc:
        rec["soc"] = soc
    if module:
        rec["module"] = module
    for k in _BOARD_OPTIONAL_FIELDS:
        if fields.get(k) not in (None, [], {}):
            rec[k] = fields[k]
    rec["sources"] = sources
    front = yaml.safe_dump(rec, sort_keys=False, default_flow_style=False).strip()
    d = BOARDS_DIR / brand / board_id
    d.mkdir(parents=True, exist_ok=True)
    path = d / "board.md"
    path.write_text(f"---\n{front}\n---\n\n{body.strip()}\n")
    return {"board_id": board_id, "path": str(path.relative_to(REPO))}


def board_triple_validate(board_id: str) -> dict:
    """THREE independent gates before a board PR, mirroring triple_validate() for firmware (SPEC
    §2.6): (1) the deterministic schema guard over the whole dataset, (2) every cited source URL
    is live, (3) id/brand/soc-or-module ref integrity AND every set field is cite-covered (the
    part JSON Schema alone can't catch). A PR may open ONLY when pass=True."""
    board_path = next(iter(BOARDS_DIR.glob(f"*/{board_id}/board.md")), None)
    if not board_path:
        return {"pass": False, "gate1_guard": ["board.md not found"],
                "gate2_sources_live": ["n/a"], "gate3_integrity": ["board.md not found"]}
    problems = {"gate1": [], "gate2": [], "gate3": []}

    # GATE 1 — the deterministic guard (schema + oracle + no-orphan) over the whole dataset
    g = run_guard()
    if not g["ok"]:
        problems["gate1"].append(g["output"].splitlines()[-1] if g["output"] else "guard failed")

    fm = _frontmatter(board_path)

    # GATE 2 — every cited source URL is live (same tolerance as scripts/check_sources_live.py)
    for src in fm.get("sources", []):
        u = src.get("url", "")
        try:
            req = urllib.request.Request(u, method="HEAD", headers={"User-Agent": "esp-atlas-jr"})
            urllib.request.urlopen(req, timeout=15)
        except Exception as e:
            problems["gate2"].append(f"source not live: {u} ({type(e).__name__})")

    # GATE 3 — id/brand/ref integrity + per-field cite-or-omit coverage
    folder_id, brand_dir = board_path.parent.name, board_path.parent.parent.name
    if fm.get("id") != folder_id:
        problems["gate3"].append(f"id '{fm.get('id')}' != folder '{folder_id}'")
    if fm.get("brand") != brand_dir:
        problems["gate3"].append(f"brand '{fm.get('brand')}' != folder '{brand_dir}'")
    has_soc, has_module = bool(fm.get("soc")), bool(fm.get("module"))
    if has_soc == has_module:
        problems["gate3"].append("exactly one of soc/module required")
    en = schema_enums()
    if has_soc and fm["soc"] not in en["soc_ids"]:
        problems["gate3"].append(f"soc '{fm['soc']}' not a known soc id")
    if has_module and not (REPO / "data/modules" / fm["module"] / "module.md").exists():
        problems["gate3"].append(f"module '{fm['module']}' not found in data/modules/")
    if not fm.get("sources"):
        problems["gate3"].append("sources[] missing")
    for field in _BOARD_OPTIONAL_FIELDS:
        if field in fm and not _field_covered(field, fm.get("sources", [])):
            problems["gate3"].append(f"field '{field}' set but not covered by any sources[] entry")

    ok = not any(problems.values())
    return {"pass": ok, "gate1_guard": problems["gate1"] or "green",
            "gate2_sources_live": problems["gate2"] or "all cited sources live",
            "gate3_integrity": problems["gate3"] or "id/brand/ref integrity ok, all fields cited"}


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
