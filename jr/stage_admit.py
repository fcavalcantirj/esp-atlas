"""EspAtlas Jr — Track A stage: admit new firmware from the launcher catalog (jr/stage_admit.py).

Phase 3: the deterministic admission gate over tools.fetch_launcher_catalog() scored by
jr/scorer.score_entry — no LLM anywhere. One run admits up to `budget` firmware records;
every skip is recorded in memory with a TTL so the next run does not re-fetch it.

NOT registered in tick.STAGES until the Phase 6 cutover: driven by hand
(`python3 jr/tick.py --track A --budget N`), like Track B was. Dry-run scores and reports,
writes nothing (memory untouched).

An admission writes firmware.md AND its first recipe (`<board>__<id>`, the board the scorer
found named in the repo itself, cited to the repo page): scripts/validate.py rejects a firmware
no recipe references (orphan), and the tick's guard would otherwise discard the whole
worktree. Track B widens the recipes from the build files, in the same tick (admit runs first).
"""
from __future__ import annotations

import json
from pathlib import Path

import re

import board_alias
import derive
import memory
import scorer
import tools
import writers
from budget import BudgetExceeded
from esp_atlas_core.floor import clears_popularity_floor

DEFAULT_BUDGET = 3
MIN_CALLS_TO_CONTINUE = 5   # a repo-meta fetch costs >= 1 call; stop before stranding one

# --- submissions: GitHub issues labelled `submission` (the site's /submit box and the issue form
# both create them). Scored FIRST, before the launcher catalog; the verdict is commented on the
# issue and the issue is closed. The site never writes catalog data: a submission is a candidate.
SUBMISSION_LABEL = "submission"
DEFAULT_REPO_SLUG = "fcavalcantirj/esp-atlas"
SUBMISSION_DERIVE_CALLS = 30      # derive() cap when the submitter named no catalogued board
_GITHUB_URL = re.compile(r"https?://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?(?=[\s/)>\]\"']|$)", re.I)
_BOARDS_LINE = re.compile(r"(?:^|\n)\s*(?:###\s*Boards|Boards)\s*:?\s*\n?\s*([^\n]+)", re.I)

REASON_HELP = {
    "below_floor": "the catalog's floor is 25 stars or 25 forks (SPEC-firmware-floor.md)",
    "fork_of_catalogued": "forks of a catalogued firmware are listed under the original",
    "fork_of_uncatalogued": "submit the original repository instead",
    "already_catalogued": "this repository is already in the catalog",
    "no_board_evidence": "name a catalogued board in the Boards line (esp-atlas.com/boards), or ship release assets / a platformio.ini that name one",
    "archived": "archived repositories are not catalogued",
    "repo_unresolved": "the repository could not be read (private, renamed or missing)",
    "invalid": "the issue must contain a github.com/owner/repo URL",
}


def parse_submission(body: str | None) -> dict | None:
    """{github, hint} from an issue body — the first github.com/owner/repo URL and, when present,
    the text after a `Boards` heading or `Boards:` line (the issue form renders `### Boards`)."""
    m = _GITHUB_URL.search(body or "")
    if not m:
        return None
    hint = None
    b = _BOARDS_LINE.search(body or "")
    if b:
        text = b.group(1).strip()
        if text and text.lower() not in ("_no response_", "none", "-"):
            hint = text
    return {"github": f"https://github.com/{m.group(1)}/{m.group(2)}", "hint": hint}


def _submission_entries(ctx, slug: str) -> list[dict]:
    """Open `submission` issues as launcher-shaped entries (one counted gh call). Malformed
    bodies come back with github=None so the caller can answer `invalid`."""
    try:
        p = ctx.gh("api", f"repos/{slug}/issues?labels={SUBMISSION_LABEL}&state=open&per_page=50")
    except BudgetExceeded:
        raise
    except Exception:  # noqa: BLE001 — an unreadable listing means "no submissions this tick", never a dead stage
        return []
    if getattr(p, "returncode", 1) != 0:
        return []
    try:
        issues = json.loads(getattr(p, "stdout", "") or "[]")
    except json.JSONDecodeError:
        return []
    out = []
    for it in issues if isinstance(issues, list) else []:
        if not isinstance(it, dict) or it.get("pull_request"):
            continue
        parsed = parse_submission(it.get("body")) or parse_submission(it.get("title"))
        out.append({"name": (parsed or {}).get("github", "").rstrip("/").split("/")[-1] or (it.get("title") or ""),
                    "github": (parsed or {}).get("github"), "hint": (parsed or {}).get("hint"),
                    "description": None, "category": None, "download": None,
                    "issue": it.get("number"), "issue_url": it.get("html_url"), "source": "submission"})
    return sorted(out, key=lambda e: e["issue"] or 0)


