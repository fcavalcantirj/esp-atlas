from click.testing import CliRunner

from esp_atlas_core.paths import REPO_ROOT

from esp_atlas_cli.main import cli
import esp_atlas_cli.main as main_module

SOC_PATH = REPO_ROOT / "data" / "socs" / "esp32-c6" / "chip.md"
BOARD_PATH = REPO_ROOT / "data" / "boards" / "espressif" / "esp32-c6-devkitc-1" / "board.md"


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


def test_search_command_band_5_finds_esp32_c5(built_db_path):
    # --band is a click float option, so "5" arrives at the core as 5.0 (regression: used to
    # stringify to "5.0" and never match the stored "5" token in wifi_bands).
    result = run(["search", "", "--band", "5"], built_db_path)
    assert result.exit_code == 0, result.output
    assert "esp32-c5" in result.output


def test_search_command_band_2_4_still_finds_2_4ghz_parts(built_db_path):
    result = run(["search", "", "--band", "2.4"], built_db_path)
    assert result.exit_code == 0, result.output
    assert "esp32-s3" in result.output


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
            "--usb-native", "--form", "xiao", "--type", "board", "--budget", "cheap", "--no-guided",
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
    result = run(["wizard"], built_db_path, input="zigbee\nwifi-6\ny\nxiao\ncheap\n")
    assert result.exit_code == 0, result.output


def test_validate_command_valid_file_passes(built_db_path):
    result = run(["validate", str(SOC_PATH)], built_db_path)
    assert result.exit_code == 0, result.output
    assert "PASS" in result.output
    assert "1/1 valid, 0 error(s)" in result.output


def test_validate_command_invalid_file_fails(built_db_path, tmp_path):
    bad_dir = tmp_path / "socs" / "esp32-c6"
    bad_dir.mkdir(parents=True)
    text = SOC_PATH.read_text(encoding="utf-8")
    bad_text = text.replace("sources:", "not_sources:")
    bad_path = bad_dir / "chip.md"
    bad_path.write_text(bad_text, encoding="utf-8")

    result = run(["validate", str(bad_path)], built_db_path)
    assert result.exit_code != 0
    assert "FAIL" in result.output
    assert "0/1 valid, 1 error(s)" in result.output


def test_validate_command_stdin_reads_full_document(built_db_path):
    text = BOARD_PATH.read_text(encoding="utf-8")
    result = run(["validate", "-"], built_db_path, input=text)
    assert result.exit_code == 0, result.output
    assert "PASS  <stdin>" in result.output


def test_validate_command_multiple_paths_reports_each(built_db_path, tmp_path):
    bad_dir = tmp_path / "socs" / "esp32-c6"
    bad_dir.mkdir(parents=True)
    bad_text = SOC_PATH.read_text(encoding="utf-8").replace("sources:", "not_sources:")
    bad_path = bad_dir / "chip.md"
    bad_path.write_text(bad_text, encoding="utf-8")

    result = run(["validate", str(SOC_PATH), str(bad_path)], built_db_path)
    assert result.exit_code != 0
    assert "1/2 valid, 1 error(s)" in result.output


def test_validate_command_missing_file_reports_error_not_crash(built_db_path, tmp_path):
    missing = tmp_path / "does-not-exist.md"
    result = run(["validate", str(missing)], built_db_path)
    assert result.exit_code != 0
    assert "FAIL" in result.output


def test_main_entry_point_runs(built_db_path, monkeypatch):
    monkeypatch.setattr("sys.argv", ["esp-atlas", "--db", str(built_db_path), "search", "zigbee"])
    import pytest

    with pytest.raises(SystemExit) as exc_info:
        main_module.main()
    assert exc_info.value.code == 0


def test_search_command_brand_filter(built_db_path):
    result = run(["search", "", "--brand", "adafruit", "--type", "board"], built_db_path)
    assert result.exit_code == 0, result.output
    assert "adafruit-feather-esp32-s3" in result.output
    assert "xiao-esp32c6" not in result.output
    assert "m5stack" not in result.output


def test_search_command_soc_filter(built_db_path):
    result = run(["search", "", "--soc", "esp32-c6", "--type", "board"], built_db_path)
    assert result.exit_code == 0, result.output
    assert "xiao-esp32c6" in result.output
    assert "esp32-c6-wroom-1" not in result.output
    assert "xiao-esp32c3" not in result.output
