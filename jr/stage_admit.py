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
import random
from datetime import datetime
from pathlib import Path

import re

import board_alias
import derive
import device_evidence
import launcher_resolve
import memory
import pending_prs
import review_memory
import scorer
import tools
import writers
from budget import BudgetExceeded
from esp_atlas_core.floor import clears_popularity_floor, is_editorial_home

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
    "below_floor": "the catalog's floor is 25 stars or 25 forks, or an independent editorial "
                   "homepage (SPEC-firmware-floor.md)",
    "fork_of_catalogued": "forks of a catalogued firmware are listed under the original",
    "fork_of_uncatalogued": "submit the original repository instead",
    "already_catalogued": "this repository is already in the catalog",
    "no_board_evidence": "name a catalogued board in the Boards line (esp-atlas.com/boards), or ship release assets / a platformio.ini that name one",
    "archived": "archived repositories are not catalogued",
    device_evidence.NOT_DEVICE_FIRMWARE: "a firmware must build for an ESP: an espressif32 platformio.ini, an ESP-IDF "
                                         "project, an Arduino sketch or a release .bin (companion apps and servers are not firmware)",
    device_evidence.NEEDS_REVIEW_TARGET: "the repository builds something but never states that it targets an ESP chip, so the "
                                         "owner reviews it by hand. To be admitted automatically, state the target: an espressif32 "
                                         "platformio.ini, CONFIG_IDF_TARGET in sdkconfig.defaults, a sketch.yaml "
                                         "`default_fqbn: esp32:esp32:<board>`, or a release .bin that is an ESP image",
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


def _device_evidence(ctx, owner_repo: str, ref: str | None, raw=None) -> dict:
    """jr/device_evidence.check through the tick's counted gh and raw reader."""
    return device_evidence.check(owner_repo, api=device_evidence.gh_api(ctx.gh), raw=ctx.budget.wrap(raw or derive.default_raw, "raw"),
                                 fetch=ctx.budget.wrap(device_evidence.default_fetch, "raw"), ref=ref)


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
    launcher_resolve.NO_SOURCE_REPO: memory.UNRESOLVED_REJECT_DAYS,
    launcher_resolve.OWNER_MISSING: memory.ARCHIVED_REJECT_DAYS,   # the author is no GitHub login: a week changes nothing
    "archived": memory.ARCHIVED_REJECT_DAYS,
    "below_floor": memory.FLOOR_REJECT_DAYS,
    device_evidence.NOT_DEVICE_FIRMWARE: memory.NO_BUILD_SIGNAL_DAYS,
    device_evidence.NEEDS_REVIEW_TARGET: memory.NO_BUILD_SIGNAL_DAYS,
    device_evidence.EVIDENCE_UNREADABLE: memory.UNRESOLVED_REJECT_DAYS,
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


def _fetch_readme(gh, owner_repo: str) -> str:
    """The README text (one charged `gh api repos/<o>/<r>/readme`), '' when there is none or it cannot
    be read: the evidence gate then judges on the description alone, never on a guess."""
    import base64
    try:
        p = gh("api", f"repos/{owner_repo}/readme")
    except BudgetExceeded:
        raise
    except Exception:  # noqa: BLE001
        return ""
    if getattr(p, "returncode", 1) != 0:
        return ""
    try:
        return base64.b64decode(json.loads(p.stdout or "{}").get("content") or "").decode("utf-8", "ignore")
    except (ValueError, AttributeError):
        return ""


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


REPO_NOTE_PREFIX = memory.REPO_NOTE_PREFIX


def repo_note_key(owner_repo: str) -> str:
    """The ledger key that remembers a decision about `owner_repo` when the decision's own record
    cannot be written: memory._write refuses a rejection over a `merged` record (the renamed-upstream
    duplicate_of case, pr3y/bruce -> brucedevices/firmware). Like `launcher-<fid>`, it is a key of its
    own, never a firmware id, and it carries no repo_id, so the by_repo_id identity view is untouched."""
    return REPO_NOTE_PREFIX + owner_repo.lower()


def _downloads(entry: dict) -> int:
    try:
        return max(0, int(str(entry.get("download") or 0).strip() or 0))
    except ValueError:
        return 0


def _interleave(ordered: list, seed: str) -> list:
    """Even slots: `ordered` (the download order). Odd slots: the same items shuffled by `seed`.
    Each item appears once. The seed is the tick's UTC hour, so an hour replays the same order and the
    next hour explores other repos: a decision that fails to stick can never hold every paid slot."""
    shuffled = list(ordered)
    random.Random(f"admit-queue:{seed}").shuffle(shuffled)
    out, taken, i, j = [], set(), 0, 0
    while len(out) < len(ordered):
        for lane, at in ((ordered, "i"), (shuffled, "j")):
            k = i if at == "i" else j
            while k < len(lane) and id(lane[k]) in taken:
                k += 1
            if k < len(lane):
                out.append(lane[k])
                taken.add(id(lane[k]))
                k += 1
            if at == "i":
                i = k
            else:
                j = k
    return out


