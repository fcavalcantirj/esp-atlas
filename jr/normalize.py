"""EspAtlas Jr — conservative title-banner sanitizer for scraped firmware display names.

Motivated by a real bad record (data/firmware/ai-stackchan2-readme/firmware.md): the drain
pipeline stored a GitHub repo-status banner as part of the firmware `name` — 【Maintenance
completed】AIｽﾀｯｸﾁｬﾝ2 — because the scraped README/repo title carried the banner GitHub renders
above an archived/maintained repo, not the app's actual name.

sanitize_firmware_name() strips ONLY a leading or trailing bracket segment whose inner text is
entirely made of known status-banner vocabulary (case-insensitive). It never touches a bracket
whose content isn't recognized banner text — real content (a chip variant, an edition tag) stays
untouched. Deterministic and idempotent: running it twice never changes the second output.

sweep_firmware_names() is the retroactive, idempotent pass over data/firmware/*/firmware.md —
see jr/DECISION-LOG.md / SPEC-espatlas-jr.md for how Jr's other retroactive passes are shaped.
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

import yaml

_JR_DIR = Path(__file__).resolve().parent
if str(_JR_DIR) not in sys.path:
    sys.path.insert(0, str(_JR_DIR))
from esp_atlas_core.frontmatter import parse_frontmatter  # noqa: E402

REPO = _JR_DIR.parent
FIRMWARE_DIR = REPO / "data" / "firmware"

# Bracket pairs a status banner may be wrapped in (open, close) — every char is single-width.
_BRACKET_PAIRS = (
    ("【", "】"),  # 【 】
    ("［", "］"),  # ［ ］ fullwidth square
    ("[", "]"),
    ("(", ")"),
    ("（", "）"),  # （ ）
)

# Single-token banner vocabulary (case-insensitive; CJK tokens have no case).
_BANNER_WORDS = {
    "maintenance", "completed", "完了", "メンテナンス", "archived", "deprecated",
    "discontinued", "wip", "notice", "update", "updated", "fixed", "beta", "alpha",
    "test", "testing", "unmaintained", "eol",
}
# Multi-word banner phrases that contain stopwords not themselves in _BANNER_WORDS.
_BANNER_PHRASES = {"work in progress", "end of life"}
# CJK banner words, checked without whitespace splitting (Japanese has no word spacing).
_CJK_BANNER_WORDS = ("完了", "メンテナンス")

_SEPARATOR_CHARS = " \t:-—–"


def _is_banner_text(inner: str) -> bool:
    """True iff every bit of `inner` is recognized status-banner vocabulary — never a partial
    match against real content."""
    norm = re.sub(r"\s+", " ", inner.strip()).lower()
    if not norm:
        return False
    if norm in _BANNER_PHRASES:
        return True
    tokens = [t for t in re.split(r"[\s\-:/]+", norm) if t]
    if tokens and all(t in _BANNER_WORDS for t in tokens):
        return True
    if " " not in norm:  # no ASCII spacing (e.g. concatenated Japanese) — try CJK word removal
        remainder = norm
        for word in _CJK_BANNER_WORDS:
            remainder = remainder.replace(word, "")
        if remainder == "":
            return True
    return False


def _strip_one_banner(text: str) -> str | None:
    """Strip ONE leading or trailing banner bracket from `text`. Returns the shortened
    string, or None when neither end has a recognized banner bracket."""
    for open_b, close_b in _BRACKET_PAIRS:
        if text.startswith(open_b):
            end = text.find(close_b, 1)
            if end != -1 and _is_banner_text(text[1:end]):
                return text[end + 1:]
    for open_b, close_b in _BRACKET_PAIRS:
        if text.endswith(close_b) and len(text) > 1:
            start = text.rfind(open_b, 0, len(text) - 1)
            if start != -1 and _is_banner_text(text[start + 1:-1]):
                return text[:start]
    return None


def sanitize_firmware_name(name: str) -> str:
    """Strip leading/trailing GitHub-repo-status banner brackets from a scraped firmware
    display name. Conservative: only recognized banner vocabulary is ever removed; anything
    else is returned unchanged. Idempotent."""
    if not name:
        return name
    result = name.strip(_SEPARATOR_CHARS)
    while True:
        stripped = _strip_one_banner(result)
        if stripped is None:
            break
        result = stripped.strip(_SEPARATOR_CHARS)
    return result if result else name


def sweep_firmware_names(data_root: Path | None = None) -> dict:
    """Idempotent retroactive pass: sanitize the `name` of every data/firmware/*/firmware.md,
    rewriting only the ones that actually change. Returns {"changed": [{id, old, new}, ...],
    "unchanged": count}. Running this twice makes the second run's "changed" empty."""
    firmware_dir = Path(data_root) / "firmware" if data_root is not None else FIRMWARE_DIR
    if not firmware_dir.exists():
        return {"changed": [], "unchanged": 0}

    changed: list[dict] = []
    unchanged = 0
    for path in sorted(firmware_dir.glob("*/firmware.md")):
        fm, body = parse_frontmatter(path)
        old_name = fm.get("name", "")
        new_name = sanitize_firmware_name(old_name)
        if new_name == old_name:
            unchanged += 1
            continue
        fm["name"] = new_name
        front = yaml.safe_dump(fm, sort_keys=False, default_flow_style=False,
                                allow_unicode=True).strip()
        path.write_text(f"---\n{front}\n---\n\n{body.strip()}\n")
        changed.append({"id": fm.get("id", path.parent.name), "old": old_name, "new": new_name})
    return {"changed": changed, "unchanged": unchanged}


def main() -> None:
    report = sweep_firmware_names()
    for c in report["changed"]:
        print(f"  {c['id']}: {c['old']!r} -> {c['new']!r}")
    print(f"sweep: {len(report['changed'])} changed, {report['unchanged']} unchanged")


if __name__ == "__main__":
    main()
