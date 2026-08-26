"""clarify(query, answers=None) -> confidence-gated clarification (SPEC-clarify.md).

    clarify("run marauder")
    # -> {"confident": True, "confidence": 1.0, "questions": [],
    #     "answered_context": {"needs": {}, "firmware_hint": None}}

    clarify("build a plant health monitor")
    # -> {"confident": False, "confidence": 0.0,
    #     "questions": [{"id": "target", "prompt": "...", "options": [...]}, ...],
    #     "answered_context": {"needs": {}, "firmware_hint": None}}

    clarify("build a plant health monitor", answers={"target": "ha", "power": "battery"})
    # -> {"confident": True, "confidence": 1.0, "questions": [],
    #     "answered_context": {"needs": {"radio": "wifi-4", "battery": True},
    #                           "firmware_hint": "esphome"}}

The confidence gate is a DETERMINISTIC function of `parse_intent()`'s own
output plus whatever `answers` fold in -- never an LLM-reported number (see
module-level `_confidence`). The only LLM call in this module picks WHICH 1-3
questions to ask next, from a FIXED, code-defined dimension catalog
(`_CATALOG`); it can select and order ids, it can never author a prompt, an
option label, or a `needs` value -- so a hostile/garbage reply can degrade
the ORDER of what's asked, never invent a new question or a new spec.
"""
import json

from esp_atlas_core.intent import parse_intent
from esp_atlas_core.llm import FAST_MODEL, GroqClient

# Fixed dimension catalog (SPEC-clarify.md §3). Every `needs` delta is
# grounded in a real field this dataset has (board.schema.json's
# power.battery_connector/display/wifi_standard/price_tier) or in
# parse_intent/wizard's own filter vocabulary (radio, budget). `firmware_hint`
# is a fixed, code-defined firmware id -- never Groq's choice.
_CATALOG = {
    "power": {
        "prompt": "Battery-powered / portable, or plugged in?",
        "options": [
            {"value": "battery", "label": "Battery-powered / portable", "needs": {"battery": True}},
            {"value": "plugged", "label": "Plugged in", "needs": {}},
        ],
    },
    "environment": {
        "prompt": "Indoor or outdoor?",
        "options": [
            {"value": "indoor", "label": "Indoor", "needs": {}},
            # outdoor implies low-power/battery -- SPEC-clarify.md §3
            {"value": "outdoor", "label": "Outdoor", "needs": {"battery": True}},
        ],
    },
    "target": {
        "prompt": "Report to your phone / Home Assistant, or standalone?",
        "options": [
            {
                "value": "ha",
                "label": "Home Assistant",
                "needs": {"radio": "wifi-4"},
                "firmware_hint": "esphome",
            },
            {"value": "standalone", "label": "Standalone", "needs": {}},
        ],
    },
    "interaction": {
        "prompt": "Screen & buttons, or headless?",
        "options": [
            {"value": "screen", "label": "Screen & buttons", "needs": {"display": True}},
            {"value": "headless", "label": "Headless", "needs": {}},
        ],
    },
    "budget": {
        "prompt": "Keep it cheap, or is a pricier board fine?",
        "options": [
            {"value": "cheap", "label": "Keep it cheap", "needs": {"budget": "cheap"}},
            {"value": "pricier", "label": "Pricier is fine", "needs": {}},
        ],
    },
}

# Deterministic fallback order when Groq is unreachable or returns nothing
# usable -- most decision-relevant dimension first, mirroring the ordering
# intuition taught to Groq as few-shot below.
_DEFAULT_ORDER = ("target", "power", "environment", "interaction", "budget")
_MAX_QUESTIONS = 3

SELECT_SYSTEM_PROMPT = """You choose which clarifying questions to ask a maker about an ESP32 project
goal that is too vague to answer directly.

Reply with JSON only, no prose, in exactly this shape:
{"question_ids": ["id1", "id2", "id3"]}

Choose 1 to 3 ids from EXACTLY this fixed list -- never invent an id that
isn't below, never return more than 3:
- power: whether the project needs to run off a battery
- environment: whether the project lives indoors or outdoors
- target: whether the project reports to Home Assistant/a phone, or is standalone
- interaction: whether the project needs a screen and buttons, or is headless
- budget: whether cost matters

Order matters -- put the question that narrows the goal the MOST first. Skip
a dimension the goal already answers (e.g. a goal that already says "cheap"
doesn't need budget asked again)."""


