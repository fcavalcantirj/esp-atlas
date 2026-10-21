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


# ---------------------------------------------------------------------------
# SSRF via redirect: an allowlisted host that bounces off-allowlist must not be
# followed. GitHub really does redirect (github.com -> objects.github...), so
# redirects cannot simply be refused -- every hop is re-validated instead.
# ---------------------------------------------------------------------------

GITHUB_ASSET = "https://github.com/o/r/releases/download/1/fw.bin"


@pytest.mark.parametrize(
    "location",
    [
        "https://evil.example.com/x.bin",            # absolute, off-allowlist
        "//evil.example.com/x.bin",                  # protocol-relative
        "http://objects.githubusercontent.com/x.bin",  # allowlisted host, downgraded scheme
        "https://github.com.evil.example/x.bin",     # suffix confusion
        "https://169.254.169.254/latest/meta-data/",  # cloud metadata
        "file:///etc/passwd",
        "",                                          # redirect with no Location
        None,
    ],
)
def test_redirect_off_the_allowlist_is_refused(location):
    from esp_atlas_core.flash import next_hop

    assert next_hop(GITHUB_ASSET, location) is None


@pytest.mark.parametrize(
    "location,expected",
    [
        # the real GitHub hop the proxy must keep working
        ("https://objects.githubusercontent.com/x.bin", "https://objects.githubusercontent.com/x.bin"),
        ("https://release-assets.githubusercontent.com/y.bin", "https://release-assets.githubusercontent.com/y.bin"),
        # relative Location resolved against the redirecting URL, then checked
        ("/o/r/releases/download/1/other.bin", "https://github.com/o/r/releases/download/1/other.bin"),
    ],
)
def test_redirect_that_stays_on_the_allowlist_is_followed(location, expected):
    from esp_atlas_core.flash import next_hop

    assert next_hop(GITHUB_ASSET, location) == expected


# ---------------------------------------------------------------------------
# Multi-part images (`flash.parts`, SPEC-wizard P3 "multi-part"): bootloader,
# partition table, boot_app0 and app are written at their OWN offsets, never as
# one merged image -- a merged image fills the gaps between them (e.g. NVS at
# 0x9000-0xDFFF) with 0xFF and wipes whatever the device keeps there.
# ---------------------------------------------------------------------------

_RELEASE = "https://github.com/o/r/releases/download/v1/"
_FOUR_PARTS = [
    {"url": _RELEASE + "bootloader.bin", "offset": "0x0"},
    {"url": _RELEASE + "partitions.bin", "offset": "0x8000"},
    {"url": _RELEASE + "boot_app0.bin", "offset": "0xe000"},
    {"url": _RELEASE + "firmware.bin", "offset": "0x10000"},
]


def _fake_parts_recipe(monkeypatch, parts):
    recipe = {
        "id": "x__y",
        "board": "m5stick-s3",
        "firmware": "launcher",
        "chip_family": "esp32-s3",
        "flash": {"method": "release-bin", "parts": parts},
    }
    monkeypatch.setattr("esp_atlas_core.flash.get_recipe", lambda _id: recipe)
    return recipe


def test_multi_part_recipe_emits_each_part_at_its_own_offset(monkeypatch, built_db_path):
    _fake_parts_recipe(monkeypatch, _FOUR_PARTS)
    manifest = build_manifest("x__y", db_path=built_db_path)
    assert manifest is not None
    assert manifest["new_install_prompt_erase"] is True  # erase stays the human's choice
    (build,) = manifest["builds"]
    assert build["chipFamily"] == "ESP32-S3"
    assert "serialType" not in build
    # Every part goes through the same-origin proxy, addressed by its index.
    assert build["parts"] == [
        {"path": "/api/flash-bin?recipe=x__y&part=0", "offset": 0x0},
        {"path": "/api/flash-bin?recipe=x__y&part=1", "offset": 0x8000},
        {"path": "/api/flash-bin?recipe=x__y&part=2", "offset": 0xE000},
        {"path": "/api/flash-bin?recipe=x__y&part=3", "offset": 0x10000},
    ]


