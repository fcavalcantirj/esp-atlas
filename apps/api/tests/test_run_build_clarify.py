from _shared import client_with_llm, marauder_boards_with_chip, marauder_recipe_boards, marauder_recipe_citations


# --- /run (grounded run-answer) ---------------------------------------------------------


def test_run_marauder_returns_grounded_boards_and_reasons(built_db_path):
    client = client_with_llm(built_db_path, {"summary": "", "boards": []})
    with client:
        r = client.get("/run/esp32marauder")
    assert r.status_code == 200
    body = r.json()
    assert body["firmware"] == "esp32marauder"
    assert body["grounded"] is True
    assert "2.4GHz Wi-Fi" in body["requirements"]
    assert "Bluetooth LE" in body["requirements"]
    board_ids = {b["board_id"] for b in body["boards"]}
    assert board_ids == marauder_recipe_boards()
    for board in body["boards"]:
        assert board["reasons"]
        assert board["sources"] and all(s["url"] for s in board["sources"])
    assert set(body["citations"]) == marauder_recipe_citations()


def test_run_chip_constraint_restricts_boards(built_db_path):
    client = client_with_llm(built_db_path, {"summary": "", "boards": []})
    with client:
        r = client.get("/run/esp32marauder", params={"constraints": "on a esp32"})
    assert r.status_code == 200
    body = r.json()
    assert {b["board_id"] for b in body["boards"]} == marauder_boards_with_chip("esp32")
    assert body["constraint"] == {"chip": "esp32"}
    assert {e["board"] for e in body["excluded_boards"]} == marauder_recipe_boards() - marauder_boards_with_chip(
        "esp32"
    )


def test_run_unknown_firmware_is_honest_not_found_not_a_404(built_db_path):
    client = client_with_llm(built_db_path, {"summary": "", "boards": []})
    with client:
        r = client.get("/run/no-such-firmware")
    assert r.status_code == 200
    body = r.json()
    assert body["grounded"] is False
    assert body["boards"] == []


def test_run_strips_a_hallucinated_board_from_the_model(built_db_path):
    client = client_with_llm(
        built_db_path,
        {
            "summary": "ok",
            "boards": [{"board_id": "not-a-real-board", "note": "invented", "source_url": "https://not-real.example"}],
        },
    )
    with client:
        r = client.get("/run/esp32marauder")
    body = r.json()
    board_ids = {b["board_id"] for b in body["boards"]}
    assert board_ids == marauder_recipe_boards()


# --- /build (grounded build-guide) ------------------------------------------


def test_build_plant_health_monitor_returns_esphome_and_real_boards(built_db_path):
    payload = {
        "firmware_id": "esphome",
        "why": "Reads sensors and reports to Home Assistant over Wi-Fi.",
        "traits": {"wifi": True, "battery": False, "cheap": True},
        "add_ons": ["soil-moisture sensor"],
    }
    client = client_with_llm(built_db_path, payload)
    with client:
        r = client.post("/build", json={"query": "build a plant health monitor"})
    assert r.status_code == 200
    body = r.json()
    assert body["goal"] == "build a plant health monitor"
    assert body["firmware"]["id"] == "esphome"
    assert body["boards"]
    board_ids = {b["board_id"] for b in body["boards"]}
    for board_id in board_ids:
        assert client.get(f"/parts/{board_id}").status_code == 200
    assert body["add_ons"] == ["soil-moisture sensor"]
    assert "soil-moisture sensor" in body["note"]


def test_build_rejects_an_invented_firmware_id_from_the_model(built_db_path):
    payload = {
        "firmware_id": "totally-invented-firmware-xyz",
        "why": "invented",
        "traits": {"wifi": True, "battery": False, "cheap": True},
        "add_ons": [],
    }
    client = client_with_llm(built_db_path, payload)
    with client:
        r = client.post("/build", json={"query": "build a plant health monitor"})
    assert r.status_code == 200
    assert r.json().get("firmware") is None
    assert r.json()["boards"], "must still recommend boards rather than dead-end"


