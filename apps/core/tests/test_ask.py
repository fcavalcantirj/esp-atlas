import pytest

from esp_atlas_core.ask import ask


class FakeLLM:
    def __init__(self, response_text="ESP32-C6 is Wi-Fi 6 + BLE 5.3 + 802.15.4."):
        self.calls = []
        self.response_text = response_text

    def complete(self, system_prompt, user_prompt, temperature=0):
        self.calls.append({"system": system_prompt, "user": user_prompt, "temperature": temperature})
        return self.response_text


def test_ask_grounds_prompt_on_retrieved_records_and_returns_citations(built_db_path):
    fake = FakeLLM()
    result = ask("Does the ESP32-C6 support Zigbee?", llm_client=fake, db_path=built_db_path, top_k=3)

    assert result["answer"] == fake.response_text
    assert result["used"], "should retrieve at least one record"
    assert "esp32-c6" in result["used"]
    assert result["citations"], "ask() must always return citations"
    for c in result["citations"]:
        assert set(c) == {"part", "file", "source_url"}
        assert c["source_url"].startswith("http")

    # grounding: the retrieved record's own datasheet text made it into the prompt
    assert len(fake.calls) == 1
    assert "ESP32-C6" in fake.calls[0]["user"]
    assert fake.calls[0]["temperature"] == 0


def test_ask_never_touches_network(built_db_path):
    fake = FakeLLM()
    ask("What boards support Thread?", llm_client=fake, db_path=built_db_path)
    assert len(fake.calls) == 1  # only the fake was invoked, no real client constructed


def test_ask_with_no_matching_records_skips_llm_and_says_so(built_db_path):
    fake = FakeLLM()
    result = ask("zzzznonexistentqueryterm12345", llm_client=fake, db_path=built_db_path)
    assert result["citations"] == []
    assert result["used"] == []
    assert "not in esp-atlas" in result["answer"].lower()
    assert fake.calls == []  # never called the LLM when there's nothing to ground on


def test_ask_caches_by_question_and_build_id(built_db_path):
    fake = FakeLLM()
    r1 = ask("Does the ESP32-H2 have Wi-Fi?", llm_client=fake, db_path=built_db_path)
    r2 = ask("Does the ESP32-H2 have Wi-Fi?", llm_client=fake, db_path=built_db_path)
    assert r1 == r2
    assert len(fake.calls) == 1  # second call served from cache, LLM not re-invoked


def test_ask_different_questions_are_not_conflated(built_db_path):
    fake = FakeLLM()
    ask("Is the ESP32-C3 RISC-V?", llm_client=fake, db_path=built_db_path)
    ask("Does the ESP32-P4 have a radio?", llm_client=fake, db_path=built_db_path)
    assert len(fake.calls) == 2


def test_ask_raises_without_prebuilt_index(tmp_path):
    fake = FakeLLM()
    empty_db = tmp_path / "empty.db"
    with pytest.raises(RuntimeError):
        ask("anything", llm_client=fake, db_path=empty_db)


# ---------------------------------------------------------------------------
# The recipe graph. firmware/recipe records are not in the parts table or the
# FTS index, so plain retrieval cannot see them and "which boards run Marauder?"
# used to answer "not in esp-atlas yet" while the site's own firmware page
# listed the boards. ask() gets an explicit second retrieval path instead.
# ---------------------------------------------------------------------------


def test_ask_answers_which_boards_run_a_firmware(built_db_path):
    from esp_atlas_core.firmware import recipes_for_firmware

    fake = FakeLLM("...")
    result = ask("Which boards can run ESP32 Marauder?", llm_client=fake, db_path=built_db_path)

    prompt = fake.calls[0]["user"]
    expected = recipes_for_firmware("esp32marauder")
    assert expected, "fixture assumption: Marauder must have recipes"
    for recipe in expected:
        assert recipe["board"] in prompt, f"{recipe['board']} missing from the grounding context"
        assert recipe["id"] in result["used"]
    assert "esp32marauder" in result["used"]
    # the tier of each claim must reach the model, not just the board list
    assert all(r["status"] in prompt for r in expected)


def test_ask_cites_the_firmware_record_behind_a_runs_on_answer(built_db_path):
    fake = FakeLLM("...")
    result = ask("What boards run Bruce?", llm_client=fake, db_path=built_db_path)
    urls = {c["source_url"] for c in result["citations"]}
    assert any("pr3y/Bruce" in url for url in urls), "the firmware's own source must be cited"


def test_ask_tells_the_model_what_a_retrieved_board_can_run(built_db_path):
    """The reverse view: ask about a board, learn what runs on it."""
    fake = FakeLLM("...")
    ask("Tell me about the M5Cardputer", llm_client=fake, db_path=built_db_path)
    prompt = fake.calls[0]["user"]
    assert "Firmware verified to run on" in prompt


def test_firmware_matching_ignores_generic_tokens(built_db_path):
    """'esp32' appears in nearly every question and must not match a firmware."""
    from esp_atlas_core.ask import _firmware_named_in

    assert _firmware_named_in("which esp32 board has the most PSRAM?") == []
    assert [fw["id"] for fw in _firmware_named_in("what runs Bruce")] == ["bruce"]
