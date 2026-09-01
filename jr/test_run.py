"""Tests for run.py's board-batch resilience (JR.md / SPEC-espatlas-jr.md §3a): a Groq
non-retryable `tool_use_failed` on one board (root-caused to the board agent lacking a tool to
discover valid soc/module ids) must not abort the rest of the batch — boards_batch()'s per-board
try/except must catch it and move on. Network/model are always mocked; no live Groq call.
"""
import logging
import sys
from pathlib import Path

import pytest

pytest.importorskip("agno")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent
import run
import tools
from agno.exceptions import ModelProviderError


@pytest.fixture(autouse=True)
def _isolated_spend(monkeypatch, tmp_path):
    """Every boards_batch() call now records real spend as a side effect — isolate the ledger so
    no test in this module ever touches the real jr/spend.json."""
    monkeypatch.setattr(tools, "_SPEND", tmp_path / "spend.json")


class _FakeBoardAgent:
    """Stands in for make_jr_board(session_id).run(...) — either raises the exact provider error
    a weak model triggers by calling an unavailable tool, or (simulating a clean author) writes a
    board dir directly, the way a real agent run would via author_board()."""

    def __init__(self, board_to_create=None):
        self._board_to_create = board_to_create

    def run(self, msg):
        if self._board_to_create is None:
            raise ModelProviderError(
                message="Error code: 400 - tool_use_failed: 'list_directory' is not a valid tool",
                status_code=400, model_name="groq", model_id="openai/gpt-oss-120b",
            )
        brand, board_id = self._board_to_create
        d = tools.BOARDS_DIR / brand / board_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "board.md").write_text(
            "---\n"
            f"id: {board_id}\n"
            "type: board\n"
            f"brand: {brand}\n"
            "name: Fake Board\n"
            "soc: esp32-c5\n"
            "sources:\n"
            "- field: '*'\n"
            "  url: https://example.com\n"
            "  verified: '2026-08-28'\n"
            "---\n\nx\n"
        )
        return None


def test_boards_batch_survives_tool_use_failed_on_one_board(monkeypatch, tmp_path):
    boards_dir = tmp_path / "boards"
    monkeypatch.setattr(tools, "BOARDS_DIR", boards_dir)
    monkeypatch.setattr(tools, "coverage_backlog", lambda: [
        {"name": "Board A", "vendor": "V", "url": "https://a.example.com"},
        {"name": "Board B", "vendor": "V", "url": "https://b.example.com"},
    ])
    monkeypatch.setattr(tools, "board_triple_validate", lambda board_id: {"pass": True})
    monkeypatch.setattr(run, "_oracle_check", lambda brand, board_id: {"approve": True, "issues": [], "notes": ""})
    monkeypatch.setattr(tools, "open_board_batch_pr",
                        lambda boards, label, base="main": {"ok": True, "pr_url": "https://pr.example/1",
                                                            "count": len(boards)})
    monkeypatch.setattr(run.notify, "send_telegram", lambda text: {"ok": True})

    calls = []

    def fake_make_jr_board(session_id):
        calls.append(session_id)
        if len(calls) == 1:
            return _FakeBoardAgent(board_to_create=None)     # board #1: simulated tool_use_failed
        return _FakeBoardAgent(board_to_create=("vendorx", "board-b"))   # board #2: authors cleanly

    monkeypatch.setattr(agent, "make_jr_board", fake_make_jr_board)

    result = run.boards_batch(n=2, label="test-batch")

    assert len(calls) == 2                        # the crash on board #1 did not abort the batch
    assert result["action"] == "batch"
    assert result["boards"] == ["board-b"]         # only the surviving board is proposed


def test_boards_batch_all_boards_failing_reports_none(monkeypatch, tmp_path):
    boards_dir = tmp_path / "boards"
    monkeypatch.setattr(tools, "BOARDS_DIR", boards_dir)
    monkeypatch.setattr(tools, "coverage_backlog", lambda: [
        {"name": "Board A", "vendor": "V", "url": "https://a.example.com"},
        {"name": "Board B", "vendor": "V", "url": "https://b.example.com"},
    ])
    sent = []
    monkeypatch.setattr(run.notify, "send_telegram", lambda text: sent.append(text) or {"ok": True})
    monkeypatch.setattr(agent, "make_jr_board",
                        lambda session_id: _FakeBoardAgent(board_to_create=None))

    result = run.boards_batch(n=2, label="test-batch")

    assert result == {"action": "none"}
    assert sent                                    # Jr still nudges "nothing today"


