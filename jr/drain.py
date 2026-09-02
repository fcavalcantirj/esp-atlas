"""EspAtlas Jr — the deterministic launcher-catalog DRAIN (jr/drain.py).

Replaces agent.py's LLM authoring loop for the Launcher-catalog source (SPEC-espatlas-jr.md
§3b: "the primary firmware source, drained FIRST"). Same plumbing (tools.py: fetch_launcher_
catalog, catalogued_firmware_ids, _catalogued_repos_and_tokens, author_firmware_and_recipes,
run_guard), but the judgment step — decide category/board/chip/capabilities, or skip — is
scorer.score_entry() (jr/scorer.py), a pure function with ZERO LLM calls. agent.py/run.py
(jr-daily) are untouched by this module and never imported here.

Pipeline (run_drain, the orchestrator):
  1. fetch_launcher_catalog() — the ~2,500-entry backlog.
  2. prefilter() — cheap, no-network dedup (already-catalogued repo/owner, name-token port/
     variant match, noise tokens) + download-desc sort. Bounds how many entries ever need a
     GitHub API call — the catalog is too large to `gh api` every entry every run.
  3. score_candidates() — for the top `fetch_limit` prefiltered entries, fetch real GitHub repo
     metadata + README title, then score_entry() decides authored (clean, mappable, real repo)
     or skip (fork/port/noise/no-board-evidence/chip-mismatch/etc — scorer.py's own gates).
  4. rank_juicy() — "juicy" = real popularity: launcher downloads AND real GitHub stars,
     combined by rank-sum (neither signal's raw scale dominates the other).
  5. cap_categories() — at most `max_per_category` per firmware_category, so a batch is
     pentest/mesh/home/... diverse, not 20 near-identical pentest tools.
  6. author_selected() — author each surviving candidate as firmware + recipe (cite-or-omit,
     the SAME author_firmware_and_recipes() the old agent used), immediately guard-checking it;
     a guard-red candidate is rolled back and reported, never left half-written, and never
     poisons the rest of the batch.
  7. A final tools.run_guard() over the whole result — the batch is done only when this is green.

    python drain.py                 # real run: fetch, score, author, guard, print a report
"""
from __future__ import annotations
import re
import sys
from collections import defaultdict
from pathlib import Path

_JR_DIR = Path(__file__).resolve().parent
if str(_JR_DIR) not in sys.path:
    sys.path.insert(0, str(_JR_DIR))
import ledger  # noqa: E402
import tools  # noqa: E402
from scorer import DOWNLOAD_FLOOR, FORK_FLOOR, NOISE_TOKENS, STAR_FLOOR, score_entry  # noqa: E402

MAX_PER_CATEGORY = 4
BATCH_SIZE = 20
# Only the top-N prefiltered (cheap, no-network) candidates ever get a `gh api` fetch — the
# launcher catalog runs to ~2,500 entries and every entry would mean two live GitHub API calls
# (repo + README), which does not fit a bounded batch run. 120 comfortably covers enough clean
# candidates to fill a 20-item, 4-per-category batch even after scorer skips + category capping
# thin some of them out, without risking a timeout on the full catalog.
PREFILTER_LIMIT = 120


def _owner_repo(github_url: str) -> str:
    fn = (github_url or "").strip().rstrip("/").replace("https://github.com/", "").lower()
    return "/".join(fn.split("/")[:2])


