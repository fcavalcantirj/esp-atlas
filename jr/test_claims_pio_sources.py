"""jr/claims_pio_sources.py — pinned project trees and vendor-verified platform packages (Jr redesign plan, step 4b).
A fake HTTP layer only; no network."""
import hashlib
import io
import json
import tarfile
import zipfile

import pytest

import claims_pio_sources as src

SHA = "971c066b37dbe3dbb9ac1096d9e72f32ab5b3452"
MANIFEST = json.dumps({"name": "Heltec WiFi Kit 32 (V3)", "build": {"mcu": "esp32s3", "variant": "heltec_wifi_kit_32_V3"}}).encode()


def tgz(files: dict) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def zipb(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


OFFICIAL_PKG = tgz({"boards/heltec_wifi_kit_32_V3.json": MANIFEST, "platform.json": b"{}"})
PIOARDUINO_PKG = zipb({"platform-espressif32/boards/heltec_wifi_kit_32_V3.json": MANIFEST})


class FakeHttp:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def json(self, url):
        self.calls.append(url)
        v = self.routes.get(url)
        if v is None:
            raise src.Unreadable(f"404 {url}")
        return v

    def bytes(self, url):
        self.calls.append(url)
        v = self.routes.get(url)
        if v is None:
            raise src.Unreadable(f"404 {url}")
        return v


def registry(pkg=OFFICIAL_PKG, checksum=None):
    return {"versions": [{"name": "6.6.0", "files": [{"name": "espressif32-6.6.0.tar.gz",
            "checksum": {"sha256": checksum or hashlib.sha256(pkg).hexdigest()},
            "download_url": "https://dl.registry.platformio.org/download/platformio/platform/espressif32/6.6.0/espressif32-6.6.0.tar.gz"}]}]}


def test_an_official_package_is_verified_against_the_registry_checksum_and_yields_its_manifest():
    http = FakeHttp({src.REGISTRY: registry(),
                     "https://dl.registry.platformio.org/download/platformio/platform/espressif32/6.6.0/espressif32-6.6.0.tar.gz": OFFICIAL_PKG})
    idx = src.PlatformIndex(http)
    got = idx("espressif32@6.6.0", "heltec_wifi_kit_32_V3")
    assert got == {"package_digest": hashlib.sha256(OFFICIAL_PKG).hexdigest(), "manifest": MANIFEST}
    assert idx("platformio/espressif32@6.6.0", "no_such_board") == {"package_digest": hashlib.sha256(OFFICIAL_PKG).hexdigest(), "manifest": None}


def test_a_package_whose_bytes_do_not_match_the_published_digest_is_refused():
    http = FakeHttp({src.REGISTRY: registry(checksum="0" * 64),
                     "https://dl.registry.platformio.org/download/platformio/platform/espressif32/6.6.0/espressif32-6.6.0.tar.gz": OFFICIAL_PKG})
    assert src.PlatformIndex(http)("espressif32@6.6.0", "heltec_wifi_kit_32_V3") is None


def test_a_pioarduino_release_is_verified_against_githubs_asset_digest():
    url = "https://github.com/pioarduino/platform-espressif32/releases/download/55.03.37/platform-espressif32.zip"
    api = "https://api.github.com/repos/pioarduino/platform-espressif32/releases/tags/55.03.37"
    http = FakeHttp({api: {"assets": [{"name": "platform-espressif32.zip", "digest": "sha256:" + hashlib.sha256(PIOARDUINO_PKG).hexdigest(),
                                       "browser_download_url": url}]}, url: PIOARDUINO_PKG})
    got = src.PlatformIndex(http)(url, "heltec_wifi_kit_32_V3")
    assert got["manifest"] == MANIFEST and got["package_digest"] == hashlib.sha256(PIOARDUINO_PKG).hexdigest()


def test_a_release_asset_without_a_published_digest_is_refused():
    url = "https://github.com/pioarduino/platform-espressif32/releases/download/55.03.37/platform-espressif32.zip"
    api = "https://api.github.com/repos/pioarduino/platform-espressif32/releases/tags/55.03.37"
    http = FakeHttp({api: {"assets": [{"name": "platform-espressif32.zip", "browser_download_url": url}]}, url: PIOARDUINO_PKG})
    assert src.PlatformIndex(http)(url, "heltec_wifi_kit_32_V3") is None


def test_each_package_is_downloaded_once_per_run():
    http = FakeHttp({src.REGISTRY: registry(),
                     "https://dl.registry.platformio.org/download/platformio/platform/espressif32/6.6.0/espressif32-6.6.0.tar.gz": OFFICIAL_PKG})
    idx = src.PlatformIndex(http)
    for b in ("heltec_wifi_kit_32_V3", "x", "y"):
        idx("espressif32@6.6.0", b)
    assert sum("dl.registry" in c for c in http.calls) == 1


def tree_routes(entries, truncated=False, files=None):
    r = {"https://api.github.com/repos/o/r": {"id": 42, "default_branch": "main", "full_name": "o/r"},
         "https://api.github.com/repos/o/r/commits/main": {"sha": SHA},
         f"https://api.github.com/repos/o/r/git/trees/{SHA}?recursive=1": {"truncated": truncated, "tree": entries}}
    for path, data in (files or {}).items():
        r[f"https://raw.githubusercontent.com/o/r/{SHA}/{path}"] = data
    return r


def test_a_project_is_pinned_to_one_commit_and_its_config_files_carry_their_blob_shas(tmp_path):
    entries = [{"path": "platformio.ini", "type": "blob", "mode": "100644", "sha": "a" * 40},
               {"path": "ini/extra_a.ini", "type": "blob", "mode": "100644", "sha": "b" * 40},
               {"path": "src/main.cpp", "type": "blob", "mode": "100644", "sha": "c" * 40}]
    http = FakeHttp(tree_routes(entries, files={"platformio.ini": b"[env:x]\n", "ini/extra_a.ini": b"[env:y]\n"}))
    proj = src.fetch_project(http, "o/r", tmp_path)
    assert proj["repo"] == {"slug": "o/r", "id": 42} and proj["sha"] == SHA
    assert proj["blobs"] == {"platformio.ini": "a" * 40, "ini/extra_a.ini": "b" * 40}
    assert (tmp_path / "platformio.ini").read_bytes() == b"[env:x]\n" and not (tmp_path / "src").exists()


@pytest.mark.parametrize("entries, truncated, why", [
    ([{"path": "platformio.ini", "type": "blob", "mode": "100644", "sha": "a" * 40}], True, "truncated"),
    ([{"path": "platformio.ini", "type": "blob", "mode": "100644", "sha": "a" * 40},
      {"path": "boards/x.json", "type": "blob", "mode": "120000", "sha": "d" * 40}], False, "symlink"),
    ([{"path": "src/main.cpp", "type": "blob", "mode": "100644", "sha": "c" * 40}], False, "no platformio.ini"),
])
def test_an_unverifiable_tree_is_refused(tmp_path, entries, truncated, why):
    http = FakeHttp(tree_routes(entries, truncated=truncated, files={"platformio.ini": b"[env:x]\n"}))
    with pytest.raises(src.Unreadable, match=why):
        src.fetch_project(http, "o/r", tmp_path)


def test_a_fact_links_to_the_board_that_cites_its_definition_and_digest():
    catalog = {"heltec-wifi-kit-32-v3": [{"id": "heltec_wifi_kit_32_V3", "platform_package": "x", "manifest_digest": "m" * 64}],
               "other": [{"id": "heltec_wifi_kit_32_V3", "platform_package": "y", "manifest_digest": "n" * 64}]}
    assert src.board_for("heltec_wifi_kit_32_V3", "m" * 64, catalog) == "heltec-wifi-kit-32-v3"
    assert src.board_for("heltec_wifi_kit_32_V3", "z" * 64, catalog) is None          # same id, other definition bytes
    both = {**catalog, "dup": [{"id": "heltec_wifi_kit_32_V3", "platform_package": "x", "manifest_digest": "m" * 64}]}
    assert src.board_for("heltec_wifi_kit_32_V3", "m" * 64, both) is None              # ambiguous: never guessed
