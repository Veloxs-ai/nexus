from typer.testing import CliRunner

from nexus_experience.cli import app


runner = CliRunner()


def test_validate_config_command_loads_channels():
    result = runner.invoke(app, ["validate-config", "configs/engagement.yaml"])

    assert result.exit_code == 0
    assert "Loaded 6 channels for tenant default." in result.output


def test_ask_command_with_mock_config(tmp_path):
    config_path = tmp_path / "engagement.yaml"
    config_path.write_text(
        """
tenant:
  id: cli-test
integration:
  mode: mock
channels:
  assistant:
    type: assistant
    enabled: true
    allowed_capabilities:
      - ask
      - session
""",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["ask", str(config_path), "What is MFA?", "--channel", "assistant"])

    assert result.exit_code == 0
    assert "decision: allowed" in result.output
    assert "citation: mock:mock-source:1.000" in result.output


def test_start_session_command(tmp_path):
    config_path = tmp_path / "engagement.yaml"
    config_path.write_text(
        """
tenant:
  id: cli-test
integration:
  mode: mock
assistant:
  greeting: Hello there
channels:
  assistant:
    type: assistant
    enabled: true
    allowed_capabilities:
      - ask
      - session
""",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["start-session", str(config_path), "--user-id", "u1"])

    assert result.exit_code == 0
    assert "greeting: Hello there" in result.output

