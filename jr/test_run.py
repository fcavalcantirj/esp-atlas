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