# ─────────────── boards_batch — oracle-review quality gate (the MagTag guard gap) ───────────────

def _write_fake_board(boards_dir, brand, board_id, ref_line):
    d = boards_dir / brand / board_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "board.md").write_text(
        "---\n"
        f"id: {board_id}\n"
        "type: board\n"
        f"brand: {brand}\n"
        "name: Fake Board\n"
        f"{ref_line}\n"
        "sources:\n"
        "- field: '*'\n"
        "  url: https://example.com\n"
        "  verified: '2026-08-28'\n"
        "---\n\nx\n"
    )


def test_boards_batch_does_not_propose_a_board_the_oracle_rejects(monkeypatch, tmp_path):
    """Simulates the MagTag esp32-wrover-e case: the oracle flags a wrong chip family, and the
    board must be cleaned up and never bundled into the PR, even though board_triple_validate
    (mocked here) would have passed it."""
    boards_dir = tmp_path / "boards"
    monkeypatch.setattr(tools, "BOARDS_DIR", boards_dir)
    monkeypatch.setattr(tools, "coverage_backlog", lambda: [
        {"name": "MagTag", "vendor": "Adafruit", "url": "https://a.example.com"},
    ])
    monkeypatch.setattr(tools, "board_triple_validate", lambda board_id: {"pass": True})
    monkeypatch.setattr(tools, "fetch_url", lambda url: {"url": url, "text": "Powered by ESP32-S2."})
    monkeypatch.setattr(tools, "oracle_review", lambda md, page, schema: {
        "approve": False,
        "issues": ["module esp32-wrover-e is a classic ESP32; the page names the ESP32-S2"],
        "notes": "wrong chip family",
    })
    pr_calls = []
    monkeypatch.setattr(tools, "open_board_batch_pr", lambda boards, label, base="main": pr_calls.append(boards))
    monkeypatch.setattr(run.notify, "send_telegram", lambda text: {"ok": True})

    def fake_make_jr_board(session_id):
        _write_fake_board(boards_dir, "adafruit", "magtag", "module: esp32-wrover-e")
        return _FakeBoardAgent(board_to_create=("adafruit", "magtag"))

    monkeypatch.setattr(agent, "make_jr_board", fake_make_jr_board)

    result = run.boards_batch(n=1, label="test-batch")

    assert result == {"action": "none"}
    assert not pr_calls                                          # never proposed
    assert not (boards_dir / "adafruit" / "magtag").exists()      # cleaned up


def test_boards_batch_proposes_a_board_the_oracle_approves(monkeypatch, tmp_path):
    boards_dir = tmp_path / "boards"
    monkeypatch.setattr(tools, "BOARDS_DIR", boards_dir)
    monkeypatch.setattr(tools, "coverage_backlog", lambda: [
        {"name": "MagTag", "vendor": "Adafruit", "url": "https://a.example.com"},
    ])
    monkeypatch.setattr(tools, "board_triple_validate", lambda board_id: {"pass": True})
    monkeypatch.setattr(tools, "fetch_url", lambda url: {"url": url, "text": "Powered by ESP32-S2."})
    monkeypatch.setattr(tools, "oracle_review",
                        lambda md, page, schema: {"approve": True, "issues": [], "notes": "matches the page"})
    monkeypatch.setattr(tools, "open_board_batch_pr",
                        lambda boards, label, base="main": {"ok": True, "pr_url": "https://pr.example/1",
                                                            "count": len(boards)})
    monkeypatch.setattr(run.notify, "send_telegram", lambda text: {"ok": True})

    def fake_make_jr_board(session_id):
        _write_fake_board(boards_dir, "adafruit", "magtag", "soc: esp32-s2")
        return _FakeBoardAgent(board_to_create=("adafruit", "magtag"))

    monkeypatch.setattr(agent, "make_jr_board", fake_make_jr_board)

    result = run.boards_batch(n=1, label="test-batch")

    assert result["action"] == "batch"
    assert result["boards"] == ["magtag"]
    assert (boards_dir / "adafruit" / "magtag").exists()


