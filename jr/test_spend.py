"""Tests for tools.record_spend's model-aware pricing (hardening for a PAID drafter: before this,
month_spend() was priced with one fixed Groq-only rate no matter which model actually ran, so a
paid board drafter's spend would never be recorded correctly and the $5/month cap could never
trip). Network is never touched — spend.json is always isolated to a tmp file.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import models
import tools


@pytest.fixture(autouse=True)
def _isolated_spend(monkeypatch, tmp_path):
    """Every test here writes to a throwaway ledger — never the real jr/spend.json."""
    monkeypatch.setattr(tools, "_SPEND", tmp_path / "spend.json")


def test_record_spend_prices_a_known_paid_model():
    cost = tools.record_spend(1_000_000, 1_000_000, model="openai/gpt-4o-mini")
    assert cost == pytest.approx(0.15 + 0.60)


def test_record_spend_prices_the_groq_default_model_unchanged():
    """Backward compatibility: the old hardcoded Groq rate must still be exactly reproduced."""
    cost = tools.record_spend(1_000_000, 1_000_000, model="openai/gpt-oss-120b")
    assert cost == pytest.approx(0.15 + 0.60)


def test_record_spend_unknown_model_uses_conservative_default():
    cost = tools.record_spend(1_000_000, 1_000_000, model="some-vendor/mystery-model")
    assert cost == pytest.approx(1.00 + 3.00)


def test_record_spend_unknown_model_overestimates_relative_to_a_priced_one():
    """Same token count, unknown model costs more than the same call against a priced one — the
    conservative default trips the $5 cap EARLIER for an unrecognized model, never later."""
    priced_cost = tools.record_spend(1_000_000, 0, model="openai/gpt-4o-mini")
    unpriced_delta = tools.record_spend(1_000_000, 0, model="another-unpriced/model") - priced_cost
    assert unpriced_delta > priced_cost


def test_record_spend_strips_provider_prefix():
    cost = tools.record_spend(1_000_000, 1_000_000, model="openrouter:openai/gpt-4o-mini")
    assert cost == pytest.approx(0.15 + 0.60)


def test_record_spend_default_model_reads_JR_BOARD_MODEL_env(monkeypatch):
    monkeypatch.setenv("JR_BOARD_MODEL", "openrouter:openai/gpt-4o-mini")
    cost = tools.record_spend(1_000_000, 1_000_000)
    assert cost == pytest.approx(0.15 + 0.60)


def test_record_spend_default_model_falls_back_when_env_unset(monkeypatch):
    monkeypatch.delenv("JR_BOARD_MODEL", raising=False)
    cost = tools.record_spend(1_000_000, 1_000_000)
    assert cost == pytest.approx(0.15 + 0.60)  # models.DEFAULT_BOARD_MODEL -> groq gpt-oss-120b


def test_record_spend_accumulates_cumulative_cost_across_mixed_model_calls():
    tools.record_spend(1_000_000, 0, model="openai/gpt-oss-120b")   # $0.15
    tools.record_spend(0, 1_000_000, model="openai/gpt-4o-mini")    # $0.60
    assert tools.month_spend() == pytest.approx(0.75)


def test_default_board_model_is_priced_in_the_table():
    """A sanity check that keeps this test file honest if DEFAULT_BOARD_MODEL is ever repointed:
    the fallback used by record_spend()'s default path must resolve to a priced entry."""
    _, model_id = models.parse_model_spec(models.DEFAULT_BOARD_MODEL)
    assert model_id in tools.PRICE_PER_MTOK
