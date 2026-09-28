"""Tests for jr/telemetry.py — guards against import-time Composio side effects.

jr-tests CI installs only "pyyaml jsonschema requests pytest" + apps/core -- no composio, no
~/.composio.key. `import telemetry` must succeed in that environment; only calling _ex() (which
routes through the real Google APIs) needs composio. This reproduces the CI environment by
blocking the composio import and reloading the module.
"""
from __future__ import annotations

import builtins
import importlib
import sys

import pytest


def test_import_succeeds_without_composio_installed(monkeypatch):
    real_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name == "composio" or name.startswith("composio."):
            raise ImportError(f"No module named {name!r}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)
    monkeypatch.delitem(sys.modules, "composio", raising=False)
    monkeypatch.delitem(sys.modules, "telemetry", raising=False)

    telemetry = importlib.import_module("telemetry")
    try:
        assert telemetry.GA4_PROPERTY == "properties/551132215"
        assert telemetry.GSC_SITE == "sc-domain:esp-atlas.com"
    finally:
        importlib.reload(telemetry)  # restore the real module for later tests


def test_composio_client_not_built_until_first_ex_call(monkeypatch):
    import telemetry

    monkeypatch.setattr(telemetry, "_client", None)
    assert telemetry._client is None  # constructing telemetry never touches Composio


def test_composio_lazily_builds_and_caches_the_client(monkeypatch, tmp_path):
    import telemetry

    built = []

    class FakeComposio:
        def __init__(self, api_key):
            built.append(api_key)
            self.tools = self

        def execute(self, **kwargs):
            return {"successful": True, "data": kwargs}

    fake_module = type(sys)("composio")
    fake_module.Composio = FakeComposio
    monkeypatch.setitem(sys.modules, "composio", fake_module)
    (tmp_path / ".composio.key").write_text("fake-key\n")
    monkeypatch.setattr(telemetry.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(telemetry, "_client", None)

    client1 = telemetry._composio()
    client2 = telemetry._composio()

    assert built == ["fake-key"]           # constructed exactly once
    assert client1 is client2              # cached across calls
