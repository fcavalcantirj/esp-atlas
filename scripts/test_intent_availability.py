import importlib.util
import json
from pathlib import Path

import httpx
import pytest

spec = importlib.util.spec_from_file_location("intent_availability", Path(__file__).with_name("intent_availability.py"))
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)


@pytest.mark.parametrize("body", [
    {"kind": "filters", "cached": True, "filters": {"radio": "wifi-6"}},
    {"kind": "firmware", "cached": False, "firmware": "circuitpython"},
    {"kind": "unreadable", "cached": False, "filters": {}},
    {"kind": "filters", "cached": False, "filters": {"radio": "wifi-4"}},
    [],
])
def test_monitor_rejects_cached_or_non_inference_success(body):
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body))) as client:
        assert monitor.probe("https://atlas.example/api", client, "unique")['status'] == "degraded"


def test_monitor_requires_fresh_inference_and_never_returns_provider_payload():
    queries = []

    def handler(request):
        assert str(request.url) == "https://atlas.example/api/intent"
        queries.append(json.loads(request.content)["query"])
        return httpx.Response(200, json={"kind": "filters", "cached": False, "filters": {"radio": "wifi-6"}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert monitor.probe("https://atlas.example/api/", client, "first")["status"] == "ok"
        assert monitor.probe("https://atlas.example/api", client, "second")["status"] == "ok"
    assert queries[0] != queries[1]


@pytest.mark.parametrize("failure", [401, 500, 503, "timeout", "bad_json"])
def test_monitor_failure_is_bounded_and_redacted(failure):
    def handler(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("private-detail", request=request)
        if failure == "bad_json":
            return httpx.Response(200, text="private-detail")
        return httpx.Response(failure, text="private-detail")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = monitor.probe("https://atlas.example/api", client, "unique")
    assert result["status"] == "degraded"
    assert "private-detail" not in json.dumps(result)
