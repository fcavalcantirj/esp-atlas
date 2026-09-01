"""esp_atlas_core.status -- the GET /status computation (INTERFACE-SPEC.md).

No mocked DB layer: every test builds a real, small esp-atlas.db from real
frontmatter fixtures (coding-domain ESP32/firmware records, never lorem
ipsum), the same way apps/core/tests/conftest.py's built_db_path does for the
full seeded dataset.
"""
from esp_atlas_core import db as dbmod
from esp_atlas_core.index_build import build_index
from esp_atlas_core.status import compute_status


def _seed_db_meta(db_path, build_id="fixture-build-id"):
    """A minimal db with just the meta rows compute_status reads -- avoids
    build_index()'s REPO_ROOT-relative path assumption, which doesn't hold for
    an out-of-repo tmp_path fixture dataset (see apps/core/tests/test_index_build.py,
    which only ever builds against the real DATA_DIR for that reason)."""
    conn = dbmod.connect(db_path)
    try:
        dbmod.create_schema(conn)
        dbmod.set_meta(conn, "build_id", build_id)
        dbmod.set_meta(conn, "count", "1")
    finally:
        conn.close()

_SOC_MD = """---
id: esp32-c6
type: soc
vendor: espressif
name: ESP32-C6
radios:
  wifi:
    standard: wifi-6
    bands_ghz:
    - 2.4
  bluetooth:
    le: '5.3'
    classic: false
  ieee802154:
    present: true
    protocols:
    - zigbee-3.0
sources:
- field: '*'
  url: https://documentation.espressif.com/esp32-c6_datasheet_en.pdf
  verified: '2026-08-21'
---

# ESP32-C6

Wi-Fi 6 + BLE 5.3 + 802.15.4 RISC-V SoC.
"""

_MODULE_MD = """---
id: esp32-c6-wroom-1
type: module
vendor: espressif
name: ESP32-C6-WROOM-1
soc: esp32-c6
flash_mb: 4
sources:
- field: '*'
  url: https://documentation.espressif.com/esp32-c6-wroom-1_datasheet_en.pdf
  verified: '2026-08-21'
---

# ESP32-C6-WROOM-1

RISC-V ESP32-C6 module.
"""

_BOARD_MD = """---
id: esp32-c6-devkitc-1
type: board
brand: espressif
name: ESP32-C6-DevKitC-1
module: esp32-c6-wroom-1
flash_mb: 8
form_factor: devkit
sources:
- field: '*'
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32c6/esp32-c6-devkitc-1/user_guide.html
  verified: '2026-08-21'
---

# ESP32-C6-DevKitC-1

Entry ESP32-C6-WROOM-1 devkit board.
"""

_BRAND_MD = """---
id: espressif
type: brand
name: Espressif
url: https://www.espressif.com
sources:
- field: '*'
  url: https://www.espressif.com
  verified: '2026-08-22'
---

# Espressif

Designs the ESP32 family of Wi-Fi/Bluetooth SoCs.
"""


def _firmware_md(fw_id, name, verified_date):
    return f"""---
id: {fw_id}
type: firmware
name: {name}
url: https://example.com/{fw_id}
category: home
socs:
- esp32-c6
distribution:
- releases
sources:
- field: '*'
  url: https://example.com/{fw_id}/releases
  verified: '{verified_date}'
---

# {name}

Fixture firmware record for esp_atlas_core.status tests.
"""


_FIRMWARE_MD_WLED = _firmware_md("wled", "WLED", "2026-08-10")
_FIRMWARE_MD_TASMOTA = _firmware_md("tasmota", "Tasmota", "2026-08-25")

_RECIPE_MD = """---
id: esp32-c6-devkitc-1__wled
type: recipe
board: esp32-c6-devkitc-1
firmware: wled
status: known-good
chip_family: esp32-c6
sources:
- field: '*'
  url: https://example.com/wled/releases
  verified: '2026-08-24'
---

# esp32-c6-devkitc-1 x wled

Fixture recipe record.
"""


def _seed_full_dataset(tmp_path):
    """One of every entity type, all cross-referencing correctly."""
    (tmp_path / "socs" / "esp32-c6").mkdir(parents=True)
    (tmp_path / "socs" / "esp32-c6" / "chip.md").write_text(_SOC_MD, encoding="utf-8")

    (tmp_path / "modules" / "esp32-c6-wroom-1").mkdir(parents=True)
    (tmp_path / "modules" / "esp32-c6-wroom-1" / "module.md").write_text(_MODULE_MD, encoding="utf-8")

    (tmp_path / "boards" / "espressif" / "esp32-c6-devkitc-1").mkdir(parents=True)
    (tmp_path / "boards" / "espressif" / "esp32-c6-devkitc-1" / "board.md").write_text(_BOARD_MD, encoding="utf-8")

    (tmp_path / "brands" / "espressif").mkdir(parents=True)
    (tmp_path / "brands" / "espressif" / "brand.md").write_text(_BRAND_MD, encoding="utf-8")

    (tmp_path / "firmware" / "wled").mkdir(parents=True)
    (tmp_path / "firmware" / "wled" / "firmware.md").write_text(_FIRMWARE_MD_WLED, encoding="utf-8")
    (tmp_path / "firmware" / "tasmota").mkdir(parents=True)
    (tmp_path / "firmware" / "tasmota" / "firmware.md").write_text(_FIRMWARE_MD_TASMOTA, encoding="utf-8")

    (tmp_path / "recipes" / "esp32-c6-devkitc-1__wled").mkdir(parents=True)
    (tmp_path / "recipes" / "esp32-c6-devkitc-1__wled" / "recipe.md").write_text(_RECIPE_MD, encoding="utf-8")
    return tmp_path


