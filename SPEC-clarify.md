# SPEC — clarify: confidence-gated clarification

> Status: DRAFT (living). Extends `SPEC-build-guide.md` and mirrors
> `esp_atlas_core.build_guide` / `esp_atlas_core.run_guide`'s grounding
> discipline. Backend + API only — no web/UI (the UI comes later).

## 1. Problem

`parse_intent()`/`build_guide()` always answer immediately, even off a vague
goal like "build a plant health monitor" or a single weak filter like "cheap".
Sometimes the right move isn't a best-effort guess — it's asking 1-3 short,
grounded questions first. `clarify(query, answers=None)` is that gate: when
the parse is confident enough to answer well, it answers (no questions); when
it isn't, it returns up to 3 clarifying questions built ONLY from a fixed,
code-defined dimension catalog (never invented), the user answers, and a
follow-up call folds the answers in and re-evaluates.

## 2. Confidence gate — deterministic, not an LLM number

`clarify()` computes `spec_count`:

```
spec_count = (number of non-"type" keys in parse_intent(query).filters)
           + (number of keys in the merged `needs` dict folded from `answers`)
```

`confidence = min(1.0, spec_count * 0.5)`. `confident = True` when
`parse_intent(query).kind == "firmware"` (confidence forced to `1.0` — naming
a real firmware is always answerable, see `intent.firmware_named_in`), OR
`spec_count >= 2`.

| parse `kind` | spec_count | confident | confidence |
|---|---|---|---|
| `firmware` | n/a | **True** | 1.0 |
| `filters` | 1 (single weak/inferred spec) | **False** | 0.5 |
| `filters` | >= 2 (explicit specs) | **True** | 1.0 |
| `unmapped` | 0 | **False** | 0.0 |
| `unreadable` | 0 | **False** | 0.0 |

This is a pure function of `parse_intent`'s own output plus the answers
already folded in — no LLM is asked "how confident are you". The only LLM
call in this module picks WHICH 1-3 questions to ask (§4), never whether to
ask at all.

Because `spec_count` also counts keys folded in from `answers`, a second
`clarify()` call with enough answers can cross the confidence line even
starting from `kind == "unmapped"` (spec_count 0) — e.g. two answered
dimensions that each contribute one `needs` key reach `spec_count == 2`.

## 3. The fixed question-dimension catalog

Code-defined in `esp_atlas_core.clarify._CATALOG` — Groq may only SELECT and
ORDER ids from this list; it never authors a prompt, an option label, or a
`needs` value. Every `needs` delta is grounded in a field this dataset
actually has (`board.schema.json`'s `power.battery_connector`, `display`,
`wifi_standard`, `price_tier`) or in `parse_intent`/`wizard`'s own filter
vocabulary (`radio`, `budget`).

| id | prompt | option -> `needs` delta |
|---|---|---|
| `power` | "Battery-powered / portable, or plugged in?" | battery -> `{"battery": true}` \| plugged -> `{}` |
| `environment` | "Indoor or outdoor?" | indoor -> `{}` \| outdoor -> `{"battery": true}` (outdoor implies low-power/battery) |
| `target` | "Report to your phone / Home Assistant, or standalone?" | ha -> `{"radio": "wifi-4"}` + `firmware_hint: "esphome"` \| standalone -> `{}` |
| `interaction` | "Screen & buttons, or headless?" | screen -> `{"display": true}` \| headless -> `{}` |
| `budget` | "Keep it cheap, or is a pricier board fine?" | cheap -> `{"budget": "cheap"}` \| pricier -> `{}` |

`firmware_hint` is a fixed, code-defined firmware id (`esphome`) — the only
dimension that carries one. It is never Groq's choice.

## 4. Multi-turn mechanism

`clarify(query, answers=None, llm_client=None, db_path=None)`:

1. Run `parse_intent(query, llm_client=llm_client, db_path=db_path)` (reused
   verbatim — clarify does not re-implement intent parsing).
2. Fold `answers` (a `{dimension_id: option_value}` dict, e.g.
   `{"target": "ha", "power": "battery"}`) into `answered_context = {"needs":
   {...merged deltas...}, "firmware_hint": "esphome" | None}`. An unknown
   dimension id or an unknown option value is silently ignored — never
   invented, never raised.
3. Compute the confidence gate (§2) over `parse_intent`'s own `filters` plus
   `answered_context.needs`.
4. **Confident:** return `{"confident": True, "confidence": ..., "questions":
   [], "answered_context": answered_context}`.
