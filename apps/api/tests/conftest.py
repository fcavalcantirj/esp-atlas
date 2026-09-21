import pytest
from fastapi.testclient import TestClient

from esp_atlas_core.index_build import build_index

from esp_atlas_api.main import create_app

# Plain helpers/constants (BOARD_PATH, SOC_PATH, client_with_llm, marauder_*) live in _shared.py,
# NOT here: a bare `from conftest import ...` collides with apps/cli/tests/conftest.py when the
# core+api+cli suites run together. Only real fixtures — auto-discovered per-directory by pytest,
# never explicitly imported — belong in conftest.py.


@pytest.fixture(scope="session")
def built_db_path(tmp_path_factory):
    """A real esp-atlas.db built once from the actual seeded data/ directory."""
    path = tmp_path_factory.mktemp("apidb") / "esp-atlas.db"
    build_index(db_path=path)
    return path


@pytest.fixture
def client(built_db_path):
    app = create_app(db_path=built_db_path)
    with TestClient(app) as c:
        yield c