def test_boards_batch_retries_once_when_oracle_rejects_then_approves_the_fix(monkeypatch, tmp_path):
    """Oracle rejects the first draft (wrong chip); the drafter is fed the issues, fixes it, and
    the SECOND oracle check approves — the board is proposed. At most ONE retry."""
    boards_dir = tmp_path / "boards"
    monkeypatch.setattr(tools, "BOARDS_DIR", boards_dir)
    monkeypatch.setattr(tools, "coverage_backlog", lambda: [
        {"name": "MagTag", "vendor": "Adafruit", "url": "https://a.example.com"},
    ])
    monkeypatch.setattr(tools, "board_triple_validate", lambda board_id: {"pass": True})
    monkeypatch.setattr(tools, "fetch_url", lambda url: {"url": url, "text": "Powered by ESP32-S2."})

    oracle_calls = []

    def fake_oracle_review(board_md_text, page_text, schema_summary):
        oracle_calls.append(board_md_text)
        if "esp32-wrover-e" in board_md_text:
            return {"approve": False, "issues": ["wrong chip family"], "notes": ""}
        return {"approve": True, "issues": [], "notes": "fixed"}

    monkeypatch.setattr(tools, "oracle_review", fake_oracle_review)
    monkeypatch.setattr(tools, "open_board_batch_pr",
                        lambda boards, label, base="main": {"ok": True, "pr_url": "https://pr.example/1",
                                                            "count": len(boards)})
    monkeypatch.setattr(run.notify, "send_telegram", lambda text: {"ok": True})

    class _FixingBoardAgent:
        def __init__(self):
            self.runs = 0

        def run(self, msg):
            self.runs += 1
            ref = "module: esp32-wrover-e" if self.runs == 1 else "soc: esp32-s2"
            _write_fake_board(boards_dir, "adafruit", "magtag", ref)
            return None

    monkeypatch.setattr(agent, "make_jr_board", lambda session_id: _FixingBoardAgent())

    result = run.boards_batch(n=1, label="test-batch")

    assert len(oracle_calls) == 2                       # rejected once, then re-checked after the retry
    assert result["action"] == "batch"
    assert result["boards"] == ["magtag"]


def test_boards_batch_stops_at_month_spend_cap(monkeypatch, tmp_path):
    boards_dir = tmp_path / "boards"
    monkeypatch.setattr(tools, "BOARDS_DIR", boards_dir)
    monkeypatch.setattr(tools, "month_spend", lambda: tools.MONTHLY_CAP_USD)
    monkeypatch.setattr(run.notify, "send_telegram", lambda text: {"ok": True})
    calls = []
    monkeypatch.setattr(agent, "make_jr_board", lambda session_id: calls.append(session_id))

    result = run.boards_batch(n=2, label="test-batch")

    assert not calls                                     # never even asked for a candidate
    assert result == {"action": "none"}


# ─────────────── boards_batch — real per-model spend accounting (paid drafter hardening) ───────────────

class _FakeMetrics:
    def __init__(self, input_tokens=0, output_tokens=0):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _FakeResp:
    def __init__(self, metrics=None):
        self.metrics = metrics


class _MeteredBoardAgent:
    """Stands in for a real Agno agent whose .run() returns a response carrying .metrics — the
    shape drain_batch() already relies on, now mirrored for the board lane."""

    def __init__(self, brand, board_id, input_tokens, output_tokens):
        self._brand, self._board_id = brand, board_id
        self._metrics = _FakeMetrics(input_tokens, output_tokens)

    def run(self, msg):
        _write_fake_board(tools.BOARDS_DIR, self._brand, self._board_id, "soc: esp32-c5")
        return _FakeResp(self._metrics)


