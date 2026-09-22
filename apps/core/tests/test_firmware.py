from esp_atlas_core.firmware import (
    boards_key,
    forks_key,
    get_firmware,
    list_firmware,
    list_recipes,
    name_key,
    popularity_key,
    recipes_for_board,
    recipes_for_firmware,
    sort_by_mode,
    sort_by_popularity,
)
from esp_atlas_core.paths import DATA_DIR

# The trust tiers a recipe may carry (must mirror schema/recipe.schema.json's
# status enum). `known-good` means the maintainer/an official list names the
# board, or esp-atlas verified it on real hardware; `reported` is cited but
# community-sourced; `declared` is extracted from the repo's own board manifest
# or README device table (provenance-cited, unverified on hardware,
# SPEC-firmware-board-mapping.md); `unverified` is a plausible build target with
# no verification; `broken` is a known regression.
TRUST_TIERS = {"known-good", "reported", "declared", "unverified", "broken"}


def _folder_ids(kind):
    """Record ids as the data/ tree spells them -- the accessors must find exactly these."""
    return {d.name for d in (DATA_DIR / kind).iterdir() if d.is_dir()}


def test_list_firmware_includes_every_seeded_firmware():
    assert {fm["id"] for fm in list_firmware()} == _folder_ids("firmware")


def test_get_firmware_known_id_returns_full_record():
    fm = get_firmware("esp32marauder")
    assert fm["name"] == "ESP32 Marauder"
    assert fm["url"] == "https://github.com/justcallmekoko/ESP32Marauder"
    assert fm["category"] == "pentest"
    # Superset, not equality: Jr's Track B widens `socs` from cited build signals (never narrows),
    # so the record may legitimately gain chips; losing one of these would be the real defect.
    assert set(fm["socs"]) >= {"esp32", "esp32-s2", "esp32-s3", "esp32-c5"}


def test_get_firmware_unknown_id_returns_none():
    assert get_firmware("no-such-firmware") is None


def test_list_recipes_includes_every_seeded_recipe():
    assert {r["id"] for r in list_recipes()} == _folder_ids("recipes")


def test_recipes_for_board_filters_by_board():
    recipes = recipes_for_board("m5cardputer")
    assert recipes, "m5cardputer should have at least one recipe"
    assert {r["id"] for r in recipes} == {
        r["id"] for r in list_recipes() if r["board"] == "m5cardputer"
    }
    assert all(r["board"] == "m5cardputer" for r in recipes)


def test_recipes_for_board_unknown_board_returns_empty():
    assert recipes_for_board("no-such-board") == []


def test_recipes_for_firmware_filters_by_firmware():
    recipes = recipes_for_firmware("launcher")
    assert recipes, "launcher should have at least one recipe"
    assert {r["id"] for r in recipes} == {
        r["id"] for r in list_recipes() if r["firmware"] == "launcher"
    }
    assert all(r["firmware"] == "launcher" for r in recipes)


def test_recipes_for_firmware_unknown_firmware_returns_empty():
    assert recipes_for_firmware("no-such-firmware") == []


def test_recipes_for_firmware_infiltra_is_no_longer_orphaned():
    ids = {r["id"] for r in recipes_for_firmware("infiltra")}
    assert ids == {"m5stick-cplus2__infiltra", "m5cardputer__infiltra"}


def test_recipes_for_firmware_m5_crystal_is_no_longer_orphaned():
    ids = {r["id"] for r in recipes_for_firmware("m5-crystal")}
    assert ids == {"m5stick-cplus2__m5-crystal", "m5stick-s3__m5-crystal"}


def test_recipes_for_firmware_rogueduck_is_no_longer_orphaned():
    ids = {r["id"] for r in recipes_for_firmware("rogueduck")}
    assert ids == {"m5stick-s3__rogueduck"}


def test_every_recipe_carries_a_valid_trust_tier():
    """Every recipe declares one of the four tiers, and says who vouched for it.

    This replaced an assertion that *every* recipe was `known-good`, which held
    only while the dataset was a hand-cited seed. `reported` (cited, but from a
    community catalogue) and `unverified` (an official build target with nothing
    shipped to verify) are legitimate tiers -- the honesty layer is that the tier
    is stated, not that it is always the highest one.
    """
    bad = [(r["id"], r.get("status")) for r in list_recipes() if r.get("status") not in TRUST_TIERS]
    assert not bad, f"recipe(s) with an unknown trust tier: {bad}"


