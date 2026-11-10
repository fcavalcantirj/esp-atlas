"""EspAtlas Jr — toolchain sources as CORROBORATION ONLY for board USB fields (owner mandate G3,
2026-11-04; SPEC-board-grounding.md "Toolchain sources are corroboration only").

The PlatformIO espressif32 manifests (jr/board_manifest.py) and the Arduino-ESP32 boards.txt
(jr/board_arduino.py) stay loaded and cited at their pinned commits, but a toolchain USB id says
what a build target enumerates as, not which connection a given board wires. So neither ever
writes `usb_serial` or `download_mode`: `usb_serial` is written only from board-specific evidence
(the vendor page board_backfill fetched and cites), and the toolchain values are recorded against
it per board and field — `corroborates` / `conflicts` with the source citation, or
`corroboration_only` when there is no board-specific value to check. A conflict routes the field
to review instead of writing it. Neither source states download mode, and nothing here infers it
from the chip.

NO LLM, NO API KEY. Read-only: this module never writes a record; the fetch is injected.
"""
from __future__ import annotations

from pathlib import Path

from board_arduino import ground_from_boards_txt
from board_manifest import MANIFEST_FIELDS, NATIVE_USB, ground_from_manifest

# The only field a toolchain source states a value for (neither states download mode).
CORROBORATED_FIELDS = ("usb_serial",)

# Per-source verdicts (also the per-source reason in board_backfill's field_reasons).
CORROBORATES = "corroborates"
CONFLICTS = "conflicts"
CORROBORATION_ONLY = "corroboration_only"   # a toolchain value with no board-specific value to check

# Per-field verdicts.
CORROBORATED = "corroborated"        # board value written; every toolchain value agrees
UNCORROBORATED = "uncorroborated"    # board value written; no toolchain source states one
NEEDS_REVIEW = "needs_review"        # board value withheld; a toolchain value disagrees

UNSPECIFIED_BRIDGE = "usb-uart-bridge-unspecified"
# The toolchain's USB-id table reports Silicon Labs' 0x10C4 unnamed (it covers CP2102, CP2102N and
# CP2104 alike), so it agrees with a board page that names either part.
_SILABS_PARTS = frozenset({"cp2102", "cp2102n"})


def agrees(board_value: str, toolchain_value: str) -> bool:
    """True when a toolchain value is consistent with the board-specific one: equal, a toolchain
    Silicon Labs id against a named CP210x, or a board page's unnamed bridge against any named
    toolchain bridge (never native USB)."""
    if board_value == toolchain_value:
        return True
    if toolchain_value == UNSPECIFIED_BRIDGE:
        return board_value in _SILABS_PARTS
    if board_value == UNSPECIFIED_BRIDGE:
        return toolchain_value != NATIVE_USB
    return False


def consult(fm: dict, board_id: str, soc: str, data_root: Path, fields: list[str],
            fetch) -> dict:
    """{"manifest": ..., "boards_txt": ...}, each {"url", "values", "reasons"} for the requested
    `fields`, in the order tried. Both sources are always asked (no short-circuit), so each can
    corroborate or conflict on its own. Discovery only: the values are never written."""
    wanted = [f for f in MANIFEST_FIELDS if f in fields]
    return {
        "manifest": ground_from_manifest(fm, board_id, soc, data_root, wanted, fetch),
        "boards_txt": ground_from_boards_txt(board_id, soc, data_root, wanted, fetch),
    }


def assess(board_values: dict, toolchain: dict) -> dict:
    """{field: {"verdict", "board_value", "checks": [{"source", "url", "value", "verdict"}]}} for
    each CORROBORATED_FIELDS field that has a board-specific value (`board_values`, the vendor's)
    or a toolchain value."""
    out: dict = {}
    for field in CORROBORATED_FIELDS:
        board_value = board_values.get(field)
        checks = [_check(source, res, field, board_value) for source, res in toolchain.items()
                  if field in res["values"]]
        if not checks and board_value is None:
            continue
        out[field] = {"verdict": _field_verdict(board_value, checks), "board_value": board_value,
                      "checks": checks}
    return out


def needs_review(assessment: dict) -> list[str]:
    """The fields whose board value must be withheld and routed to a human."""
    return [f for f, a in assessment.items() if a["verdict"] == NEEDS_REVIEW]


def source_reasons(toolchain: dict, assessment: dict) -> dict:
    """{source: {field: reason}}: a source that stated a value reports its verdict, one that did
    not keeps its own skip reason (no_manifest, field_absent, ...)."""
    out: dict = {}
    for source, res in toolchain.items():
        reasons = dict(res["reasons"])
        for field in res["values"]:
            reasons[field] = next(c["verdict"] for c in assessment[field]["checks"]
                                  if c["source"] == source)
        out[source] = reasons
    return out


def describe(assessment: dict) -> list[str]:
    """One line per field for the run report, every toolchain value with its citation:
    `usb_serial needs_review (board cp2102n; boards_txt ch340 conflicts <url>)`."""
    lines = []
    for field, a in assessment.items():
        parts = [f"board {a['board_value'] or 'none'}"]
        parts += [f"{c['source']} {c['value']} {c['verdict']} {c['url']}" for c in a["checks"]]
        lines.append(f"{field} {a['verdict']} ({'; '.join(parts)})")
    return lines


def _check(source: str, res: dict, field: str, board_value) -> dict:
    value = res["values"][field]
    if board_value is None:
        verdict = CORROBORATION_ONLY
    else:
        verdict = CORROBORATES if agrees(board_value, value) else CONFLICTS
    return {"source": source, "url": res["url"], "value": value, "verdict": verdict}


def _field_verdict(board_value, checks: list[dict]) -> str:
    if board_value is None:
        return CORROBORATION_ONLY
    if any(c["verdict"] == CONFLICTS for c in checks):
        return NEEDS_REVIEW
    return CORROBORATED if checks else UNCORROBORATED
