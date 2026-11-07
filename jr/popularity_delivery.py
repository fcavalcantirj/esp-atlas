"""Restart-safe, scheduled popularity PR-to-deployed-site reconciliation.

The hourly Jr runner calls this on every natural tick. A source fetch or open
PR is never counted as delivery; each transition is persisted outside the
repository and advanced only from live GitHub, deployed API and rendered page
evidence. All remote operations are injectable for offline tests.
"""
from __future__ import annotations

import html
import json
import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import yaml

import demand_closure
import publish

SITE = "https://esp-atlas.com"
TERMINAL = {"readback_verified", "deployed_no_count_change", "closed", "superseded"}
SHA = re.compile(r"[0-9a-f]{40}")


def expected_samples(root: Path, paths: list[str]) -> list[dict]:
    """Pick deterministic first/middle/last changed firmware records after validation."""
    records = []
    for rel in sorted(p for p in paths if p.startswith("data/firmware/") and p.endswith("/firmware.md")):
        text = (root / rel).read_text(encoding="utf-8")
        fm = yaml.safe_load(text.split("---", 2)[1])
        pop = fm.get("popularity") if isinstance(fm, dict) else None
        if not isinstance(pop, dict):
            raise ValueError(f"published firmware popularity unreadable: {rel}")
        row = {"id": fm["id"], "stars": pop.get("stars"), "forks": pop.get("forks"),
               "github_as_of": pop.get("github_as_of")}
        if not isinstance(row["id"], str) or not isinstance(row["github_as_of"], str):
            raise ValueError(f"published firmware popularity incomplete: {rel}")
        records.append(row)
    if len(records) <= 3:
        return records
    return [records[0], records[len(records) // 2], records[-1]]


def register(state: dict, published: publish.PublishResult, samples: list[dict],
             now: datetime, receipt: str) -> None:
    """Keep past deliveries; a refreshed open PR supersedes its old head only."""
    deliveries = state.setdefault("deliveries", [])
    if not isinstance(deliveries, list):
        raise ValueError("popularity delivery state malformed")
    if any(row.get("pr_url") == published.pr_url and row.get("head_sha") == published.commit
           for row in deliveries if isinstance(row, dict)):
        return
    for row in deliveries:
        if row.get("pr_url") == published.pr_url and row.get("state") == "pending":
            row["state"] = "superseded"
            row["superseded_at"] = now.isoformat()
    changed_ids = sorted({Path(p).parent.name for p in published.paths
                          if p.startswith("data/firmware/") and p.endswith("/firmware.md")})
    live_sequence = state.get("delivery_live_sequence")
    live_sequence = live_sequence if type(live_sequence) is int and live_sequence >= 0 else 0
    deliveries.append({"pr_url": published.pr_url, "head_sha": published.commit,
                       "state": "pending", "published_at": now.isoformat(),
                       "receipt": receipt, "samples": samples, "changed_ids": changed_ids,
                       "changed_records": len(changed_ids),
                       "live_check_sequence": live_sequence})


def _pr(gh, url: str) -> dict | None:
    response = gh("pr", "view", url, "--json", "state,headRefOid,mergeCommit,mergedAt")
    if getattr(response, "returncode", 1) != 0:
        return None
    try:
        doc = json.loads(response.stdout or "")
    except (TypeError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def _status_revision(fetch) -> str | None:
    try:
        return demand_closure._deployed_revision(fetch)
    except (demand_closure._Unread, OSError, TypeError, ValueError):
        return None


def _json(fetch, url: str) -> dict | None:
    try:
        status, body = fetch(url)
        doc = json.loads(body) if status == 200 else None
        return doc if isinstance(doc, dict) else None
    except (OSError, TypeError, ValueError):
        return None


def _purge_confirmed(response: object) -> bool:
    if not isinstance(response, dict) or response.get("ok") is not True or response.get("status") != 200:
        return False
    try:
        body = json.loads(response.get("body") or "")
    except (TypeError, ValueError):
        return False
    return isinstance(body, dict) and body.get("revalidated") is True and body.get("tag") == "catalog"


def _visible_date(raw: str) -> str | None:
    try:
        if len(raw) == 10:
            return raw
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except (TypeError, ValueError):
        return None


def _rendered_counts(fragment: str) -> dict[str, int] | None:
    """Read complete visible number spans, rejecting duplicates or partial digits."""
    figures = re.findall(
        r'<span class="firmware-popularity-figure">([0-9]+)</span>\s*(stars|forks)\b',
        fragment,
    )
    counts: dict[str, int] = {}
    for number, unit in figures:
        if unit in counts:
            return None
        counts[unit] = int(number)
    return counts


def _readback(fetch, git, merge_sha: str, samples: list[dict]) -> tuple[bool, dict]:
    before = _status_revision(fetch)
    if not before or not demand_closure.contains_merge(git, merge_sha, before):
        return False, {"reason": "deployed revision missing or does not contain merge"}
    checked = []
    for row in samples:
        ident = urllib.parse.quote(row["id"], safe="")
        api = _json(fetch, f"{SITE}/api/firmware/{ident}")
        popularity = api.get("popularity") if isinstance(api, dict) else None
        if not isinstance(popularity, dict) or any(popularity.get(k) != row[k]
                                                   for k in ("stars", "forks", "github_as_of")):
            return False, {"reason": f"API readback differs for {row['id']}", "checked": checked}
        try:
            status, body = fetch(f"{SITE}/firmware/{ident}")
            page = body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)
        except (OSError, TypeError, ValueError):
            return False, {"reason": f"page readback unavailable for {row['id']}", "checked": checked}
        match = re.search(r'<p class="firmware-popularity">(.*?)</p>', page, re.DOTALL)
        visible = " ".join(html.unescape(re.sub(r"<[^>]*>", " ", match.group(1))).split()) if match else ""
        counts = _rendered_counts(match.group(1)) if match else None
        expected_counts = {unit: row[key] for key, unit in (("stars", "stars"), ("forks", "forks"))
                           if row[key] is not None}
        date = _visible_date(row["github_as_of"])
        if (status != 200 or not date or f"as of {date}" not in visible or counts != expected_counts):
            return False, {"reason": f"rendered page differs for {row['id']}", "checked": checked}
        checked.append(row["id"])
    after = _status_revision(fetch)
    if before != after:
        return False, {"reason": "deployment changed during readback", "checked": checked}
    return True, {"deployed_revision": before, "sample_ids": checked}


def reconcile(state_file: Path, *, load_state, write_state, gh, git, secret: str | None,
              fetch=None, revalidate=publish.revalidate_catalog,
              now: datetime | None = None) -> list[dict]:
    """Advance all outstanding publications one phase at a time, persisting every success."""
    now = now or datetime.now(timezone.utc)
    fetch = fetch or demand_closure.default_fetch
    state = load_state(state_file)
    deliveries = state.get("deliveries")
    if not isinstance(deliveries, list):
        return []
    def save(row):
        row["checked_at"] = now.isoformat()
        write_state(state_file, state)

    for row in deliveries:
        if not isinstance(row, dict) or row.get("state") in TERMINAL:
            continue
        url, head = row.get("pr_url"), row.get("head_sha")
        if not isinstance(url, str) or not isinstance(head, str) or not SHA.fullmatch(head):
            row["reason"] = "delivery state lacks exact PR identity"
            save(row)
            continue
        if row["state"] == "pending":
            pr = _pr(gh, url)
            if pr is None:
                row["reason"] = "PR state unreadable"
                save(row)
                continue
            if pr.get("state") == "OPEN":
                if pr.get("headRefOid") != head:
                    row.update(state="superseded", reason="open PR head changed")
                else:
                    row["reason"] = "awaiting guarded merge"
                save(row)
                continue
            if pr.get("state") != "MERGED":
                row.update(state="closed", reason="PR closed without merge")
                save(row)
                continue
            if pr.get("headRefOid") != head:
                row.update(state="superseded", reason="merged PR head differs from published head")
                save(row)
                continue
            merge = pr.get("mergeCommit") if isinstance(pr.get("mergeCommit"), dict) else {}
            merge_sha = merge.get("oid")
            if not isinstance(merge_sha, str) or not SHA.fullmatch(merge_sha):
                row["reason"] = "merged PR has no exact merge commit"
                save(row)
                continue
            row.update(state="merged", merge_sha=merge_sha, merged_at=pr.get("mergedAt"), reason="")
            save(row)
    # A later *verified live* snapshot may replace a sampled record. Mere merge
    # ancestry is insufficient: with a one-deployment lag the older revision
    # can be ready for readback now, while the newer merge is not deployed yet.
    # Certify the ready predecessor first. Only verified newer page evidence
    # can supersede it; missing ancestry leaves the older delivery pending.
    active_states = {"merged", "deployed", "invalidated"}
    merged_evidence = [r for r in deliveries if isinstance(r, dict) and
                       r.get("state") in active_states | {"readback_verified"} and
                       isinstance(r.get("merge_sha"), str) and SHA.fullmatch(r["merge_sha"])]
    candidates = [(old, new) for old in merged_evidence if old.get("state") in active_states
                  for new in merged_evidence if new.get("state") == "readback_verified"
                  and new is not old and new["merge_sha"] != old["merge_sha"]
                  and {s.get("id") for s in old.get("samples") or [] if isinstance(s, dict)} &
                  set(new.get("changed_ids") or [s.get("id") for s in new.get("samples") or []
                                                 if isinstance(s, dict)])]
    if candidates and getattr(git("fetch", "origin", "main"), "returncode", 1) == 0:
        for old, new in candidates:
            if old.get("state") not in active_states:
                continue
            if demand_closure.contains_merge(git, old["merge_sha"], new["merge_sha"]):
                old.update(state="superseded", superseded_by=new["pr_url"],
                           superseded_by_merge_sha=new["merge_sha"],
                           reason="newer merged popularity snapshot changed a sampled firmware")
                save(old)

    # One live check per tick. Alternate an opportunity for the newest
    # untried, actually deployed merge with a fair retry of older work. A
    # transient failure followed by continuous new deployments otherwise
    # leaves the fair queue permanently one revision behind live values.
    # The turn and retry sequence persist across process restarts.
    active = [r for r in deliveries if isinstance(r, dict) and r.get("state") in active_states]
    if active:
        def sequence(row):
            value = row.get("live_check_sequence")
            return value if type(value) is int and value >= 0 else 0

        latest = state.get("delivery_live_sequence")
        latest = latest if type(latest) is int and latest >= 0 else 0
        latest = max(latest, *(sequence(row) for row in active)) + 1
        chosen = None
        if latest % 2 == 0:
            untried = [row for row in active if sequence(row) == 0]
            if untried:
                revision = _status_revision(fetch)
                if revision and getattr(git("fetch", "origin", "main"), "returncode", 1) == 0:
                    ready = [row for row in untried if
                             isinstance(row.get("merge_sha"), str) and
                             SHA.fullmatch(row["merge_sha"]) and
                             demand_closure.contains_merge(git, row["merge_sha"], revision)]
                    if ready:
                        chosen = ready[0]
                        for candidate in ready[1:]:
                            if demand_closure.contains_merge(git, chosen["merge_sha"],
                                                             candidate["merge_sha"]):
                                chosen = candidate
        if chosen is None:
            chosen = min(enumerate(active), key=lambda pair: (sequence(pair[1]), pair[0]))[1]
        state["delivery_live_sequence"] = latest
        chosen["live_check_sequence"] = latest
        save(chosen)
        for queued in active:
            if queued is not chosen:
                queued["reason"] = "delivery check queued by fair scheduler"
                save(queued)

    for row in [chosen] if active else []:
        if row["state"] == "merged":
            revision = _status_revision(fetch)
            if not revision or getattr(git("fetch", "origin", "main"), "returncode", 1) != 0 or \
                    not demand_closure.contains_merge(git, row["merge_sha"], revision):
                row["reason"] = "awaiting deployed API revision containing merge"
                save(row)
                continue
            row.update(state="deployed", deployed_revision=revision, reason="")
            save(row)
        if row["state"] in ("deployed", "invalidated"):
            try:
                purge = revalidate(secret)
            except Exception as exc:
                purge = {"ok": False, "reason": f"{type(exc).__name__}: {exc}"}
            if not _purge_confirmed(purge):
                row["reason"] = "catalog cache invalidation failed: " + str(purge)[:200]
                save(row)
                continue
            row.update(state="invalidated", invalidated_at=now.isoformat(),
                       revalidation={"status": purge.get("status"), "ok": True}, reason="")
            save(row)
            if not row.get("samples"):
                row.update(state="deployed_no_count_change", reason="receipt only; no popularity field changed")
                save(row)
                continue
            ok, evidence = _readback(fetch, git, row["merge_sha"], row["samples"])
            if not ok:
                row["reason"] = evidence["reason"]
                save(row)
                continue
            row.update(state="readback_verified", readback=evidence, reason="")
            save(row)
    return [{"pr_url": row.get("pr_url"), "state": row.get("state"),
             "reason": row.get("reason", "")}
            for row in deliveries if isinstance(row, dict)]
