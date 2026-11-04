"""device_evidence's release_bin probe end to end: jr/safe_fetch.py over a local TLS server
(jr/fake_https.py — no internet), then jr/image_sandbox.py's restricted child running the real
validator. Owner rule: a refusal, timeout, overflow or sandbox failure is needs_review, never
esp_target; an outage (5xx) is unknown."""
from __future__ import annotations

import pytest

import device_evidence as dev
import fake_https
import image_sandbox
import safe_fetch
from test_device_evidence import VALID_S3_IMAGE, fake_repo

ASSET = "https://assets.test/o/r/releases/download/v1/fw.bin"
CAP = 64 * 1024


def releases(url=ASSET):
    return [{"tag_name": "v1", "draft": False, "assets": [{"name": "fw.bin", "browser_download_url": url}]}]


def gate(server, url=ASSET, max_bytes=dev.MAX_IMAGE_BYTES, **timeouts):
    """check() of a README-only repo whose release asset is `url`, fetched for real from `server`."""
    api, raw, _fetch, _ = fake_repo(tree=["README.md"], releases=releases(url))
    fetch = lambda u: safe_fetch.fetch_capped(u, max_bytes, **timeouts, **server.seams())  # noqa: E731
    return dev.check("o/r", api=api, raw=raw, fetch=fetch, ref="main")


def why(res):
    return dev.review_note(res)["why"]


def test_a_valid_image_behind_a_redirect_is_esp_target(https_server):
    https_server.routes["/o/r/releases/download/v1/fw.bin"] = fake_https.redirect("https://cdn.test/blob")
    https_server.routes["/blob"] = fake_https.exact(VALID_S3_IMAGE)
    res = gate(https_server)
    assert res["ok"] is True and res["verdict"] == dev.ESP_TARGET and res["kind"] == "release_bin"


def test_a_content_length_claiming_large_with_a_small_valid_image_is_esp_target(https_server):
    https_server.routes["/o/r/releases/download/v1/fw.bin"] = fake_https.body(VALID_S3_IMAGE, content_length=10**9)
    assert gate(https_server)["verdict"] == dev.ESP_TARGET


@pytest.mark.parametrize("location", ["https://127.0.0.1/fw.bin", "https://169.254.169.254/latest/meta-data/",
                                      "https://10.0.0.7/fw.bin"])
def test_a_redirect_to_an_internal_address_needs_review(https_server, location):
    https_server.routes["/o/r/releases/download/v1/fw.bin"] = fake_https.redirect(location)
    res = gate(https_server)
    assert res["ok"] is False and res["verdict"] == dev.NEEDS_REVIEW and safe_fetch.BLOCKED_ADDRESS in why(res)


@pytest.mark.parametrize("route", [fake_https.chunked(b"\xff" * 4096, count=64), fake_https.stream(CAP * 4, content_length=None),
                                   fake_https.stream(CAP * 4, content_length=10)],
                         ids=["chunked", "no-content-length", "content-length-lies-small"])
def test_an_asset_over_the_cap_needs_review(https_server, route):
    https_server.routes["/o/r/releases/download/v1/fw.bin"] = route
    res = gate(https_server, max_bytes=CAP)
    assert res["verdict"] == dev.NEEDS_REVIEW and safe_fetch.TOO_LARGE in why(res)


def test_an_http_downgrade_needs_review(https_server):
    https_server.routes["/o/r/releases/download/v1/fw.bin"] = fake_https.redirect("http://cdn.test/blob")
    res = gate(https_server)
    assert res["verdict"] == dev.NEEDS_REVIEW and safe_fetch.NOT_HTTPS in why(res)


def test_an_http_asset_url_needs_review(https_server):
    res = gate(https_server, url="http://assets.test/fw.bin")
    assert res["verdict"] == dev.NEEDS_REVIEW and safe_fetch.NOT_HTTPS in why(res)


def test_a_redirect_chain_over_five_needs_review(https_server):
    https_server.routes["/o/r/releases/download/v1/fw.bin"] = fake_https.redirect("https://assets.test/r5")
    for i in range(5, 0, -1):
        https_server.routes[f"/r{i}"] = fake_https.redirect(f"https://assets.test/r{i - 1}")
    https_server.routes["/r0"] = fake_https.exact(VALID_S3_IMAGE)
    res = gate(https_server)
    assert res["verdict"] == dev.NEEDS_REVIEW and safe_fetch.TOO_MANY_REDIRECTS in why(res)


def test_a_slow_drip_hitting_the_total_timeout_needs_review(https_server):
    https_server.routes["/o/r/releases/download/v1/fw.bin"] = fake_https.drip(every=0.1, count=100)
    res = gate(https_server, read_timeout=5.0, total_timeout=1.0)
    assert res["verdict"] == dev.NEEDS_REVIEW and safe_fetch.TIMEOUT in why(res)


def test_a_404_asset_needs_review(https_server):
    res = gate(https_server)
    assert res["verdict"] == dev.NEEDS_REVIEW and "not readable" in why(res)


def test_a_503_asset_is_unknown_and_retried(https_server):
    https_server.routes["/o/r/releases/download/v1/fw.bin"] = fake_https.body(b"", 0, status="503 Service Unavailable")
    res = gate(https_server)
    assert res["ok"] is None and res["verdict"] is None and "HTTP 503" in dev.reject_reason(res)


# --- the sandboxed validator --------------------------------------------------------------------------

def _validator(tmp_path, monkeypatch, body):
    path = tmp_path / "validator.py"
    path.write_text("def validate(data):\n    " + body + "\n")
    monkeypatch.setattr(image_sandbox, "ESP_IMAGE", path)


@pytest.mark.parametrize("body", ["raise RuntimeError('parser crashed')", "import time; time.sleep(30)",
                                  "print('esp_target'); return {}"], ids=["crash", "timeout", "non-json"])
def test_a_validator_crash_timeout_or_garbage_needs_review(https_server, tmp_path, monkeypatch, body):
    _validator(tmp_path, monkeypatch, body)
    monkeypatch.setattr(image_sandbox, "WALL_TIMEOUT", 1.0)
    https_server.routes["/o/r/releases/download/v1/fw.bin"] = fake_https.exact(VALID_S3_IMAGE)
    res = gate(https_server)
    assert res["verdict"] == dev.NEEDS_REVIEW and "image validator sandbox" in why(res)


def test_a_validator_that_opens_a_socket_never_reaches_esp_target(https_server, tmp_path, monkeypatch):
    """Were the child networked, this validator would phone home and answer esp_target."""
    _validator(tmp_path, monkeypatch, "import socket; socket.create_connection(('93.184.215.14', 443), 1); "
                                      "return {'status': 'esp_target', 'chip': 'esp32', 'reasons': ['phoned home']}")
    https_server.routes["/o/r/releases/download/v1/fw.bin"] = fake_https.exact(VALID_S3_IMAGE)
    res = gate(https_server)
    assert res["verdict"] == dev.NEEDS_REVIEW and "network is disabled" in why(res)
