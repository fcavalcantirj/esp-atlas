from click.testing import CliRunner

from esp_atlas_cli.main import cli
import esp_atlas_cli.main as main_module


def run(args, db_path, input=None):
    runner = CliRunner()
    return runner.invoke(cli, ["--db", str(db_path), *args], input=input)


def test_build_index_command(tmp_path):
    db_path = tmp_path / "fresh.db"
    result = run(["build-index"], db_path)
    assert result.exit_code == 0, result.output
    assert "Built esp-atlas.db" in result.output
    assert db_path.exists()


def test_search_command_finds_zigbee_parts(built_db_path):
    result = run(["search", "zigbee"], built_db_path)
    assert result.exit_code == 0, result.output
    assert "esp32-c6" in result.output


def test_search_command_with_filters(built_db_path):
    result = run(["search", "", "--form", "xiao"], built_db_path)
    assert result.exit_code == 0, result.output
    assert "xiao-esp32c6" in result.output
    assert "[board]" in result.output


def test_search_command_no_matches(built_db_path):
    result = run(["search", "zzzznonexistentqueryterm12345"], built_db_path)
    assert result.exit_code == 0
    assert "No matches" in result.output


def test_search_command_rejects_bad_filter_gracefully(built_db_path):
    result = run(["search", "wifi", "--type", "bogus"], built_db_path)
    assert result.exit_code != 0


def test_wizard_command_with_flags(built_db_path):
    result = run(["wizard", "--protocol", "zigbee", "--no-guided"], built_db_path)
    assert result.exit_code == 0, result.output
    assert "esp32-c6" in result.output
    assert "score" in result.output.lower()


def test_wizard_command_guided_prompts(built_db_path):
    # blank answers to every prompt except a protocol
    result = run(["wizard"], built_db_path, input="zigbee\n\n\n\n\n")
    assert result.exit_code == 0, result.output
    assert "esp32-c6" in result.output or "esp32-h2" in result.output


def test_ask_command_shows_answer_and_citations(built_db_path, monkeypatch):
    def fake_ask(question, llm_client=None, db_path=None, top_k=5):
        return {
            "answer": "The ESP32-C6 supports Wi-Fi 6.",
            "citations": [
                {"part": "ESP32-C6", "file": "data/socs/esp32-c6/chip.md", "source_url": "https://example.com/c6.pdf"}
            ],
            "used": ["esp32-c6"],
        }

    monkeypatch.setattr(main_module, "core_ask", fake_ask)
    result = run(["ask", "Does the ESP32-C6 support Wi-Fi 6?"], built_db_path)
    assert result.exit_code == 0, result.output
    assert "Wi-Fi 6" in result.output
    assert "https://example.com/c6.pdf" in result.output


def test_ask_command_never_calls_real_groq_client(built_db_path, monkeypatch):
    calls = []

    def fake_ask(question, llm_client=None, db_path=None, top_k=5):
        calls.append(question)
        return {"answer": "no network used", "citations": [], "used": []}

    monkeypatch.setattr(main_module, "core_ask", fake_ask)
    result = run(["ask", "anything"], built_db_path)
    assert result.exit_code == 0
    assert calls == ["anything"]


def test_ask_command_surfaces_rate_limit_error(built_db_path, monkeypatch):
    from esp_atlas_core.llm import GroqRateLimitError

    def fake_ask(question, llm_client=None, db_path=None, top_k=5):
        raise GroqRateLimitError("rate limited")

    monkeypatch.setattr(main_module, "core_ask", fake_ask)
    result = run(["ask", "anything"], built_db_path)
    assert result.exit_code != 0
    assert "rate limited" in result.output.lower()


def test_search_command_all_filters(built_db_path):
    result = run(
        ["search", "", "--radio", "wifi-6", "--band", "2.4", "--protocol", "zigbee", "--type", "soc"],
        built_db_path,
    )
    assert result.exit_code == 0, result.output
    assert "esp32-c6" in result.output


def test_wizard_command_all_flags(built_db_path):
    result = run(
        [
            "wizard", "--protocol", "zigbee", "--radio", "wifi-6", "--band", "2.4",
            "--usb-native", "--form", "xiao", "--type", "board", "--budget", "low", "--no-guided",
        ],
        built_db_path,
    )
    assert result.exit_code == 0, result.output
    assert "xiao-esp32c6" in result.output
    assert "budget" in result.output.lower()


def test_wizard_command_no_matches(built_db_path):
    result = run(["wizard", "--form", "nonexistent-form-factor", "--no-guided"], built_db_path)
    assert result.exit_code == 0
    assert "No matches" in result.output


def test_wizard_command_guided_all_answers(built_db_path):
    result = run(["wizard"], built_db_path, input="zigbee\nwifi-6\ny\nxiao\nlow\n")
    assert result.exit_code == 0, result.output


def test_main_entry_point_runs(built_db_path, monkeypatch):
    monkeypatch.setattr("sys.argv", ["esp-atlas", "--db", str(built_db_path), "search", "zigbee"])
    import pytest

    with pytest.raises(SystemExit) as exc_info:
        main_module.main()
    assert exc_info.value.code == 0
