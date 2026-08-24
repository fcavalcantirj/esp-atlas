"""ESP Web Tools manifests generated from a recipe (SPEC-wizard P3).

    build_manifest("m5cardputer__launcher")  # -> {"name": ..., "builds": [...]}

A `release-bin` recipe already carries everything a manifest needs -- the chip
family, where the binary lives and at what offset -- so the manifest is derived,
never authored. Two shapes are supported, matching the spec: a merged image
(`flash.bin_url` + `flash.offset`, one part) and a multi-part image
(`flash.parts[]`, emitted verbatim).

`parts[].path` deliberately points at esp-atlas's own streaming proxy rather
than the upstream URL: esptool-js fetches each part in the browser, and GitHub
release assets send no Access-Control-Allow-Origin (measured 2026-08-23), so a
direct fetch is blocked by CORS. The proxy makes the fetch same-origin. It
streams; it never stores a copy (SPEC-wizard's "never rehost" line).

On `serialType` (verified against esp-web-tools 10.4.0 source, `src/flash.ts`):
the field is real but it does NOT configure the serial link. The tool detects
cdc-vs-uart itself from the port's USB VID/PID, then uses `serialType` only to
*choose between several builds of the same chip*. Its lookup is:

    builds.find(b => b.chipFamily === chip && b.serialType === detected)
    || builds.find(b => b.chipFamily === chip && b.serialType === undefined)

A build whose label disagrees with what was detected is never a fallback. So a
lone labelled build is a trap: a board that exposes both native USB and a UART
bridge would fail with "your board is not supported" whenever the user picks the
port we didn't predict. A recipe here maps to ONE merged binary that flashes
over either transport, so we emit one build with NO `serialType` and let it match
any port. (SPEC-wizard asks us to derive the field from the board's USB fields;
that reasoning is inverted -- see the note raised with the architect.)
"""
from urllib.parse import urlparse

from esp_atlas_core.firmware import get_firmware, list_recipes
from esp_atlas_core.search import get_part

# soc id -> the chipFamily string ESP Web Tools expects. Explicit rather than
# uppercasing the id, so a chip the tool cannot flash yet is a clean "no
# manifest" instead of a value it will reject at runtime.
# soc id -> the chipFamily string ESP Web Tools expects. Matching is exact string
# equality against esptool-js's CHIP_NAME, so these are byte-for-byte from the
# `Build["chipFamily"]` union in esp-web-tools 10.4.0 src/const.ts. A chip absent
# here yields no manifest, rather than a value the tool rejects mid-flash.
_CHIP_FAMILIES = {
    "esp32": "ESP32",
    "esp32-c2": "ESP32-C2",
    "esp32-c3": "ESP32-C3",
    "esp32-c5": "ESP32-C5",
    "esp32-c6": "ESP32-C6",
    "esp32-c61": "ESP32-C61",
    "esp32-h2": "ESP32-H2",
    "esp32-p4": "ESP32-P4",
    "esp32-s2": "ESP32-S2",
    "esp32-s3": "ESP32-S3",
}

# Hosts the proxy may fetch from. GitHub serves release assets from these after
# redirecting off github.com; anything else must be added deliberately.
ALLOWED_BIN_HOSTS = frozenset(
    {
        "github.com",
        "objects.githubusercontent.com",
        "release-assets.githubusercontent.com",
    }
)

# Where the proxy lives from the browser's point of view. The API is mounted
# under /api on Vercel but served at the root by a standalone uvicorn, so the
# caller passes the URL it actually resolves to; this is only the fallback.
PROXY_PATH = "/api/flash-bin"


def get_recipe(recipe_id):
    return next((r for r in list_recipes() if r["id"] == recipe_id), None)


def _parts(recipe_id, flash, proxy_url):
    """Manifest parts, always pointed at the same-origin proxy."""
    if flash.get("parts"):
        return [
            {"path": f"{proxy_url}?recipe={recipe_id}&part={index}", "offset": _offset(part.get("offset"))}
            for index, part in enumerate(flash["parts"])
        ]
    if flash.get("bin_url"):
        return [{"path": f"{proxy_url}?recipe={recipe_id}", "offset": _offset(flash.get("offset"))}]
    return []


def _offset(value):
    """Recipes write offsets as hex strings ('0x10000'); manifests want ints."""
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    return int(str(value), 16 if str(value).lower().startswith("0x") else 10)


def bin_url_for(recipe_id, part=None):
    """The upstream binary a proxy request resolves to, or None.

    The caller names a recipe, never a URL, so the target is always derived from
    a record in the repo -- there is no request shape that turns this into an
    open proxy. The host is checked anyway, in case a record itself is wrong.
    """
    recipe = get_recipe(recipe_id)
    if recipe is None:
        return None
    flash = recipe.get("flash") or {}

    if part is not None:
        parts = flash.get("parts") or []
        if not 0 <= part < len(parts):
            return None
        url = parts[part].get("url")
    else:
        url = flash.get("bin_url")

    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_BIN_HOSTS:
        return None
    return url


def build_manifest(recipe_id, db_path=None, proxy_url=PROXY_PATH):
    """An ESP Web Tools manifest for one recipe, or None if it cannot flash in-browser."""
    recipe = get_recipe(recipe_id)
    if recipe is None:
        return None

    flash = recipe.get("flash") or {}
    if flash.get("method") != "release-bin":
        return None  # esp-web-tools recipes have their own manifest; the rest are handoffs

    chip_family = _CHIP_FAMILIES.get(recipe.get("chip_family"))
    if chip_family is None:
        return None

    parts = _parts(recipe_id, flash, proxy_url)
    if not parts:
        return None  # a release-bin recipe with no binary recorded yet

    board = get_part(recipe["board"], db_path=db_path)
    if board is None:
        return None

    firmware = get_firmware(recipe["firmware"]) or {}
    return {
        "name": f"{firmware.get('name', recipe['firmware'])} for {board['name']}",
        "version": recipe.get("firmware_version") or "unspecified",
        # Ask before wiping. The tool treats every flash here as a new install
        # (its "is this an update?" check compares the device's Improv-reported
        # firmware name to this manifest's `name`, which will not match), and a
        # new install otherwise erases the whole chip silently. Flashing already
        # risks the user's keys and config -- SPEC-wizard's own disclaimer says
        # so -- so the human decides. With this set, the dialog's checkbox
        # defaults to NOT erasing.
        "new_install_prompt_erase": True,
        "builds": [{"chipFamily": chip_family, "parts": parts}],
    }
