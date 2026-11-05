#!/usr/bin/env python3
"""One real, uncached inference check for an external health monitor.

Run against the API base URL, e.g.:
    python3 scripts/intent_availability.py https://esp-atlas.com/api

Exit 0 means an uncached request understood an explicit Wi-Fi 6 constraint.
Exit 1 means degraded inference; emit this failure in the existing uptime
alert channel. Schedule separately at a bounded cadence (e.g. hourly), not
on every /health or /status poll. No provider credentials are needed here.
This HTTP-only check emits no browser analytics/search-empty event.
"""
import argparse
import json
import uuid

import httpx


def probe(api_url, client, nonce):
    # A fresh phrasing bypasses the intent DB cache; a firmware query would
    # take the deterministic path and could hide broken provider credentials.
    query = f"Find a board with Wi-Fi 6. Availability probe {nonce}."
    try:
        response = client.post(api_url.rstrip("/") + "/intent", json={"query": query})
    except httpx.RequestError:
        return {"status": "degraded", "component": "intent", "reason": "transport"}
    if response.status_code != 200:
        return {"status": "degraded", "component": "intent", "reason": "http_status", "http_status": response.status_code}
    try:
        body = response.json()
        available = (
            body.get("kind") == "filters"
            and body.get("cached") is False
            and isinstance(body.get("filters"), dict)
            and body["filters"].get("radio") == "wifi-6"
        )
    except (ValueError, AttributeError, TypeError):
        available = False
    return {"status": "ok" if available else "degraded", "component": "intent", "reason": "uncached_constraint" if available else "unexpected_response"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("api_url")
    args = parser.parse_args()
    with httpx.Client(timeout=20, follow_redirects=False) as client:
        result = probe(args.api_url, client, uuid.uuid4().hex)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
