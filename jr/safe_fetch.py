"""EspAtlas Jr — the capped, redirect-checked HTTPS GET of an untrusted asset (jr/safe_fetch.py).

device_evidence's release_bin probe downloads a release asset a stranger's repo points at. Owner
spec 2026-11-04 (fetch side) for that download, all enforced here:

  https only          every hop, the first one included; credentials in the URL and any port
                      but 443 are refused too
  redirects by hand   at most MAX_REDIRECTS, each Location re-validated as if it were the first URL
  public hosts only   every hop's host is resolved ONCE and every answer must be a public address
                      (blocked_reason): private, loopback, link-local, multicast, reserved,
                      unspecified, shared, and the IPv4-mapped forms of those; 6to4, NAT64 and
                      Teredo forms whatever they embed. The connection is dialed to that validated
                      address (TLS still verifies the hostname), so a second DNS answer — rebinding
                      — can never pick the destination.
  a byte cap          max_bytes counted on bytes RECEIVED while streaming; Content-Length is never
                      trusted. A server that closes the connection (we ask it to) is read to the
                      close, so a short claim cannot hide a long body; one byte over aborts.
  bounded time        connect_timeout per dial and TLS handshake, read_timeout per read, and
                      total_timeout over everything (DNS included) — a watchdog shuts the socket,
                      so a slow drip of headers or body cannot outlive it.

fetch_capped never raises for any of that: it returns Fetched, whose `reason` is None for a whole
body or one of the constants below. NOT_FOUND (404/410) is a fact about the asset; UNAVAILABLE
(a 5xx/429, DNS failure, refused or reset connection) says nothing about it; every other reason
is a refusal. `resolve`, `dial` and `ssl_context` are seams for the local test server only.
"""
from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
import threading
import time
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

MAX_BYTES = 16 * 1024 * 1024        # the owner's cap on a release asset
MAX_REDIRECTS = 5
CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 30.0
TOTAL_TIMEOUT = 120.0
HTTPS_PORT = 443
CHUNK = 64 * 1024
USER_AGENT = "esp-atlas-jr-derive/0.1"

NOT_HTTPS = "not_https"
BAD_URL = "bad_url"
BLOCKED_ADDRESS = "blocked_address"
TOO_MANY_REDIRECTS = "too_many_redirects"
TOO_LARGE = "too_large"
TIMEOUT = "timeout"
TLS_ERROR = "tls_error"
HTTP_STATUS = "http_status"
NOT_FOUND = "not_found"
UNAVAILABLE = "unavailable"

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_TUNNEL_NETS = (ipaddress.ip_network("64:ff9b::/96"), ipaddress.ip_network("64:ff9b:1::/48"))   # NAT64
# Checked in this order, so 169.254.169.254 reads "link-local", not the broader "private".
_BLOCKED_KINDS = ("is_unspecified", "is_loopback", "is_link_local", "is_multicast", "is_private", "is_reserved")


@dataclass(frozen=True)
class Fetched:
    """`data` is the whole body when `reason` is None; otherwise None, and `detail` says why.
    `url` is the last hop tried, `hops` every URL requested in order."""
    data: bytes | None
    reason: str | None = None
    detail: str = ""
    url: str = ""
    hops: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.reason is None


class _Stop(Exception):
    def __init__(self, reason: str, detail: str):
        super().__init__(detail)
        self.reason, self.detail = reason, detail


def blocked_reason(ip: str) -> str | None:
    """Why `ip` is not a public destination, or None when it is."""
    try:
        addr = ipaddress.ip_address(ip.split("%", 1)[0])
    except ValueError:
        return f"{ip!r} is not an IP address"
    if addr.version == 6:
        if addr.ipv4_mapped:
            inner = blocked_reason(str(addr.ipv4_mapped))
            return f"{ip} maps {inner}" if inner else None
        if addr.sixtofour or addr.teredo or any(addr in net for net in _TUNNEL_NETS):
            return f"{ip} is a 6to4, Teredo or NAT64 tunnel address"
    for kind in _BLOCKED_KINDS:
        if getattr(addr, kind):
            return f"{ip} is {kind[3:].replace('_', '-')}"
    if not addr.is_global:
        return f"{ip} is not globally routable"
    return None