def _approve_everything(monkeypatch):
    monkeypatch.setattr(tools, "board_triple_validate", lambda board_id: {"pass": True})
    monkeypatch.setattr(run, "_oracle_check",
                        lambda brand, board_id: {"approve": True, "issues": [], "notes": ""})
    monkeypatch.setattr(tools, "open_board_batch_pr",
                        lambda boards, label, base="main": {"ok": True, "pr_url": "https://pr.example/1",
                                                            "count": len(boards)})
    monkeypatch.setattr(run.notify, "send_telegram", lambda text: {"ok": True})


def test_boards_batch_records_spend_every_iteration(monkeypatch, tmp_path):
    boards_dir = tmp_path / "boards"
    monkeypatch.setattr(tools, "BOARDS_DIR", boards_dir)
    monkeypatch.setattr(tools, "coverage_backlog", lambda: [
        {"name": "Board A", "vendor": "V", "url": "https://a.example.com"},
    ])
    monkeypatch.setenv("JR_BOARD_MODEL", "openrouter:openai/gpt-4o-mini")
    _approve_everything(monkeypatch)
    monkeypatch.setattr(agent, "make_jr_board",
                        lambda session_id: _MeteredBoardAgent("vendorx", "board-a", 1_000_000, 1_000_000))

    assert tools.month_spend() == 0.0
    result = run.boards_batch(n=1, label="test-batch")

    assert result["action"] == "batch"
    assert tools.month_spend() == pytest.approx(0.75)   # 1M in @$0.15/Mtok + 1M out @$0.60/Mtok


def test_boards_batch_stops_once_accumulated_spend_reaches_cap(monkeypatch, tmp_path):
    boards_dir = tmp_path / "boards"
    monkeypatch.setattr(tools, "BOARDS_DIR", boards_dir)
    monkeypatch.setattr(tools, "coverage_backlog", lambda: [
        {"name": "Board A", "vendor": "V", "url": "https://a.example.com"},
        {"name": "Board B", "vendor": "V", "url": "https://b.example.com"},
        {"name": "Board C", "vendor": "V", "url": "https://c.example.com"},
    ])
    monkeypatch.setenv("JR_BOARD_MODEL", "openrouter:openai/gpt-4o-mini")
    _approve_everything(monkeypatch)

    calls = []

    def fake_make_jr_board(session_id):
        calls.append(session_id)
        # 10M tokens each way @ gpt-4o-mini pricing = $1.50 + $6.00 = $7.50 -- blows the $5 cap
        # on the very first iteration.
        return _MeteredBoardAgent("vendorx", f"board-{len(calls)}", 10_000_000, 10_000_000)

    monkeypatch.setattr(agent, "make_jr_board", fake_make_jr_board)

    result = run.boards_batch(n=3, label="test-batch")

    assert len(calls) == 1                          # the 2nd/3rd iterations never even started
    assert tools.month_spend() >= tools.MONTHLY_CAP_USD
    assert result["action"] == "batch"               # the one board authored before the cap tripped still ships


def test_unknown_model_spend_trips_cap_faster_than_a_priced_one(monkeypatch, tmp_path):
    """An unrecognized JR_BOARD_MODEL must OVER-price (never under), so the cap trips at least as
    early as it would for a known model at the same token volume."""
    boards_dir = tmp_path / "boards"
    monkeypatch.setattr(tools, "BOARDS_DIR", boards_dir)
    monkeypatch.setattr(tools, "coverage_backlog", lambda: [
        {"name": "Board A", "vendor": "V", "url": "https://a.example.com"},
        {"name": "Board B", "vendor": "V", "url": "https://b.example.com"},
    ])
    monkeypatch.setenv("JR_BOARD_MODEL", "openrouter:some-vendor/unpriced-model")
    _approve_everything(monkeypatch)
    calls = []

    def fake_make_jr_board(session_id):
        calls.append(session_id)
        return _MeteredBoardAgent("vendorx", f"board-{len(calls)}", 2_000_000, 1_000_000)

    monkeypatch.setattr(agent, "make_jr_board", fake_make_jr_board)

    run.boards_batch(n=3, label="test-batch")

    # 2M in @$1.00/Mtok + 1M out @$3.00/Mtok = $5.00 -- caps out on the first iteration alone
    assert tools.month_spend() == pytest.approx(5.0)
    assert len(calls) == 1


