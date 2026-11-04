"""Tests for jr/safe_fetch.py — the capped, redirect-checked HTTPS GET of a release asset.

Owner spec 2026-11-04 (fetch side): the 16 MB cap is enforced while streaming whatever
Content-Length says (absent, wrong or lying), redirects are followed by hand and each hop is
re-validated, private/internal destinations are refused, and every timeout is bounded. Every test
talks to a local TLS server (jr/fake_https.py, the `https_server` fixture): no internet."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

import fake_https
import safe_fetch as sf
from fake_https import PUBLIC_IP

VALID_S3_IMAGE = (Path(__file__).resolve().parent / "fixtures" / "esp_image" / "app_esp32s3.bin").read_bytes()
URL = "https://assets.test/fw.bin"
CAP = 64 * 1024                 # a small cap keeps the overflow tests fast; one test uses the real 16 MB


def fetch(server, url=URL, **kw):
    return sf.fetch_capped(url, **{"max_bytes": CAP, **kw, **server.seams()})


# --- the cap, whatever Content-Length says ---------------------------------------------------------

def test_a_whole_asset_under_the_cap_is_returned(https_server):
    https_server.routes["/fw.bin"] = fake_https.exact(VALID_S3_IMAGE)
    got = fetch(https_server)
    assert got.ok and got.reason is None and got.data == VALID_S3_IMAGE and got.url == URL


def test_a_chunked_response_over_the_cap_is_aborted(https_server):
    https_server.routes["/fw.bin"] = fake_https.chunked(b"\xff" * 4096, count=1000)   # 4 MB, no Content-Length
    got = fetch(https_server)
    assert not got.ok and got.reason == sf.TOO_LARGE and got.data is None
    assert str(CAP) in got.detail


def test_a_chunked_response_over_the_real_16_mb_cap_is_aborted(https_server):
    https_server.routes["/fw.bin"] = fake_https.chunked(b"\xff" * 65536, count=300)    # 19.7 MB
    got = sf.fetch_capped(URL, **https_server.seams())
    assert got.reason == sf.TOO_LARGE and sf.MAX_BYTES == 16 * 1024 * 1024


def test_an_absent_content_length_over_the_cap_is_aborted(https_server):
    https_server.routes["/fw.bin"] = fake_https.stream(CAP * 4, content_length=None)
    assert fetch(https_server).reason == sf.TOO_LARGE


def test_a_content_length_claiming_small_with_a_large_body_is_aborted(https_server):
    """Content-Length: 10, then megabytes: the body is read to the close, not to the claim."""
    https_server.routes["/fw.bin"] = fake_https.stream(CAP * 4, content_length=10)
    assert fetch(https_server).reason == sf.TOO_LARGE


def test_a_content_length_claiming_large_with_a_small_valid_body_is_read(https_server):
    """A claim of 1 GB is not a refusal: only bytes actually received count against the cap."""
    https_server.routes["/fw.bin"] = fake_https.body(VALID_S3_IMAGE, content_length=10**9)
    got = fetch(https_server)
    assert got.ok and got.data == VALID_S3_IMAGE


def test_a_body_of_exactly_the_cap_is_whole(https_server):
    https_server.routes["/fw.bin"] = fake_https.stream(CAP, content_length=CAP)
    got = fetch(https_server)
    assert got.ok and len(got.data) == CAP


def test_one_byte_over_the_cap_is_too_large(https_server):
    https_server.routes["/fw.bin"] = fake_https.stream(CAP + 1, content_length=None)
    assert fetch(https_server).reason == sf.TOO_LARGE


# --- redirects: by hand, at most 5, every hop re-validated -----------------------------------------

def test_a_redirect_is_followed_and_the_final_url_reported(https_server):
    https_server.routes["/fw.bin"] = fake_https.redirect("https://cdn.test/blob/1")
    https_server.routes["/blob/1"] = fake_https.exact(VALID_S3_IMAGE)
    got = fetch(https_server)
    assert got.ok and got.data == VALID_S3_IMAGE and got.url == "https://cdn.test/blob/1"
    assert got.hops == [URL, "https://cdn.test/blob/1"]


def test_a_relative_redirect_resolves_against_the_hop(https_server):
    https_server.routes["/fw.bin"] = fake_https.redirect("/blob/2", status="301 Moved Permanently")
    https_server.routes["/blob/2"] = fake_https.exact(VALID_S3_IMAGE)
    assert fetch(https_server).url == "https://assets.test/blob/2"


@pytest.mark.parametrize("location", ["https://127.0.0.1/fw.bin", "https://169.254.169.254/latest/meta-data/",
                                      "https://10.0.0.7/fw.bin", "https://[::1]/fw.bin",
                                      "https://[::ffff:127.0.0.1]/fw.bin", "https://[2002:a9fe:a9fe::]/fw.bin",
                                      "https://0.0.0.0/fw.bin", "https://localhost/fw.bin"])
def test_a_redirect_to_an_internal_address_is_refused_before_any_connection(https_server, location):
    https_server.routes["/fw.bin"] = fake_https.redirect(location)
    dials = []
    got = sf.fetch_capped(URL, max_bytes=CAP, **https_server.seams(dial_log=dials))
    assert not got.ok and got.reason == sf.BLOCKED_ADDRESS and got.data is None
    assert dials == [(PUBLIC_IP, 443)]           # only the first, public hop was ever dialed


def test_a_hostname_resolving_to_a_private_address_is_refused(https_server):
    seams = https_server.seams()
    seams["resolve"] = lambda host, port: ["10.1.2.3"]
    assert sf.fetch_capped(URL, max_bytes=CAP, **seams).reason == sf.BLOCKED_ADDRESS


def test_any_private_address_among_the_answers_refuses_the_host(https_server):
    seams = https_server.seams()
    seams["resolve"] = lambda host, port: [PUBLIC_IP, "192.168.1.1"]
    assert sf.fetch_capped(URL, max_bytes=CAP, **seams).reason == sf.BLOCKED_ADDRESS


def test_the_connection_goes_to_the_validated_address_so_dns_rebinding_cannot_swap_it(https_server):
    """A resolver that answers public, then loopback: the hop resolves ONCE and dials that answer."""
    https_server.routes["/fw.bin"] = fake_https.exact(VALID_S3_IMAGE)
    answers, dials = iter([[PUBLIC_IP], ["127.0.0.1"]]), []
    seams = https_server.seams(dial_log=dials)
    seams["resolve"] = lambda host, port: next(answers)
    got = sf.fetch_capped(URL, max_bytes=CAP, **seams)
    assert got.ok and dials == [(PUBLIC_IP, 443)]


def _chain(server, n):
    for i in range(n, 0, -1):
        server.routes[f"/r{i}"] = fake_https.redirect(f"https://assets.test/r{i - 1}")
    server.routes["/r0"] = fake_https.exact(VALID_S3_IMAGE)


def test_five_redirects_are_followed(https_server):
    _chain(https_server, 5)
    got = fetch(https_server, "https://assets.test/r5")
    assert got.ok and len(got.hops) == 6


def test_a_redirect_chain_over_five_is_refused(https_server):
    _chain(https_server, 6)
    got = fetch(https_server, "https://assets.test/r6")
    assert got.reason == sf.TOO_MANY_REDIRECTS and "/r0" not in https_server.seen


def test_a_redirect_loop_is_refused(https_server):
    https_server.routes["/fw.bin"] = fake_https.redirect(URL)
    assert fetch(https_server).reason == sf.TOO_MANY_REDIRECTS


def test_a_redirect_without_a_location_is_refused(https_server):
    https_server.routes["/fw.bin"] = lambda h: h.raw(b"HTTP/1.1 302 Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
    assert fetch(https_server).reason == sf.HTTP_STATUS


def test_an_http_downgrade_redirect_is_refused(https_server):
    https_server.routes["/fw.bin"] = fake_https.redirect("http://assets.test/fw.bin")
    dials = []
    got = sf.fetch_capped(URL, max_bytes=CAP, **https_server.seams(dial_log=dials))
    assert got.reason == sf.NOT_HTTPS and dials == [(PUBLIC_IP, 443)]


@pytest.mark.parametrize("url,reason", [("http://assets.test/fw.bin", sf.NOT_HTTPS), ("ftp://assets.test/fw.bin", sf.NOT_HTTPS),
                                        ("file:///etc/passwd", sf.NOT_HTTPS), ("https://user:pw@assets.test/fw.bin", sf.BAD_URL),
                                        ("https://assets.test:8443/fw.bin", sf.BAD_URL), ("https:///fw.bin", sf.BAD_URL),
                                        ("https://assets.test:x/fw.bin", sf.BAD_URL)])
def test_a_url_outside_the_policy_is_refused_without_a_connection(https_server, url, reason):
    dials = []
    got = sf.fetch_capped(url, max_bytes=CAP, **https_server.seams(dial_log=dials))
    assert got.reason == reason and dials == []


# --- timeouts --------------------------------------------------------------------------------------

def test_a_slow_drip_body_hits_the_total_timeout(https_server):
    """One byte every 0.1 s never trips the 5 s read timeout; the 1 s total deadline still ends it."""
    https_server.routes["/fw.bin"] = fake_https.drip(every=0.1, count=200)
    t0 = time.monotonic()
    got = fetch(https_server, read_timeout=5.0, total_timeout=1.0)
    assert got.reason == sf.TIMEOUT and time.monotonic() - t0 < 3.0


def test_slow_dripped_headers_hit_the_total_timeout(https_server):
    https_server.routes["/fw.bin"] = fake_https.drip(every=0.1, count=200, headers=False)
    t0 = time.monotonic()
    got = fetch(https_server, read_timeout=5.0, total_timeout=1.0)
    assert got.reason == sf.TIMEOUT and time.monotonic() - t0 < 3.0


def test_a_stalled_body_hits_the_read_timeout(https_server):
    https_server.routes["/fw.bin"] = fake_https.drip(every=3.0, count=5)
    t0 = time.monotonic()
    got = fetch(https_server, read_timeout=0.5, total_timeout=10.0)
    assert got.reason == sf.TIMEOUT and time.monotonic() - t0 < 2.5


def test_a_slow_resolver_hits_the_total_timeout(https_server):
    seams = https_server.seams()
    seams["resolve"] = lambda host, port: time.sleep(5) or [PUBLIC_IP]
    t0 = time.monotonic()
    got = sf.fetch_capped(URL, max_bytes=CAP, total_timeout=0.5, **seams)
    assert got.reason == sf.TIMEOUT and time.monotonic() - t0 < 2.0


# --- status codes and TLS --------------------------------------------------------------------------

@pytest.mark.parametrize("status,reason", [("404 Not Found", sf.NOT_FOUND), ("410 Gone", sf.NOT_FOUND),
                                           ("403 Forbidden", sf.HTTP_STATUS), ("206 Partial Content", sf.HTTP_STATUS),
                                           ("503 Service Unavailable", sf.UNAVAILABLE), ("429 Too Many Requests", sf.UNAVAILABLE)])
def test_a_status_other_than_200_is_a_structured_reason(https_server, status, reason):
    https_server.routes["/fw.bin"] = fake_https.body(b"", 0, status=status)
    got = fetch(https_server)
    assert got.reason == reason and got.data is None and status.split()[0] in got.detail


def test_an_untrusted_certificate_is_refused(https_server):
    https_server.routes["/fw.bin"] = fake_https.exact(VALID_S3_IMAGE)
    seams = https_server.seams()
    seams["ssl_context"] = None                  # the system trust store: the test CA is not in it
    assert sf.fetch_capped(URL, max_bytes=CAP, **seams).reason == sf.TLS_ERROR


def test_a_refused_connection_is_unavailable_not_a_verdict(https_server):
    seams = https_server.seams()
    seams["dial"] = lambda ip, port, timeout: (_ for _ in ()).throw(ConnectionRefusedError(111, "refused"))
    assert sf.fetch_capped(URL, max_bytes=CAP, **seams).reason == sf.UNAVAILABLE


def test_an_unresolvable_host_is_unavailable(https_server):
    seams = https_server.seams()
    seams["resolve"] = lambda host, port: (_ for _ in ()).throw(OSError(-2, "Name or service not known"))
    assert sf.fetch_capped(URL, max_bytes=CAP, **seams).reason == sf.UNAVAILABLE


def test_the_request_asks_for_the_whole_asset_and_a_closed_connection(https_server):
    got_headers = {}

    def route(h):
        got_headers.update({k.lower(): v for k, v in h.headers.items()})
        fake_https.exact(VALID_S3_IMAGE)(h)
    https_server.routes["/fw.bin"] = route
    assert fetch(https_server).ok
    assert "range" not in got_headers and got_headers["connection"] == "close"
    assert got_headers["host"] == "assets.test" and got_headers["accept-encoding"] == "identity"


# --- the address policy ----------------------------------------------------------------------------

@pytest.mark.parametrize("ip", ["127.0.0.1", "127.8.8.8", "10.0.0.1", "172.16.0.1", "192.168.0.1", "169.254.169.254",
                                "100.64.0.1", "0.0.0.0", "224.0.0.1", "239.255.255.250", "240.0.0.1", "255.255.255.255",
                                "192.0.2.1", "::", "::1", "fe80::1", "fc00::1", "ff02::1", "::ffff:127.0.0.1",
                                "::ffff:10.0.0.1", "::ffff:169.254.169.254", "2002:7f00:1::", "2002:a00:1::",
                                "2002:a9fe:a9fe::", "2002:8c52:7003::", "64:ff9b::a00:1", "64:ff9b::8c52:7003",
                                "2001:0:4136:e378:8000:63bf:3fff:fdd2", "2001:db8::1", "fe80::1%eth0"])
def test_internal_addresses_are_blocked(ip):
    """6to4, NAT64 and Teredo forms are refused whatever they embed: tunnel forms, never a release CDN."""
    assert sf.blocked_reason(ip)


@pytest.mark.parametrize("ip", [PUBLIC_IP, "140.82.112.3", "185.199.108.133", "2606:50c0:8000::154", "::ffff:140.82.112.3"])
def test_public_addresses_are_allowed(ip):
    assert sf.blocked_reason(ip) is None


def test_garbage_is_blocked():
    assert sf.blocked_reason("not-an-ip")


def test_an_end_of_body_caused_by_the_watchdog_is_a_timeout_never_a_whole_body():
    """The watchdog's shutdown can surface as a clean EOF (read1 -> b"") instead of a TLS error:
    the bytes read so far are still not the asset."""
    class Watchdog:
        fired = False

    class Resp:
        will_close, chunked = False, False

        def __init__(self):
            self.reads = [b"\xe9" * 10, b""]

        def read1(self, n):
            Watchdog.fired = len(self.reads) == 1
            return self.reads.pop(0)
    hop = sf._Hop(CAP, 1.0, 1.0, time.monotonic() + 10, None, None, None)
    with pytest.raises(sf._Stop) as stop:
        hop._read_capped(Resp(), Watchdog)
    assert stop.value.reason == sf.TIMEOUT