def _resolve_hint(hint: str | None, atlas: dict) -> tuple[str | None, str | None]:
    """(board_id, the piece that named it): the first catalogued board a submitter's Boards line
    names, via jr/board_alias (compact / containment / cited alias — deterministic, never fuzzy)."""
    for piece in re.split(r"[,;/\n]+", hint or ""):
        piece = piece.strip()
        if not piece:
            continue
        r = board_alias.resolve_token(piece, boards=atlas)
        if r and r.get("atlas_id"):
            return r["atlas_id"], piece
    return None, None


def _derived_board(ctx, owner_repo: str, atlas: dict, raw=None) -> tuple[str | None, dict | None]:
    """(board_id, the signal that named it) from the repo's own build files (release assets,
    platformio.ini, CI, IDF targets) — the same reader Track B uses, capped at SUBMISSION_DERIVE_CALLS."""
    api = lambda path: json.loads(ctx.gh("api", path).stdout)  # noqa: E731 — counted through ctx.gh
    raw = ctx.budget.wrap(raw or derive.default_raw, "raw")
    d = derive.derive(owner_repo, api=api, raw=raw, max_calls=SUBMISSION_DERIVE_CALLS,
                      today=ctx.now.strftime("%Y-%m-%d"))
    res = derive.resolve(d, boards=atlas)
    best = sorted(res["boards"].items(), key=lambda kv: (kv[1][0]["rank"], kv[0]))
    if not best:
        return None, None
    return best[0][0], dict(best[0][1][0])


def _answer(ctx, slug: str, issue: int, text: str, close: bool = True) -> None:
    """Comment the verdict on the submission issue and close it. Dry-run: nothing."""
    if ctx.dry_run or not issue:
        return
    ctx.gh("api", "-X", "POST", f"repos/{slug}/issues/{issue}/comments", "-f", f"body={text}")
    if close:
        ctx.gh("api", "-X", "PATCH", f"repos/{slug}/issues/{issue}", "-f", "state=closed")


def _verdict_text(reason: str | None, admitted: bool, needs_human: bool, page_id: str | None = None) -> str:
    if admitted:
        tail = (" A human reviews and merges it (flagged needs-human)." if needs_human
                else " CI must be green before it merges; a human can still veto.")
        return ("**Admitted.** EspAtlas Jr is opening a pull request with the firmware record and its "
                f"first cited recipe{' (`' + page_id + '`)' if page_id else ''}." + tail +
                " Track B then maps every board the repo's own build files name.")
    key = (reason or "").split(":")[0]
    help_ = REASON_HELP.get(key, "")
    return (f"**Not admitted** — `{reason}`." + (f" {help_}." if help_ else "") +
            " Rules are deterministic (no AI): esp-atlas.com/how-we-work. Fix the cause and open a new submission.")

# Skip reason -> memory TTL (days). The floor/archived/unresolved gates have their own
# constants in jr/memory.py; every other skip is a "scored but skipped" note re-checked
# after SEEN_TTL_DAYS.
REJECT_TTLS = {
    "repo_unresolved": memory.UNRESOLVED_REJECT_DAYS,
    "archived": memory.ARCHIVED_REJECT_DAYS,
    "below_floor": memory.FLOOR_REJECT_DAYS,
}


def _meta_from_api(doc: dict) -> dict:
    """Map a `gh api repos/<owner>/<repo>` payload onto tools.fetch_github_repo's dict shape
    (the shape jr/scorer.score_entry reads). Same keys, same meanings."""
    source, parent = doc.get("source") or {}, doc.get("parent") or {}
    lic = doc.get("license") or {}
    return {
        "full_name": doc.get("full_name"), "description": doc.get("description"),
        "license": lic.get("spdx_id"), "topics": doc.get("topics", []),
        "homepage": doc.get("homepage"), "default_branch": doc.get("default_branch"),
        "stars": doc.get("stargazers_count"), "archived": doc.get("archived"),
        "forks": doc.get("forks_count"),
        "id": doc.get("id"), "fork": doc.get("fork"),
        "source_full_name": source.get("full_name"),
        "source_stars": source.get("stargazers_count"),
        "parent_full_name": parent.get("full_name"),
        "pushed_at": doc.get("pushed_at"), "language": doc.get("language"),
    }