# ─────────────── boards_batch — crash cleanup (no orphan board dirs) ───────────────

class _CrashingBoardAgent:
    """Simulates a drafter that authors a board dir (a real author_board() call succeeded) and
    THEN crashes on a later tool call in the same .run() — the partial dir must never survive."""

    def __init__(self, brand, board_id):
        self._brand, self._board_id = brand, board_id

    def run(self, msg):
        _write_fake_board(tools.BOARDS_DIR, self._brand, self._board_id, "soc: esp32-c5")
        raise RuntimeError("simulated mid-run crash after authoring")


def test_boards_batch_crash_mid_iteration_leaves_no_orphan_board_dir(monkeypatch, tmp_path):
    boards_dir = tmp_path / "boards"
    monkeypatch.setattr(tools, "BOARDS_DIR", boards_dir)
    monkeypatch.setattr(tools, "coverage_backlog", lambda: [
        {"name": "Board A", "vendor": "V", "url": "https://a.example.com"},
    ])
    monkeypatch.setattr(run.notify, "send_telegram", lambda text: {"ok": True})
    monkeypatch.setattr(agent, "make_jr_board",
                        lambda session_id: _CrashingBoardAgent("vendorx", "board-crash"))

    result = run.boards_batch(n=1, label="test-batch")

    assert result == {"action": "none"}
    assert not (boards_dir / "vendorx" / "board-crash").exists()   # no orphan left behind
    assert not any(boards_dir.rglob("board.md"))                   # nothing at all survives


# ─────────────── boards_batch — observability (legible disposition per candidate) ───────────────

def test_boards_batch_logs_board_pick_oracle_verdict_triple_validate_and_disposition(
        monkeypatch, tmp_path, caplog):
    boards_dir = tmp_path / "boards"
    monkeypatch.setattr(tools, "BOARDS_DIR", boards_dir)
    monkeypatch.setattr(tools, "coverage_backlog", lambda: [
        {"name": "Board A", "vendor": "V", "url": "https://a.example.com"},
    ])
    _approve_everything(monkeypatch)
    monkeypatch.setattr(agent, "make_jr_board",
                        lambda session_id: _MeteredBoardAgent("vendorx", "board-a", 100, 100))

    with caplog.at_level(logging.INFO, logger="run"):
        result = run.boards_batch(n=1, label="test-batch")

    assert result["action"] == "batch"
    text = "\n".join(r.message for r in caplog.records)
    assert "vendorx/board-a" in text                    # board picked is legible
    assert "approve=True" in text                        # oracle verdict is legible
    assert "board_triple_validate" in text and "pass=True" in text
    assert "proposed" in text                            # final disposition is legible


# ─────────────── _oracle_check — oracle spend accounting (paid-oracle hardening) ───────────────

def _write_magtag_board(boards_dir):
    d = boards_dir / "adafruit" / "magtag"
    d.mkdir(parents=True, exist_ok=True)
    (d / "board.md").write_text(
        "---\nid: magtag\ntype: board\nbrand: adafruit\nname: Adafruit MagTag\nsoc: esp32-s2\n"
        "sources:\n- field: '*'\n  url: https://example.com\n  verified: '2026-08-28'\n---\n\nx\n"
    )


def test_oracle_check_records_spend_from_oracle_usage_tokens(monkeypatch, tmp_path):
    boards_dir = tmp_path / "boards"
    _write_magtag_board(boards_dir)
    monkeypatch.setattr(tools, "BOARDS_DIR", boards_dir)
    monkeypatch.setattr(tools, "fetch_url", lambda url: {"url": url, "text": "ESP32-S2 wireless module"})
    monkeypatch.setattr(tools, "oracle_review", lambda md, page, schema: {
        "approve": True, "issues": [], "notes": "ok",
        "usage": {"prompt_tokens": 1000, "completion_tokens": 500},
    })
    monkeypatch.setenv("JR_ORACLE_MODEL", "openrouter:z-ai/glm-5.2:free")

    run._oracle_check("adafruit", "magtag")

    price_in, price_out = tools._price_per_token("z-ai/glm-5.2:free")
    assert tools.month_spend() == pytest.approx(1000 * price_in + 500 * price_out)


