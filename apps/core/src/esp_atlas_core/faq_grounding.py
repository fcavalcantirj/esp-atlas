"""Resolve + verify FAQ claims against the real dataset -- the build-time guard
that promotes spike/faq-c6/grounding.py into production (see faq.py's module
docstring for the generator that produces the claims this checks).

A claim is `{"file", "path", "expect", "in_answer": [...], "kind": optional}`,
one per factual clause in a generated FAQ answer. `ground_items` raises
FAQGroundingError -- failing the build -- the moment any claim doesn't hold,
so no ungrounded answer can ship (cite-or-omit, enforced mechanically).

Three things have to hold for every non-"absent" claim:
  1. the dotted path resolves in that file's REAL, freshly-reloaded
     frontmatter (never trusted from whatever the generator already had in
     memory -- this is what actually catches drift, unlike checking a value
     against itself)
  2. the resolved value matches what the claim says it is ("count" compares
     len(value); "list-contains" checks each expected item is in the list;
     "present" only checks the path resolves; the default compares equality)
  3. the field is covered by that record's own `sources` list -- field-exact,
     a dotted-prefix ancestor, or the `field: '*'` catch-all

For a template-generated answer the equality check in (2) is a tautology by
construction (the claim's `expect` and the rendered phrase both come from the
same resolved value) -- that is expected, not a weakness. The guard's real
protection is (1) re-reading the file fresh off disk rather than trusting
the generator's in-memory copy, (3) cite-or-omit, and the `in_answer` check
below, which independently confirms the exact phrase made it into the
rendered text -- that is what catches a template/string-building bug.
"""
from esp_atlas_core.frontmatter import parse_frontmatter
from esp_atlas_core.paths import REPO_ROOT

_MISSING = object()


class FAQGroundingError(Exception):
    """Raised when a generated FAQ answer can't be traced to the real dataset."""


def load_frontmatter(relpath):
    fm, _body = parse_frontmatter(REPO_ROOT / relpath)
    return fm


def resolve(fm, dotted_path):
    """Walk a dotted path through nested dicts. Returns _MISSING if any hop is absent."""
    node = fm
    for key in dotted_path.split("."):
        if not isinstance(node, dict) or key not in node:
            return _MISSING
        node = node[key]
    return node


def is_present(fm, dotted_path):
    return resolve(fm, dotted_path) is not _MISSING


def source_covers(fm, dotted_path):
    sources = fm.get("sources") or []
    for source in sources:
        field = source.get("field")
        if field == "*" or field == dotted_path or dotted_path.startswith(f"{field}."):
            return True
    return False


def _check_phrases(item_id, claim, answer):
    for phrase in claim.get("in_answer", []):
        if phrase not in answer:
            raise FAQGroundingError(f"{item_id}: phrase {phrase!r} not present in the answer text")


def ground_claim(item_id, claim, answer):
    fm = load_frontmatter(claim["file"])
    path = claim["path"]
    kind = claim.get("kind")

    if kind == "absent":
        if is_present(fm, path):
            raise FAQGroundingError(f"{item_id}: expected {path!r} absent from {claim['file']}")
        _check_phrases(item_id, claim, answer)
        return

    if not is_present(fm, path):
        raise FAQGroundingError(f"{item_id}: {path!r} not found in {claim['file']}")
    value = resolve(fm, path)

    if kind == "present":
        pass
    elif kind == "list-contains":
        for expected in claim["expect"]:
            if expected not in value:
                raise FAQGroundingError(f"{item_id}: {expected!r} not in {claim['file']}#{path}")
    elif kind == "count":
        if len(value) != claim["expect"]:
            raise FAQGroundingError(
                f"{item_id}: len({claim['file']}#{path}) = {len(value)}, claim says {claim['expect']!r}"
            )
    else:
        if value != claim["expect"]:
            raise FAQGroundingError(
                f"{item_id}: {claim['file']}#{path} = {value!r}, claim says {claim['expect']!r}"
            )

    if not source_covers(fm, path):
        raise FAQGroundingError(
            f"{item_id}: {path!r} has no covering `sources` entry in {claim['file']} "
            "(cite-or-omit: a fact with no source can't ground an FAQ answer)"
        )
    _check_phrases(item_id, claim, answer)


def ground_item(item):
    if not item.get("claims"):
        raise FAQGroundingError(f"{item['id']}: has no grounding claims")
    for claim in item["claims"]:
        ground_claim(item["id"], claim, item["answer"])


def ground_items(items):
    """The build-time guard: verify every item, then return them unchanged.

    Raises FAQGroundingError on the first ungrounded claim -- fails the whole
    generation call rather than shipping a partially-grounded FAQ.
    """
    for item in items:
        ground_item(item)
    return items
