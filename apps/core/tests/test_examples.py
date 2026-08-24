"""Unit behavior of esp_atlas_core.examples.generate_examples.

The G7 no-dead-examples invariant lives in test_wizard_oracle.py (section 7);
this file pins the generator's shape: one firmware example per recipe-backed
firmware, needs drawn only from KNOWN_NEEDS, counts that match the wizard, and
deterministic output.
"""
from esp_atlas_core.examples import GROUPS, RUN_FIRMWARE, generate_examples
from esp_atlas_core.firmware import list_firmware, recipes_for_firmware
from esp_atlas_core.wizard import KNOWN_NEEDS, wizard


def _by_kind(examples, kind):
    return [e for e in examples if e["kind"] == kind]


def test_firmware_examples_one_per_recipe_backed_firmware(built_db_path):
    examples = _by_kind(generate_examples(db_path=built_db_path), "firmware")
    expected = {fw["id"]: fw for fw in list_firmware() if recipes_for_firmware(fw["id"])}

    assert {e["firmware"] for e in examples} == set(expected)
    for e in examples:
        fw = expected[e["firmware"]]
        assert e["id"] == f"run-{fw['id']}"
        assert e["label"] == f"Run {fw['name']}"
        assert e["count"] == len(recipes_for_firmware(fw["id"]))
        assert "needs" not in e


def test_firmware_examples_ordered_by_count_desc_then_label(built_db_path):
    examples = _by_kind(generate_examples(db_path=built_db_path), "firmware")
    assert [(-e["count"], e["label"]) for e in examples] == sorted(
        (-e["count"], e["label"]) for e in examples
    )


def test_needs_examples_use_only_known_needs(built_db_path):
    for e in _by_kind(generate_examples(db_path=built_db_path), "needs"):
        unknown = set(e["needs"]) - KNOWN_NEEDS
        assert not unknown, f"{e['id']} uses unknown need(s) {sorted(unknown)}"
        assert "firmware" not in e


def test_needs_examples_counts_equal_wizard_result_counts(built_db_path):
    for e in _by_kind(generate_examples(db_path=built_db_path), "needs"):
        assert e["count"] == len(wizard(e["needs"], db_path=built_db_path)), e["id"]


def test_example_ids_and_labels_are_unique_and_non_empty(built_db_path):
    examples = generate_examples(db_path=built_db_path)
    ids = [e["id"] for e in examples]
    labels = [e["label"] for e in examples]
    assert all(ids) and all(labels)
    assert len(set(ids)) == len(ids)
    assert len(set(labels)) == len(labels)


def test_every_example_carries_a_known_group(built_db_path):
    """The three home shelves (SPEC-home-explorer §2) are decided here, not in the client."""
    for e in generate_examples(db_path=built_db_path):
        assert e["group"] in GROUPS, f"{e['id']} has unknown group {e['group']!r}"
        if e["kind"] == "firmware":
            assert e["group"] == RUN_FIRMWARE


def test_generate_examples_is_deterministic(built_db_path):
    assert generate_examples(db_path=built_db_path) == generate_examples(db_path=built_db_path)
