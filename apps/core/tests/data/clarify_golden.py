"""The GOLDEN QUERY MATRIX for real-Groq clarify() question SELECTION
(SPEC-clarify.md §8).

Unlike build_guide/parse_intent's golden matrices, the confidence GATE itself
is pure deterministic code (SPEC-clarify.md §2) -- there is nothing to golden-
test about it against live inference. What live Groq CAN get wrong is WHICH
1-3 dimension ids it picks for a vague goal, since that's the one judgment
call this module hands to the model. This matrix pins that.

Each entry:
    query        -- a plain-language, intentionally vague build goal (must
                     resolve to kind != "firmware" so a question set is
                     actually produced)
    expect_any_of -- dimension ids where AT LEAST ONE must appear in the
                     returned questions -- the acceptable, grounded picks for
                     this goal, not a single required ordering (live models
                     are not perfectly deterministic about order).
"""

GOLDEN = [
    dict(
        id="plant_health_monitor",
        query="build a plant health monitor",
        expect_any_of=("target", "power", "environment"),
    ),
    dict(
        id="outdoor_gadget",
        query="a gadget I can leave outside all summer",
        expect_any_of=("power", "environment"),
    ),
    dict(
        id="home_dashboard",
        query="something to show me stats on a little screen",
        expect_any_of=("interaction", "target"),
    ),
    dict(
        id="cheap_project",
        query="a fun weekend project, nothing fancy",
        expect_any_of=("budget", "target", "interaction"),
    ),
]