def _fetch_meta(gh, owner_repo: str):
    """One charged `gh api repos/<owner>/<repo>`; (meta, fetched). Unparseable owner/repo or
    any gh failure maps to {"error": ...} without raising, so the scorer's repo_unresolved
    path (7-day TTL) covers renames, outages and 404s alike."""
    parts = (owner_repo or "").split("/")
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return {"error": f"unparseable repo {owner_repo!r}"}, False
    try:
        p = gh("api", f"repos/{parts[0]}/{parts[1]}")
    except BudgetExceeded:
        raise
    except Exception as e:  # noqa: BLE001 — transient failure reads as unresolved, retried in 7 d
        return {"error": f"{type(e).__name__}: {str(e)[:120]}"}, False
    if getattr(p, "returncode", 1) != 0:
        return {"error": (getattr(p, "stderr", "") or "").strip()[:200]}, False
    try:
        return _meta_from_api(json.loads(p.stdout or "{}")), True
    except (json.JSONDecodeError, TypeError, AttributeError) as e:
        return {"error": f"unparseable api response: {e}"}, False


def _catalogued_ids(led: dict, now) -> dict:
    """{repo_id: firmware_id} over every memory record that has not expired — the rename-proof
    identity net behind the scorer's duplicate_of rule (a repo the catalog knows under an old
    path is still caught after a rename)."""
    out = {}
    for rid, fid in (led.get("by_repo_id") or {}).items():
        rec = (led.get("by_id") or {}).get(fid)
        if rec is not None and not memory.is_expired(rec, now):
            out[str(rid)] = fid
    return out


