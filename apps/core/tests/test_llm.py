import httpx
import pytest

from esp_atlas_core.llm import GroqClient, GroqConfigError, GroqRateLimitError


def _client_with_transport(handler, **kwargs):
    transport = httpx.MockTransport(handler)
    return GroqClient(http_client=httpx.Client(transport=transport), **kwargs)


def test_complete_raises_config_error_without_api_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    def handler(request):
        raise AssertionError("must not make a network call when the key is missing")

    client = _client_with_transport(handler)
    with pytest.raises(GroqConfigError):
        client.complete("system", "user")


def test_complete_returns_message_content_on_success():
    def handler(request):
        assert request.headers["authorization"] == "Bearer test-key"
        body = request.read()
        assert b"system" in body and b"user" in body
        return httpx.Response(200, json={"choices": [{"message": {"content": "ESP32-C6 has Wi-Fi 6."}}]})

    client = _client_with_transport(handler, api_key="test-key")
    result = client.complete("system", "user")
    assert result == "ESP32-C6 has Wi-Fi 6."


def test_complete_uses_env_model_and_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "env-key")
    monkeypatch.setenv("GROQ_MODEL", "env-model")

    def handler(request):
        import json

        payload = json.loads(request.read())
        assert payload["model"] == "env-model"
        assert request.headers["authorization"] == "Bearer env-key"
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    client = _client_with_transport(handler)
    assert client.complete("s", "u") == "ok"


def test_complete_retries_on_429_then_succeeds():
    calls = {"n": 0}
    sleeps = []

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, headers={"retry-after": "0.01"}, json={"error": "rate limited"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "grounded answer"}}]})

    client = _client_with_transport(handler, api_key="k", sleep_fn=sleeps.append)
    result = client.complete("s", "u")
    assert result == "grounded answer"
    assert calls["n"] == 3
    assert sleeps == [0.01, 0.01]


def test_complete_gives_up_after_max_retries():
    def handler(request):
        return httpx.Response(429, headers={"retry-after": "0.01"}, json={"error": "rate limited"})

    client = _client_with_transport(handler, api_key="k", sleep_fn=lambda s: None, max_retries=2)
    with pytest.raises(GroqRateLimitError):
        client.complete("s", "u")


def test_complete_never_hits_real_network_in_tests(monkeypatch):
    # Guard: if this test's handler is somehow bypassed, httpx would try a real
    # connection and fail fast in this sandboxed environment rather than hang.
    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": "fake"}}]})

    client = _client_with_transport(handler, api_key="k")
    assert client.complete("s", "u") == "fake"
