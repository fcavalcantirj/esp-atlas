"""scripts/check_claims.py — the trusted re-proof of a build-target claim (Jr redesign plan, step 5).

The claim under test is built by the real producer (jr/claims_pio.py) from NightDriverStrip's platformio.ini at
971c066b, served by a fake HTTP layer with the fixture manifest; the checker must re-prove it end to end and
refuse every kind of tampering. No network.
"""
import copy
import hashlib
import json
from pathlib import Path

import pytest

import check_claims as cc

REPO = Path(__file__).resolve().parent.parent
FIX = REPO / "jr" / "fixtures" / "claims_pio"
SHA = "971c066b37dbe3dbb9ac1096d9e72f32ab5b3452"
SLUG = "PlummersSoftwareLLC/NightDriverStrip"
RID = 408525324
SPEC = "https://github.com/pioarduino/platform-espressif32/releases/download/55.03.37/platform-espressif32.zip"
INI = (FIX / "nds-971c066b" / "platformio.ini").read_bytes()
BLOB = "a" * 40
MANIFEST = (FIX / "heltec_wifi_kit_32_V3.pioarduino-55.03.37.json").read_bytes()
MDIGEST = hashlib.sha256(MANIFEST).hexdigest()


class FakeHttp:
    def __init__(self, routes):
        self.routes = routes

    def json(self, url):
        if url not in self.routes:
            raise cc.src.Unreadable(f"404 {url}")
        return self.routes[url]

    def bytes(self, url):
        if url not in self.routes:
            raise cc.src.Unreadable(f"404 {url}")
        return self.routes[url]


def routes(ini=INI):
    return {f"https://api.github.com/repos/{SLUG}": {"id": RID, "default_branch": "main", "full_name": SLUG},
            f"https://api.github.com/repos/{SLUG}/git/trees/{SHA}?recursive=1":
                {"truncated": False, "tree": [{"path": "platformio.ini", "type": "blob", "mode": "100644", "sha": BLOB}]},
            f"https://raw.githubusercontent.com/{SLUG}/{SHA}/platformio.ini": ini}


def index(spec, board):
    if spec != SPEC:
        return None
    p = FIX / f"{board}.pioarduino-55.03.37.json"
    return {"package_digest": "f" * 64, "manifest": p.read_bytes() if p.exists() else None}


CATALOG = {"heltec-wifi-kit-32-v3": [{"id": "heltec_wifi_kit_32_V3", "platform_package": SPEC, "manifest_digest": MDIGEST}]}
FIRMWARE = {"id": "nightdriverstrip", "url": f"https://github.com/{SLUG}"}


@pytest.fixture(scope="module")
def recipe(tmp_path_factory):
    """The producer's own claim for env heltecv3demo, as a build-target recipe."""
    claim = cc.src.claim_for(FakeHttp(routes()), SLUG, SHA, "heltecv3demo", index, tmp_path_factory.mktemp("p"))
    return {"id": "heltec-wifi-kit-32-v3__nightdriverstrip", "type": "recipe", "board": "heltec-wifi-kit-32-v3",
            "firmware": "nightdriverstrip", "status": "build-target", "chip_family": "esp32-s3", "claim": claim,
            "sources": [{"field": "claim", "url": f"https://github.com/{SLUG}/blob/{SHA}/platformio.ini", "verified": "2026-11-22"}]}


def check(recipe, http=None, catalog=CATALOG, firmware=FIRMWARE, tmp=None):
    return cc.check_recipe(recipe, firmware, catalog, http or FakeHttp(routes()), index, tmp)


def test_the_producers_own_claim_re_proves(recipe, tmp_path):
    v = check(recipe, tmp=tmp_path)
    assert v["verdict"] == cc.PASS, v["reasons"]


