"""Safety contract for the test harness after the accidental live PR incident."""
from __future__ import annotations

import os
import pwd
import subprocess
from pathlib import Path

import pytest

import popularity_run


def test_jr_fixture_rejects_real_gh_and_live_popularity_state(tmp_path):
    assert Path(os.environ["JR_POPULARITY_STATE_FILE"]).is_relative_to(tmp_path)
    with pytest.raises(AssertionError, match="real gh"):
        subprocess.run(["gh", "version"], capture_output=True, text=True)

    live = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".local/state/esp-atlas/jr-popularity.json"
    with pytest.raises(AssertionError, match="live state"):
        popularity_run._state_integrity(live)
    with pytest.raises(AssertionError, match="live state"):
        popularity_run._write_state(live, {})


# Network isolation is a separate guard from blocking the gh executable: a
# forgotten revalidate/http injection used to reach production through urllib.
def test_inherited_production_secrets_are_removed(monkeypatch):
    import offline_test_guard

    assert "REVALIDATE_SECRET" not in os.environ
    for name in ("REVALIDATE_SECRET", "GH_TOKEN", "GITHUB_TOKEN", "GROQ_API_KEY",
                 "TELEGRAM_BOT_TOKEN", "POPULARITY_DATABASE_URL"):
        monkeypatch.setenv(name, "test-only-canary")
    offline_test_guard.clear_production_secrets(monkeypatch)
    assert not any(name in os.environ for name in (
        "REVALIDATE_SECRET", "GH_TOKEN", "GITHUB_TOKEN", "GROQ_API_KEY",
        "TELEGRAM_BOT_TOKEN", "POPULARITY_DATABASE_URL"))


def test_default_revalidate_cannot_post_to_production(monkeypatch):
    import _socket
    import publish

    dns = []
    monkeypatch.setattr(_socket, "getaddrinfo", lambda *a, **kw: dns.append(a))
    result = publish.revalidate_catalog("test-only-not-a-real-secret", timeout=0.1)
    assert result["ok"] is False and result["status"] == 0
    assert "Jr test blocked network" in result["body"]
    assert dns == [], "the production name must not reach the system resolver"


@pytest.mark.parametrize("address", [("198.51.100.1", 443), ("127.0.0.1", 9), ("::1", 9)])
def test_unregistered_sockets_and_dns_are_denied(address):
    import socket

    with pytest.raises(AssertionError, match="blocked network"):
        socket.getaddrinfo(*address)
    family = socket.AF_INET6 if ":" in address[0] else socket.AF_INET
    with socket.socket(family) as client:
        with pytest.raises(AssertionError, match="blocked network"):
            client.connect(address)
        with pytest.raises(AssertionError, match="blocked network"):
            client.connect_ex(address)
    with socket.socket(family, socket.SOCK_DGRAM) as client:
        with pytest.raises(AssertionError, match="blocked network"):
            client.sendto(b"test-only", address)


def test_real_urllib_only_reaches_the_explicit_local_server(https_server):
    import urllib.request
    import fake_https

    https_server.routes["/test"] = fake_https.exact(b"local only")
    url = f"https://127.0.0.1:{https_server.port}/test"
    # The test certificate names assets.test, not the numeric dial address.
    context = https_server.client_ctx
    context.check_hostname = False
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context))
    with opener.open(url, timeout=1) as response:
        assert response.read() == b"local only"
    assert https_server.seen == ["/test"]


@pytest.mark.parametrize("host", ["esp-atlas.com", "198.51.100.1", "0.0.0.0"])
def test_local_allowlist_cannot_enable_a_production_endpoint(allow_local_test_server, host):
    with pytest.raises(ValueError, match="numeric loopback"):
        allow_local_test_server(host, 443)
