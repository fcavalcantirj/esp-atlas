from esp_atlas_core.brands import get_brand, list_brands


def test_get_brand_known_slug_returns_name_and_url(built_db_path):
    brand = get_brand("lilygo", db_path=built_db_path)
    assert brand == {"slug": "lilygo", "name": "LILYGO", "url": "https://lilygo.cc"}


def test_get_brand_unknown_slug_returns_none(built_db_path):
    assert get_brand("no-such-brand", db_path=built_db_path) is None


def test_list_brands_includes_every_seeded_brand(built_db_path):
    brands = list_brands(db_path=built_db_path)
    assert brands["espressif"] == {"name": "Espressif", "url": "https://www.espressif.com"}
    assert brands["m5stack"] == {"name": "M5Stack", "url": "https://m5stack.com"}
    assert len(brands) == 11
