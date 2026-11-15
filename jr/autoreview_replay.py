"""EspAtlas Jr — replay Jr's real edge pipeline on the labelled history (SPEC-jr-review-routing.md §7).

The measuring stick for "the algorithm must clearly improve": for every firmware in
jr/fixtures/autoreview/cases.json it runs Jr's REAL code — the admit scorer (`scorer.score_entry` on the
repo metadata `drain.default_fetch_meta` builds) and boardmap's `derive.derive` + `derive.resolve` +
`writers.plan_recipes` — and reports which board edges Jr would write, how, and what the evidence checker
(`jr/autoreview.check`) says about each. Live GitHub answers are recorded once into a cassette directory
and replayed offline after that, so a before/after comparison runs on identical inputs.

    python3 jr/autoreview_replay.py --cassettes DIR [--record] [--out metrics.json]

M1 wrong edges written · M2 correct edges found · M3 Cardputer-Adv edges for the ADV-only firmware ·
M4 share of written edges the checker PASSes (auto-merge eligible).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

import autoreview
import board_alias
import derive
import scorer
import writers

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
CASES = HERE / "fixtures" / "autoreview" / "cases.json"


class Cassette:
    """Recorded GitHub answers for one repository: {"meta": {...}, "api": {path: json}, "raw": {url: text}}.
    Replay mode raises KeyError for anything not recorded, so a replay can never silently go live."""

    def __init__(self, path: Path, record: bool = False, live_meta=None, live_api=None, live_raw=None):
        self.path, self.record = path, record
        self.data = json.loads(path.read_text()) if path.exists() else {"meta": None, "api": {}, "raw": {}}
        self.live_meta = live_meta or (lambda url: __import__("drain").default_fetch_meta(url))
        self.live_api, self.live_raw = live_api or derive.default_api, live_raw or derive.default_raw

    def meta(self, url: str):
        if self.data["meta"] is None:
            if not self.record:
                raise KeyError(f"meta not recorded for {url}")
            self.data["meta"] = self.live_meta(url)
        return self.data["meta"]

    def api(self, path: str):
        if path not in self.data["api"]:
            if not self.record:
                raise KeyError(f"api not recorded: {path}")
            try:
                self.data["api"][path] = {"ok": self.live_api(path)}
            except Exception as e:  # noqa: BLE001 — an upstream error is part of the recording
                self.data["api"][path] = {"error": str(e)[:200]}
        rec = self.data["api"][path]
        if "error" in rec:
            raise RuntimeError(rec["error"])
        return rec["ok"]

    def raw(self, url: str):
        if url not in self.data["raw"]:
            if not self.record:
                raise KeyError(f"raw not recorded: {url}")
            self.data["raw"][url] = self.live_raw(url)
        return self.data["raw"][url]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, sort_keys=True))


def _cassette_path(dir_: Path, repo: str) -> Path:
    return dir_ / (hashlib.sha256(repo.lower().encode()).hexdigest()[:16] + ".json")


def _evidence(meta: dict, cas: Cassette, signals: list[dict]) -> dict:
    """What the checker reads: description, README, platformio.ini texts derive fetched, asset names."""
    pio = "\n".join(t for u, t in cas.data["raw"].items() if t and u.endswith("platformio.ini"))
    assets = []
    for path, rec in cas.data["api"].items():
        if "/releases" in path and isinstance(rec.get("ok"), (list, dict)):
            rels = rec["ok"] if isinstance(rec["ok"], list) else [rec["ok"]]
            assets += [a.get("name", "") for r in rels if isinstance(r, dict) for a in r.get("assets", [])]
    return {"description": (meta or {}).get("description") or "", "readme": (meta or {}).get("readme_body") or "",
            "platformio": pio, "assets": " ".join(dict.fromkeys(assets))}


def replay_firmware(case: dict, entry: dict | None, cas: Cassette, catalog: dict, gate: bool = False) -> dict:
    """{board: {"via": [...], "verdict": ..., "reason": ..., "written": bool}} for every edge Jr's real code
    would write. `gate=True` runs the production evidence gate (`writers.evidence_gate` on the admit edge,
    the evidence-aware `writers.plan_recipes` on boardmap's); False reproduces the algorithm without it."""
    url = f"https://github.com/{case['repo']}"
    meta = cas.meta(url) or {}            # repo fields + README: what the evidence gate reads
    edges: dict[str, dict] = {}
    if entry:
        # The admit stage scores on ONE `gh api repos/<o>/<r>` (stage_admit._meta_from_api): no README.
        import stage_admit
        try:
            admit_meta = stage_admit._meta_from_api(cas.api(f"repos/{case['repo']}"))
        except Exception:  # noqa: BLE001 — an unreadable repo scores as unresolved
            admit_meta = {"error": "unreadable"}
        res = scorer.score_entry(entry, admit_meta, set(), set(), {}, catalogued_token_sets=[])
        board = ((res.get("record") or {}).get("board")) if res.get("decision") == "authored" else None
        if board and gate:
            ev_text = {"description": " ".join(x for x in (entry.get("name"), admit_meta.get("description"),
                                                         entry.get("description")) if x),
                       "readme": meta.get("readme_body") or ""}
            board = writers.evidence_gate(board, ev_text, catalog)[0]
            for orig, _r in (writers.reverse_siblings({board}, ev_text, catalog) if board else []):
                edges.setdefault(orig, {"via": []})["via"].append("admit:both")
        if board:
            edges.setdefault(board, {"via": []})["via"].append("admit")
    d = derive.derive(case["repo"], api=cas.api, raw=cas.raw, max_calls=30, today="2026-11-15")
    res = derive.resolve(d, boards=catalog)
    ev = _evidence(meta, cas, d["signals"])
    with tempfile.TemporaryDirectory() as tmp:
        plan = writers.plan_recipes(case["firmware"], res, root=Path(tmp),
                                    board_soc=lambda b: (catalog.get(b) or {}).get("soc"),
                                    evidence=ev if gate else None, catalog=catalog if gate else None)
    for rid, board, _soc, sigs in plan["new"]:
        edges.setdefault(board, {"via": []})["via"].append("boardmap:" + ",".join(sorted({s["kind"] for s in sigs})))
    out = {}
    for board, e in edges.items():
        v = autoreview.check(board, ev, catalog)
        out[board] = {"via": e["via"], "verdict": v.verdict, "reason": (v.reasons or [""])[0], "written": True}
    return out


ADV_ONLY = ("advanceos-for-cardputer ask-master bitmap16dx cardputer-abs-b-radar cardputer-iss-tracker cardputergpsmap "
            "cypher-puter-os daoa-mini-cardputeradv flipper-zero-esp32-adv m5stack-cardputer-sparks m5stack-cardputer-ssh "
            "meshcore-cardputer-adv meshtastic-adv microgroove miniacid picoware raising-hell-cardputer ratcom stellar-map "
            "tagtinker-adv vanguard zx-spectrum-cardputer-internal").split()


def metrics(cases: list[dict], results: dict) -> dict:
    """results: {firmware: {board: edge}}."""
    wrong = [c for c in cases if c["label"] == "wrong"]
    correct = [c for c in cases if c["label"] == "correct"]
    def written(c):
        e = results.get(c["firmware"], {}).get(c["board"])
        return bool(e and e["written"])
    all_edges = [e for fw in results.values() for e in fw.values() if e["written"]]
    return {
        "M1_wrong_edges_written": sum(written(c) for c in wrong), "M1_of": len(wrong),
        "M1_wrong_written_as_PASS": sum(1 for c in wrong if written(c) and results[c["firmware"]][c["board"]]["verdict"] == autoreview.PASS),
        "M2_correct_edges_found": sum(written(c) for c in correct), "M2_of": len(correct),
        "M3_adv_edges_written": sum(1 for f in ADV_ONLY if (results.get(f, {}).get("m5cardputer-adv") or {}).get("written")),
        "M3_of": len(ADV_ONLY),
        "M4_pass_share_of_written": round(sum(1 for e in all_edges if e["verdict"] == autoreview.PASS) / len(all_edges), 3) if all_edges else 0.0,
        "edges_written": len(all_edges),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cassettes", required=True, type=Path)
    ap.add_argument("--record", action="store_true", help="fetch what is missing from GitHub (needs gh auth)")
    ap.add_argument("--launcher", type=Path, help="a launcherhub list JSON, for the admit path's entries")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--gate", action="store_true", help="run with the production evidence gate (step 1)")
    args = ap.parse_args(argv)
    cases = json.loads(CASES.read_text())
    launcher = json.loads(args.launcher.read_text()) if args.launcher else []
    by_repo = {}
    for e in launcher:
        gh = str(e.get("github") or "").lower().rstrip("/").replace("https://github.com/", "")
        if gh:
            by_repo.setdefault("/".join(gh.split("/")[:2]), e)
    board_alias.clear_caches()
    catalog = board_alias.atlas_boards()
    results, errors = {}, []
    for repo in sorted({c["repo"] for c in cases}):
        firmware = next(c["firmware"] for c in cases if c["repo"] == repo)
        cas = Cassette(_cassette_path(args.cassettes, repo), record=args.record)
        try:
            results[firmware] = replay_firmware({"repo": repo, "firmware": firmware}, by_repo.get(repo.lower()), cas,
                                                catalog, gate=args.gate)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{firmware}: {type(e).__name__}: {e}")
        if args.record:
            cas.save()
    report = {"metrics": metrics(cases, results), "errors": errors, "edges": results}
    text = json.dumps(report, indent=1, sort_keys=True)
    (args.out.write_text(text + "\n") if args.out else print(text))
    print(json.dumps(report["metrics"]), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