def prefilter(entries: list[dict], catalogued_repos: set[str], catalogued_tokens: set[str],
             ledger_state: dict | None = None) -> list[dict]:
    """Cheap, no-network pre-filter over the FULL launcher catalog. Mirrors the dedup checks
    score_entry() itself performs (repo/owner match, name-token port/variant match) plus
    scorer.NOISE_TOKENS (games/emulators/platforms) — run BEFORE any GitHub API call, not
    instead of the real scorer gate later (score_entry() is still the authority; this only
    bounds how many entries reach it). Also skips any entry whose repo is already in
    `ledger_state` (jr/ledger.py) with a BLOCKING status (proposed/rejected) — the repo-level half
    of deliverable 3's dedup gate, so a second drain within the same review window doesn't even
    fetch metadata for something it already proposed or a human already rejected. `ledger_state`
    defaults to None (no ledger check) so this stays backward compatible with callers that never
    pass one. Returns the survivors sorted by launcher `download` popularity, descending."""
    out = []
    for e in entries:
        gh = (e.get("github") or "").strip()
        if not gh.startswith("http"):
            continue
        fn = gh.rstrip("/").replace("https://github.com/", "").lower()
        owner_repo = "/".join(fn.split("/")[:2])
        if not owner_repo or "/" not in owner_repo:
            continue
        if owner_repo in catalogued_repos or fn.split("/")[0] in catalogued_repos:
            continue
        if ledger_state and ledger.is_blocked(ledger_state, repo=owner_repo):
            continue
        # A repo already scored-and-skipped for being below the popularity floor (recorded "seen",
        # SPEC-firmware-floor.md) must not be re-fetched every run — the whole point of the ledger note.
        if ledger_state and ledger.is_seen(ledger_state, repo=owner_repo):
            continue
        name = e.get("name") or ""
        name_tokens = {t for t in re.split(r"[-_\s]", name.lower()) if len(t) >= 4}
        if name_tokens & catalogued_tokens:
            continue
        name_low = f" {name.lower()} "
        if any(t in name_low for t in NOISE_TOKENS):
            continue
        out.append(e)
    out.sort(key=lambda e: e.get("download") or 0, reverse=True)
    return out


def _readme_title(text: str | None) -> str | None:
    """First markdown heading in a README, or None — the citable `readme_title` score_entry's
    board-mapping reads (device_from_text checks name, then description, then this)."""
    for line in (text or "").splitlines():
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip() or None
    return None


def default_fetch_meta(github_url: str) -> dict:
    """The real fetch_meta: repo API fields (tools.fetch_github_repo — full_name, fork, source,
    stars, description, license) plus a readme_title extracted from tools.fetch_github_readme.
    Two live network calls; only ever invoked on the bounded, prefiltered candidate set."""
    meta = tools.fetch_github_repo(github_url)
    if not meta or meta.get("error"):
        return meta
    meta = dict(meta)
    meta["readme_title"] = _readme_title(tools.fetch_github_readme(github_url))
    return meta


def score_candidates(entries: list[dict], catalogued_repos: set[str], catalogued_tokens: set[str],
                     fetch_meta=default_fetch_meta, ledger_state: dict | None = None) -> tuple[list[dict], list[dict]]:
    """Fetch real GitHub metadata for each (already-prefiltered) entry and hand it to
    score_entry() — the ONE judgment call in this whole pipeline, and it's deterministic. Once
    score_entry() derives the candidate's firmware id (only knowable after a live fetch — the id
    is slugged from the repo name), also checks that id (and its repo) against `ledger_state`: an
    id already proposed or rejected is skipped here even if its repo slipped past prefilter's
    cheaper repo-only check (e.g. two different repos that would slug to the same id) —
    deliverable 3's id-level half of the dedup gate. `ledger_state` defaults to None (no ledger
    check). Returns (scored, skipped): `scored` entries carry the authored record plus the
    popularity signals (`download`, `stars`) and a citable `description` for the firmware body;
    `skipped` entries carry {name, github, reason} for reporting."""
    scored, skipped = [], []
    for e in entries:
        gh = (e.get("github") or "").strip()
        meta = fetch_meta(gh)
        if not meta or meta.get("error"):
            skipped.append({"name": e.get("name"), "github": gh,
                            "reason": f"repo_unresolved: {meta.get('error') if meta else 'no metadata'}"})
            continue
        result = score_entry(e, meta, catalogued_repos, catalogued_tokens)
        if result["decision"] != "authored":
            skipped.append({"name": e.get("name"), "github": gh, "reason": result["reason"]})
            continue
        rec = result["record"]
        if ledger_state:
            ledger_record = ledger.lookup(ledger_state, firmware_id=rec["id"], repo=_owner_repo(gh))
            if ledger_record and ledger_record["status"] in ledger.BLOCKING_STATUSES:
                skipped.append({"name": e.get("name"), "github": gh,
                                "reason": f"already_{ledger_record['status']}: '{rec['id']}' is in the proposed ledger"})
                continue
        # Popularity floor (SPEC-firmware-floor.md): author only if the candidate clears ANY of
        # three signals — stars >= STAR_FLOOR OR downloads >= DOWNLOAD_FLOOR OR forks >= FORK_FLOOR.
        # Below ALL THREE is filler: skip it, tagged "below-popularity-floor", carrying id+repo so
        # run_drain can record it "seen" in the ledger (so it isn't re-fetched every run). NEW-authoring only.
        stars = meta.get("stars") or 0
        downloads = e.get("download") or 0
        forks = meta.get("forks") or 0
        if stars < STAR_FLOOR and downloads < DOWNLOAD_FLOOR and forks < FORK_FLOOR:
            skipped.append({"name": e.get("name"), "github": gh, "reason": "below-popularity-floor",
                            "firmware_id": rec["id"], "repo": _owner_repo(gh),
                            "stars": stars, "download": downloads, "forks": forks})
            continue
        scored.append({
            "record": rec,
            "download": e.get("download") or 0,
            "stars": meta.get("stars") or 0,
            "forks": meta.get("forks") or 0,
            "description": (meta.get("description") or e.get("description") or "").strip(),
        })
    return scored, skipped


