import asyncio

import pytest


def test_manifest_endpoint_serves_an_absolute_same_origin_proxy_url(client):
    r = client.get("/manifest/m5cardputer__launcher.json")
    assert r.status_code == 200
    build = r.json()["builds"][0]
    assert build["chipFamily"] == "ESP32-S3"
    assert "serialType" not in build
    # The path must resolve against this deployment (the API sits at /api on
    # Vercel but at the root under uvicorn), so it is built from the request.
    assert build["parts"][0]["path"].startswith("http://testserver/flash-bin?recipe=")


def test_manifest_404s_when_a_recipe_cannot_flash_in_browser(client):
    assert client.get("/manifest/nope__nope.json").status_code == 404
    # web-flasher recipes are guided handoffs, not in-browser flashes
    assert client.get("/manifest/m5cardputer__m5stick-nemo.json").status_code == 404


def test_flash_bin_refuses_a_recipe_it_cannot_resolve(client):
    """The proxy only ever fetches what a record points at."""
    assert client.get("/flash-bin?recipe=nope__nope").status_code == 403
    # a release-bin recipe with no recorded binary is still a refusal
    assert client.get("/flash-bin?recipe=m5cardputer__esp32marauder").status_code == 403


def test_flash_bin_takes_no_caller_supplied_url(client):
    """There must be no request shape that turns this into an open proxy."""
    r = client.get("/flash-bin?url=https://evil.example.com/x.bin")
    assert r.status_code == 422  # `recipe` is required; `url` is not a parameter
    r = client.get("/flash-bin?recipe=m5cardputer__launcher&url=https://evil.example.com/x.bin")
    assert r.status_code in (200, 502)  # the stray param is ignored, never honoured


class _FakeResponse:
    def __init__(self, status_code, headers=None):
        self.status_code = status_code
        self.headers = headers or {}

    async def aclose(self):
        pass


class _RedirectingClient:
    """Minimal httpx stand-in that replays a scripted redirect chain."""

    def __init__(self, *responses):
        self._responses = list(responses)
        self.requested = []

    def build_request(self, method, url, headers=None):
        return (method, url, headers)

    async def send(self, request, stream=False):
        self.requested.append(request[1])
        return self._responses.pop(0)


def test_proxy_refuses_a_redirect_off_the_allowlist():
    """An allowlisted host that 302s elsewhere must be stopped mid-chain."""
    from esp_atlas_api.main import _fetch_following_allowlisted_redirects

    client = _RedirectingClient(
        _FakeResponse(302, {"location": "https://evil.example.com/payload.bin"})
    )
    with pytest.raises(PermissionError):
        asyncio.run(
            _fetch_following_allowlisted_redirects(
                client, "https://github.com/o/r/releases/download/1/fw.bin", {}
            )
        )
    assert client.requested == ["https://github.com/o/r/releases/download/1/fw.bin"], (
        "the off-allowlist hop must never be requested"
    )


def test_proxy_follows_the_real_github_hop():
    """github.com -> objects.githubusercontent.com is the normal path and must work."""
    from esp_atlas_api.main import _fetch_following_allowlisted_redirects

    client = _RedirectingClient(
        _FakeResponse(302, {"location": "https://objects.githubusercontent.com/fw.bin"}),
        _FakeResponse(200),
    )
    response = asyncio.run(
        _fetch_following_allowlisted_redirects(
            client, "https://github.com/o/r/releases/download/1/fw.bin", {}
        )
    )
    assert response.status_code == 200
    assert client.requested[-1] == "https://objects.githubusercontent.com/fw.bin"
