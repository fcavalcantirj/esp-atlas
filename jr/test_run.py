"""Tests for run.py's board-batch resilience (JR.md / SPEC-espatlas-jr.md §3a): a Groq
non-retryable `tool_use_failed` on one board (root-caused to the board agent lacking a tool to
discover valid soc/module ids) must not abort the rest of the batch — boards_batch()'s per-board
try/except must catch it and move on. Network/model are always mocked; no live Groq call.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent
import run
import tools
from agno.exceptions import ModelProviderError


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
