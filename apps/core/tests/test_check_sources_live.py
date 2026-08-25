"""The citation-liveness checker's verdict logic.

Lives here because CI only collects tests under apps/*/tests, and this logic is
worth protecting: it decides whether a PR is told its citations are broken. The
script is not a package, so it is loaded by path.
"""
import importlib.util
from pathlib import Path

import httpx
import pytest

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check_sources_live.py"
_spec = importlib.util.spec_from_file_location("check_sources_live", _SCRIPT)
checker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(checker)


def _client(*responses):
    """A client that replays the given statuses (or raises the given errors)."""
    queue = list(responses)

    def handler(request):
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        status, headers = item if isinstance(item, tuple) else (item, {})
        return httpx.Response(status, headers=headers)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _check(*responses):
    """Run check_url with sleeping disabled, so backoff never slows the suite."""
    with _client(*responses) as client:
        return checker.check_url(client, "https://example.com/x", sleep=lambda _s: None)


@pytest.mark.parametrize("status", sorted(checker.ALIVE_STATUS_CODES))
def test_alive_statuses(status):
    assert _check(status)[0] == "ALIVE"


@pytest.mark.parametrize("status", sorted(checker.DEAD_STATUS_CODES))
def test_only_gone_means_dead(status):
    """404/410 is the server saying the page is gone — the one true DEAD."""
    assert _check(status)[0] == "DEAD"


@pytest.mark.parametrize("status", sorted(checker.INCONCLUSIVE_STATUS_CODES))
def test_refused_to_answer_is_never_dead(status):
    """A 429 or a transient 5xx is no evidence the citation is broken.

    This is the regression that made CI cry wolf: GitHub rate-limits the runner,
    every retry gets another 429, and a live URL was reported as a dead source.
    """
    verdict, detail = _check(status, status, status)
    assert verdict == "INCONCLUSIVE", f"HTTP {status} must not be reported as a broken link"
    assert str(status) in detail


def test_a_rate_limit_that_clears_on_retry_is_alive():
    assert _check(429, 200)[0] == "ALIVE"


def test_retry_after_header_is_honoured():
    waits = []
    with _client((429, {"retry-after": "7"}), 200) as client:
        checker.check_url(client, "https://example.com/x", sleep=waits.append)
    assert waits == [7.0], "the server's own Retry-After must win over our backoff"


def test_backoff_grows_and_is_capped():
    waits = []
    with _client(429, 429, 429) as client:
        checker.check_url(client, "https://example.com/x", sleep=waits.append)
    assert waits == sorted(waits) and all(w <= checker.MAX_BACKOFF_SECONDS for w in waits)


def test_timeout_is_inconclusive_but_unresolvable_host_is_dead():
    """A slow network says nothing; a host that cannot resolve is really gone."""
    timeout = httpx.ConnectTimeout("timed out")
    assert _check(timeout, timeout, timeout)[0] == "INCONCLUSIVE"
    assert _check(httpx.UnsupportedProtocol("no such scheme"))[0] == "DEAD"
