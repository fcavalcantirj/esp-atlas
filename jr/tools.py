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


def uncatalogued_with_code(limit: int = 5) -> list[dict]:
    """Launcher-catalog entries NOT yet in the atlas that pass the with-code gate (resolve to a
    real GitHub repo). Ranked by `download` as a popularity proxy (real GitHub-star ranking is a
    follow-up — the API's own like-count must never be used, SPEC §3b). Returns compact dicts."""
    have = catalogued_firmware_ids()
    out = []
    for e in fetch_launcher_catalog():
        gh = (e.get("github") or "").strip()
        if not gh or not gh.startswith("http"):
            continue                                    # with-code gate: must resolve to a repo
        slug = gh.rstrip("/").split("/")[-1].lower()
        if slug in have or e.get("name", "").lower() in have:
            continue                                    # dedup vs catalogued
        out.append({
            "name": e.get("name"), "github": gh, "category": e.get("category"),
            "author": e.get("author"), "download": e.get("download", 0),
            "description": (e.get("description") or "")[:200],
        })
    out.sort(key=lambda x: x.get("download") or 0, reverse=True)
    return out[:limit]


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


def open_pr(firmware_id: str, title: str, body: str, base: str = "main") -> dict:
    """Open a cited PR for an authored record on branch `jr/firmware-<id>` (never writes `main`;
    SPEC §2.3 bot-proposes-humans-dispose). Assumes run_guard() passed. Returns {"ok","pr_url"}."""
    branch = f"jr/firmware-{firmware_id}"
    rel = f"data/firmware/{firmware_id}/firmware.md"
    def git(*a): return subprocess.run(["git", *a], cwd=REPO, capture_output=True, text=True)
    git("checkout", "-B", branch)
    git("add", rel)
    c = git("commit", "-m", title)
    git("push", "-u", "origin", branch, "--force-with-lease")
    pr = subprocess.run(
        ["gh", "pr", "create", "--base", base, "--head", branch, "--title", title, "--body", body],
        cwd=REPO, capture_output=True, text=True,
    )
    git("checkout", "main")  # leave main clean; the record lives on the branch/PR
    return {"ok": pr.returncode == 0, "pr_url": pr.stdout.strip(),
            "error": (pr.stderr or c.stderr).strip()[:300]}


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