def test_every_recipe_cites_at_least_one_source():
    uncited = [r["id"] for r in list_recipes() if not r.get("sources")]
    assert not uncited, f"uncited recipe(s): {uncited}"


def test_list_recipes_carries_the_cited_reason_text():
    recipe = next(r for r in list_recipes() if r["id"] == "m5cardputer__esp32marauder")
    assert recipe["reason"] == "ESP32 Marauder lists the M5Cardputer among its supported devices."


def test_every_recipe_has_non_empty_reason_text():
    """The reason is the recipe body itself -- every seeded recipe has one."""
    empty = [r["id"] for r in list_recipes() if not r.get("reason")]
    assert not empty, f"recipe(s) with no reason text: {empty}"


def test_sort_by_popularity_orders_stars_desc_forks_desc_name_asc_nulls_last():
    """The oracle: stars desc, forks desc (tie-break), name asc (tie-break),
    null/absent stars sort LAST ordered by name (SPEC-firmware-popularity.md
    §2/§6). Both the `/firmware` list endpoint and the `/examples` projection
    reuse this exact comparator, so it is pinned here once and trusted
    everywhere else."""
    fixture = [
        {"name": "Alpha", "popularity": {"stars": 100, "forks": 5}},
        {"name": "Beta", "popularity": {"stars": 100, "forks": 10}},
        {"name": "Gamma", "popularity": {"stars": 50, "forks": 999}},
        {"name": "Zeta", "popularity": {"stars": 50, "forks": 999}},
        {"name": "Delta", "popularity": None},
        {"name": "Epsilon", "popularity": {"stars": None, "forks": 20}},
    ]

    ordered = sort_by_popularity(fixture)

    assert [r["name"] for r in ordered] == [
        "Beta",     # 100 stars, 10 forks
        "Alpha",    # 100 stars, 5 forks
        "Gamma",    # 50 stars, 999 forks -- tie with Zeta, name asc
        "Zeta",     # 50 stars, 999 forks
        "Delta",    # null popularity -- last, name asc
        "Epsilon",  # null stars (forks present but irrelevant) -- last, name asc
    ]


def test_popularity_key_treats_absent_popularity_field_the_same_as_null():
    assert popularity_key({"name": "NoPopKey"}) == popularity_key({"name": "NoPopKey", "popularity": None})


def test_list_firmware_carries_boards_count_matching_recipes_for_firmware():
    """`boards` (SPEC-firmware-ordering.md §4.A) must equal
    `len(recipes_for_firmware(id))` for every record -- computed in one Counter
    pass over `list_recipes()`, so this is really a cross-check that the fast
    path agrees with the (slow, O(n^2)-if-called-per-record) reference."""
    for fm in list_firmware():
        assert fm["boards"] == len(recipes_for_firmware(fm["id"])), fm["id"]