def test_build_no_firmware_fits_is_honest_and_still_200(built_db_path):
    payload = {
        "firmware_id": None,
        "why": "nothing fits",
        "traits": {"wifi": True, "battery": True, "cheap": True},
        "add_ons": ["motor driver"],
    }
    client = client_with_llm(built_db_path, payload)
    with client:
        r = client.post("/build", json={"query": "a line-following robot"})
    assert r.status_code == 200
    body = r.json()
    assert body.get("firmware") is None
    assert body["boards"]
    assert "no ready-made firmware" in body["note"].lower()


def test_build_empty_query_is_422(client):
    r = client.post("/build", json={"query": ""})
    assert r.status_code == 422


# --- /clarify (confidence-gated clarification) -------------------------------


def test_clarify_run_marauder_is_confident_with_no_questions(client):
    r = client.post("/clarify", json={"query": "run marauder"})
    assert r.status_code == 200
    body = r.json()
    assert body["confident"] is True
    assert body["confidence"] == 1.0
    assert body["questions"] == []


def test_clarify_plant_health_monitor_returns_grounded_questions(built_db_path):
    payload = {"filters": {"type": "board"}, "unmapped": ["plant health monitor"]}
    client = client_with_llm(built_db_path, payload)
    with client:
        r = client.post("/clarify", json={"query": "build a plant health monitor"})
    assert r.status_code == 200
    body = r.json()
    assert body["confident"] is False
    assert 1 <= len(body["questions"]) <= 3
    for question in body["questions"]:
        assert question["id"]
        assert question["prompt"]
        assert question["options"]
        for option in question["options"]:
            assert option["label"]
            assert isinstance(option["needs"], dict)


def test_clarify_answers_fold_in_and_can_become_confident(built_db_path):
    payload = {"filters": {"type": "board"}, "unmapped": ["plant health monitor"]}
    client = client_with_llm(built_db_path, payload)
    with client:
        r = client.post(
            "/clarify",
            json={"query": "build a plant health monitor", "answers": {"target": "ha", "power": "battery"}},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["confident"] is True
    assert body["questions"] == []
    assert body["answered_context"]["needs"] == {"radio": "wifi-4", "battery": True}
    assert body["answered_context"]["firmware_hint"] == "esphome"


def test_clarify_empty_query_is_422(client):
    r = client.post("/clarify", json={"query": ""})
    assert r.status_code == 422


def test_examples_endpoint_returns_resolvable_entries(client):
    r = client.get("/examples")
    assert r.status_code == 200
    results = r.json()["results"]
    assert results
    for ex in results:
        assert ex["count"] >= 1, ex["id"]
        if ex["kind"] == "firmware":
            assert ex["firmware"] and "needs" not in ex
        else:
            assert ex["kind"] == "needs"
            assert ex["needs"] and "firmware" not in ex


def test_examples_needs_round_trip_through_wizard(client):
    for ex in client.get("/examples").json()["results"]:
        if ex["kind"] != "needs":
            continue
        r = client.post("/wizard", json={"needs": ex["needs"]})
        assert r.status_code == 200, (ex["id"], r.text)
        assert r.json()["results"], f"{ex['id']}: needs round-trip returned 0 results"


def test_examples_firmware_entries_carry_popularity_and_are_ranked_by_it(client):
    """SPEC-firmware-popularity.md §3.B: /examples plumbs stars/forks through
    from each firmware's own popularity, ranked by the same comparator
    /firmware?sort=popularity uses -- the two surfaces can never diverge."""
    firmware_examples = [ex for ex in client.get("/examples").json()["results"] if ex["kind"] == "firmware"]
    assert firmware_examples

    firmware_by_id = {fw["id"]: fw for fw in client.get("/firmware").json()["results"]}
    for ex in firmware_examples:
        popularity = firmware_by_id[ex["firmware"]].get("popularity") or {}
        assert ex.get("stars") == popularity.get("stars"), ex["id"]
        assert ex.get("forks") == popularity.get("forks"), ex["id"]

    # /firmware defaults to popularity order already, so filtering it down to the
    # recipe-backed subset gives exactly the expected examples order.
    example_firmware_ids = {ex["firmware"] for ex in firmware_examples}
    expected_order = [fw["id"] for fw in client.get("/firmware").json()["results"] if fw["id"] in example_firmware_ids]
    assert [ex["firmware"] for ex in firmware_examples] == expected_order
