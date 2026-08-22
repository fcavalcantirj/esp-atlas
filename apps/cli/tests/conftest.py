import pytest
from esp_atlas_core.index_build import build_index


@pytest.fixture(scope="session")
def built_db_path(tmp_path_factory):
    path = tmp_path_factory.mktemp("clidb") / "esp-atlas.db"
    build_index(db_path=path)
    return path