def rank_juicy(scored: list[dict]) -> list[dict]:
    """"Juicy" = real popularity: launcher downloads AND real GitHub stars (SPEC §3b: real
    stars, never the launcher's own near-zero like-count) — a genuine AND, not an OR. Combined
    by the PRODUCT of each signal's reverse rank position (not raw value: downloads run into the
    tens of thousands while stars rarely pass a few thousand, so summing/multiplying raw numbers
    would let downloads alone decide every time). Reverse-rank product means an entry maxed on
    exactly one axis and near-zero on the other scores no better than a middling entry that's
    decent on both — a single-axis outlier isn't allowed to buy its way to the top; it has to
    actually be popular by both measures. No invented weighting constant, just rank position."""
    if not scored:
        return []
    n = len(scored)
    by_download = sorted(scored, key=lambda s: s["download"], reverse=True)
    dl_rank = {id(s): i for i, s in enumerate(by_download)}
    by_stars = sorted(scored, key=lambda s: s["stars"], reverse=True)
    star_rank = {id(s): i for i, s in enumerate(by_stars)}
    return sorted(scored, key=lambda s: (n - dl_rank[id(s)]) * (n - star_rank[id(s)]), reverse=True)


def cap_categories(ranked: list[dict], max_per_category: int = MAX_PER_CATEGORY,
                   batch_size: int = BATCH_SIZE) -> tuple[list[dict], list[dict]]:
    """Greedily fill the batch (already juicy-ranked, most popular first) up to `batch_size`,
    skipping any entry whose category already hit `max_per_category` — so the batch spreads
    across pentest/mesh/home/... instead of being N near-identical entries in one category.
    Returns (selected, dropped_for_cap)."""
    counts: dict[str, int] = defaultdict(int)
    selected, dropped = [], []
    for s in ranked:
        if len(selected) >= batch_size:
            dropped.append(s)
            continue
        cat = s["record"]["category"]
        if counts[cat] >= max_per_category:
            dropped.append(s)
            continue
        selected.append(s)
        counts[cat] += 1
    return selected, dropped


def _cleanup(firmware_id: str) -> None:
    """Remove a rolled-back candidate's firmware dir, recipe dir(s), and coverage run-case —
    mirrors run.py's own _cleanup/remove_run_case pattern for a rejected batch member."""
    import shutil
    shutil.rmtree(tools.FIRMWARE_DIR / firmware_id, ignore_errors=True)
    for rdir in (tools.REPO / "data/recipes").glob(f"*__{firmware_id}"):
        shutil.rmtree(rdir, ignore_errors=True)
    tools.remove_run_case(firmware_id)