def _parse_json(text):
    """The model is asked for JSON only; tolerate a fenced block around it."""
    body = (text or "").strip()
    if body.startswith("```"):
        body = body.split("```")[1]
        if body.startswith("json"):
            body = body[4:]
    start, end = body.find("{"), body.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(body[start : end + 1])
    except json.JSONDecodeError:
        return None


def _default_question_ids(remaining_ids):
    return [i for i in _DEFAULT_ORDER if i in remaining_ids][:_MAX_QUESTIONS]


def _select_question_ids(query, remaining_ids, llm_client):
    """Which unanswered dimension ids to ask next, in order -- see module
    docstring. Never raises: any failure (down/rate-limited/garbage/invented
    ids) degrades to the deterministic default order, never a dead end."""
    if not remaining_ids:
        return []

    client = llm_client or GroqClient(model=FAST_MODEL)
    try:
        raw_text = client.complete(SELECT_SYSTEM_PROMPT, query, temperature=0)
    except Exception:
        return _default_question_ids(remaining_ids)

    raw = _parse_json(raw_text)
    ids = raw.get("question_ids") if isinstance(raw, dict) else None
    if not isinstance(ids, list):
        return _default_question_ids(remaining_ids)

    remaining = set(remaining_ids)
    seen = set()
    selected = []
    for entry in ids:
        if isinstance(entry, str) and entry in remaining and entry not in seen:
            seen.add(entry)
            selected.append(entry)

    return selected[:_MAX_QUESTIONS] if selected else _default_question_ids(remaining_ids)


def _render_question(dimension_id):
    dimension = _CATALOG[dimension_id]
    return {
        "id": dimension_id,
        "prompt": dimension["prompt"],
        "options": [
            {"label": option["label"], "value": option["value"], "needs": dict(option["needs"])}
            for option in dimension["options"]
        ],
    }


def _match_option(dimension, value):
    if not isinstance(value, str):
        return None
    token = value.strip().lower()
    for option in dimension["options"]:
        if token == option["value"] or token == option["label"].lower():
            return option
    return None


def _fold_answers(answers):
    """{dimension_id: option_value} -> {"needs": {...merged deltas...},
    "firmware_hint": "<id>" | None}. An unknown dimension id or option value
    is silently ignored -- grounded in the fixed catalog only, never invented,
    never raised."""
    needs = {}
    firmware_hint = None
    for dimension_id, value in (answers or {}).items():
        dimension = _CATALOG.get(dimension_id)
        if dimension is None:
            continue
        option = _match_option(dimension, value)
        if option is None:
            continue
        needs.update(option["needs"])
        if option.get("firmware_hint"):
            firmware_hint = option["firmware_hint"]
    return {"needs": needs, "firmware_hint": firmware_hint}


def _spec_count(filters):
    return len([key for key in (filters or {}) if key != "type"])


def _confidence(parsed, context):
    """A DETERMINISTIC function of the parse + folded answers -- SPEC-clarify.md §2."""
    if parsed["kind"] == "firmware":
        return True, 1.0
    specs = _spec_count(parsed.get("filters")) + len(context.get("needs") or {})
    confidence = min(1.0, specs * 0.5)
    return confidence >= 1.0, confidence


def clarify(query, answers=None, llm_client=None, db_path=None, use_cache=True):
    """Confidence-gated clarification -- see module docstring for the shape.

    HIGH confidence (kind=="firmware", or kind=="filters" with >= 2 explicit
    specs) answers directly with no questions. LOW confidence (kind ==
    "unmapped"/"unreadable", or a single weak/inferred spec) returns 1-3
    grounded questions from the fixed catalog. Passing `answers` folds them
    into `answered_context` and re-evaluates -- enough answered dimensions can
    cross the confidence line even from an originally "unmapped" goal.

    `use_cache` is forwarded to parse_intent()'s own query-string cache
    (default True, same as parse_intent) -- pass False in tests that reuse a
    query string across stubs, same idiom as test_intent_oracle.py.
    """
    parsed = parse_intent(query, llm_client=llm_client, db_path=db_path, use_cache=use_cache)
    context = _fold_answers(answers)
    confident, confidence = _confidence(parsed, context)

    if confident:
        return {
            "confident": True,
            "confidence": confidence,
            "questions": [],
            "answered_context": context,
        }

    answered_ids = {key for key in (answers or {}) if key in _CATALOG}
    remaining_ids = [dimension_id for dimension_id in _DEFAULT_ORDER if dimension_id not in answered_ids]
    question_ids = _select_question_ids(query, remaining_ids, llm_client)

    return {
        "confident": False,
        "confidence": confidence,
        "questions": [_render_question(dimension_id) for dimension_id in question_ids],
        "answered_context": context,
    }
