"""Proves the FAQ feeds Home Search's real FTS5 layer through parts_fts.notes,
promoted from spike/faq-c6/fts_proof.py + test_fts_search.py (REPORT.md (d)) --
no db.py schema change, no new column, just index_build._row_for's existing
notes join. Uses esp_atlas_core.search.search() and index_build.build_index()
unmodified, over the real seeded data/ tree."""
from esp_atlas_core import index_build
from esp_atlas_core.index_build import build_index
from esp_atlas_core.search import search


def _build_without_faq(db_path, monkeypatch):
    """The "before" baseline: same real dataset, FAQ generation stubbed out --
    isolates what the FAQ injection itself changes about search results."""
    monkeypatch.setattr(index_build.faqmod, "generate_faq", lambda soc_id, fm, soc_by_id: [])
    build_index(db_path=db_path)


def test_pinout_is_absent_from_esp32_c6s_own_data(built_db_path):
    """Sanity check the demo term is genuinely new, not already present via
    esp32-c6's own name/aka/prose/notes -- otherwise this test proves nothing."""
    import sqlite3

    conn = sqlite3.connect(built_db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT name, aka, prose, notes FROM parts_fts WHERE id = 'esp32-c6'").fetchone()
    combined_before_faq = " ".join(v or "" for v in (row["name"], row["aka"], row["prose"])).lower()
    assert "pinout" not in combined_before_faq


def test_esp32_c6_becomes_findable_by_pinout_only_after_faq_injection(tmp_path, monkeypatch):
    db_no_faq = tmp_path / "no_faq.db"
    _build_without_faq(db_no_faq, monkeypatch)
    monkeypatch.undo()

    db_with_faq = tmp_path / "with_faq.db"
    build_index(db_path=db_with_faq)

    before_ids = [r["id"] for r in search("pinout", filters={}, db_path=db_no_faq)]
    after_ids = [r["id"] for r in search("pinout", filters={}, db_path=db_with_faq)]

    assert "esp32-c6" not in before_ids, "esp32-c6 shouldn't match 'pinout' before FAQ text is indexed"
    assert "esp32-c6" in after_ids, "esp32-c6 should match 'pinout' once the FAQ text is in parts_fts"


def test_notes_column_carries_faq_question_text_for_a_soc(built_db_path):
    import sqlite3

    conn = sqlite3.connect(built_db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT notes FROM parts_fts WHERE id = 'esp32-c6'").fetchone()
    assert "What is the ESP32-C6 pinout / GPIO count?" in row["notes"]


def test_notes_column_unaffected_for_non_soc_types(built_db_path):
    """A board/module's own `notes` list still lands in parts_fts.notes verbatim
    -- FAQ generation only ever touches soc rows."""
    import sqlite3

    from esp_atlas_core.frontmatter import parse_frontmatter
    from esp_atlas_core.paths import REPO_ROOT

    conn = sqlite3.connect(built_db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT notes FROM parts_fts WHERE id = 'esp32-c6-devkitc-1'").fetchone()
    fm, _body = parse_frontmatter(REPO_ROOT / "data" / "boards" / "espressif" / "esp32-c6-devkitc-1" / "board.md")
    assert row["notes"] == "\n".join(fm.get("notes") or [])
