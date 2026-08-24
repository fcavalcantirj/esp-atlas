"""Manifest generation + the proxy's allowlist (SPEC-wizard P3)."""
import pytest

from esp_atlas_core.flash import (
    ALLOWED_BIN_HOSTS,
    _offset,
    bin_url_for,
    build_manifest,
    get_recipe,
)
from esp_atlas_core.firmware import list_recipes


def _release_bin_recipes():
    return [r for r in list_recipes() if (r.get("flash") or {}).get("method") == "release-bin"]


def test_manifest_shape_matches_esp_web_tools(built_db_path):
    manifest = build_manifest("m5cardputer__launcher", db_path=built_db_path)
    assert manifest is not None
    assert manifest["new_install_prompt_erase"] is True  # ask before wiping
    build = manifest["builds"][0]
    assert build["chipFamily"] == "ESP32-S3"
    assert build["parts"][0]["offset"] == 0
    # Merged image: exactly one part, and it must go through our own proxy --
    # a raw GitHub URL here would be blocked by CORS in the browser.
    assert len(build["parts"]) == 1
    assert build["parts"][0]["path"].startswith("/api/flash-bin")
    assert "githubusercontent" not in build["parts"][0]["path"]


def test_builds_carry_no_serial_type(built_db_path):
    """A lone labelled build is a trap, so we ship an unlabelled one.

    esp-web-tools picks a build by (chipFamily, serialType) and falls back only
    to a build whose serialType is *undefined*; a build labelled for the other
    transport is never used. One recipe here is one merged binary that flashes
    over either, so labelling it could only ever reject a valid port.
    """
    for recipe_id in ("m5cardputer__launcher", "m5stack-core2__launcher"):
        build = build_manifest(recipe_id, db_path=built_db_path)["builds"][0]
        assert "serialType" not in build, "an unmatched serialType would fail the flash"


def test_offsets_are_json_numbers_not_hex_strings(built_db_path):
    """esptool-js does arithmetic on the offset; a string corrupts the address."""
    for part in build_manifest("m5cardputer__launcher", db_path=built_db_path)["builds"][0]["parts"]:
        assert isinstance(part["offset"], int)


def test_chip_families_match_esp_web_tools_exactly(built_db_path):
    """Matching is exact string equality against esptool-js's CHIP_NAME."""
    from esp_atlas_core.flash import _CHIP_FAMILIES

    allowed = {
        "ESP32", "ESP32-C2", "ESP32-C3", "ESP32-C5", "ESP32-C6",
        "ESP32-C61", "ESP32-H2", "ESP32-P4", "ESP32-S2", "ESP32-S3", "ESP8266",
    }
    assert set(_CHIP_FAMILIES.values()) <= allowed


def test_no_manifest_without_a_recorded_binary(built_db_path):
    """A release-bin recipe with no bin_url is a handoff, not a broken manifest."""
    recipe = get_recipe("m5cardputer__esp32marauder")
    assert not (recipe.get("flash") or {}).get("bin_url"), "fixture assumption changed"
    assert build_manifest("m5cardputer__esp32marauder", db_path=built_db_path) is None


def test_no_manifest_for_unknown_or_non_release_bin_recipes(built_db_path):
    assert build_manifest("nope__nope", db_path=built_db_path) is None
    handoff = next(r for r in list_recipes() if (r.get("flash") or {}).get("method") == "web-flasher")
    assert build_manifest(handoff["id"], db_path=built_db_path) is None


def test_every_release_bin_recipe_with_a_url_yields_a_manifest(built_db_path):
    """No half-configured recipe: if it records a binary, it must flash."""
    broken = [
        r["id"]
        for r in _release_bin_recipes()
        if (r.get("flash") or {}).get("bin_url") and build_manifest(r["id"], db_path=built_db_path) is None
    ]
    assert not broken, f"recipe(s) record a binary but produce no manifest: {broken}"


def test_bin_url_resolves_only_from_a_recipe(built_db_path):
    assert bin_url_for("m5cardputer__launcher").startswith("https://github.com/bmorcelli/Launcher/releases/")
    assert bin_url_for("nope__nope") is None
    # A part index outside the recorded parts must not fall back to bin_url.
    assert bin_url_for("m5cardputer__launcher", part=7) is None


def test_every_recorded_bin_url_is_https_and_allowlisted():
    """The SSRF surface: a record must never point the proxy off-allowlist."""
    from urllib.parse import urlparse

    offenders = []
    for recipe in _release_bin_recipes():
        url = (recipe.get("flash") or {}).get("bin_url")
        if not url:
            continue
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_BIN_HOSTS:
            offenders.append((recipe["id"], url))
    assert not offenders, f"bin_url off the allowlist: {offenders}"


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/x/y.bin",  # plaintext
        "https://evil.example.com/x.bin",  # off-allowlist host
        "https://github.com.evil.example/x.bin",  # suffix-confusion host
        "file:///etc/passwd",
        "https://169.254.169.254/latest/meta-data/",  # cloud metadata
    ],
)
def test_bin_url_rejects_untrusted_targets(monkeypatch, url):
    """Even if a record itself were wrong, the host check must refuse it."""
    monkeypatch.setattr(
        "esp_atlas_core.flash.get_recipe",
        lambda _id: {"id": "x__y", "flash": {"method": "release-bin", "bin_url": url}},
    )
    assert bin_url_for("x__y") is None


def test_offset_parses_hex_and_decimal():
    assert _offset("0x10000") == 65536
    assert _offset("0x0") == 0
    assert _offset(None) == 0
    assert _offset(4096) == 4096
