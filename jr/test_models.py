"""Tests for the model factory (JR_BOARD_MODEL / JR_ORACLE_MODEL configurability): spec
parsing, provider -> base_url/api-key resolution, and the Agno model objects it builds for
make_jr_board. No network — nothing here calls a real model.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import models


def test_default_models_are_free_tier():
    assert models.DEFAULT_BOARD_MODEL == "groq:openai/gpt-oss-120b"
    assert models.DEFAULT_ORACLE_MODEL == "openrouter:z-ai/glm-5.2:free"


def test_parse_model_spec_splits_on_first_colon_only():
    # an OpenRouter free-tier model id can itself contain a colon
    assert models.parse_model_spec("openrouter:z-ai/glm-5.2:free") == ("openrouter", "z-ai/glm-5.2:free")
    assert models.parse_model_spec("groq:openai/gpt-oss-120b") == ("groq", "openai/gpt-oss-120b")


def test_parse_model_spec_rejects_missing_colon():
    with pytest.raises(ValueError, match="bad model spec"):
        models.parse_model_spec("groq-only-no-colon")


def test_parse_model_spec_rejects_empty_model_id():
    with pytest.raises(ValueError, match="bad model spec"):
        models.parse_model_spec("groq:")


def test_client_config_groq_selects_groq_base_url_and_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "g-key")
    cfg = models.client_config("groq:openai/gpt-oss-120b")

    assert cfg == {
        "provider": "groq", "model_id": "openai/gpt-oss-120b",
        "base_url": "https://api.groq.com/openai/v1", "api_key": "g-key",
    }


def test_client_config_openrouter_selects_openrouter_base_url_and_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    cfg = models.client_config("openrouter:z-ai/glm-5.2:free")

    assert cfg == {
        "provider": "openrouter", "model_id": "z-ai/glm-5.2:free",
        "base_url": "https://openrouter.ai/api/v1", "api_key": "or-key",
    }


def test_client_config_unknown_provider_errors_clearly():
    with pytest.raises(ValueError, match="unknown model provider 'bogus'"):
        models.client_config("bogus:some-model")


def test_make_agno_model_groq_builds_groq_client(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "g-key")
    from agno.models.groq import Groq

    m = models.make_agno_model("groq:openai/gpt-oss-120b")

    assert isinstance(m, Groq)
    assert m.id == "openai/gpt-oss-120b"
    assert m.api_key == "g-key"
    # No base_url override: passing one double-appends "/openai/v1" onto the Groq SDK's
    # client base_url and 404s. Agno's own default (None here -> SDK default) is correct.
    assert m.base_url is None


def test_make_agno_model_openrouter_builds_openrouter_client(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    from agno.models.openrouter import OpenRouter

    m = models.make_agno_model("openrouter:z-ai/glm-5.2:free")

    assert isinstance(m, OpenRouter)
    assert m.id == "z-ai/glm-5.2:free"
    assert m.api_key == "or-key"
    # No base_url override passed in — this is Agno's OWN class default, not ours.
    assert m.base_url == OpenRouter.base_url


def test_make_agno_model_groq_client_base_url_is_not_double_appended(monkeypatch):
    """Regression test for the live-run bug: passing base_url="https://api.groq.com/openai/v1"
    into Agno's Groq(...) made the underlying Groq SDK client base_url
    "https://api.groq.com/openai/v1/", and the SDK then appends "/openai/v1/chat/completions"
    onto THAT, producing a 404 (nothing authored in that run). Without a base_url override,
    the SDK client resolves its own correct base_url: "https://api.groq.com"."""
    monkeypatch.setenv("GROQ_API_KEY", "g-key")

    m = models.make_agno_model("groq:openai/gpt-oss-120b")
    client = m.get_client()

    assert str(client.base_url) == "https://api.groq.com"


def test_make_agno_model_unknown_provider_errors_clearly():
    with pytest.raises(ValueError, match="unknown model provider"):
        models.make_agno_model("bogus:some-model")
