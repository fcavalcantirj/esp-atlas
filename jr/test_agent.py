"""Tests for agent.py's model wiring: make_jr_board() must build its drafter model from
JR_BOARD_MODEL via the models.py factory (default unchanged: free Groq gpt-oss-120b). No
network — building an Agno model object doesn't call out, it only reads env vars.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent


def test_make_jr_board_defaults_to_free_groq_model(monkeypatch):
    monkeypatch.delenv("JR_BOARD_MODEL", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "g-key")
    from agno.models.groq import Groq

    a = agent.make_jr_board("t-default")

    assert isinstance(a.model, Groq)
    assert a.model.id == "openai/gpt-oss-120b"


def test_make_jr_board_honors_jr_board_model_override(monkeypatch):
    monkeypatch.setenv("JR_BOARD_MODEL", "openrouter:some-vendor/some-model")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    from agno.models.openrouter import OpenRouter

    a = agent.make_jr_board("t-override")

    assert isinstance(a.model, OpenRouter)
    assert a.model.id == "some-vendor/some-model"
    assert a.model.api_key == "or-key"
