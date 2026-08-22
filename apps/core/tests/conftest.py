import pytest

from esp_atlas_core.index_build import build_index


@pytest.fixture(scope="session")
def built_db_path(tmp_path_factory):
    """A real esp-atlas.db built once from the actual seeded data/ directory."""
    path = tmp_path_factory.mktemp("db") / "esp-atlas.db"
    build_index(db_path=path)
    return path