# --- P1 ordering oracle (SPEC-firmware-ordering.md §5.1) --------------------
#
# One hand-built fixture, exercised under every `sort_by_mode` mode, each
# mode's exact id order pinned below. Coding-tool names throughout (never
# lorem/animals/food). What each row is doing here:
#
#   cargo/rustc/clippy  -- same stars (200): forks breaks cargo+clippy (80)
#                           ahead of rustc (50); cargo/clippy then break on
#                           name (raw, case-sensitive -- popularity_key's
#                           existing, unchanged tie-break).
#   vitea/viteb         -- literally the same name ("Vite"): name_key can
#                           only break the tie on `id` (vitea < viteb).
#   zephyrrtos/advanceos -- tied stars+forks; the casefold case from the spec
#                           itself: naive case-sensitive sort puts capital-Z
#                           "ZephyrRTOS" before lowercase "advanceos" (that's
#                           the bug this oracle exists to catch), but
#                           name_key's casefold puts "advanceos" first.
#   eslint/prettier      -- tied `boards` (5): boards_key falls back to
#                           popularity_key, and eslint's higher stars wins.
#   ghostbuild            -- no name, no popularity, no boards: the
#                           "null/missing everywhere" row. It lands last under
#                           every single mode (popularity: null stars; name
#                           and name-desc: null name, direction-invariant
#                           trailing bucket; forks: null forks; boards: null
#                           boards) and is the one no-crash-on-None/undefined
#                           proof point (§8).
_ORACLE_FIXTURE = [
    {"id": "cargo", "name": "Cargo", "popularity": {"stars": 200, "forks": 80}, "boards": 3},
    {"id": "rustc", "name": "Rustc", "popularity": {"stars": 200, "forks": 50}, "boards": 3},
    {"id": "clippy", "name": "Clippy", "popularity": {"stars": 200, "forks": 80}, "boards": 1},
    {"id": "vitea", "name": "Vite", "popularity": {"stars": 999, "forks": 5}, "boards": 1},
    {"id": "viteb", "name": "Vite", "popularity": {"stars": 10, "forks": 1}, "boards": 1},
    {"id": "zephyrrtos", "name": "ZephyrRTOS", "popularity": {"stars": 40, "forks": 3}, "boards": 1},
    {"id": "advanceos", "name": "advanceos", "popularity": {"stars": 40, "forks": 3}, "boards": 1},
    {"id": "eslint", "name": "ESLint", "popularity": {"stars": 300, "forks": 40}, "boards": 5},
    {"id": "prettier", "name": "Prettier", "popularity": {"stars": 250, "forks": 60}, "boards": 5},
    {"id": "ghostbuild", "popularity": {"stars": None, "forks": None}},
]


def _oracle_ids(mode):
    return [r["id"] for r in sort_by_mode(_ORACLE_FIXTURE, mode)]


def test_oracle_popularity_mode_matches_pinned_id_order():
    assert _oracle_ids("popularity") == [
        "vitea", "eslint", "prettier", "cargo", "clippy", "rustc",
        "zephyrrtos", "advanceos", "viteb", "ghostbuild",
    ]


def test_oracle_name_mode_matches_pinned_id_order():
    assert _oracle_ids("name") == [
        "advanceos", "cargo", "clippy", "eslint", "prettier", "rustc",
        "vitea", "viteb", "zephyrrtos", "ghostbuild",
    ]


def test_oracle_name_desc_mode_matches_pinned_id_order():
    assert _oracle_ids("name-desc") == [
        "zephyrrtos", "vitea", "viteb", "rustc", "prettier", "eslint",
        "clippy", "cargo", "advanceos", "ghostbuild",
    ]


def test_oracle_forks_mode_matches_pinned_id_order():
    assert _oracle_ids("forks") == [
        "cargo", "clippy", "prettier", "rustc", "eslint", "vitea",
        "zephyrrtos", "advanceos", "viteb", "ghostbuild",
    ]


def test_oracle_boards_mode_matches_pinned_id_order():
    assert _oracle_ids("boards") == [
        "eslint", "prettier", "cargo", "rustc", "vitea", "clippy",
        "zephyrrtos", "advanceos", "viteb", "ghostbuild",
    ]


def test_oracle_unknown_mode_clamps_to_popularity():
    assert _oracle_ids("not-a-real-mode") == _oracle_ids("popularity")


def test_oracle_ghostbuild_lands_last_in_every_mode():
    for mode in ("popularity", "name", "name-desc", "forks", "boards"):
        assert _oracle_ids(mode)[-1] == "ghostbuild", mode


def test_name_key_breaks_identical_names_by_id():
    assert name_key(_ORACLE_FIXTURE[3])[-1] == "vitea"  # vitea
    assert name_key(_ORACLE_FIXTURE[4])[-1] == "viteb"  # viteb
    assert sorted(
        [_ORACLE_FIXTURE[4], _ORACLE_FIXTURE[3]], key=name_key
    ) == [_ORACLE_FIXTURE[3], _ORACLE_FIXTURE[4]]


def test_forks_key_null_forks_sorts_to_trailing_bucket():
    assert forks_key({"id": "z", "name": "Z", "popularity": {"stars": 1, "forks": None}})[0] == 1
    assert forks_key({"id": "a", "name": "A", "popularity": {"stars": 1, "forks": 1}})[0] == 0


def test_boards_key_null_boards_sorts_to_trailing_bucket():
    assert boards_key({"id": "z", "name": "Z"})[0] == 1
    assert boards_key({"id": "a", "name": "A", "boards": 0})[0] == 0