_COMPONENT_NAMES = ["API", "Data", "Jr / catalog", "Deploy"]


def test_healthy_seeded_dataset_is_fully_operational(built_db_path):
    """The real, whole seeded data/ directory -- every component ok, overall operational."""
    result = compute_status(db_path=built_db_path)
    assert result["status"] == "operational"
    assert [c["name"] for c in result["components"]] == _COMPONENT_NAMES
    assert all(c["status"] == "ok" for c in result["components"])
    assert "generated_at" in result and result["generated_at"]


def test_api_component_reports_record_count(built_db_path):
    result = compute_status(db_path=built_db_path)
    api = next(c for c in result["components"] if c["name"] == "API")
    assert api["status"] == "ok"
    assert any(ch.isdigit() for ch in api["detail"])


def test_data_component_counts_every_entity_type(tmp_path):
    data_dir = _seed_full_dataset(tmp_path / "data")
    db_path = tmp_path / "esp-atlas.db"
    _seed_db_meta(db_path)

    result = compute_status(db_path=db_path, data_dir=data_dir)
    data = next(c for c in result["components"] if c["name"] == "Data")
    assert data["status"] == "ok"
    assert "1 socs" in data["detail"]
    assert "1 modules" in data["detail"]
    assert "1 boards" in data["detail"]
    assert "1 brands" in data["detail"]
    assert "2 firmwares" in data["detail"]
    assert "1 recipes" in data["detail"]
    assert "schema_valid=true" in data["detail"]
    assert result["status"] == "operational"


def test_catalog_component_picks_the_newest_verified_firmware(tmp_path):
    """Jr / catalog reports whichever firmware has the LATEST verified date
    across its own sources, not just the last one seeded on disk."""
    data_dir = _seed_full_dataset(tmp_path / "data")
    db_path = tmp_path / "esp-atlas.db"
    _seed_db_meta(db_path)

    result = compute_status(db_path=db_path, data_dir=data_dir)
    catalog = next(c for c in result["components"] if c["name"] == "Jr / catalog")
    assert catalog["status"] == "ok"
    assert "tasmota" in catalog["detail"]
    assert "2026-08-25" in catalog["detail"]
    assert "wled" not in catalog["detail"]


def test_catalog_component_warns_when_no_firmware_data(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = tmp_path / "esp-atlas.db"
    build_index(db_path=db_path, data_dir=data_dir)

    result = compute_status(db_path=db_path, data_dir=data_dir)
    catalog = next(c for c in result["components"] if c["name"] == "Jr / catalog")
    assert catalog["status"] == "warn"
    assert result["status"] == "degraded"


def test_deploy_component_reports_local_with_no_vercel_env(built_db_path, monkeypatch):
    monkeypatch.delenv("VERCEL_GIT_COMMIT_SHA", raising=False)
    result = compute_status(db_path=built_db_path)
    deploy = next(c for c in result["components"] if c["name"] == "Deploy")
    assert deploy["status"] == "ok"
    assert deploy["detail"] == "local"


def test_deploy_component_reports_commit_branch_and_env_from_vercel_vars(built_db_path, monkeypatch):
    monkeypatch.setenv("VERCEL_GIT_COMMIT_SHA", "abcdef1234567890")
    monkeypatch.setenv("VERCEL_GIT_COMMIT_REF", "main")
    monkeypatch.setenv("VERCEL_ENV", "production")
    result = compute_status(db_path=built_db_path)
    deploy = next(c for c in result["components"] if c["name"] == "Deploy")
    assert deploy["status"] == "ok"
    assert "abcdef1" in deploy["detail"]
    assert "main" in deploy["detail"]
    assert "production" in deploy["detail"]


def test_api_component_is_down_when_index_was_never_built(tmp_path):
    """A db path that has never been through build_index() -- the API component
    must report down (never raise), and that alone must sink the overall status."""
    db_path = tmp_path / "never-built.db"
    result = compute_status(db_path=db_path)
    api = next(c for c in result["components"] if c["name"] == "API")
    assert api["status"] == "down"
    assert result["status"] == "down"


def test_data_component_warns_on_empty_data_directory(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = tmp_path / "esp-atlas.db"
    build_index(db_path=db_path, data_dir=data_dir)

    result = compute_status(db_path=db_path, data_dir=data_dir)
    data = next(c for c in result["components"] if c["name"] == "Data")
    assert data["status"] == "warn"
    assert result["status"] == "degraded"


def test_a_broken_component_probe_degrades_instead_of_raising(built_db_path, monkeypatch):
    """Simulates one component's probe blowing up -- compute_status must still
    return 4 components and a non-crashing overall status, never propagate."""
    import esp_atlas_core.status as status_module

    def _boom():
        raise RuntimeError("simulated probe failure")

    monkeypatch.setattr(status_module, "_component_deploy", lambda: {"name": "Deploy", **status_module._safe(_boom)})
    result = compute_status(db_path=built_db_path)
    deploy = next(c for c in result["components"] if c["name"] == "Deploy")
    assert deploy["status"] == "down"
    assert "simulated probe failure" in deploy["detail"]
    assert result["status"] == "degraded"
