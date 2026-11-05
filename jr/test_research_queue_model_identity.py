"""Physical SKU similarity is not evidence that two models are the same device."""
import pytest

import research_queue as rq


def display(model, kind="board"):
    entry = {"id": f"acme-{model.lower()}", "kind": kind,
             "title": f"Display {model}", "aliases": [model]}
    if kind == "board":
        entry["brand"] = "acme"
    return entry


@pytest.mark.parametrize("kind", ["board", "part"])
@pytest.mark.parametrize("term", ["es3n28p", "ES3N28P", "es3n-28p", "acme-es3n28p"])
def test_a_distinct_physical_model_is_not_a_typo_for_the_catalogued_sibling(kind, term):
    classification, evidence = rq.classify(term, [display("ES3C28P", kind)])
    assert classification == rq.MISSING_CONTENT
    assert evidence["ids"] == []


@pytest.mark.parametrize("kind", ["board", "part"])
@pytest.mark.parametrize("model", ["ES3C28P", "ES3N28P"])
def test_each_known_physical_alias_matches_only_its_own_model(kind, model):
    catalog = [display("ES3C28P", kind), display("ES3N28P", kind)]
    classification, evidence = rq.classify(model, catalog)
    assert classification == rq.ALIAS_TYPO
    assert evidence["ids"] == [f"acme-{model.lower()}"]
    assert all(match["distance"] == 0 for match in evidence["matches"])


@pytest.mark.parametrize("term", ["ES3C28P", "acme-es3c28p", "es3c28p display"])
def test_exact_alias_id_and_reordered_identity_are_preserved(term):
    _, evidence = rq.classify(term, [display("ES3C28P")])
    assert evidence["ids"] == ["acme-es3c28p"]
    assert all(match["distance"] == 0 for match in evidence["matches"])


def test_bare_freenove_aliases_do_not_mix_a_b_and_s_variants():
    catalog = [{"id": f"freenove-fnk0104{v}", "kind": "board", "brand": "freenove",
                "title": f"Display FNK0104{v.upper()}", "aliases": [f"FNK0104{v.upper()}"]}
               for v in "abs"]
    _, evidence = rq.classify("fnk0104s", catalog)
    assert evidence["ids"] == ["freenove-fnk0104s"]


def test_a_different_chip_model_is_not_a_typo_for_an_existing_chip():
    classification, evidence = rq.classify("esp32-c5", [
        {"id": "esp32-c6", "kind": "part", "title": "ESP32-C6", "aliases": []}])
    assert classification == rq.MISSING_CONTENT
    assert evidence["ids"] == []


@pytest.mark.parametrize("term, expected", [
    ("lilygo-t-bem", "lilygo-t-beam"),
    ("esp32marudr", "esp32marauder"),
    ("marauder", "esp32marauder"),
])
def test_ordinary_word_and_firmware_typo_matching_is_preserved(term, expected):
    catalog = [
        {"id": "lilygo-t-beam", "kind": "board", "brand": "lilygo", "title": "T-Beam", "aliases": []},
        {"id": "esp32marauder", "kind": "firmware", "title": "ESP32 Marauder", "aliases": []},
    ]
    classification, evidence = rq.classify(term, catalog)
    assert classification == rq.ALIAS_TYPO
    assert evidence["ids"] == [expected]