def test_oracle_check_records_spend_with_oracle_model_stripped_of_provider_prefix(monkeypatch, tmp_path):
    boards_dir = tmp_path / "boards"
    _write_magtag_board(boards_dir)
    monkeypatch.setattr(tools, "BOARDS_DIR", boards_dir)
    monkeypatch.setattr(tools, "fetch_url", lambda url: {"url": url, "text": "ESP32-S2 wireless module"})
    monkeypatch.setattr(tools, "oracle_review", lambda md, page, schema: {
        "approve": True, "issues": [], "notes": "ok",
        "usage": {"prompt_tokens": 42, "completion_tokens": 7},
    })
    monkeypatch.setenv("JR_ORACLE_MODEL", "groq:llama-3.1-70b")
    calls = []
    monkeypatch.setattr(tools, "record_spend", lambda *a, **k: calls.append((a, k)) or 0.0)

    run._oracle_check("adafruit", "magtag")

    assert calls == [((42, 7), {"model": "llama-3.1-70b"})]


def test_oracle_check_records_zero_spend_when_usage_absent(monkeypatch, tmp_path):
    boards_dir = tmp_path / "boards"
    _write_magtag_board(boards_dir)
    monkeypatch.setattr(tools, "BOARDS_DIR", boards_dir)
    monkeypatch.setattr(tools, "fetch_url", lambda url: {"url": url, "text": "ESP32-S2 wireless module"})
    monkeypatch.setattr(tools, "oracle_review",
                        lambda md, page, schema: {"approve": True, "issues": [], "notes": "ok"})
    calls = []
    monkeypatch.setattr(tools, "record_spend", lambda *a, **k: calls.append((a, k)) or 0.0)

    run._oracle_check("adafruit", "magtag")

    assert calls[0][0] == (0, 0)


def test_oracle_check_does_not_record_spend_when_board_md_missing(monkeypatch, tmp_path):
    boards_dir = tmp_path / "boards"
    monkeypatch.setattr(tools, "BOARDS_DIR", boards_dir)
    calls = []
    monkeypatch.setattr(tools, "record_spend", lambda *a, **k: calls.append((a, k)) or 0.0)

    result = run._oracle_check("adafruit", "does-not-exist")

    assert result["approve"] is False
    assert not calls


# ─────────────── run.py __main__ CLI — default INFO logging ───────────────

