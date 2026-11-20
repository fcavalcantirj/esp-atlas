"""Search and filters for the firmware index (SPEC-firmware-search.md).

The API is the only place that filters and orders firmware (SPEC-firmware-ordering.md, Golden Rule 3); this
module is that place. Pure functions over the records `list_firmware()` / `list_recipes()` already return.

    search_firmware(records, recipes, board_names, q="ghost esp")            # -> [ghostesp, ...] by relevance
    search_firmware(records, recipes, board_names, board="m5cardputer")      # -> every firmware with a recipe for it
    facets(records, recipes, board_names)                                     # -> the options of the filter controls
"""
import re
import unicodedata
from collections import Counter

from esp_atlas_core.firmware import _records, sort_by_mode, sort_by_popularity

# words people add to a firmware search that name nothing (Search Console, 2026-11: "cathack firmware",
# "bruce esp32 flasher", "ghost esp flasher", "firmware for …")
NOISE = frozenset({"firmware", "firmwares", "for", "the", "a", "an", "on", "with", "to", "flash", "flasher",
                   "flashing", "webflasher", "install", "download", "bin"})
TESTED = "known-good"
MAX_TOKENS = 8
# where a word was found, best first: (field, weight)
WEIGHTS = (("name", 100), ("ident", 40), ("boards", 30), ("tags", 20), ("summary", 5))
RELEVANCE = "relevance"


def fold(text) -> str:
    """Lower-case, strip accents, drop everything that is not a letter or a digit: "Stack-chan" -> "stackchan"."""
    plain = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", plain.lower())


def query_tokens(q) -> list:
    """The words of a query that name something, folded; filler words dropped; at most MAX_TOKENS."""
    words = [fold(w) for w in re.split(r"[^\w]+", str(q or "").lower(), flags=re.UNICODE)]
    return [w for w in words if w and w not in NOISE][:MAX_TOKENS]


def board_names() -> dict:
    """{board id: display name} for every board record."""
    return {b["id"]: b.get("name") or b["id"] for b in _records("board") if b.get("id")}


def _boards_of(recipes) -> dict:
    out = {}
    for r in recipes:
        if r.get("firmware") and r.get("board"):
            out.setdefault(r["firmware"], []).append(r)
    return out


def _fields(record, its_recipes, names) -> dict:
    boards = [r["board"] for r in its_recipes]
    return {
        "name": fold(record.get("name")),
        "ident": fold(record.get("id")) + " " + fold(record.get("maintainer")),
        "boards": " ".join(fold(b) + " " + fold(names.get(b)) for b in boards),
        "tags": " ".join(fold(x) for x in [record.get("category"), *(record.get("capabilities") or []),
                                           *(record.get("socs") or []), *(record.get("distribution") or [])]),
        "summary": fold(record.get("summary")),
    }


def _score(fields, tokens, whole):
    """None when a word is found nowhere; else the sum of each word's best field weight, plus a bonus when the
    whole query is the name or starts it."""
    total = 0
    for token in tokens:
        weight = next((w for field, w in WEIGHTS if token in fields[field]), None)
        if weight is None:
            return None
        total += weight
    if whole and fields["name"] == whole:
        total += 1000
    elif whole and fields["name"].startswith(whole):
        total += 200
    return total


def search_firmware(records, recipes, names, *, q=None, board=None, soc=None, category=None, capability=None,
                    tested=False, sort=None) -> list:
    """`records` narrowed by every given filter (AND) and by the words of `q`, then ordered: by relevance when
    there are query words and no other `sort` was asked for, else by `sort_by_mode`. An unknown filter value
    matches nothing."""
    by_fw = _boards_of(recipes)
    tokens = query_tokens(q)
    whole = "".join(tokens)
    kept, scores = [], {}
    for record in records:
        its = by_fw.get(record.get("id"), [])
        if board and not any(r["board"] == board for r in its):
            continue
        if tested and not any(r.get("status") == TESTED and (not board or r["board"] == board) for r in its):
            continue
        if soc and soc not in (record.get("socs") or []):
            continue
        if category and record.get("category") != category:
            continue
        if capability and capability not in (record.get("capabilities") or []):
            continue
        if tokens:
            score = _score(_fields(record, its, names), tokens, whole)
            if score is None:
                continue
            scores[record.get("id")] = score
        kept.append(record)
    if tokens and sort in (None, "", RELEVANCE):
        ranked = sort_by_popularity(kept)                         # the tie-break order, then stable by score
        return sorted(ranked, key=lambda r: -scores[r.get("id")])
    return sort_by_mode(kept, sort if sort and sort != RELEVANCE else "popularity")


def facets(records, recipes, names) -> dict:
    """The options of the filter controls with their firmware counts, over the WHOLE catalog: most used first,
    then by id. Boards carry their display name."""
    ids = {r.get("id") for r in records}
    board_fw = {}
    for r in recipes:
        if r.get("firmware") in ids and r.get("board"):
            board_fw.setdefault(r["board"], set()).add(r["firmware"])

    def ranked(counter):
        return [{"id": k, "count": n} for k, n in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0])) if k]
    return {
        "boards": [{"id": b, "name": names.get(b) or b, "count": len(fw)}
                   for b, fw in sorted(board_fw.items(), key=lambda kv: (-len(kv[1]), kv[0]))],
        "socs": ranked(Counter(s for r in records for s in (r.get("socs") or []))),
        "categories": ranked(Counter(r.get("category") for r in records)),
        "capabilities": ranked(Counter(c for r in records for c in (r.get("capabilities") or []))),
    }
