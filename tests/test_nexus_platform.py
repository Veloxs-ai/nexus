from pathlib import Path

from nexus.platform import NexusPlatform


def test_platform_validates_layer_contracts():
    platform = NexusPlatform.from_config(Path("configs/nexus.yaml"))

    statuses = platform.layer_statuses()

    assert len(statuses) == 7
    assert all(status.ready for status in statuses)


def test_platform_resolves_relative_paths():
    platform = NexusPlatform.from_config(Path("configs/nexus.yaml"))

    assert platform.resolve("enterprise-data-pipeline").name == "enterprise-data-pipeline"

