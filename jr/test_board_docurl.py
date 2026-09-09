"""doc_url_candidates — Espressif drops the -vN revision from some doc slugs
(esp32-devkitc-v4 → .../esp32-devkitc/). backfill falls back to the stripped slug and
cites whichever actually resolved. A bare trailing -N is NOT stripped (real variant)."""
import board_backfill as bb


def test_candidates_strip_only_vN_suffix():
    c = bb.doc_url_candidates("esp32-devkitc-v4", "esp32")
    assert c == [
        bb.board_user_guide_url("esp32-devkitc-v4", "esp32"),
        bb.board_user_guide_url("esp32-devkitc", "esp32"),
    ]
    # -02 / -1 are real variants, not revisions → no strip
    assert bb.doc_url_candidates("esp32-c3-devkitc-02", "esp32-c3") == [
        bb.board_user_guide_url("esp32-c3-devkitc-02", "esp32-c3")]


def test_backfill_falls_back_to_stripped_slug_and_cites_it(tmp_path):
    d = tmp_path / "boards" / "espressif" / "esp32-devkitc-v4"
    d.mkdir(parents=True)
    (d / "board.md").write_text(
        "---\nid: esp32-devkitc-v4\ntype: board\nbrand: espressif\nname: X\nsoc: esp32\nsources: []\n---\n\nbody\n")
    stripped = bb.board_user_guide_url("esp32-devkitc", "esp32")

    def fetch(u):
        if u == stripped:
            return {"ok": True, "status": 200,
                    "text": "<p>CP2102N USB-to-UART bridge.</p>"
                            "<img src='../_images/esp32-devkitc-pinout.png'>"}
        return {"ok": False, "status": 404}

    entry = bb.backfill_board(d / "board.md", tmp_path, fetch, "2026-09-09")
    assert entry["status"] == "backfilled"
    assert entry["url"] == stripped               # cited the slug that resolved, not the 404
    assert entry["board_id"] == "esp32-devkitc-v4"
