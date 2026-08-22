from pathlib import Path

from esp_atlas_core.paths import REPO_ROOT, resolve_db_path, resolve_repo_root


def test_resolve_repo_root_defaults_to_package_layout():
    assert resolve_repo_root() == REPO_ROOT


def test_resolve_repo_root_honors_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("ESP_ATLAS_REPO_ROOT", str(tmp_path))
    assert resolve_repo_root() == tmp_path


def test_resolve_db_path_honors_explicit_env_override(monkeypatch, tmp_path):
    monkeypatch.delenv("VERCEL", raising=False)
    override = tmp_path / "custom.db"
    monkeypatch.setenv("ESP_ATLAS_DB_PATH", str(override))
    assert resolve_db_path() == override


def test_resolve_db_path_defaults_to_tmp_on_vercel(monkeypatch, tmp_path):
    monkeypatch.delenv("ESP_ATLAS_DB_PATH", raising=False)
    monkeypatch.setenv("VERCEL", "1")
    assert resolve_db_path(repo_root=tmp_path) == Path("/tmp/esp-atlas.db")


def test_resolve_db_path_defaults_to_tmp_when_repo_root_read_only(monkeypatch, tmp_path):
    monkeypatch.delenv("ESP_ATLAS_DB_PATH", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    ro_dir = tmp_path / "readonly"
    ro_dir.mkdir()
    ro_dir.chmod(0o555)
    try:
        assert resolve_db_path(repo_root=ro_dir) == Path("/tmp/esp-atlas.db")
    finally:
        ro_dir.chmod(0o755)


def test_resolve_db_path_defaults_to_repo_root_when_writable(monkeypatch, tmp_path):
    monkeypatch.delenv("ESP_ATLAS_DB_PATH", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    assert resolve_db_path(repo_root=tmp_path) == tmp_path / "esp-atlas.db"
