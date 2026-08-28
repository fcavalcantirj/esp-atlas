"""EspAtlas Jr — model factory (configurable drafter/oracle models).

One place that maps a "provider:model_id" spec (JR_BOARD_MODEL / JR_ORACLE_MODEL) to the
provider's base_url + api-key env var, so the Agno drafter agent (agent.py's make_jr_board)
and the raw-HTTP oracle call (tools.oracle_review) never drift. Free-by-default (no metered
spend): the defaults below are both free-tier models; JR_BOARD_MODEL/JR_ORACLE_MODEL let
Felipe override either independently. Unknown providers fail loud (ValueError), never a
silent fallback.
"""
from __future__ import annotations
import os

DEFAULT_BOARD_MODEL = "groq:openai/gpt-oss-120b"
DEFAULT_ORACLE_MODEL = "openrouter:z-ai/glm-5.2:free"

_PROVIDERS = {
    "groq": {"base_url": "https://api.groq.com/openai/v1", "env_key": "GROQ_API_KEY"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "env_key": "OPENROUTER_API_KEY"},
}


def parse_model_spec(spec: str) -> tuple[str, str]:
    """Split "provider:model_id" into (provider, model_id). Only the FIRST colon splits — an
    OpenRouter model id can itself contain a colon (e.g. "z-ai/glm-5.2:free")."""
    provider, sep, model_id = (spec or "").partition(":")
    if not sep or not provider or not model_id:
        raise ValueError(f"bad model spec {spec!r} — expected 'provider:model_id'")
    return provider, model_id


def client_config(spec: str) -> dict:
    """(provider, model_id, base_url, api_key) for a "provider:model_id" spec — the shape a
    plain OpenAI-compatible chat/completions POST needs (tools.oracle_review). Raises
    ValueError on an unknown provider."""
    provider, model_id = parse_model_spec(spec)
    cfg = _PROVIDERS.get(provider)
    if not cfg:
        raise ValueError(f"unknown model provider {provider!r} — supported: {sorted(_PROVIDERS)}")
    return {
        "provider": provider,
        "model_id": model_id,
        "base_url": cfg["base_url"],
        "api_key": os.environ.get(cfg["env_key"], ""),
    }


def make_agno_model(spec: str):
    """The Agno model instance for `spec`, for wiring an Agent(model=...) (e.g. make_jr_board).
    Uses the SAME provider table as client_config() so the drafter and the oracle never
    disagree about which endpoint/key a provider means."""
    cfg = client_config(spec)
    if cfg["provider"] == "groq":
        from agno.models.groq import Groq
        return Groq(id=cfg["model_id"], api_key=cfg["api_key"] or None, base_url=cfg["base_url"])
    from agno.models.openrouter import OpenRouter
    return OpenRouter(id=cfg["model_id"], api_key=cfg["api_key"] or None, base_url=cfg["base_url"])
