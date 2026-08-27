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
