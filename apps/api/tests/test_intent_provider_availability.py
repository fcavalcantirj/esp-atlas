"""Provider failures must preserve the keyword-search fallback contract."""
import json
import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from esp_atlas_api.main import create_app
from esp_atlas_core.llm import GroqClient


@pytest.mark.parametrize("failure", [401, 403, 404, 500, "timeout", "bad_json", "bad_shape"])
def test_provider_failure_is_safe_503_and_does_not_poison_intent_cache(built_db_path, caplog, failure):
    calls = []

    def provider(request):
        calls.append(request)
        if len(calls) > 1:
            return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"filters": {"radio": "wifi-6"}})}}]})
        if failure == "timeout":
            raise httpx.ReadTimeout("private-provider-detail", request=request)
        if failure == "bad_json":
            return httpx.Response(200, text="private-provider-detail")
        if failure == "bad_shape":
            return httpx.Response(200, json={"private-provider-detail": "do not expose"})
        return httpx.Response(failure, json={"error": "private-provider-detail"})

    llm = GroqClient(api_key="private-test-key", http_client=httpx.Client(transport=httpx.MockTransport(provider)))
    app = create_app(db_path=built_db_path, llm_client=llm)
    # Each parametrized case starts with a distinct, uncached phrasing.
    query = f"wifi six board provider availability case {failure}"
    with TestClient(app) as client, caplog.at_level(logging.WARNING):
        failed = client.post("/intent", json={"query": query})
        assert failed.status_code == 503
        assert "Keyword search" in failed.json()["detail"]
        assert "private-provider-detail" not in failed.text + caplog.text
        assert "private-test-key" not in failed.text + caplog.text
        assert "intent_provider_unavailable" in caplog.text
        if isinstance(failure, int):
            assert f"upstream_status={failure}" in caplog.text
        fallback = client.get("/search", params={"q": "esp32-c6"})
        assert fallback.status_code == 200
        assert "esp32-c6" in {item["id"] for item in fallback.json()["results"]}
        recovered = client.post("/intent", json={"query": query})
        assert recovered.status_code == 200
        assert recovered.json()["cached"] is False
        assert recovered.json()["filters"]["radio"] == "wifi-6"
        cached = client.post("/intent", json={"query": query})
        assert cached.json()["cached"] is True
    assert len(calls) == 2


def test_deterministic_firmware_intent_needs_no_provider(built_db_path):
    def provider(request):
        raise AssertionError("deterministic firmware lookup must not call Groq")

    llm = GroqClient(api_key="unused", http_client=httpx.Client(transport=httpx.MockTransport(provider)))
    with TestClient(create_app(db_path=built_db_path, llm_client=llm)) as client:
        response = client.post("/intent", json={"query": "run CircuitPython"})
    assert response.status_code == 200
    assert response.json()["kind"] == "firmware"
