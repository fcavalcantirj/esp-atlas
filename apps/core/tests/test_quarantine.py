"""Quarantine (Jr redesign plan, step 2b, 2026-11-22).

A recipe whose build-target claim stops re-proving is hidden from the site at once (through a deploy), while a
reviewed correction follows. `data/quarantine.json` lists the hidden recipe ids. The SERVING process (the
deployed API, ESP_ATLAS_IMMUTABLE_DATA=1) drops them at the one place every core reader enumerates records,
frontmatter.iter_data_files, so /recipes, search, facets, counts, board and firmware pages all agree. Jr, the
validators and the claim checker (no flag) still see every record: Jr must never re-propose a hidden edge as
missing. If the file exists but cannot be read, serving fails closed for build-target facts only."""
import json

import pytest

from esp_atlas_core import frontmatter as fmod

RECIPE = "---\nid: {id}\ntype: recipe\nboard: b\nfirmware: f\nstatus: {status}\nchip_family: esp32\n---\n\nbody\n"


@pytest.fixture
def data(tmp_path, monkeypatch):
    for rid, status in (("b__keep", "unverified"), ("b__hide", "build-target"), ("b__fact", "build-target")):
        d = tmp_path / "recipes" / rid
        d.mkdir(parents=True)
        (d / "recipe.md").write_text(RECIPE.format(id=rid, status=status), encoding="utf-8")
    monkeypatch.setattr(fmod, "_PARSED", {})
    monkeypatch.setattr(fmod, "_FILES", {})
    return tmp_path


def recipe_ids(root):
    return sorted(p.parent.name for kind, p in fmod.iter_data_files(root) if kind == "recipe")


def quarantine(root, ids, raw=None):
    (root / "quarantine.json").write_text(raw if raw is not None else json.dumps(
        {"version": 1, "recipes": {i: {"reason": "claim FAIL", "run": "123", "since": "2026-11-22"} for i in ids},
         "suspended_repos": {}}), encoding="utf-8")


def test_serving_hides_quarantined_recipes(data, monkeypatch):
    monkeypatch.setenv("ESP_ATLAS_IMMUTABLE_DATA", "1")
    quarantine(data, ["b__hide"])
    assert recipe_ids(data) == ["b__fact", "b__keep"]


def test_everything_else_still_sees_every_record(data, monkeypatch):
    monkeypatch.delenv("ESP_ATLAS_IMMUTABLE_DATA", raising=False)
    quarantine(data, ["b__hide"])
    assert recipe_ids(data) == ["b__fact", "b__hide", "b__keep"]


def test_no_quarantine_file_hides_nothing(data, monkeypatch):
    monkeypatch.setenv("ESP_ATLAS_IMMUTABLE_DATA", "1")
    assert recipe_ids(data) == ["b__fact", "b__hide", "b__keep"]


@pytest.mark.parametrize("raw", ["{not json", json.dumps({"version": 1, "recipes": ["b__hide"]}), json.dumps([])])
def test_an_unreadable_quarantine_file_fails_closed_for_build_target_facts_only(data, monkeypatch, raw):
    monkeypatch.setenv("ESP_ATLAS_IMMUTABLE_DATA", "1")
    quarantine(data, [], raw=raw)
    assert recipe_ids(data) == ["b__keep"]


def test_other_kinds_are_never_filtered(data, monkeypatch):
    monkeypatch.setenv("ESP_ATLAS_IMMUTABLE_DATA", "1")
    (data / "firmware" / "f").mkdir(parents=True)
    (data / "firmware" / "f" / "firmware.md").write_text("---\nid: f\ntype: firmware\n---\n", encoding="utf-8")
    quarantine(data, ["b__hide", "f"])
    assert [p.parent.name for k, p in fmod.iter_data_files(data) if k == "firmware"] == ["f"]


def test_the_shipped_quarantine_file_is_well_formed_and_names_real_recipes():
    """data/quarantine.json ships with the data; validate it like data (CI never deploys a broken one)."""
    path = fmod.DATA_DIR / "quarantine.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc.get("version") == 1 and isinstance(doc.get("recipes"), dict) and isinstance(doc.get("suspended_repos"), dict)
    for rid, entry in doc["recipes"].items():
        assert (fmod.DATA_DIR / "recipes" / rid / "recipe.md").is_file(), rid
        assert {"reason", "run", "since"} <= set(entry), rid