5. **Not confident:** pick 1-3 unanswered dimension ids to ask next
   (`_select_question_ids`, §5), render each as `{"id", "prompt", "options":
   [{"label", "value", "needs"}]}`, and return `{"confident": False,
   "confidence": ..., "questions": [...], "answered_context":
   answered_context}`.

The caller (a wizard UI, later) shows the returned questions, collects the
user's picks, and makes ONE follow-up `clarify(query, answers={...})` call
with every dimension answered so far (not one call per question) — the
re-evaluated confidence either closes the loop or returns the next batch of
unanswered dimensions.

## 5. Question selection — Groq picks ids, never content

Groq is given the goal and the list of still-unanswered dimension ids (with
their one-line descriptions) and replies `{"question_ids": ["id1", "id2",
"id3"]}`, ordered most-decision-relevant first. The reply is validated:

- Any id not in the fixed catalog (or already answered) is dropped.
- If nothing valid survives (down/rate-limited/garbage Groq, or a fake LLM
  returning invented ids), the caller degrades to a deterministic default
  order (`target, power, environment, interaction, budget`, filtered to
  unanswered ids, capped at 3) — never a 500, never an invented dimension.

Board/firmware selection is unaffected by this module — `clarify()` never
picks a board, and the only firmware it can ever name is the fixed
`firmware_hint` in §3.

## 6. Anchoring `build_guide()` with `answered_context`

`build_guide(query, llm_client=None, db_path=None, answered_context=None)`
gains an optional fourth argument (default `None`, so every existing call
site — including `POST /build`, which stays unchanged, see §7 — is
unaffected):

- `answered_context["needs"]["battery"]` forces `traits.battery = True`.
- `answered_context["needs"]["radio"]` forces `traits.wifi = True`.
- `answered_context["needs"]["budget"] == "cheap"` forces `traits.cheap =
  True`.
- `answered_context["firmware_hint"]`, if it names a real firmware id,
  **overrides** whatever `firmware_id` the LLM/fallback path picked — the
  user directly told us the target, so there is nothing left to infer.

Board recommendation is unchanged (still 100% deterministic, still ranked by
`traits` — see `build_guide.py`'s existing `_board_score`/`_board_why`), so a
`battery: True` trait already surfaces battery-capable boards ahead of others
with no new code path.

Example: `build_guide("build a plant health monitor", answered_context=
{"needs": {"battery": True, "radio": "wifi-4"}, "firmware_hint": "esphome"})`
→ `firmware.id == "esphome"` (forced, not inferred) and the top-ranked board
has `power.battery_connector == true`.

## 7. API

`POST /clarify` — body `{"query": "<1-500 chars>", "answers": {"<dimension
id>": "<option value>", ...} | null}`, response the `clarify()` shape above.
Always 200 — Groq failures degrade to the deterministic default order (§5),
never raise. `POST /intent`, `POST /build`, `GET /run/{firmware_id}` are
**unchanged** — `answered_context` is a Python-level `build_guide()` argument
only, not (yet) exposed over HTTP; the web layer that would wire
`clarify()` → `build_guide(..., answered_context=...)` together is future
work (this spec is backend/API-only).

## 8. Tests / oracle

Unit (`apps/core/tests/test_clarify.py`), fake LLM, no network — mirrors
`test_build_guide.py`'s structure:

- `clarify("run marauder")` → `confident is True`, `questions == []`.
- `clarify("esp32-s3 with 8mb psram")` (>= 2 explicit specs) → `confident is
  True`.
- `clarify("build a plant health monitor")` → `confident is False`, 1-3
  questions, every option's `needs` keys drawn only from the fixed catalog.
- Answering with `{"target": "ha", "power": "battery"}` → `confident is
  True`; feeding that `answered_context` into `build_guide()` →
  `firmware.id == "esphome"` and at least one board has a battery connector.
- Groq unreachable for question selection → deterministic default order, no
  crash, no invented dimension.
- A fake LLM returning a question id outside the fixed catalog → dropped,
  never surfaced in `questions`.
- Edge cases: empty `answers` (`{}`), answers supplied for an already-firmware
  query (stays confident, answers are irrelevant), and a gibberish/unmapped
  query.

Live-Groq oracle (question-selection only — the confidence gate itself is
pure deterministic code, nothing to golden-test against real inference):
`apps/core/tests/data/clarify_golden.py`, `scripts/clarify_oracle.py`,
`apps/core/tests/test_clarify_golden_live.py`, `make clarify-oracle` — same
on-demand, not-CI-blocking pattern as `build-guide-oracle`.