def _decided_by_id(led: dict, rec: dict | None, now) -> bool:
    """A path record whose GitHub id a DIFFERENT live record holds: the repo was renamed upstream and
    decided under its new path (ji1ore/remotekeyer_wifi -> ji1ore/Wifi_Rig_CW, rejected below_floor as
    wifi-rig-cw). The loop's id gate takes exactly this decision after a paid meta fetch; the queue
    takes it with zero calls, so the dead path never leads the undecided backlog again (2026-11-17:
    12+ ticks of "top: ji1ore/remotekeyer_wifi", one wasted call each)."""
    rid = (rec or {}).get("repo_id")
    if rid is None:
        return False
    other = memory.lookup(led, repo_id=rid)
    if other is None or other is rec:
        return False
    return (memory.is_blocked(led, repo_id=rid, now=now) or memory.is_seen(led, repo_id=rid, now=now)
            or other.get("status") == "merged")


def launcher_queue(catalog: list, led: dict, cat_repos: set, now, pending=None,
                   seed: str | None = None) -> tuple[list, int, str]:
    """Admit's launcher backlog, built with ZERO calls (SPEC-espatlas-jr.md, the backlog queue).

    Entries are grouped by repo (an entry with no repo by its launcher ledger key), one entry per
    group (its most-downloaded one), ranked by the group's TOTAL downloads. Returns
    (ordered entries, undecided count, top label):
      1. the undecided backlog, what the call share is for: most downloads first, interleaved with
         a shuffle seeded by `seed` (the tick's UTC hour; see _interleave) so the most wanted repo
         goes first and every other paid slot explores;
      2. the decided, which the loop skips for free (memory, catalogued with a live id, merged);
      3. the tail, which needs a call but decides nothing new: a catalogued repo whose id no live
         record holds (the rename-proof identity refresh), a live owner-review decision (evidence
         re-check), an id an open or vetoed tick PR holds. They never stand in front of new work.
    Before this (2026-11-12 to 2026-11-14) the loop walked the alphabet from "A" every tick and
    stopped before brucedevices/firmware every hour: 1,205 undecided repos were never reached."""
    groups: dict = {}
    for i, e in enumerate(catalog):
        github = (e.get("github") or "").strip()
        if launcher_resolve.needs_resolution(e):
            k = launcher_resolve.ledger_key(e)
            key = ("launcher", k[0]) if k else ("unkeyed", i)
        else:
            owner_repo = scorer._owner_repo(github)
            key = ("repo", owner_repo) if owner_repo and "/" in owner_repo else ("unkeyed", i)
        groups.setdefault(key, []).append(e)
    undecided, decided, tail = [], [], []
    for (kind, k), es in groups.items():
        rep = sorted(es, key=lambda e: (-_downloads(e), e.get("name") or "", e.get("github") or ""))[0]
        item = (-sum(_downloads(e) for e in es), rep.get("name") or "", rep.get("github") or "", k, rep)
        if kind == "unkeyed":
            decided.append(item)
        elif kind == "launcher":
            done = memory.is_blocked(led, firmware_id=k, now=now) or memory.is_seen(led, firmware_id=k, now=now)
            (decided if done else undecided).append(item)
        else:
            rec = memory.lookup(led, repo=k)
            live_id = bool(rec and rec.get("repo_id") is not None and not memory.is_expired(rec, now))
            cand_id = scorer._slug(scorer._repo_name_from_url(rep.get("github") or ""))
            if review_memory.live_decision(led, now, repo=k):
                tail.append(item)
            elif memory.is_blocked(led, repo=k, now=now) or memory.is_seen(led, repo=k, now=now) or (
                    rec and rec.get("status") == "merged") or _decided_by_id(led, rec, now):
                decided.append(item)
            elif scorer.catalogued_reason(k, cat_repos):
                (decided if live_id else tail).append(item)
            elif pending is not None and cand_id and pending.hold(cand_id):
                tail.append(item)
            else:
                undecided.append(item)
    undecided.sort(key=lambda t: t[:3])
    if seed is not None and len(undecided) > 2:
        undecided = _interleave(undecided, seed)
    decided.sort(key=lambda t: (t[1], t[2]))
    tail.sort(key=lambda t: t[:3])
    top = f"{undecided[0][3]}, {-undecided[0][0]} downloads" if undecided else "none"
    return [t[4] for t in undecided + decided + tail], len(undecided), top


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


