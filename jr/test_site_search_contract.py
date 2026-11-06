"""Cross-language D2 contract: the web producer fixture must parse in Jr's GA4 lane."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import demand  # noqa: E402


def _row(event_name: str, q: str, count: int) -> dict:
    return {
        "dimensionValues": [{"value": event_name}, {"value": q}],
        "metricValues": [{"value": str(count)}],
    }


def test_public_model_tokens_survive_web_to_ga4_to_jr_contract():
    fixture = Path(__file__).resolve().parents[1] / "apps/web/lib/analytics-demand-contract.json"
    contract = json.loads(fixture.read_text())
    rows = []
    for case in contract["eligible"]:
        rows.append(_row("search_submit", case["emitted"], case["submits"]))
        if case["empty"]:
            rows.append(_row("search_empty", case["emitted"], case["empty"]))
    # GA4 returns the placeholder when the producer withheld unsafe/free-form q.
    rows.extend(_row("search_submit", "(not set)", 1) for _ in contract["excluded"])

    parsed, available = demand.parse_ga4_searchterm_rows(rows)
    assert available is True
    assert {row["term"]: (row["events"], row["zero_result"]) for row in parsed} == {
        "fnk0104s": (6, True),
        "es3c28p": (7, False),
    }
    assert {row["term"] for row in demand._floor_filter_events(parsed)} == {"fnk0104s", "es3c28p"}