def author_selected(selected: list[dict], existing_ids: set[str] | None = None,
                    today: str | None = None) -> tuple[list[str], list[dict]]:
    """Author each selected candidate as firmware + recipe via the SAME tools.
    author_firmware_and_recipes() the old LLM loop used, then immediately run_guard() it — a
    record that reds the guard is rolled back (never left half-written) and reported with why,
    and never poisons the rest of the batch. `existing_ids` seeds the in-batch id-dedup set
    (default: the real catalogued_firmware_ids()) so two candidates that would slug to the same
    firmware_id, or a candidate matching something already in the atlas, can't collide. Threads
    each candidate's popularity (stars from repo_meta, downloads from the launcher entry) and
    `today` (the run date; injectable for deterministic tests) into authoring so a dated
    `popularity` snapshot is persisted on every authored firmware (SPEC-firmware-floor.md).
    Returns (authored_ids, dropped: [{id, reason}])."""
    existing_ids = set(tools.catalogued_firmware_ids()) if existing_ids is None else set(existing_ids)
    authored: list[str] = []
    dropped: list[dict] = []
    for s in selected:
        rec = s["record"]
        fid = rec["id"]
        if fid in existing_ids:
            dropped.append({"id": fid, "reason": f"id_already_catalogued: '{fid}' already exists"})
            continue
        body = s.get("description") or f"{rec['name']} — {rec['category']} firmware for the {rec['board']}."
        result = tools.author_firmware_and_recipes(
            firmware_id=fid, name=rec["name"], url=rec["url"], category=rec["category"],
            boards=[rec["board"]], body=body, capabilities=rec.get("capabilities"),
            maintainer=rec.get("maintainer"),
            stars=s.get("stars"), downloads=s.get("download"), forks=s.get("forks"), today=today,
        )
        if "error" in result:
            dropped.append({"id": fid, "reason": f"author_error: {result['error']}"})
            continue
        guard = tools.run_guard()
        if not guard["ok"]:
            _cleanup(fid)
            tail = guard["output"].splitlines()[-1] if guard["output"] else "guard failed"
            dropped.append({"id": fid, "reason": f"guard_red: {tail}"})
            continue
        existing_ids.add(fid)
        authored.append(fid)
    return authored, dropped


def run_drain(fetch_limit: int = PREFILTER_LIMIT, batch_size: int = BATCH_SIZE,
             max_per_category: int = MAX_PER_CATEGORY, fetch_catalog=tools.fetch_launcher_catalog,
             fetch_meta=default_fetch_meta, ledger_path=ledger.DEFAULT_LEDGER_PATH,
             today: str | None = None) -> dict:
    """The full drain, end to end. Additive-only: writes new data/firmware/<id>/ +
    data/recipes/<board>__<id>/ dirs (plus their coverage run-case) and never touches jr-daily
    (agent.py/run.py) or scorer.py's public behavior. Loads jr/ledger.py's proposed-ledger
    (`ledger_path`, injectable for tests) once and threads it through prefilter/score_candidates
    so a candidate already proposed or rejected in an earlier run is skipped before it's ever
    re-authored (deliverable 3) — catalogued-in-main dedup (catalogued_repos/catalogued_tokens)
    continues to cover merged the same way it always has."""
    entries = fetch_catalog()
    catalogued_repos, catalogued_tokens = tools._catalogued_repos_and_tokens()
    ledger_state = ledger.load_ledger(ledger_path)
    prefiltered = prefilter(entries, catalogued_repos, catalogued_tokens, ledger_state=ledger_state)[:fetch_limit]
    scored, skipped = score_candidates(prefiltered, catalogued_repos, catalogued_tokens,
                                       fetch_meta=fetch_meta, ledger_state=ledger_state)
    # Candidates skipped for being below BOTH popularity floors (SPEC-firmware-floor.md): record
    # each "seen" in the ledger so the next run's prefilter skips it before any fetch, and report them.
    skipped_popularity = [s for s in skipped if s.get("reason") == "below-popularity-floor"]
    for s in skipped_popularity:
        ledger.record_seen(s["firmware_id"], s["repo"], path=ledger_path)
    ranked = rank_juicy(scored)
    selected, dropped_cap = cap_categories(ranked, max_per_category=max_per_category, batch_size=batch_size)
    authored, dropped_guard = author_selected(selected, today=today)
    guard = tools.run_guard()
    return {
        "fetched": len(entries),
        "prefiltered": len(prefiltered),
        "scored_clean": len(scored),
        "skipped_scoring": len(skipped),
        "skipped_popularity": skipped_popularity,
        "selected": len(selected),
        "dropped_cap": len(dropped_cap),
        "authored": authored,
        "dropped_guard": dropped_guard,
        "guard": guard,
    }


if __name__ == "__main__":
    report = run_drain()
    print(f"fetched={report['fetched']} prefiltered={report['prefiltered']} "
         f"scored_clean={report['scored_clean']} skipped_scoring={report['skipped_scoring']} "
         f"selected={report['selected']} dropped_cap={report['dropped_cap']}")
    print(f"authored ({len(report['authored'])}): {report['authored']}")
    for d in report["dropped_guard"]:
        print(f"  dropped: {d['id']} — {d['reason']}")
    pop = report.get("skipped_popularity", [])
    print(f"skipped below-popularity-floor ({len(pop)}):")
    for s in pop:
        print(f"  {s['firmware_id']} — stars={s['stars']} downloads={s['download']}")
    print(f"guard ok={report['guard']['ok']}")
