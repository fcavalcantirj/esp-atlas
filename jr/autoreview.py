"""EspAtlas Jr — autoreview: an independent evidence check of one recipe edge (SPEC-jr-review-routing.md §7).

`check(board, sources, catalog)` answers PASS / FAIL / UNCERTAIN for the claim "firmware targets <board>",
from the upstream text the recipe cites (repository description, README, platformio.ini). Pure and
deterministic: no network, no LLM, and none of Jr's own mapping code (jr/device_map, jr/board_alias, the
admit scorer), so it cannot repeat the mapping mistake it checks for. Shadow only: it reports, never merges.

PASS means the cited upstream text targets the claimed board; the recipe still says `unverified`
(never hardware-tested). Anything the rules do not cover is UNCERTAIN, never a guess.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

PASS, FAIL, UNCERTAIN = "PASS", "FAIL", "UNCERTAIN"
RULES_VERSION = "4"

# Boards whose name is the prefix of a more specific product that is NOT compatible hardware.
# claimed board -> regex of the sibling that does not prove it (SIBLING_LABEL names it in reasons).
SIBLINGS: dict[str, str] = {
    # "Cardputer ADV", "Cardputer (ADV)", "ADV Cardputer", "Cardputer Advanced", or its ADV-only keyboard chip
    "m5cardputer": (r"cardputer[\s_-]*[\(\[\{]?\s*adv(anced)?(?![a-z])|\badv(anced)?[\s_-]*(m5\s*(stack\s*)?)?cardputer"
                    r"|\btca8418\b"),
}
SIBLING_LABEL: dict[str, str] = {"m5cardputer": "Cardputer ADV"}
SIBLING_BOARD: dict[str, str] = {"m5cardputer": "m5cardputer-adv"}   # the catalogued board the sibling text names
# A plain mention of the claimed board that still counts once a sibling is named: it must single the
# original out (an "original"/"v1.1"/"standard" qualifier, or the pair named side by side).
EXPLICIT_ORIGINAL: dict[str, str] = {
    "m5cardputer": (r"(original|first[\s-]*gen(eration)?)\s+(m5\s*(stack\s*)?)?cardputer|if\s+you\s+(are\s+using|use|have)\s+(a\s+|an\s+|the\s+)?(m5\s*(stack\s*)?)?cardputer[\s_-]*adv(?![a-z])|cardputer\s*(\(|-)?\s*(v?1\.[01]|standard|original|non[- ]adv)"
                    r"|cardputer\s*(&|and|/|,|or)\s*(the\s+)?(m5\s*)?(cardputer)?[\s_-]*adv(?![a-z])"
                    r"|cardputer[\s_-]*adv(?![a-z])\s*(&|and|/|,|or)\s*(the\s+)?(original\s+|standard\s+)?(m5\s*)?cardputer(?![\s_-]*adv)"),
}
# Carrier modules: a build env on the module whose name, libraries or flags name a product built on it
# proves that product, not the bare module.
CARRIERS: dict[str, tuple[str, ...]] = {
    "m5stamp-s3": ("cardputer", "sticks3", "stick_s3", "dial", "dinmeter", "capsule", "atoms3", "airq"),
}
# A caveat about the original, not a claim of support (DasBrow, room 12192)
CAVEAT = re.compile(r"\b(untested|not\s+(yet\s+)?tested|unverified|not\s+(yet\s+)?(been\s+)?verified"
                    r"|hasn'?t\s+(yet\s+)?been\s+(tested|verified)|experimental)\b", re.I)
# A mention that does not say the firmware targets the board: provenance, roadmap, or a hardware version
# that does not exist (the Cardputer is v1.0 / v1.1; "v2" names something else). DasBrow's #1722 review.
NONTARGET = re.compile(r"\b(ported\s+from|port\s+of|inspired\s+by|based\s+on|fork(ed)?\s+(of|from)|derived\s+from"
                       r"|planned|roadmap|coming\s+soon|to-?do|will\s+(support|add|come))\b"
                       r"|cardputer\s*v(?!1(\.\d)?\b)\d", re.I)
# A doubt only when the negation is about support ("doesn't run on", "not supported"), never any "not".
NEGATION = re.compile(r"(\bnot|\bno longer|isn'?t|doesn'?t|does not|won'?t|cannot|can'?t)\s+(be\s+|yet\s+)*(supported|support|work|run|compatible)"
                      r"|\b(unsupported|incompatible)\b", re.I)
# A sentence that rules the claimed board out: the sibling "only", or a negation bound to a support verb.
EXCLUSION: dict[str, str] = {
    "m5cardputer": (r"cardputer[\s_-]*adv[\s_-]*only|only\s+(for|on|supports?|targets?)\s+(the\s+)?(m5\s*)?cardputer[\s_-]*adv"
                    r"|(not|isn'?t|is not|doesn'?t|does not|won'?t|cannot|can'?t)\s+(be\s+)?(supported|support|work|run|compatible)"
                    r"|\b(unsupported|incompatible)\b|\bno\s+support\b"
                    r"|\bnot\s+(for\s+|on\s+)?(the\s+|an?\s+)?(original|first[\s-]*gen(eration)?|regular|standard)\s+(m5\s*(stack\s*)?)?cardputer"),
}


@dataclass
class Verdict:
    verdict: str
    reasons: list = field(default_factory=list)
    rules_version: str = RULES_VERSION


def _compact(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _board_terms(board: str, catalog: dict) -> list[str]:
    """How the claimed board is written: its id and catalog name/aka, compacted (>= 5 chars, so a
    bare 'm5' or 's3' never counts)."""
    rec = catalog.get(board) or {}
    terms = {board, rec.get("name") or ""} | set(rec.get("aka") or [])
    out = {_compact(t) for t in terms if t}
    return sorted(t for t in out if len(t) >= 5)


def _envs(platformio: str) -> list[dict]:
    """[{name, board, text}] for each [env:<name>] section (text = its options, lowercased)."""
    out, cur = [], None
    for line in (platformio or "").splitlines():
        m = re.match(r"\s*\[env:([^\]]+)\]", line)
        if m:
            cur = {"name": m.group(1).strip(), "board": "", "text": ""}
            out.append(cur)
            continue
        if re.match(r"\s*\[", line):
            cur = None
            continue
        if cur is not None:
            b = re.match(r"\s*board\s*=\s*(\S+)", line)
            if b:
                cur["board"] = b.group(1).strip().lower()
            cur["text"] += line.lower() + "\n"
    return out


_NOT_PROSE = re.compile(r"https?://\S+|\b[\w.-]+/[\w.-]+@[\w.^~-]+|\b[\w/.-]*\.(h|hpp|cpp|ino|py|json)\b"
                        r"|\b(m5stack|lib_deps|#include)\s*[/=<]\s*\S+"
                        # v3: a name followed by a library/SDK word is a software reference, not a device
                        # ("M5Cardputer Arduino library" in an ADV-only README, #1747)
                        r"|\b[\w.-]+\s+((arduino|platformio|esp[\s-]?idf|idf)\s+)?(library|libraries|lib|sdk|bsp|component)\b", re.I)


def _prose(text: str) -> str:
    """Upstream text minus what is not a statement about hardware: URLs, library and include references
    (the M5Cardputer library shares its name with the board id)."""
    return _NOT_PROSE.sub(" ", text or "")


_ADDS = re.compile(r"\b(and|or|also|plus|as\s+well)\b|[&+]", re.I)


def _without_gloss(board: str, sentence: str) -> str:
    """`sentence` minus a parenthetical attached directly to the sibling's name that adds nothing with a
    conjunction: "Cardputer-ADV (Cardputer v1.1)" glosses the ADV, it does not list the original as a second
    device (v4, 2026-11-19: m5-crystal builds only [env:cardputer-adv] and v3 PASSed the original on that
    gloss). "(and the original Cardputer)" / "(also Cardputer v1.1)" still add it."""
    sib = SIBLINGS.get(board)
    if not sib:
        return sentence
    return re.sub(rf"((?:{sib}))\s*\(([^)]*)\)",
                  lambda m: m.group(0) if _ADDS.search(m.group(m.lastindex)) else m.group(1), sentence, flags=re.I)


def _names_plain(board: str, text: str, catalog: dict) -> bool:
    low = _prose(text).lower()
    sib = SIBLINGS.get(board)
    if sib:
        low = re.sub(sib, " ", low)          # a sibling mention is not a mention of the board
    comp = _compact(low)
    if any(t in comp for t in _board_terms(board, catalog)):
        return True
    # the product's own short name (the catalog id without the vendor prefix): "cardputer", "sticks3"
    short = re.sub(r"^(m5stack-|m5|lilygo-|waveshare-)", "", board)
    pattern = "[-_ ]?".join(re.escape(part) for part in short.split("-"))
    return len(short) >= 6 and re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", low) is not None


def check(board: str, sources: dict, catalog: dict) -> Verdict:
    """`sources`: {"description": str, "readme": str, "platformio": str} as cited for the edge."""
    texts = {k: v or "" for k, v in (sources or {}).items()}
    if not any(texts.values()):
        return Verdict(UNCERTAIN, ["no readable upstream source"])
    prose = "\n".join([texts.get("description", ""), texts.get("readme", "")])
    assets = texts.get("assets", "")
    envs = _envs(texts.get("platformio", ""))

    # carrier: a module claimed from a product build. Naming the module as the MCU inside a product
    # ("Cardputer (M5Stack StampS3)") is exactly the confusion; only a module-only build counts.
    if board in CARRIERS:
        products = CARRIERS[board]
        def _product(s: str) -> bool:
            return any(p in _compact(s) for p in products)
        hits = [e["name"] for e in envs if _product(e["name"]) or _product(e["text"])]
        own = [e["name"] for e in envs if not (_product(e["name"]) or _product(e["text"]))
               and "stamps3" in _compact(e["board"] + e["name"])]
        if own:
            return Verdict(PASS, [f"carrier: module-only build env(s) {', '.join(own[:3])}"])
        if hits or _product(_prose(prose)):
            return Verdict(FAIL, [f"carrier: {board} appears only as the base of a product build"
                                  + (f" ({', '.join(hits[:3])})" if hits else "")])

    all_text = prose + "\n" + "\n".join(e["name"] for e in envs) + "\n" + assets
    named = _names_plain(board, all_text, catalog)
    sib = SIBLINGS.get(board)
    sib_named = bool(sib and re.search(sib, all_text, re.I))
    if sib_named:
        sentences = [x for x in re.split(r"(?<=[.!?])\s+|\n", _prose(all_text)) if x.strip()]
        orig = [x for x in sentences if re.search(EXPLICIT_ORIGINAL.get(board, r"(?!)"), _without_gloss(board, x), re.I)]
        excl = EXCLUSION.get(board)
        statement = lambda x: not x.strip().strip("*_ ").endswith("?")  # noqa: E731
        # "ADV only" rules the original out only when it is about the device, i.e. contrasted with the
        # original in the same sentence ("Cardputer ADV only - the original Cardputer has a different
        # keyboard"); a feature note ("Accelerometer (Cardputer ADV only)") is not.
        adv_only = excl and any(re.search(excl, x, re.I) and re.search(r"only", x, re.I)
                                and re.search(EXPLICIT_ORIGINAL[board], x, re.I) for x in sentences if statement(x))
        if adv_only or any(excl and re.search(excl, x, re.I) and statement(x) for x in orig):
            return Verdict(FAIL, ["sibling: the source rules the original out explicitly"])
        # "the original Cardputer is untested" is a caveat, not support: it never counts on its own
        explicit = any(statement(x) and not CAVEAT.search(x) for x in orig)
        # v2: the original and the sibling as separate table rows or list items enumerate both devices
        # a table row or a list item ("- ", "* ", "+ "): bold text ("**M5Cardputer**") starts with '*' too
        items = [x for x in _prose(all_text).splitlines() if re.match(r"\s*(\||[-*+]\s)", x)]
        # a device row is short and is the device name itself ("M5Cardputer", "**M5Stack Cardputer ADV**"),
        # never a sentence that mentions it in passing ("Pair the Cardputer with your phone")
        cells = [re.split(r"\s\|\s|\|", x.strip().strip("|"), maxsplit=1)[0] for x in items]
        first = [c for c in (re.sub(r"[*_`\[\]]|^[-+*]\s*", "", c).strip() for c in cells) if 0 < len(c) <= 32]
        sib_items = [x for x in first if re.search(sib, x, re.I)]
        plain_items = [x for x in first if not re.search(sib, x, re.I) and _names_plain(board, x, catalog)]
        enumerated = bool(sib_items and plain_items)
        # v2: a feature marked "(... ADV only)" without contrasting the original implies the rest runs on it
        feature_only = excl and any(re.search(r"adv[\s_-]*only", x, re.I) and not re.search(EXPLICIT_ORIGINAL[board], x, re.I)
                                    for x in sentences)
        names = [_compact(a) for a in assets.split()]
        both_assets = any("adv" in a for a in names) and any("cardputer" in a and "adv" not in a for a in names)
        env_names = {_compact(e["name"]) for e in envs}
        both_envs = any("adv" in n for n in env_names) and any(_names_plain(board, e["name"], catalog) for e in envs)
        if not named:
            return Verdict(FAIL, [f"sibling: the source names only the {SIBLING_LABEL[board]}, never {board} itself"])
        if not (explicit or both_envs or both_assets or enumerated or feature_only):
            return Verdict(UNCERTAIN, [f"sibling: the source names the {SIBLING_LABEL[board]} and {board} only generically"])
    if not named:
        return Verdict(FAIL, [f"named: the source never names {board}"])
    # a statement that names the board and rules it out ("Not for the original Cardputer") is a FAIL
    # whether or not a sibling is named (#1724 review of SquachWatch-CYD)
    excl = EXCLUSION.get(board)
    if excl:
        for x in re.split(r"(?<=[.!?])\s+|\n", _prose(prose)):
            if (x.strip() and not x.strip().strip("*_ ").endswith("?") and re.search(excl, x, re.I)
                    and re.search(EXPLICIT_ORIGINAL.get(board, r"(?!)"), x, re.I)):
                return Verdict(FAIL, [f"exclusion: the source rules {board} out: '{x.strip()[:100]}'"])
    # named is not targets: at least one mention must be a target, not provenance or a roadmap
    built = any(_names_plain(board, e["name"], catalog) for e in envs) or _names_plain(board, assets, catalog)
    mentions = [x for x in re.split(r"(?<=[.!?])\s+|\n", _prose(prose)) if x.strip() and _names_plain(board, x, catalog)]
    if not built and mentions and all(NONTARGET.search(x) for x in mentions):
        return Verdict(UNCERTAIN, [f"context: {board} is named only as provenance or a plan: '{mentions[0].strip()[:100]}'"])
    for sentence in re.split(r"(?<=[.!?])\s+|\n", prose):
        if _names_plain(board, sentence, catalog) and NEGATION.search(sentence):
            return Verdict(UNCERTAIN, [f"negation: '{sentence.strip()[:120]}'"])
    return Verdict(PASS, [f"named: the source names {board}"])


class Capture:
    """Wraps derive's `api`/`raw` callables and keeps what they answered, so the evidence gate reads the
    exact upstream text Jr's own derivation read (no second fetch). `readme()` is the one extra call."""

    def __init__(self, api, raw):
        self._api, self._raw, self.api_answers, self.raw_answers = api, raw, {}, {}

    def api(self, path: str):
        out = self._api(path)
        self.api_answers[path] = out
        return out

    def raw(self, url: str):
        out = self._raw(url)
        self.raw_answers[url] = out
        return out

    def readme(self, owner_repo: str) -> str:
        import base64
        try:
            doc = self._api(f"repos/{owner_repo}/readme")
            return base64.b64decode(doc.get("content") or "").decode("utf-8", "ignore") if isinstance(doc, dict) else ""
        except Exception:  # noqa: BLE001 — no README is evidence of nothing, never an error
            return ""

    def evidence(self, owner_repo: str, readme: str) -> dict:
        meta = self.api_answers.get(f"repos/{owner_repo}") or {}
        assets = []
        for path, doc in self.api_answers.items():
            if "/releases" in path:
                for rel in (doc if isinstance(doc, list) else [doc]):
                    if isinstance(rel, dict):
                        assets += [a.get("name", "") for a in rel.get("assets") or [] if isinstance(a, dict)]
        pio = "\n".join(t for u, t in self.raw_answers.items() if t and u.endswith("platformio.ini"))
        return {"description": (meta.get("description") if isinstance(meta, dict) else "") or "",
                "readme": readme or "", "platformio": pio, "assets": " ".join(dict.fromkeys(assets))}