def _raised_where(decision: dict) -> str:
    rv = decision.get("review") or {}
    return f"{rv.get('pr_ref')} {rv.get('outcome')}" if rv.get("pr_ref") else rv.get("outcome") or "raised"


def _hold(ctx, decision: dict, ev: dict | None, rev: str | None, repo_id) -> None:
    """A held decision is left as it is — except one raised before revisions existed, which gets
    this tick's evidence revision (and repo_id) backfilled, keeping its outcome, PR and expiry."""
    rv = decision.get("review") or {}
    if ctx.dry_run or rv.get("evidence_rev") or rev is None:
        return
    raised = datetime.fromisoformat(rv["raised_at"]) if rv.get("raised_at") else ctx.now
    memory.record_review_decision(decision["id"], decision.get("repo") or "", decision.get("reason") or "",
                                  repo_id=repo_id, evidence=ev, evidence_rev=rev, pr_ref=rv.get("pr_ref"),
                                  outcome=rv.get("outcome") or "raised", raised_at=raised,
                                  path=ctx.ledger_path, now=ctx.now)


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

    pending = pending_prs.of(ctx)   # what an open or vetoed tick PR holds (from its own file list)
    led = memory.load(ctx.ledger_path)   # read-only here; writes below honor dry-run
    cat_repos, cat_toks = tools._catalogued_repos_and_tokens(ctx.root / "data" / "firmware")
    # Per-firmware token sets (not the flat cat_toks pool above) so scorer.score_entry's
    # name-token dedup rejects only a real subset/near-duplicate match, never a lone shared word
    # (the bug that plateaued the catalog at 82 — see scorer.score_entry's docstring).
    cat_token_sets = tools._catalogued_token_sets(ctx.root / "data" / "firmware")
    cat_ids = _catalogued_ids(led, ctx.now)
    paths, lines, admitted, rejects, needs_human = [], [], 0, {}, False
    would_admit, decided, items, review, would_write = 0, 0, [], [], []

    def would(path, field, value=None):
        """Dry-run: a write a real run would make, for the tick report."""
        would_write.append({"path": path, "field": field, "value": value})

    def reject(key):
        rejects[key] = rejects.get(key, 0) + 1

    launcher_skips: dict = {}      # launcher repos are skipped by the hundred: one aggregate line, never one per repo
    fetched_this_tick: set = set()   # owner/repo already paid a meta fetch this tick: one paid decision per repo

    def count_skip(key):
        """A launcher skip that writes nothing: counted in rejects and the aggregate line."""
        reject(key)
        launcher_skips[key] = launcher_skips.get(key, 0) + 1

    def skip_reject(fid, owner_repo, reason, repo_id, issue=None, review_ev=None):
        """Record the rejection (memory, counts). Returns a report line for a submission (rare and
        meaningful — the submitter reads it), or None for a launcher entry (aggregated below).
        An empty id or repo is never recorded (a falsy ledger key is corruption): counted
        `unkeyed` instead. `review_ev` (evidence, rev) makes it an owner-review decision
        (SPEC-jr-review-routing.md §5) instead of a plain rejection."""
        if not fid or not owner_repo:
            count_skip("unkeyed")
            return None
        key = reason.split(":")[0]
        reject(key)
        if pending_note and owner_repo != pending_note["key"][1]:
            pending_note["ttl"] = REJECT_TTLS.get(key, memory.SEEN_TTL_DAYS)   # the note follows its repo's decision
        if ctx.dry_run:
            would(memory.LEDGER_RELPATH, f"by_id.{fid}", f"rejected ({key})")
        elif review_ev is not None:
            memory.record_review_decision(fid, owner_repo, reason, repo_id=repo_id, evidence=review_ev[0],
                                          evidence_rev=review_ev[1], path=ctx.ledger_path, now=ctx.now)
        else:
            after = memory.record_rejected(fid, owner_repo, reason,
                                           ttl_days=REJECT_TTLS.get(key, memory.SEEN_TTL_DAYS),
                                           repo_id=repo_id, path=ctx.ledger_path, now=ctx.now)
            remember_repo(owner_repo, reason, key, after)
        if issue:
            return f"{fid}: skip {key} (submission #{issue})"
        launcher_skips[key] = launcher_skips.get(key, 0) + 1
        return None

    def remember_repo(owner_repo, reason, key, after=None):
        """A decision the ledger refused to record under its own id (memory._write keeps a `merged`
        record) is kept under the repo's note key, so the repo is never paid for again while it
        holds (the backlog queue's guarantee: every paid call ends in a remembered decision)."""
        if after is not None and (memory.is_blocked(after, repo=owner_repo, now=ctx.now)
                                  or memory.is_seen(after, repo=owner_repo, now=ctx.now)):
            return
        if ctx.dry_run:
            would(memory.LEDGER_RELPATH, f"by_id.{repo_note_key(owner_repo)}", f"rejected ({key})")
            return
        memory.record_rejected(repo_note_key(owner_repo), owner_repo, reason,
                               ttl_days=REJECT_TTLS.get(key, memory.SEEN_TTL_DAYS), path=ctx.ledger_path, now=ctx.now)

    def note(line):
        if line:
            lines.append(line)

    def held_by_pr(hold, cand_id, issue):
        """A candidate an open or vetoed tick PR holds (jr/pending_prs.py): counted, never admitted,
        nothing remembered — the index is rebuilt every tick. A rename or an identity ambiguity is
        named on its own line, with both ids and the PR. An ambiguous candidate is no decision: nothing
        is persisted — not even a resolved launcher entry's note — and a submission's issue stays open
        and unanswered, read again once the hold ends (fail closed)."""
        nonlocal pending_note
        reject(hold.reason)
        if hold.seen_id is not None:
            pending_note = None
        if issue and hold.seen_id is not None:
            lines.append(f"submission #{issue}: deferred, {hold.reason} ({hold.note})")
            return
        if issue:
            _answer(ctx, slug, issue, _verdict_text(f"{hold.reason}: {hold.note}", False, False))
            lines.append(f"submission #{issue}: {hold.reason.replace('_', ' ')} ({cand_id})")
            return
        launcher_skips[hold.reason] = launcher_skips.get(hold.reason, 0) + 1
        if hold.seen_as is not None or hold.seen_id is not None:
            lines.append(f"{cand_id}: {hold.reason} ({hold.note})")

    resolver_calls = 0

    def resolve_launcher(entry):
        """G1b: a launcher entry with no repo (github None / owner-only) -> ("repo", owner/repo)
        to score normally, ("skip", None) when it is decided, keyless or deferred to the next
        tick, or ("stop", None) when admit's budget cannot afford the search plus the meta fetch.
        Inconclusive searches are recorded once as no_source_repo under the launcher fid (7 d);
        a search GitHub refuses because the author is not a login is owner_missing (90 d)."""
        nonlocal decided, resolver_calls
        key = launcher_resolve.ledger_key(entry)
        if key is None:
            count_skip("unkeyed")
            return "skip", None
        kid, krepo = key
        if memory.is_blocked(led, firmware_id=kid, now=ctx.now) or memory.is_seen(led, firmware_id=kid, now=ctx.now):
            decided += 1
            return "skip", None
        searchable = launcher_resolve.build_query(entry) is not None
        if searchable and resolver_calls >= launcher_resolve.RESOLVER_CALLS_PER_TICK:
            count_skip("resolve_deferred")
            return "skip", None
        label = entry.get("name") or kid
        if searchable and ctx.budget.remaining_calls() < MIN_CALLS_TO_CONTINUE + 1:
            lines.append(f"stopped before {label}: tick budget low ({ctx.budget.remaining_calls()} calls left)")
            return "stop", None
        if searchable and ctx.budget.calls - calls_at_start + 2 > call_cap:   # the search + the meta fetch
            lines.append(f"stopped before {label}: admit's call share used ({call_cap} of the tick's calls); the rest is Track B's")
            return "stop", None
        resolver_calls += int(searchable)
        try:
            res = launcher_resolve.resolve(entry, ctx.gh)
        except BudgetExceeded as e:
            lines.append(f"stopped during {label}: {e}")
            return "stop", None
        if res["repo"]:
            return "repo", res["repo"]
        detail = res["error"] or f"{len(res['matches'])} matches for {res['query']!r}"
        key = launcher_resolve.OWNER_MISSING if res.get("error_kind") == launcher_resolve.OWNER_MISSING \
            else launcher_resolve.NO_SOURCE_REPO
        skip_reject(kid, krepo, f"{key}: {detail[:100]}", None)
        return "skip", None

    # A resolved entry's own note {key, repo, ttl}, written once its repo is decided, with that
    # decision's TTL (a repo_unresolved fetch is retried in 7 d, not behind a 30-day note).
    pending_note = None

    def flush_note():
        nonlocal pending_note
        if pending_note and ctx.dry_run:
            would(memory.LEDGER_RELPATH, f"by_id.{pending_note['key'][0]}", "seen")
        elif pending_note:
            kid, krepo = pending_note["key"]
            memory.record_seen(kid, krepo, reason=f"resolved: {pending_note['repo']}",
                               ttl_days=pending_note["ttl"], path=ctx.ledger_path, now=ctx.now)
        pending_note = None

    # Submissions first (one counted call to list them), then the launcher catalog.
    slug = (ctx.env or {}).get("JR_REPO_SLUG") or DEFAULT_REPO_SLUG
    submissions = _submission_entries(ctx, slug)
    atlas = board_alias.atlas_boards(ctx.root) if submissions else {}
    queue, backlog, top = launcher_queue(catalog, led, cat_repos, ctx.now, pending,
                                         seed=ctx.now.strftime("%Y-%m-%dT%H"))
    lines.append(f"backlog {backlog} undecided (top: {top})")
    entries = [dict(e) for e in submissions] + [dict(e) for e in queue]

    for entry in entries:
        flush_note()          # the previous entry reached a decision (a break never gets here)
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
        if not issue and launcher_resolve.needs_resolution(entry):
            action, resolved = resolve_launcher(entry)
            if action == "stop":
                break
            if action == "skip":
                continue
            github = f"https://github.com/{resolved}"
            entry = dict(entry, github=github)      # the scorer reads the entry's own github
            pending_note = {"key": launcher_resolve.ledger_key(entry), "repo": resolved, "ttl": memory.SEEN_TTL_DAYS}
        owner_repo = scorer._owner_repo(github)
        # A live owner-review decision is not a plain block: it holds only while the evidence it was
        # taken on is unchanged, which takes the repo's metadata to tell (SPEC-jr-review-routing.md §5).
        held = review_memory.live_decision(led, ctx.now, repo=owner_repo)
        if not held and (memory.is_blocked(led, repo=owner_repo, now=ctx.now) or memory.is_seen(led, repo=owner_repo, now=ctx.now)):
            decided += 1
            if issue:
                prior = memory.lookup(led, repo=owner_repo) or {}
                _answer(ctx, slug, issue, _verdict_text(f"already_decided: {prior.get('reason') or prior.get('status') or 'seen'}"
                                                        + (f" (until {prior['expires']})" if prior.get("expires") else ""), False, False))
                lines.append(f"submission #{issue}: already decided")
            continue
        # A renamed repo decided under its GitHub id by another live record (the queue's rule,
        # _decided_by_id) is decided here too, before the paid meta fetch the id gate below needs.
        if not issue and not held and _decided_by_id(led, memory.lookup(led, repo=owner_repo), ctx.now):
            decided += 1
            continue
        # The admit wall (2026-11-14): a catalogued repo whose GitHub id a live ledger record already
        # holds (a `merged` record, typically) is decided without the paid meta fetch. It used to pay
        # one call per launcher entry per tick and score `already_catalogued`, a write memory._write
        # refuses over `merged`; Bruce's ~35 entries ate admit's whole call share every hour. The rule
        # is the scorer's own (scorer.catalogued_reason). Without a live id the repo is fetched as
        # before, so the rename-proof identity net (_catalogued_ids) keeps its id.
        cat_reason = None if held else scorer.catalogued_reason(owner_repo, cat_repos)
        known = memory.lookup(led, repo=owner_repo) if cat_reason else None
        if cat_reason and known and known.get("repo_id") is not None and not memory.is_expired(known, ctx.now):
            if issue:
                reject("already_catalogued")
                _answer(ctx, slug, issue, _verdict_text(cat_reason, False, False))
                lines.append(f"{scorer._slug(scorer._repo_name_from_url(github)) or owner_repo}: "
                             f"skip already_catalogued (submission #{issue})")
            else:
                count_skip("already_catalogued")
            continue
        merged = None if held else memory.lookup(led, repo=owner_repo)
        if not issue and merged and merged.get("status") == "merged":
            count_skip("already_catalogued")          # we have it: reconciled from the catalog itself
            continue
        if not issue and owner_repo in fetched_this_tick:
            count_skip("same_repo_this_tick")   # this tick already paid for this repo's decision
            continue
        # An id already sitting in an OPEN Jr PR — hydrated into the worktree ledger at tick start
        # (tick.hydrate_open_pr_ledger) because this worktree reads origin/main's ledger, which
        # lacks the un-merged PR's own `proposed` entry. A hydrated record is keyed by the firmware
        # id (its owner/repo is not recoverable from a file path), so the repo gate above cannot see
        # it; this id gate catches it. The authored id is deterministic from the github url alone
        # (scorer derives it the same way), so this fires BEFORE any meta fetch — no wasted call —
        # and stops two consecutive ticks producing a duplicate PR (#158/#159, #162/#163). The PR's own
        # file list (jr/pending_prs.py) backs it: an id an open tick PR changes — or one a closed-unmerged
        # tick PR changed inside the veto TTL — is held even when the ledger hydration could not see it.
        # A hold whose PR verified the repository's GitHub id is decided by that id once the metadata
        # is read (below): the same slug under another id is ambiguous, not the held firmware.
        cand_id = scorer._slug(scorer._repo_name_from_url(github))
        cand_rec = memory.lookup(led, firmware_id=cand_id) if cand_id else None
        hold = pending.hold(cand_id)
        if hold and hold.repo_id is None:
            held_by_pr(hold, cand_id, issue)
            continue
        if not hold and cand_rec and cand_rec.get("status") == "proposed" and not memory.is_expired(cand_rec, ctx.now):
            reject("already_proposed")
            if issue:
                where = cand_rec.get("pr_ref") or "an open PR covers this firmware"
                _answer(ctx, slug, issue, _verdict_text(f"already_proposed: {where}", False, False))
                lines.append(f"submission #{issue}: already proposed ({cand_id})")
            else:
                launcher_skips["already_proposed"] = launcher_skips.get("already_proposed", 0) + 1
            continue
        if ctx.budget.remaining_calls() < MIN_CALLS_TO_CONTINUE:
            lines.append(f"stopped before {owner_repo}: tick budget low "
                         f"({ctx.budget.remaining_calls()} calls left)")
            break
        if not issue and ctx.budget.calls - calls_at_start >= call_cap:
            lines.append(f"stopped before {owner_repo}: admit's call share used ({call_cap} of the tick's calls); the rest is Track B's")
            break
        fetched_this_tick.add(owner_repo)
        try:
            meta, _fetched = _fetch_meta(ctx.gh, owner_repo)
        except BudgetExceeded as e:
            lines.append(f"stopped during {owner_repo}: {e}")   # meta fetch is read-only: nothing half-written
            break
        repo_id = meta.get("id")
        # Identity is the repository: a held repository renamed upstream keeps its GitHub id, so the
        # id is matched before the slug, and a held slug under another id is never admitted.
        hold = pending.match(cand_id, repo_id)
        if hold:
            held_by_pr(hold, cand_id, issue)
            continue
        held = held or (review_memory.live_decision(led, ctx.now, repo_id=repo_id) if repo_id is not None else None)
        rev_ev = review_memory.evidence(meta, downloads=entry.get("download")) if not meta.get("error") else None
        rev = review_memory.evidence_rev(rev_ev) if rev_ev is not None else None
        if held and review_memory.holds(held, rev):
            decided += 1
            _hold(ctx, held, rev_ev, rev, repo_id)
            lines.append(f"review already raised: {owner_repo} ({_raised_where(held)}), evidence unchanged")
            if issue:
                _answer(ctx, slug, issue, _verdict_text(f"already_decided: {held.get('reason')} (until {held.get('expires')})",
                                                        False, False))
            continue
        if repo_id is not None and memory.lookup(led, repo_id=repo_id) is not held and (
                memory.is_blocked(led, repo_id=repo_id, now=ctx.now) or memory.is_seen(led, repo_id=repo_id, now=ctx.now)):
            decided += 1
            continue
        if held:                                     # new evidence: reconsidered as if new, never its own duplicate
            cat_ids = {k: v for k, v in cat_ids.items() if v != held.get("id")}
        fid = scorer._slug(scorer._repo_name_from_url(github)) or owner_repo   # empty -> skip_reject counts it `unkeyed`
        # Popularity floor (SPEC-firmware-floor.md, via esp_atlas_core.floor — never re-typed):
        # below stars AND forks AND no independent editorial home AND no qualifying download
        # count is filler, rejected for FLOOR_REJECT_DAYS. `downloads=None` explicit: this is
        # the topic-admit/submission path, which has no launcher download count to pass (only
        # jr/drain.py's launcher-catalog path has one) — no behavior change here.
        if meta.get("error"):
            note(skip_reject(fid, owner_repo, f"repo_unresolved: {meta['error'][:80]}", None, issue=issue))
            if issue:
                _answer(ctx, slug, issue, _verdict_text(f"repo_unresolved: {meta['error'][:80]}", False, False))
            continue
        if not clears_popularity_floor(meta.get("stars"), meta.get("forks"), meta.get("homepage"), downloads=None):
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
        res = scorer.score_entry(entry, meta, cat_repos, cat_toks, cat_ids,
                                 catalogued_token_sets=cat_token_sets, board_hint=hint_board)
        # A build-file board for every candidate (2026-11-17), not only submissions: the prose names no
        # catalogued board, but the repo's own platformio.ini / sketch.yaml may (`board = esp32-s3-devkitc-1`,
        # project_aura 797 stars; the ESP32-C3-DevKitM-1 of esp32-c3-adblock, 3597). The device-build
        # evidence gate below reads those files anyway: run it first here, take the board from the targets
        # it returns (device_evidence.board_from_targets: the first catalogued board, a chip is never one),
        # and score again with it as the hint — the submission path's own mechanism, so the recipe cites
        # the build file line and the evidence gate is not run twice.
        pre_ev = None
        if (not issue and res["decision"] == "skip" and res["reason"].startswith("no_board_evidence")
                and ctx.budget.remaining_calls() >= device_evidence.MAX_CALLS + MIN_CALLS_TO_CONTINUE):
            try:
                pre_ev = _device_evidence(ctx, owner_repo, meta.get("default_branch"), raw=raw)
            except BudgetExceeded as e:
                lines.append(f"stopped during {owner_repo}: {e}")
                break
            if pre_ev.get("ok"):
                atlas = atlas or board_alias.atlas_boards(ctx.root)
                built_board, built_signal = device_evidence.board_from_targets(pre_ev, atlas)
                if built_board:
                    hint_board, evidence = built_board, built_signal
                    res = scorer.score_entry(entry, meta, cat_repos, cat_toks, cat_ids,
                                             catalogued_token_sets=cat_token_sets, board_hint=hint_board)
                    if res["decision"] != "skip":
                        lines.append(f"{res['record']['id']}: board {built_board} from {built_signal['kind']} ({built_signal['url']})")
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
            reject("already_catalogued")
            remember_repo(owner_repo, f"already_catalogued: record {out_id} exists", "already_catalogued")
            if issue:
                _answer(ctx, slug, issue, _verdict_text(f"already_catalogued: {out_id}", False, False))
            continue
        # Device-build evidence (jr/device_evidence.py, review finding 3): a record says "flash this
        # onto an ESP", so the repo itself must build for one. Topics/description naming a board
        # are not enough — rebelthor/warble, a Go server, passed every gate above on them alone.
        if pre_ev is not None:
            ev = pre_ev                                   # already read for the board above: one gate run
        else:
            if ctx.budget.remaining_calls() < device_evidence.MAX_CALLS:
                lines.append(f"stopped before {owner_repo}'s build evidence: tick budget low "
                             f"({ctx.budget.remaining_calls()} calls left)")
                break
            try:
                ev = _device_evidence(ctx, owner_repo, meta.get("default_branch"), raw=raw)
            except BudgetExceeded as e:
                lines.append(f"stopped during {owner_repo}: {e}")
                break
        if ev["ok"] is None and issue:
            # Unreadable is not a verdict, and submissions are read from OPEN issues only: leave
            # it open and unremembered so the next tick checks it again.
            lines.append(f"submission #{issue}: deferred, build evidence unreadable")
            continue
        if not ev["ok"]:
            reason = device_evidence.reject_reason(ev)
            asks = ev.get("verdict") == device_evidence.NEEDS_REVIEW
            note(skip_reject(out_id, owner_repo, reason, repo_id, issue=issue,
                             review_ev=(rev_ev, rev) if asks else None))
            if asks:
                # Ambiguous, never guessed: not admitted, and listed in the tick report for the owner —
                # once: the decision it records holds the target until its evidence changes or it expires.
                review.append({"id": out_id, "repo": owner_repo, **device_evidence.review_note(ev),
                               "repo_id": repo_id, "evidence_rev": rev, "evidence": rev_ev, "reason": reason})
                lines.append(f"needs owner review: {owner_repo} ({ev['kind']}) {ev['url']}")
            if issue:
                _answer(ctx, slug, issue, _verdict_text(reason, False, False))
            continue
        # The evidence gate (SPEC-jr-review-routing.md §7): a board picked from the repo's name or
        # description passes the independent check, which also reads the README (one charged call).
        # FAIL refuses the candidate; "Cardputer" named only generically next to an ADV-only README
        # becomes the Cardputer-Adv edge. Submissions and build-file signals carry their own evidence.
        receipt, ev_text = None, None
        if not (evidence is not None and rec["board"] == hint_board):
            ev_text = {"description": " ".join(x for x in (entry.get("name"), meta.get("description"),
                                                         entry.get("description")) if x),
                       "readme": _fetch_readme(ctx.gh, owner_repo)}
            target, receipt, refusals = writers.evidence_gate(rec["board"], ev_text, board_alias.atlas_boards(ctx.root))
            if target is None:
                reason = "evidence_check: " + refusals[0][1].split(": ", 1)[1]
                note(skip_reject(out_id, owner_repo, reason, repo_id, issue=issue))
                if issue:
                    _answer(ctx, slug, issue, _verdict_text(reason, False, False))
                continue
            if target != rec["board"]:
                if tools.board_soc(target, repo=ctx.root) != rec["chip"]:
                    note(skip_reject(out_id, owner_repo, f"chip_family_mismatch: evidence moved the edge to '{target}'",
                                     repo_id, issue=issue))
                    continue
                lines.append(f"{out_id}: evidence check moved the edge {rec['board']} -> {target}")
                rec = dict(rec, board=target)
        if res.get("needs_human"):
            needs_human = True
        if ctx.dry_run:
            lines.append(f"{out_id}: would admit{' (needs_human)' if res.get('needs_human') else ''}"
                         + (f" (submission #{issue})" if issue else ""))
            would_admit += 1
            would(str(fmd.relative_to(ctx.root)), "*", out_id)
            rdir = ctx.root / "data" / "recipes" / f"{rec['board']}__{out_id}"
            if not (rdir / "recipe.md").exists():
                would(str((rdir / "recipe.md").relative_to(ctx.root)), "*", f"{rec['board']}__{out_id}")
            would(memory.LEDGER_RELPATH, f"by_id.{out_id}", "proposed")
            continue
        repo_url = rec["url"]
        # Coerce whatever GitHub actually returned; a missing forks_count stays None so the
        # writer omits only that field instead of dropping the whole popularity block. `homepage`
        # is stamped as `editorial_home` only when it actually clears is_editorial_home (the same
        # rule clears_popularity_floor used two gates up to admit this candidate) — otherwise a
        # candidate admitted ONLY via its editorial home would pass here but fail every later
        # OFFLINE re-check (scripts/firmware_floor_audit.py), which cannot see a live homepage,
        # and be discarded and re-discovered forever (the drift this stamp closes).
        pop_stars = meta.get("stars")
        pop_forks = meta.get("forks")
        editorial_home = meta.get("homepage") if is_editorial_home(meta.get("homepage")) else None
        popularity = {"stars": int(pop_stars) if isinstance(pop_stars, int) else None,
                     "forks": int(pop_forks) if isinstance(pop_forks, int) else None}
        if editorial_home is not None:
            popularity["editorial_home"] = editorial_home
        text = writers.render_firmware(rec, [{"field": "*", "url": repo_url},
                                             {"field": "popularity", "url": repo_url}],
                                       today, needs_human=bool(res.get("needs_human")),
                                       popularity=popularity)
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
                                      repo_url, [signal], today, receipt=receipt), encoding="utf-8")
            paths.append(str(rdir.relative_to(ctx.root)))
            # firmware that names both the Cardputer-Adv and the original explicitly gets both edges (§7)
            if ev_text is not None:
                cat = board_alias.atlas_boards(ctx.root)
                for orig, orig_receipt in writers.reverse_siblings({rec["board"]}, ev_text, cat):
                    odir = ctx.root / "data" / "recipes" / f"{orig}__{out_id}"
                    if tools.board_soc(orig, repo=ctx.root) == rec["chip"] and not (odir / "recipe.md").exists():
                        odir.mkdir(parents=True, exist_ok=True)
                        osig = dict(signal, token=(cat.get(orig) or {}).get("name") or orig, extra={})
                        (odir / "recipe.md").write_text(
                            writers.render_recipe(f"{orig}__{out_id}", orig, out_id, rec["chip"], repo_url, [osig],
                                                  today, receipt=orig_receipt), encoding="utf-8")
                        paths.append(str(odir.relative_to(ctx.root)))
        memory.record_proposed(out_id, owner_repo, repo_id=repo_id, evidence_url=repo_url,
                               path=ctx.ledger_path, now=ctx.now)
        if evidence is not None and rec["board"] == hint_board:
            ev = (f"named by the submitter in issue #{issue}" if evidence.get("kind") == "submission"
                  else f"{evidence.get('kind')} signal `{evidence.get('token')}` ({evidence.get('url')})")
        else:
            ev = "named in the repository name/description"
        items.append({"kind": "firmware", "id": out_id, "name": rec["name"], "url": repo_url, "repo_id": repo_id,
                      "stars": meta.get("stars"), "forks": meta.get("forks"), "fork": bool(meta.get("fork")),
                      "archived": bool(meta.get("archived")), "license": meta.get("license"),
                      "board": rec["board"], "chip": rec["chip"], "recipe": f"{rec['board']}__{out_id}",
                      "evidence": ev, "needs_human": bool(res.get("needs_human")), "submission": issue})
        admitted += 1
        lines.append(f"{out_id}: +record{' (needs_human)' if res.get('needs_human') else ''}"
                     + (f" (submission #{issue})" if issue else ""))
        if issue:
            _answer(ctx, slug, issue, _verdict_text(None, True, bool(res.get("needs_human")), f"{rec['board']}__{out_id}"))
    else:
        flush_note()          # the last entry reached a decision
    if launcher_skips:
        total = sum(launcher_skips.values())
        lines.append(f"skipped {total} launcher repos: " + ", ".join(f"{k} {v}" for k, v in sorted(launcher_skips.items(), key=lambda kv: (-kv[1], kv[0]))))
    summary = "; ".join(lines) if lines else "no candidates"
    if decided and lines:
        summary += f" ({decided} already decided, skipped)"
    elif decided:
        summary = f"{decided} already decided, skipped"
    return tick.StageResult("admit", paths=paths, summary=summary, admitted=admitted,
                            rejects=rejects, needs_human=needs_human, items=items, review=review,
                            would_write=would_write, backlog=backlog)