def fetch_capped(url: str, max_bytes: int = MAX_BYTES, connect_timeout: float = CONNECT_TIMEOUT,
                 read_timeout: float = READ_TIMEOUT, total_timeout: float = TOTAL_TIMEOUT, *,
                 max_redirects: int = MAX_REDIRECTS, resolve=None, dial=None, ssl_context=None) -> Fetched:
    """GET `url` under the policy above. `resolve(host, port) -> [ip]` and `dial(ip, port, timeout)
    -> socket` default to getaddrinfo and socket.create_connection; `ssl_context` to the system
    trust store."""
    hop = _Hop(max_bytes, connect_timeout, read_timeout, time.monotonic() + total_timeout,
               resolve or _getaddrinfo, dial or socket.create_connection, ssl_context or ssl.create_default_context())
    hops: list[str] = []
    try:
        for _ in range(max_redirects + 1):
            hops.append(url)
            data, location = hop.get(url)
            if location is None:
                return Fetched(data, url=url, hops=hops)
            url = location
        raise _Stop(TOO_MANY_REDIRECTS, f"more than {max_redirects} redirects (last: {url})")
    except _Stop as stop:
        return Fetched(None, stop.reason, stop.detail, url, hops)


def _getaddrinfo(host: str, port: int) -> list[str]:
    return [ai[4][0] for ai in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)]


