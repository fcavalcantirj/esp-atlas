"""A local HTTPS server for the jr/safe_fetch.py tests (test support only; no internet).

One self-signed certificate (generated per session with `cryptography`, an esptool dependency
pinned in jr/requirements-image.txt) names every test host; the client trusts exactly it. Routes
write raw HTTP so a test can lie in Content-Length, chunk without end or drip a byte at a time —
the shapes http.server's helpers would never produce.

safe_fetch refuses loopback, so the tests reach this server through safe_fetch's seams: `resolve`
maps the test hosts to PUBLIC_IP (a global address, never dialed) and `dial` connects PUBLIC_IP to
the server's real 127.0.0.1 port. Every other address is dialed for real, so a refusal that failed
to happen would show up as a connection.
"""
from __future__ import annotations

import datetime
import ipaddress
import socket
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PUBLIC_IP = "93.184.215.14"     # a global unicast address the test `dial` maps to the local server
HOSTS = ("assets.test", "cdn.test")


def write_cert(dirpath: Path) -> tuple[Path, Path]:
    """(cert.pem, key.pem): a self-signed certificate for HOSTS, valid for a day."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, HOSTS[0])])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5)).not_valid_after(now + datetime.timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(h) for h in HOSTS]), critical=False)
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    cert_pem, key_pem = dirpath / "cert.pem", dirpath / "key.pem"
    cert_pem.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_pem.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                          serialization.NoEncryption()))
    return cert_pem, key_pem


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):  # noqa: N802 — http.server's name
        path = self.path.split("?", 1)[0]
        route = self.server.routes.get(path)
        self.server.seen.append(self.path)
        try:
            if route is None:
                self.raw(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            else:
                route(self)
        except (BrokenPipeError, ConnectionResetError, ssl.SSLError, OSError):
            pass                    # the client hung up on purpose (cap reached, timeout)
        self.close_connection = True

    def raw(self, data: bytes) -> None:
        self.wfile.write(data)
        self.wfile.flush()

    def log_message(self, *a):      # keep pytest output clean
        pass


class Server:
    """The running server: `routes` {path: handler(h)}, `seen` request paths, `port`."""

    def __init__(self, cert_pem: Path, key_pem: Path):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.httpd.daemon_threads = True
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert_pem, key_pem)
        self.httpd.socket = ctx.wrap_socket(self.httpd.socket, server_side=True)
        self.httpd.routes, self.httpd.seen = {}, []
        self.port = self.httpd.server_address[1]
        self.client_ctx = ssl.create_default_context(cafile=str(cert_pem))
        threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()

    @property
    def routes(self) -> dict:
        return self.httpd.routes

    @property
    def seen(self) -> list[str]:
        return self.httpd.seen

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()

    def seams(self, resolve_log: list | None = None, dial_log: list | None = None) -> dict:
        """safe_fetch keyword arguments reaching this server as HOSTS -> PUBLIC_IP."""
        def resolve(host, port):
            if resolve_log is not None:
                resolve_log.append(host)
            if host in HOSTS:
                return [PUBLIC_IP]
            return [ai[4][0] for ai in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)]

        def dial(ip, port, timeout):
            if dial_log is not None:
                dial_log.append((ip, port))
            if ip == PUBLIC_IP and port == 443:
                return socket.create_connection(("127.0.0.1", self.port), timeout)
            ipaddress.ip_address(ip)          # a real address: dial it for real
            return socket.create_connection((ip, port), timeout)

        return {"resolve": resolve, "dial": dial, "ssl_context": self.client_ctx}


# --- response shapes -------------------------------------------------------------------------------

def body(data: bytes, content_length: int | None = None, status: str = "200 OK"):
    """A body with a Content-Length that may lie (default: the true length; None: absent)."""
    def route(h):
        head = f"HTTP/1.1 {status}\r\nContent-Type: application/octet-stream\r\nConnection: close\r\n"
        if content_length is not None:
            head += f"Content-Length: {content_length}\r\n"
        h.raw(head.encode() + b"\r\n" + data)
    return route


def exact(data: bytes):
    return body(data, len(data))


def chunked(chunk: bytes, count: int):
    """`count` chunks of `chunk` in chunked transfer coding (no Content-Length)."""
    def route(h):
        h.raw(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n")
        frame = f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n"
        for _ in range(count):
            h.raw(frame)
        h.raw(b"0\r\n\r\n")
    return route


def stream(total: int, content_length: int | None, piece: int = 64 * 1024):
    """`total` bytes of 0xFF written in pieces, under a Content-Length that may lie or be absent."""
    def route(h):
        head = "HTTP/1.1 200 OK\r\nConnection: close\r\n"
        if content_length is not None:
            head += f"Content-Length: {content_length}\r\n"
        h.raw(head.encode() + b"\r\n")
        sent = 0
        while sent < total:
            n = min(piece, total - sent)
            h.raw(b"\xff" * n)
            sent += n
    return route


def redirect(location: str, status: str = "302 Found"):
    return lambda h: h.raw(f"HTTP/1.1 {status}\r\nLocation: {location}\r\nContent-Length: 0\r\n"
                           "Connection: close\r\n\r\n".encode())


def drip(every: float = 0.1, count: int = 200, headers: bool = True):
    """One byte every `every` seconds: of the body (headers sent at once) or of the headers."""
    def route(h):
        if headers:
            h.raw(b"HTTP/1.1 200 OK\r\nConnection: close\r\n\r\n")
            out = b"\xff" * count
        else:
            out = b"HTTP/1.1 200 OK\r\n" + b"X-Slow: " + b"a" * count + b"\r\n\r\n"
        for i in range(len(out)):
            h.raw(out[i:i + 1])
            time.sleep(every)
    return route
