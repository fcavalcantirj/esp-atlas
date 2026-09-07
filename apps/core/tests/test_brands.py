from esp_atlas_core.brands import get_brand, list_brands
from esp_atlas_core.paths import DATA_DIR


def test_get_brand_known_slug_returns_name_and_url(built_db_path):
    brand = get_brand("lilygo", db_path=built_db_path)
    assert brand == {"slug": "lilygo", "name": "LILYGO", "url": "https://lilygo.cc"}


def test_get_brand_unknown_slug_returns_none(built_db_path):
    assert get_brand("no-such-brand", db_path=built_db_path) is None


def test_list_brands_includes_every_seeded_brand(built_db_path):
    brands = list_brands(db_path=built_db_path)
    assert brands["espressif"] == {"name": "Espressif", "url": "https://www.espressif.com"}
    assert brands["m5stack"] == {"name": "M5Stack", "url": "https://m5stack.com"}
    # every brand folder under data/brands is a brand; the catalog grows (pinning 11 broke on the first new vendor)
    assert len(brands) == len([d for d in (DATA_DIR / "brands").iterdir() if (d / "brand.md").exists()])