def run(ctx, budget: int = DEFAULT_BUDGET, raw=None, call_share: float = 1.0):
    """The Track A stage for jr/tick.py: returns a tick.StageResult. `raw` (tests) replaces
    derive.default_raw for the build-file reads a submission without a board hint triggers.
    `call_share` is the fraction of the tick's REMAINING gh calls this stage may spend scanning
    the launcher backlog (the hourly path passes A/(A+B)): the 22:00 UTC tick spent all 146
    calls on admit and boardmap got none. Submissions are exempt from the cap (they are rare
    and a person is waiting); a launcher candidate is skipped for this tick when the cap is hit."""
    import tick
    today = ctx.now.strftime("%Y-%m-%d")
    calls_at_start = ctx.budget.calls
    call_cap = int(ctx.budget.remaining_calls() * max(0.0, min(1.0, call_share)))
    fetch_catalog = ctx.budget.wrap(tools.fetch_launcher_catalog, "https")
    try:
        catalog = fetch_catalog()
    except BudgetExceeded as e:
        return tick.StageResult("admit", paths=[], summary=f"stopped: {e}", admitted=0,
                                rejects={})
    except Exception as e:  # noqa: BLE001 — a blind stage flags a human, writes nothing
        return tick.StageResult("admit", paths=[], summary=f"catalog unreadable: {type(e).__name__}: {str(e)[:120]}",
                                admitted=0, rejects={}, needs_human=True)
    if not isinstance(catalog, list):
        return tick.StageResult("admit", paths=[], summary="catalog unreadable: not a list",
                                admitted=0, rejects={}, needs_human=True)

    led = memory.load(ctx.ledger_path)   # read-only here; writes below honor dry-run
    cat_repos, cat_toks = tools._catalogued_repos_and_tokens(ctx.root / "data" / "firmware")
    cat_ids = _catalogued_ids(led, ctx.now)
    paths, lines, admitted, rejects, needs_human = [], [], 0, {}, False
    would_admit, decided, items = 0, 0, []

    def reject(key):
        rejects[key] = rejects.get(key, 0) + 1

    launcher_skips: dict = {}      # launcher entries are skipped by the hundred: one aggregate line, never one per entry

    def skip_reject(fid, owner_repo, reason, repo_id, issue=None):
        """Record the rejection (memory, counts). Returns a report line for a submission (rare and
        meaningful — the submitter reads it), or None for a launcher entry (aggregated below)."""
        key = reason.split(":")[0]
        reject(key)
        if not ctx.dry_run:
            memory.record_rejected(fid, owner_repo, reason,
                                   ttl_days=REJECT_TTLS.get(key, memory.SEEN_TTL_DAYS),
                                   repo_id=repo_id, path=ctx.ledger_path, now=ctx.now)
        if issue:
            return f"{fid}: skip {key} (submission #{issue})"
        launcher_skips[key] = launcher_skips.get(key, 0) + 1
        return None

    def note(line):
        if line:
            lines.append(line)

    # Submissions first (one counted call to list them), then the launcher catalog.
    slug = (ctx.env or {}).get("JR_REPO_SLUG") or DEFAULT_REPO_SLUG
    submissions = _submission_entries(ctx, slug)
    atlas = board_alias.atlas_boards(ctx.root) if submissions else {}
    entries = [dict(e) for e in submissions] + sorted(catalog, key=lambda e: ((e.get("name") or ""), (e.get("github") or "")))

    for entry in entries:
        issue = entry.get("issue")
        if issue and not entry.get("github"):
            reject("invalid")
            _answer(ctx, slug, issue, _verdict_text("invalid: no github.com/owner/repo URL in the issue", False, False))
            lines.append(f"submission #{issue}: invalid")
            continue
        if admitted + would_admit >= budget:
            lines.append(f"stopped: budget reached ({admitted + would_admit} admitted)")
            break
        github = (entry.get("github") or "").strip()
        owner_repo = scorer._owner_repo(github)
        if memory.is_blocked(led, repo=owner_repo, now=ctx.now) or memory.is_seen(led, repo=owner_repo, now=ctx.now):
            decided += 1
            if issue:
                prior = memory.lookup(led, repo=owner_repo) or {}
                _answer(ctx, slug, issue, _verdict_text(f"already_decided: {prior.get('reason') or prior.get('status') or 'seen'}"
                                                        + (f" (until {prior['expires']})" if prior.get("expires") else ""), False, False))
                lines.append(f"submission #{issue}: already decided")
            continue
        if ctx.budget.remaining_calls() < MIN_CALLS_TO_CONTINUE:
            lines.append(f"stopped before {owner_repo}: tick budget low "
                         f"({ctx.budget.remaining_calls()} calls left)")
            break
        if not issue and ctx.budget.calls - calls_at_start >= call_cap:
            lines.append(f"stopped before {owner_repo}: admit's call share used ({call_cap} of the tick's calls); the rest is Track B's")
            break
        try:
            meta, _fetched = _fetch_meta(ctx.gh, owner_repo)
        except BudgetExceeded as e:
            lines.append(f"stopped during {owner_repo}: {e}")   # meta fetch is read-only: nothing half-written
            break
        repo_id = meta.get("id")
        if repo_id is not None and (memory.is_blocked(led, repo_id=repo_id, now=ctx.now)
                                    or memory.is_seen(led, repo_id=repo_id, now=ctx.now)):
            decided += 1
            continue
        fid = scorer._slug(scorer._repo_name_from_url(github)) or owner_repo or "(unnamed entry)"   # the report names every skip
        # Popularity floor (SPEC-firmware-floor.md, via esp_atlas_core.floor — never re-typed):
        # below stars AND forks is filler, rejected for FLOOR_REJECT_DAYS.
        if meta.get("error"):
            note(skip_reject(fid, owner_repo, f"repo_unresolved: {meta['error'][:80]}", None, issue=issue))
            if issue:
                _answer(ctx, slug, issue, _verdict_text(f"repo_unresolved: {meta['error'][:80]}", False, False))
            continue
        if not clears_popularity_floor(meta.get("stars"), meta.get("forks")):
            reason = f"below_floor: {meta.get('stars')} stars / {meta.get('forks')} forks"
            note(skip_reject(fid, owner_repo, reason, repo_id, issue=issue))
            if issue:
                _answer(ctx, slug, issue, _verdict_text(reason, False, False))
            continue
        hint_board, evidence = None, None      # evidence: the signal that names the board, for the first recipe's citation
        if issue:
            hint_board, piece = _resolve_hint(entry.get("hint"), atlas)
            if hint_board:
                evidence = {"rank": 0, "kind": "submission", "token": piece,
                            "url": entry.get("issue_url") or f"https://github.com/{slug}/issues/{issue}",
                            "soc": None, "line": None, "extra": {"issue": issue}}
            else:
                if ctx.budget.remaining_calls() < SUBMISSION_DERIVE_CALLS + MIN_CALLS_TO_CONTINUE:
                    lines.append(f"submission #{issue}: deferred, tick budget low for a derive")
                    continue
                try:
                    hint_board, evidence = _derived_board(ctx, owner_repo, atlas, raw=raw)
                except BudgetExceeded as e:
                    lines.append(f"stopped during submission #{issue}: {e}")
                    break
        res = scorer.score_entry(entry, meta, cat_repos, cat_toks, cat_ids, board_hint=hint_board)
        if res["decision"] == "skip":
            note(skip_reject(fid, owner_repo, res["reason"], repo_id, issue=issue))
            if issue:
                _answer(ctx, slug, issue, _verdict_text(res["reason"], False, False))
            continue
        rec = res["record"]
        out_id = rec["id"]
        # Worktree check: the scorer derives the chip from this clone's boards; the tick writes
        # into a worktree. Refuse to write when the worktree disagrees (same bug class as the
        # Track B resolver reading the wrong tree).
        if tools.board_soc(rec["board"], repo=ctx.root) != rec["chip"]:
            note(skip_reject(out_id, owner_repo,
                                     f"chip_family_mismatch: worktree disagrees on board '{rec['board']}'",
                                     repo_id, issue=issue))
            continue
        fmd = ctx.root / "data" / "firmware" / out_id / "firmware.md"
        if fmd.exists():
            lines.append(f"{out_id}: record exists, nothing written")
            if issue:
                _answer(ctx, slug, issue, _verdict_text(f"already_catalogued: {out_id}", False, False))
            continue
        if res.get("needs_human"):
            needs_human = True
        if ctx.dry_run:
            lines.append(f"{out_id}: would admit{' (needs_human)' if res.get('needs_human') else ''}"
                         + (f" (submission #{issue})" if issue else ""))
            would_admit += 1
            continue
        repo_url = rec["url"]
        text = writers.render_firmware(rec, [{"field": "*", "url": repo_url},
                                             {"field": "popularity", "url": repo_url}],
                                       today, needs_human=bool(res.get("needs_human")),
                                       popularity={"stars": meta.get("stars"), "forks": meta.get("forks")})
        fmd.parent.mkdir(parents=True, exist_ok=True)
        fmd.write_text(text, encoding="utf-8")
        paths.append(str(fmd.relative_to(ctx.root)))
        # The first recipe, in the same write: scripts/validate.py rejects a firmware no recipe
        # references (orphan), and the tick's guard would then discard the WHOLE worktree —
        # boardmap's recipes included. The scorer found this board named in the repo's own
        # name/description/README title, so the repo page is the citation; Track B widens it
        # from the build files later in the same tick (admit runs before boardmap).
        rdir = ctx.root / "data" / "recipes" / f"{rec['board']}__{out_id}"
        if not (rdir / "recipe.md").exists():
            if evidence is not None and rec["board"] == hint_board:
                signal = evidence                 # the submission issue, or the build-file signal, that named the board
            else:
                board_name = board_alias.atlas_boards(ctx.root).get(rec["board"], {}).get("name") or rec["board"]
                signal = {"rank": 0, "kind": "repo", "token": board_name, "url": repo_url, "soc": None,
                          "line": None, "extra": {}}
            rdir.mkdir(parents=True, exist_ok=True)
            (rdir / "recipe.md").write_text(
                writers.render_recipe(f"{rec['board']}__{out_id}", rec["board"], out_id, rec["chip"],
                                      repo_url, [signal], today), encoding="utf-8")
            paths.append(str(rdir.relative_to(ctx.root)))
        memory.record_proposed(out_id, owner_repo, repo_id=repo_id, evidence_url=repo_url,
                               path=ctx.ledger_path, now=ctx.now)
        if evidence is not None and rec["board"] == hint_board:
            ev = (f"named by the submitter in issue #{issue}" if evidence.get("kind") == "submission"
                  else f"{evidence.get('kind')} signal `{evidence.get('token')}` ({evidence.get('url')})")
        else:
            ev = "named in the repository name/description"
        items.append({"kind": "firmware", "id": out_id, "name": rec["name"], "url": repo_url,
                      "stars": meta.get("stars"), "forks": meta.get("forks"), "fork": bool(meta.get("fork")),
                      "archived": bool(meta.get("archived")), "license": meta.get("license"),
                      "board": rec["board"], "chip": rec["chip"], "recipe": f"{rec['board']}__{out_id}",
                      "evidence": ev, "needs_human": bool(res.get("needs_human")), "submission": issue})
        admitted += 1
        lines.append(f"{out_id}: +record{' (needs_human)' if res.get('needs_human') else ''}"
                     + (f" (submission #{issue})" if issue else ""))
        if issue:
            _answer(ctx, slug, issue, _verdict_text(None, True, bool(res.get("needs_human")), f"{rec['board']}__{out_id}"))
    if launcher_skips:
        total = sum(launcher_skips.values())
        lines.append(f"skipped {total} launcher entries: " + ", ".join(f"{k} {v}" for k, v in sorted(launcher_skips.items(), key=lambda kv: (-kv[1], kv[0]))))
    summary = "; ".join(lines) if lines else "no candidates"
    if decided and lines:
        summary += f" ({decided} already decided, skipped)"
    elif decided:
        summary = f"{decided} already decided, skipped"
    return tick.StageResult("admit", paths=paths, summary=summary, admitted=admitted,
                            rejects=rejects, needs_human=needs_human, items=items)