def _check_url(url: str) -> tuple[str, str]:
    """(host, request target) of a URL the policy allows, else _Stop."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as e:
        raise _Stop(BAD_URL, f"{url!r}: {e}") from None
    if parts.scheme.lower() != "https":
        raise _Stop(NOT_HTTPS, f"{url!r}: only https is fetched")
    if "@" in parts.netloc:
        raise _Stop(BAD_URL, f"{url!r}: credentials in the URL")
    if not parts.hostname:
        raise _Stop(BAD_URL, f"{url!r}: no host")
    if port not in (None, HTTPS_PORT):
        raise _Stop(BAD_URL, f"{url!r}: port {port}, only {HTTPS_PORT} is fetched")
    return parts.hostname, (parts.path or "/") + (f"?{parts.query}" if parts.query else "")


class _Watchdog:
    """Shuts the connection at the total deadline. It holds a dup of the socket — shutdown(2) on
    any descriptor ends the connection — so it never touches the TLS object the reader is in."""

    def __init__(self, seconds: float):
        self.fired = False
        self._sock = None
        self._lock = threading.Lock()
        self._timer = threading.Timer(max(seconds, 0.0), self._fire)
        self._timer.daemon = True
        self._timer.start()

    def attach(self, sock: socket.socket) -> None:
        with self._lock:
            self._sock = sock.dup()
            if self.fired:
                self._shut()

    def _fire(self) -> None:
        with self._lock:
            self.fired = True
            self._shut()

    def _shut(self) -> None:
        if self._sock is not None:
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def cancel(self) -> None:
        self._timer.cancel()
        with self._lock:
            if self._sock is not None:
                self._sock.close()


class _PinnedHTTPS(http.client.HTTPSConnection):
    """An HTTPS connection to `host` dialed to the already-validated `ip`."""

    def __init__(self, host: str, ip: str, tls: ssl.SSLContext, dial, watchdog: _Watchdog,
                 connect_timeout: float, read_timeout: float):
        super().__init__(host, HTTPS_PORT, timeout=connect_timeout, context=tls)
        self._ip, self._tls, self._dial, self._watchdog, self._read_timeout = ip, tls, dial, watchdog, read_timeout

    def connect(self) -> None:
        raw = self._dial(self._ip, HTTPS_PORT, self.timeout)
        self._watchdog.attach(raw)
        raw.settimeout(self.timeout)                      # the TLS handshake: connect_timeout
        self.sock = self._tls.wrap_socket(raw, server_hostname=self.host)
        self.sock.settimeout(self._read_timeout)


@dataclass
class _Hop:
    max_bytes: int
    connect_timeout: float
    read_timeout: float
    deadline: float
    resolve: object
    dial: object
    tls: ssl.SSLContext

    def remaining(self) -> float:
        return self.deadline - time.monotonic()

    def get(self, url: str) -> tuple[bytes | None, str | None]:
        """(body, None) or (None, the next URL) for one request, else _Stop."""
        host, target = _check_url(url)
        ip = self._pinned_ip(host)
        watchdog = _Watchdog(self.remaining())
        conn = _PinnedHTTPS(host, ip, self.tls, self.dial, watchdog,
                            min(self.connect_timeout, max(self.remaining(), 0.001)), self.read_timeout)
        try:
            conn.request("GET", target, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity",
                                                 "Connection": "close"})
            resp = conn.getresponse()
            location = self._redirect(url, resp)
            return (None, location) if location else (self._read_capped(resp, watchdog), None)
        except _Stop:
            raise
        except Exception as e:  # noqa: BLE001 — every transport failure becomes a structured reason
            raise self._transport_stop(url, e, watchdog) from None
        finally:
            watchdog.cancel()
            conn.close()

    def _pinned_ip(self, host: str) -> str:
        """The one address this hop dials: every answer for `host` must be public."""
        try:
            answers = [str(ipaddress.ip_address(host))]
        except ValueError:
            answers = self._resolve_within(host)
        if not answers:
            raise _Stop(UNAVAILABLE, f"{host} resolved to no address")
        for ip in answers:
            why = blocked_reason(ip)
            if why:
                raise _Stop(BLOCKED_ADDRESS, f"{host} -> {why}")
        return answers[0]

    def _resolve_within(self, host: str) -> list[str]:
        box: dict = {}

        def run():
            try:
                box["ips"] = list(self.resolve(host, HTTPS_PORT))
            except Exception as e:  # noqa: BLE001 — carried back to the caller's thread
                box["error"] = e
        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        worker.join(max(min(self.connect_timeout, self.remaining()), 0.0))
        if worker.is_alive():
            raise _Stop(TIMEOUT, f"resolving {host} outlived the deadline")
        if "error" in box:
            raise _Stop(UNAVAILABLE, f"cannot resolve {host}: {box['error']}")
        return box["ips"]

    @staticmethod
    def _redirect(url: str, resp) -> str | None:
        status = resp.status
        if status in _REDIRECT_STATUSES:
            location = (resp.getheader("Location") or "").strip()
            if not location:
                raise _Stop(HTTP_STATUS, f"HTTP {status} redirect without a Location from {url}")
            return urljoin(url, location)
        if status in (404, 410):
            raise _Stop(NOT_FOUND, f"HTTP {status} from {url}")
        if status == 429 or status >= 500:
            raise _Stop(UNAVAILABLE, f"HTTP {status} from {url}")
        if status != 200:
            raise _Stop(HTTP_STATUS, f"HTTP {status} from {url}")
        return None

    def _read_capped(self, resp, watchdog: _Watchdog) -> bytes:
        """The body, counted as it arrives. A closing server is read to the close whatever its
        Content-Length claims; chunked framing ends a chunked body."""
        if resp.will_close and not resp.chunked:
            resp.length = None
        body = bytearray()
        while not watchdog.fired:
            chunk = resp.read1(min(CHUNK, self.max_bytes + 1 - len(body)))
            if not chunk:
                break
            body += chunk
            if len(body) > self.max_bytes:
                raise _Stop(TOO_LARGE, f"more than {self.max_bytes} bytes received; aborted")
        if watchdog.fired:          # the watchdog's shutdown reads as an end of body: never whole
            raise _Stop(TIMEOUT, f"the total timeout ended the download after {len(body)} bytes")
        return bytes(body)

    def _transport_stop(self, url: str, e: Exception, watchdog: _Watchdog) -> _Stop:
        what = f"{url}: {type(e).__name__}: {e}"[:300]
        if watchdog.fired or self.remaining() <= 0:
            return _Stop(TIMEOUT, f"the total timeout ended the request ({what})")
        if isinstance(e, TimeoutError):
            return _Stop(TIMEOUT, f"connect or read timeout ({what})")
        if isinstance(e, ssl.SSLCertVerificationError):
            return _Stop(TLS_ERROR, what)
        if isinstance(e, ValueError):           # http.client's InvalidURL: control characters
            return _Stop(BAD_URL, what)
        return _Stop(UNAVAILABLE, what)
