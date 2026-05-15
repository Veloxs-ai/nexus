from pathlib import Path

from nexus_processing.config import load_config
from nexus_processing.models import JobMode
from nexus_processing.pipeline import hydrate_job_defaults


def test_load_config_parses_jobs_and_integration():
    config = load_config(Path("configs/processing.yaml"))

    assert config.integration.upstream_project == "../enterprise-data-pipeline"
    assert config.integration.raw_landing_contract == "jsonl"
    assert set(config.jobs) == {"customer_profiles", "policy_documents"}
    assert config.jobs["policy_documents"].mode == JobMode.DOCUMENTS


def test_hydrate_job_defaults_applies_chunking_and_metadata():
    config = hydrate_job_defaults(load_config(Path("configs/processing.yaml")))

    assert config.jobs["policy_documents"].chunking is not None
    assert config.jobs["policy_documents"].chunking.max_tokens == 80
    assert "security" in config.jobs["customer_profiles"].metadata.keyword_tags

