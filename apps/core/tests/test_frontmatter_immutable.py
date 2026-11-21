"""A deployed API reads data/ that never changes within the deployment (apps/web/api/index.py sets
ESP_ATLAS_IMMUTABLE_DATA=1). There, each data file is parsed once per process; everywhere else (Jr, local
runs, tests) every call reads the disk as before.

2026-11-21: an uncached firmware page took 2.3-3.9 s because /api/firmware/<id> (1.4 s) and /api/recipes
(0.8 s) re-parsed about 640 YAML files on every request; Google held back crawling the new pages."""
from pathlib import Path

import pytest

from esp_atlas_core import frontmatter as fmod

REPO = Path(__file__).resolve().parents[3]
DOC = "---\nid: x\ntags: [a]\n---\n\nbody\n"


@pytest.fixture
def counted(tmp_path, monkeypatch):
    f = tmp_path / "x.md"
    f.write_text(DOC, encoding="utf-8")
    reads = []
    real = Path.read_text
    monkeypatch.setattr(Path, "read_text", lambda self, *a, **k: (reads.append(str(self)), real(self, *a, **k))[1])
    monkeypatch.setattr(fmod, "_PARSED", {})
    monkeypatch.setattr(fmod, "_FILES", {})
    return f, reads


def test_with_immutable_data_a_file_is_read_once_and_each_caller_gets_its_own_copy(counted, monkeypatch):
    f, reads = counted
    monkeypatch.setenv("ESP_ATLAS_IMMUTABLE_DATA", "1")
    fm, body = fmod.parse_frontmatter(f)
    fm["tags"].append("mutated")                               # a caller that changes what it got
    fm2, body2 = fmod.parse_frontmatter(f)
    assert reads == [str(f)] and fm2 == {"id": "x", "tags": ["a"]} and body2 == body == "body"


def test_without_the_flag_every_call_reads_the_disk(counted, monkeypatch):
    f, reads = counted
    monkeypatch.delenv("ESP_ATLAS_IMMUTABLE_DATA", raising=False)
    fmod.parse_frontmatter(f)
    f.write_text(DOC.replace("id: x", "id: y"), encoding="utf-8")
    assert fmod.parse_frontmatter(f)[0]["id"] == "y" and len(reads) == 2
    monkeypatch.setenv("ESP_ATLAS_IMMUTABLE_DATA", "0")       # only "1" turns it on
    fmod.parse_frontmatter(f)
    assert len(reads) == 3


def test_with_immutable_data_the_file_listing_is_taken_once(tmp_path, monkeypatch):
    (tmp_path / "firmware" / "a").mkdir(parents=True)
    (tmp_path / "firmware" / "a" / "firmware.md").write_text(DOC, encoding="utf-8")
    monkeypatch.setattr(fmod, "_FILES", {})
    monkeypatch.setenv("ESP_ATLAS_IMMUTABLE_DATA", "1")
    first = list(fmod.iter_data_files(tmp_path))
    (tmp_path / "firmware" / "b").mkdir()
    (tmp_path / "firmware" / "b" / "firmware.md").write_text(DOC, encoding="utf-8")
    assert list(fmod.iter_data_files(tmp_path)) == first          # immutable: the deployment's files
    monkeypatch.delenv("ESP_ATLAS_IMMUTABLE_DATA")
    assert len(list(fmod.iter_data_files(tmp_path))) == 2         # mutable: listed again


def test_the_deployed_entry_point_turns_it_on_before_anything_reads_the_data():
    text = (REPO / "apps" / "web" / "api" / "index.py").read_text(encoding="utf-8")
    flag = text.index('os.environ.setdefault("ESP_ATLAS_IMMUTABLE_DATA", "1")')
    assert flag < text.index("from esp_atlas_api.main import") and flag < text.index("build_index(")