def test_run_cli_configures_info_logging_before_dispatching_the_job(monkeypatch):
    calls = []
    monkeypatch.setattr(run.logging, "basicConfig", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(sys, "argv", ["run.py", "noop_job"])
    monkeypatch.setitem(run.__dict__, "noop_job", lambda: {"action": "none"})

    run._run_cli()

    assert calls == [{"level": logging.INFO}]


def test_run_cli_dispatches_to_the_named_job(monkeypatch, capsys):
    monkeypatch.setattr(run.logging, "basicConfig", lambda **kwargs: None)
    monkeypatch.setattr(sys, "argv", ["run.py", "fake_job"])
    monkeypatch.setitem(run.__dict__, "fake_job", lambda: {"action": "batch", "count": 1})

    run._run_cli()

    out = capsys.readouterr().out
    assert "fake_job" in out and "batch" in out


def test_run_cli_defaults_to_daily_job_when_no_argv(monkeypatch):
    monkeypatch.setattr(run.logging, "basicConfig", lambda **kwargs: None)
    monkeypatch.setattr(sys, "argv", ["run.py"])
    calls = []
    monkeypatch.setitem(run.__dict__, "daily", lambda: calls.append("daily") or {"action": "none"})

    run._run_cli()

    assert calls == ["daily"]


def test_boards_batch_logs_rejection_reason_when_triple_validate_fails(monkeypatch, tmp_path, caplog):
    boards_dir = tmp_path / "boards"
    monkeypatch.setattr(tools, "BOARDS_DIR", boards_dir)
    monkeypatch.setattr(tools, "coverage_backlog", lambda: [
        {"name": "Board A", "vendor": "V", "url": "https://a.example.com"},
    ])
    monkeypatch.setattr(tools, "board_triple_validate",
                        lambda board_id: {"pass": False, "gate3_integrity": ["bad ref"]})
    monkeypatch.setattr(run, "_oracle_check",
                        lambda brand, board_id: {"approve": True, "issues": [], "notes": ""})
    monkeypatch.setattr(run.notify, "send_telegram", lambda text: {"ok": True})
    monkeypatch.setattr(agent, "make_jr_board",
                        lambda session_id: _MeteredBoardAgent("vendorx", "board-a", 100, 100))

    with caplog.at_level(logging.INFO, logger="run"):
        result = run.boards_batch(n=1, label="test-batch")

    assert result == {"action": "none"}
    text = "\n".join(r.message for r in caplog.records)
    assert "rejected" in text and "board_triple_validate failed" in text


# ─────────────── boards_batch — informative Telegram notify (tried boards + reasons) ───────────────

def test_boards_batch_notifies_tried_boards_and_reasons_when_all_rejected(monkeypatch, tmp_path):
    """When 0 boards are proposed, the notify must say WHAT was tried and WHY, not just
    'nothing authorable this pass'."""
    boards_dir = tmp_path / "boards"
    monkeypatch.setattr(tools, "BOARDS_DIR", boards_dir)
    monkeypatch.setattr(tools, "coverage_backlog", lambda: [
        {"name": "Adafruit Metro ESP32-S2", "vendor": "Adafruit", "url": "https://a.example.com"},
        {"name": "Inkplate 6MOTION", "vendor": "Soldered", "url": "https://b.example.com"},
    ])
    monkeypatch.setattr(tools, "fetch_url", lambda url: {"url": url, "text": "irrelevant"})

    def fake_oracle_review(md, page, schema):
        if "adafruit-metro-esp32-s2" in md:
            return {"approve": False,
                    "issues": ["form_factor, dimensions_mm, io not supported by page"], "notes": ""}
        return {"approve": False,
                "issues": ["primary chip is STM32, ESP only co-processor"], "notes": ""}

    monkeypatch.setattr(tools, "oracle_review", fake_oracle_review)
    sent = []
    monkeypatch.setattr(run.notify, "send_telegram", lambda text: sent.append(text) or {"ok": True})

    calls = []

    def fake_make_jr_board(session_id):
        calls.append(session_id)
        if len(calls) == 1:   # make_jr_board is called once per outer iteration, not per retry
            return _FakeBoardAgent(board_to_create=("adafruit", "adafruit-metro-esp32-s2"))
        return _FakeBoardAgent(board_to_create=("soldered", "inkplate-6motion"))

    monkeypatch.setattr(agent, "make_jr_board", fake_make_jr_board)

    result = run.boards_batch(n=2, label="test-batch")

    assert result == {"action": "none"}
    assert len(sent) == 1
    msg = sent[0]
    assert "adafruit-metro-esp32-s2" in msg
    assert "form_factor, dimensions_mm, io not supported by page" in msg
    assert "inkplate-6motion" in msg
    assert "primary chip is STM32, ESP only co-processor" in msg
    assert "nothing authorable this pass" not in msg


class _NoOpBoardAgent:
    """Authors nothing at all (no dir, no crash) — the 'drafter authored nothing' disposition."""

    def run(self, msg):
        return None


def test_boards_batch_notify_truncates_tried_list_with_more_count(monkeypatch, tmp_path):
    boards_dir = tmp_path / "boards"
    monkeypatch.setattr(tools, "BOARDS_DIR", boards_dir)
    monkeypatch.setattr(tools, "coverage_backlog", lambda: [
        {"name": f"Board {i}", "vendor": "V", "url": f"https://{i}.example.com"} for i in range(7)
    ])
    sent = []
    monkeypatch.setattr(run.notify, "send_telegram", lambda text: sent.append(text) or {"ok": True})
    monkeypatch.setattr(agent, "make_jr_board", lambda session_id: _NoOpBoardAgent())

    result = run.boards_batch(n=7, label="test-batch")

    assert result == {"action": "none"}
    msg = sent[0]
    assert "drafter authored nothing" in msg
    assert msg.count("candidate #") == 5
    assert "…and 2 more" in msg


def test_boards_batch_success_message_lists_board_and_pr_link(monkeypatch, tmp_path):
    boards_dir = tmp_path / "boards"
    monkeypatch.setattr(tools, "BOARDS_DIR", boards_dir)
    monkeypatch.setattr(tools, "coverage_backlog", lambda: [
        {"name": "MagTag", "vendor": "Adafruit", "url": "https://a.example.com"},
    ])
    monkeypatch.setattr(tools, "board_triple_validate", lambda board_id: {"pass": True})
    monkeypatch.setattr(tools, "fetch_url", lambda url: {"url": url, "text": "Powered by ESP32-S2."})
    monkeypatch.setattr(tools, "oracle_review",
                        lambda md, page, schema: {"approve": True, "issues": [], "notes": "matches"})
    monkeypatch.setattr(tools, "open_board_batch_pr",
                        lambda boards, label, base="main": {"ok": True, "pr_url": "https://pr.example/1",
                                                            "count": len(boards)})
    sent = []
    monkeypatch.setattr(run.notify, "send_telegram", lambda text: sent.append(text) or {"ok": True})

    def fake_make_jr_board(session_id):
        _write_fake_board(boards_dir, "adafruit", "magtag", "soc: esp32-s2")
        return _FakeBoardAgent(board_to_create=("adafruit", "magtag"))

    monkeypatch.setattr(agent, "make_jr_board", fake_make_jr_board)

    result = run.boards_batch(n=1, label="test-batch")

    assert result["action"] == "batch"
    msg = sent[0]
    assert "magtag" in msg
    assert "https://pr.example/1" in msg


def test_boards_batch_success_message_notes_rejections_on_partial_pass(monkeypatch, tmp_path):
    """A partial pass (some proposed, some rejected) must stay legible — the success message
    still lists the proposed board(s) + PR link, plus a one-line note about the rejections."""
    boards_dir = tmp_path / "boards"
    monkeypatch.setattr(tools, "BOARDS_DIR", boards_dir)
    monkeypatch.setattr(tools, "coverage_backlog", lambda: [
        {"name": "Board A", "vendor": "V", "url": "https://a.example.com"},
        {"name": "Board B", "vendor": "V", "url": "https://b.example.com"},
    ])
    monkeypatch.setattr(tools, "fetch_url", lambda url: {"url": url, "text": "irrelevant"})
    monkeypatch.setattr(tools, "board_triple_validate", lambda board_id: {"pass": True})

    def fake_oracle_review(md, page, schema):
        if "board-a" in md:
            return {"approve": False, "issues": ["wrong chip"], "notes": ""}
        return {"approve": True, "issues": [], "notes": "ok"}

    monkeypatch.setattr(tools, "oracle_review", fake_oracle_review)
    monkeypatch.setattr(tools, "open_board_batch_pr",
                        lambda boards, label, base="main": {"ok": True, "pr_url": "https://pr.example/1",
                                                            "count": len(boards)})
    sent = []
    monkeypatch.setattr(run.notify, "send_telegram", lambda text: sent.append(text) or {"ok": True})

    calls = []

    def fake_make_jr_board(session_id):
        calls.append(session_id)
        if len(calls) == 1:   # make_jr_board is called once per outer iteration, not per retry
            return _FakeBoardAgent(board_to_create=("vendorx", "board-a"))
        return _FakeBoardAgent(board_to_create=("vendorx", "board-b"))

    monkeypatch.setattr(agent, "make_jr_board", fake_make_jr_board)

    result = run.boards_batch(n=2, label="test-batch")

    assert result["action"] == "batch"
    assert result["boards"] == ["board-b"]
    msg = sent[0]
    assert "board-b" in msg
    assert "https://pr.example/1" in msg
    assert "1 candidate(s) rejected" in msg
