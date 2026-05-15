from typer.testing import CliRunner

from nexus.cli import app


runner = CliRunner()


def test_validate_config_command():
    result = runner.invoke(app, ["validate-config", "configs/nexus.yaml"])

    assert result.exit_code == 0
    assert "Loaded 7 layers." in result.output


def test_validate_platform_command():
    result = runner.invoke(app, ["validate-platform", "configs/nexus.yaml"])

    assert result.exit_code == 0
    assert "platform_ready: true" in result.output


def test_prepare_demo_command(monkeypatch):
    outputs = ["Processed 2 outputs for customer_profiles.\n", "Indexed 4 documents.\n"]

    def fake_prepare_demo(self):
        return outputs

    monkeypatch.setattr("nexus.platform.NexusPlatform.prepare_demo", fake_prepare_demo)
    result = runner.invoke(app, ["prepare-demo", "configs/nexus.yaml"])

    assert result.exit_code == 0
    assert "Indexed 4 documents." in result.output
