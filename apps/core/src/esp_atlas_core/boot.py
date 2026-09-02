"""Board Firmware-Download-mode data for the First-Flash troubleshooter
(SPEC-first-flash.md P0).

Reads `download_mode` / `usb_serial` straight from each board's frontmatter --
no DB, no network -- so the /debug connect troubleshooter can tell the user
exactly how to put THEIR board into flash mode. Every board read is wrapped:
one malformed board.md must never take out the whole list, and this must never
raise.
"""
from esp_atlas_core.frontmatter import iter_data_files, parse_frontmatter


def list_boot_modes(data_dir=None):
    """Return `[{id, name, download_mode, usb_serial, first_flash_notes}]` for every board that
    cites a `download_mode`, skipping any board that can't be read or lacks the
    minimum fields. Fast (frontmatter only) and never raises."""
    results = []
    for kind, path in iter_data_files(data_dir):
        if kind != "board":
            continue
        try:
            fm, _ = parse_frontmatter(path)
        except Exception:
            continue  # unreadable/malformed board -- skip, never fail the list
        if not isinstance(fm, dict):
            continue
        download_mode = fm.get("download_mode")
        if not isinstance(download_mode, dict) or "mode" not in download_mode:
            continue
        board_id = fm.get("id")
        name = fm.get("name")
        if not board_id or not name:
            continue
        results.append(
            {
                "id": board_id,
                "name": name,
                "download_mode": download_mode,
                "usb_serial": fm.get("usb_serial"),
                # Cited first-flash gotchas (schema `first_flash_notes`); [] when the record has none.
                "first_flash_notes": [n for n in (fm.get("first_flash_notes") or []) if isinstance(n, str) and n.strip()],
            }
        )
    return results
