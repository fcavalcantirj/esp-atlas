"""Network/credential isolation for Jr tests, never production code.

This guards Python's socket entry points in the test process. Local servers must
register their exact numeric loopback address and port; localhost alone is not
permission to contact an unrelated service on the developer's machine.

This is defense-in-depth, not a security sandbox: captured aliases, child
processes and credential files require a disposable, credential-free execution
environment with external networking disabled and no writable host mounts.
"""
from __future__ import annotations

import ipaddress
import os
import socket

_SECRET_SUFFIXES = ("_TOKEN", "_SECRET", "_API_KEY", "_PASSWORD")
_SECRET_NAMES = {
    "DATABASE_URL", "POPULARITY_DATABASE_URL", "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "TELEGRAM_CHAT_ID",
    "TELEGRAM_HOME_CHANNEL",
}


def clear_production_secrets(monkeypatch):
    """Remove inherited credentials; a test may explicitly inject fake values."""
    for name in list(os.environ):
        upper = name.upper()
        if upper.endswith(_SECRET_SUFFIXES) or upper in _SECRET_NAMES:
            monkeypatch.delenv(name, raising=False)


def install_network_guard(monkeypatch):
    """Deny DNS/dials/datagrams except explicitly registered loopback endpoints."""
    allowed = set()

    def endpoint(host, port):
        try:
            if isinstance(host, bytes):
                host = host.decode("ascii")
            ip = ipaddress.ip_address(host)
        except (ValueError, TypeError, UnicodeError):
            return None
        if not ip.is_loopback or type(port) is not int or not 0 < port <= 65535:
            return None
        return str(ip), port

    def allow_local_test_server(host, port):
        target = endpoint(host, port)
        if target is None:
            raise ValueError("test server must be a numeric loopback address and explicit port")
        allowed.add(target)

    def check(address):
        target = endpoint(*address[:2]) if isinstance(address, tuple) and len(address) >= 2 else None
        if target not in allowed:
            # Never include URLs, headers or credential-bearing proxy values.
            raise AssertionError("Jr test blocked network: inject a fake or register a local test server")

    original_getaddrinfo = socket.getaddrinfo
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_sendto = socket.socket.sendto

    def getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        if host == "localhost":
            # Synthetic local resolution is harmless; connect still requires the
            # exact registered port. Never ask the host resolver about this name.
            host = "127.0.0.1"
        else:
            check((host, port))
        # Only numeric addresses reach the OS: no external DNS query even here.
        return original_getaddrinfo(host, port, family, type, proto, flags | socket.AI_NUMERICHOST)

    def connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            check(address)
        return original_connect(sock, address)

    def connect_ex(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            check(address)
        return original_connect_ex(sock, address)

    def sendto(sock, data, *args):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            check(args[-1] if args else None)
        return original_sendto(sock, data, *args)

    def loopback_name(host):
        if host == "localhost":
            return "127.0.0.1"
        try:
            ip = ipaddress.ip_address(host)
        except (ValueError, TypeError):
            ip = None
        if ip is None or not ip.is_loopback:
            raise AssertionError("Jr test blocked network: external DNS")
        return str(ip)

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(socket, "gethostbyname", loopback_name)
    monkeypatch.setattr(socket, "gethostbyname_ex", lambda host: ("localhost", [], [loopback_name(host)]))
    monkeypatch.setattr(socket, "gethostbyaddr", lambda host: ("localhost", [], [loopback_name(host)]))
    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket.socket, "sendto", sendto)
    if hasattr(socket.socket, "sendmsg"):
        original_sendmsg = socket.socket.sendmsg

        def sendmsg(sock, buffers, ancdata=(), flags=0, address=None):
            if address is not None and sock.family in (socket.AF_INET, socket.AF_INET6):
                check(address)
            if address is None:
                return original_sendmsg(sock, buffers, ancdata, flags)
            return original_sendmsg(sock, buffers, ancdata, flags, address)

        monkeypatch.setattr(socket.socket, "sendmsg", sendmsg)
    return allow_local_test_server
