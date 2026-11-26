"""scripts/check_claims.py, backfill kind (root-cause plan step 2): a board.md change is re-derived by Jr's own
resolver on the PRE-change board, from the trusted checkout; anything the re-derivation does not cover fails."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO / "scripts"), str(REPO / "jr"), str(REPO / "apps" / "core" / "src")]

import board_backfill as bb  # noqa: E402
import check_claims as cc  # noqa: E402

FIX = REPO / "jr" / "fixtures" / "board_backfill"
TODAY = "2026-11-26"
BID, SOC = "esp32-devkitc", "esp32"
URL = bb.VENDOR_DOC_RESOLVERS["espressif"](BID, SOC)[0]


def _fetch(pages):
    def fetch(url):
        t = pages.get(url)
        return {"ok": True, "status": 200, "text": t} if t is not None else {"ok": False, "status": 404, "error": "HTTP 404"}
    return fetch


PAGES = {URL: (FIX / "esp32-devkitc.html").read_text()}
BASE = (f"---\nid: {BID}\ntype: board\nbrand: espressif\nname: ESP32-DevKitC\nsoc: {SOC}\n"
        "sources:\n- field: '*'\n  url: https://example.test/devkitc\n  verified: '2026-01-01'\n---\n\n# devkitc\n")


def _head(value="usb-uart-bridge-unspecified", url=URL, extra="", body="# devkitc\n", name="ESP32-DevKitC"):
    return (f"---\nid: {BID}\ntype: board\nbrand: espressif\nname: {name}\nsoc: {SOC}\n{extra}usb_serial: {value}\n"
            "sources:\n- field: '*'\n  url: https://example.test/devkitc\n  verified: '2026-01-01'\n"
            f"- field: usb_serial\n  url: {url}\n  verified: '{TODAY}'\n---\n\n{body}")


def check(head, pages=PAGES):
    return cc.check_board_backfill(BASE, head, REPO / "data", _fetch(pages), TODAY)


def test_a_value_jrs_resolver_re_derives_from_the_cited_page_passes():
    r = check(_head())
    assert r["verdict"] == cc.PASS, r
    assert any("sha256" in x for x in r["reasons"])                     # the source is bound by its hash


@pytest.mark.parametrize("head,why", [
    (_head(value="ch340"), "differs"),                                  # a value the page does not give
    (_head(url="https://example.test/other"), "cited URL"),             # cited somewhere else
    (_head(name="Renamed"), "existing field"),                          # an existing value changed
    (_head(body="# devkitc\nnew prose\n"), "body"),                     # prose changed
    (_head(extra="images:\n  photo: https://x/p.jpg\n"), "not under the backfill gate"),
])
def test_anything_the_re_derivation_does_not_cover_fails(head, why):
    r = check(head)
    assert r["verdict"] == cc.FAIL and any(why in x for x in r["reasons"]), r


def test_an_unreadable_page_is_inconclusive_never_pass():
    assert check(_head(), pages={})["verdict"] == cc.INCONCLUSIVE


def test_a_board_change_with_no_backfilled_field_is_not_a_backfill_claim():
    assert cc.check_board_backfill(BASE, BASE, REPO / "data", _fetch(PAGES), TODAY) is None