def test_part_resolves_by_index_and_never_falls_back(monkeypatch):
    _fake_parts_recipe(monkeypatch, _FOUR_PARTS)
    for index, part in enumerate(_FOUR_PARTS):
        assert bin_url_for("x__y", part=index) == part["url"]
    # Out of range is a refusal, and a parts recipe has no single merged image
    # for a part-less request to fall back to.
    assert bin_url_for("x__y", part=4) is None
    assert bin_url_for("x__y", part=-1) is None
    assert bin_url_for("x__y") is None


@pytest.mark.parametrize("index", [0, 1, 2, 3])
@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/o/r/releases/download/v1/x.bin",  # plaintext
        "https://evil.example.com/x.bin",  # off-allowlist host
        "https://github.com.evil.example/x.bin",  # suffix-confusion host
        "https://169.254.169.254/latest/meta-data/",  # cloud metadata
    ],
)
def test_each_part_url_off_the_allowlist_is_refused(monkeypatch, index, url):
    parts = [dict(p) for p in _FOUR_PARTS]
    parts[index]["url"] = url
    _fake_parts_recipe(monkeypatch, parts)
    assert bin_url_for("x__y", part=index) is None
    # The bad part does not poison the others: they still resolve.
    for other in set(range(4)) - {index}:
        assert bin_url_for("x__y", part=other) == parts[other]["url"]


def test_every_recorded_part_url_is_https_and_allowlisted():
    """The SSRF surface for multi-part records, same rule as bin_url."""
    from urllib.parse import urlparse

    offenders = []
    for recipe in _release_bin_recipes():
        for index, part in enumerate((recipe.get("flash") or {}).get("parts") or []):
            parsed = urlparse(part.get("url") or "")
            if parsed.scheme != "https" or parsed.hostname not in ALLOWED_BIN_HOSTS:
                offenders.append((recipe["id"], index, part.get("url")))
    assert not offenders, f"part url off the allowlist: {offenders}"


def test_every_multi_part_recipe_yields_a_manifest_with_every_part(built_db_path):
    """No half-configured multi-part recipe: every recorded part must be flashed."""
    short = []
    for recipe in _release_bin_recipes():
        parts = (recipe.get("flash") or {}).get("parts")
        if not parts:
            continue
        manifest = build_manifest(recipe["id"], db_path=built_db_path)
        if manifest is None or len(manifest["builds"][0]["parts"]) != len(parts):
            short.append(recipe["id"])
    assert not short, f"multi-part recipe(s) that do not flash every part: {short}"


DOUTOR_VPD = "m5stick-s3__doutor-vpd"
DOUTOR_VPD_IMAGES = [  # (file, offset) -- the release's own manifest.json `install` list
    ("bootloader.bin", 0x0),
    ("partitions.bin", 0x8000),
    ("boot_app0.bin", 0xE000),
    ("firmware.bin", 0x10000),
]


def test_doutor_vpd_writes_four_images_at_their_own_offsets(built_db_path):
    recipe = get_recipe(DOUTOR_VPD)
    assert recipe is not None
    assert "bin_url" not in recipe["flash"], "never one merged image: NVS sits in the gaps"
    manifest = build_manifest(DOUTOR_VPD, db_path=built_db_path)
    assert manifest is not None
    assert manifest["new_install_prompt_erase"] is True
    (build,) = manifest["builds"]
    assert build["chipFamily"] == "ESP32-S3"
    assert [p["offset"] for p in build["parts"]] == [offset for _f, offset in DOUTOR_VPD_IMAGES]
    assert [p["path"] for p in build["parts"]] == [
        f"/api/flash-bin?recipe={DOUTOR_VPD}&part={i}" for i in range(len(DOUTOR_VPD_IMAGES))
    ]
    urls = [bin_url_for(DOUTOR_VPD, part=i) for i in range(len(DOUTOR_VPD_IMAGES))]
    for url, (name, _offset) in zip(urls, DOUTOR_VPD_IMAGES):
        assert url is not None and url.startswith(
            "https://github.com/fcavalcantirj/doutor-vpd-firmware/releases/download/"
        )
        assert url.endswith("/" + name)
    # One pinned release for all four, never `releases/latest/...`: the proxy marks
    # every part `immutable` at the edge, cached per part, so a moving URL could
    # hand a browser images from two different releases.
    assert len({url.rsplit("/", 1)[0] for url in urls}) == 1
    assert not any("/releases/latest/" in url for url in urls)