@pytest.mark.parametrize("edit, why", [
    (lambda r: r["claim"].__setitem__("board_id", "m5stick-c"), "board"),
    (lambda r: r["claim"].__setitem__("env", "m5plusdemo"), "refused"),
    (lambda r: r["claim"]["repo"].__setitem__("id", 1), "repo id"),
    (lambda r: r["claim"]["platform"].__setitem__("manifest_digest", "0" * 64), "manifest"),
    (lambda r: r["claim"]["platform"].__setitem__("package_digest", "0" * 64), "package"),
    (lambda r: r["claim"]["files"][0].__setitem__("blob", "b" * 40), "files"),
    (lambda r: r["claim"].__setitem__("platformio_version", "0.0.1"), "platformio"),
    (lambda r: r.__setitem__("board", "some-other-board"), "board page"),
    (lambda r: r.__setitem__("flash", {"method": "release-bin"}), "flash"),
])
def test_any_tampering_fails(recipe, tmp_path, edit, why):
    r = copy.deepcopy(recipe)
    edit(r)
    v = check(r, tmp=tmp_path)
    assert v["verdict"] == cc.FAIL and any(why in x for x in v["reasons"]), v


def test_a_claim_on_a_firmware_from_another_repo_fails(recipe, tmp_path):
    v = check(recipe, firmware={"id": "nightdriverstrip", "url": "https://github.com/someone/else"}, tmp=tmp_path,
              http=FakeHttp({**routes(), "https://api.github.com/repos/someone/else": {"id": 7, "default_branch": "main"}}))
    assert v["verdict"] == cc.FAIL and any("repo id" in x for x in v["reasons"])


def test_an_unreadable_source_is_inconclusive_never_pass(recipe, tmp_path):
    r = routes()
    del r[f"https://raw.githubusercontent.com/{SLUG}/{SHA}/platformio.ini"]
    v = check(recipe, http=FakeHttp(r), tmp=tmp_path)
    assert v["verdict"] == cc.INCONCLUSIVE


def test_the_config_changed_at_the_same_commit_fails(recipe, tmp_path):
    changed = INI.replace(b"heltec_wifi_kit_32_V3", b"heltec_wifi_kit_32_v2", 1)
    v = check(recipe, http=FakeHttp(routes(ini=changed)), tmp=tmp_path)
    assert v["verdict"] == cc.FAIL


def test_a_claim_whose_id_is_not_its_named_repos_fails_even_when_the_firmware_agrees(recipe, tmp_path):
    """Only check 1 can see this: the claim names NightDriverStrip but carries repo B's id, and the firmware
    record points at repo B."""
    r = copy.deepcopy(recipe)
    r["claim"]["repo"]["id"] = 999
    http = FakeHttp({**routes(), "https://api.github.com/repos/someone/b": {"id": 999, "default_branch": "main"}})
    v = check(r, firmware={"id": "nightdriverstrip", "url": "https://github.com/someone/b"}, http=http, tmp=tmp_path)
    assert v["verdict"] == cc.FAIL and any(f"{SLUG} is {RID}" in x for x in v["reasons"]), v


def test_an_env_named_for_another_product_fails_the_trusted_check(recipe, tmp_path):
    """2026-11-27: the product-name refusal is enforced by the checker too, never only by the producer. Here the
    catalog names say env heltecv3demo carries another product's name ('heltecv3demo' made up for the test)."""
    names = {"heltec-wifi-kit-32-v3": {"wifikit32v3"}, "other-product": {"heltecv3demo"}}
    v = cc.check_recipe(recipe, FIRMWARE, CATALOG, FakeHttp(routes()), index, tmp_path, names=names)
    assert v["verdict"] == cc.FAIL and any("product name" in x and "other-product" in x for x in v["reasons"]), v
    ok = cc.check_recipe(recipe, FIRMWARE, CATALOG, FakeHttp(routes()), index, tmp_path,
                         names={"heltec-wifi-kit-32-v3": {"wifikit32v3"}})
    assert ok["verdict"] == cc.PASS, ok["reasons"]
