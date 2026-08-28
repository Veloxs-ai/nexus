# Copyright 2026 Veloxs AI Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

import json

from nexus_processing.config import ChunkingConfig, ProcessingConfig, ProcessingJobConfig
from nexus_processing.models import JobMode
from nexus_processing.pipeline import (
    hydrate_job_defaults,
    process_documents,
    process_records,
    run_job,
)


def test_process_records_outputs_enriched_records(make_metadata_config):
    job = __import__("tests.conftest", fromlist=["make_record_job"]).make_record_job()

    records = process_records(
        "customer_profiles",
        job,
        [
            {
                "customer_id": "c001",
                "customer_name": " Acme ",
                "status": " ACTIVE ",
                "notes": "Renewal support request from Jane Doe.",
            }
        ],
        make_metadata_config(),
    )

    assert records[0].record_id == "c001"
    assert records[0].payload["name"] == "Acme"
    assert records[0].metadata["classification"] == "customer"


def test_process_documents_outputs_chunks_with_context(make_metadata_config):
    job = ProcessingJobConfig(
        mode=JobMode.DOCUMENTS,
        input_uri="input.jsonl",
        output_uri="output.jsonl",
        primary_key="document_id",
        document_text_field="body",
        document_title_field="title",
        text_fields=["title", "body"],
        chunking=ChunkingConfig(max_tokens=5, overlap_tokens=1),
    )

    chunks = process_documents(
        "policy_documents",
        job,
        [
            {
                "document_id": "doc-001",
                "title": "Security Policy",
                "body": "MFA access review encryption policy exception workflow",
            }
        ],
        make_metadata_config(),
    )

    assert [chunk.chunk_id for chunk in chunks] == ["doc-001:0", "doc-001:1"]
    assert chunks[0].metadata["document_title"] == "Security Policy"
    assert chunks[0].metadata["classification"] == "security"


def test_run_job_reads_and_writes_jsonl(tmp_path, make_metadata_config):
    input_path = tmp_path / "raw.jsonl"
    input_path.write_text(
        json.dumps(
            {
                "customer_id": "c001",
                "customer_name": " Acme ",
                "status": " ACTIVE ",
                "notes": "Renewal support request.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    config = ProcessingConfig(
        defaults={"metadata": make_metadata_config()},
        jobs={
            "customer_profiles": __import__(
                "tests.conftest", fromlist=["make_record_job"]
            ).make_record_job()
        },
    )
    config.jobs["customer_profiles"].input_uri = "raw.jsonl"
    config.jobs["customer_profiles"].output_uri = "processed.jsonl"

    count = run_job(hydrate_job_defaults(config), "customer_profiles", tmp_path)

    assert count == 1
    output = json.loads((tmp_path / "processed.jsonl").read_text(encoding="utf-8"))
    assert output["record_id"] == "c001"
    assert output["payload"]["status"] == "active"
