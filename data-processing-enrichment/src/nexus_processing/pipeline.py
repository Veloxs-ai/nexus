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

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .chunking import chunk_text
from .config import MetadataConfig, ProcessingConfig, ProcessingJobConfig
from .enrichment import build_text, extract_metadata
from .io import read_jsonl, write_jsonl
from .models import DocumentChunk, JobMode, ProcessedRecord
from .transforms import transform_record


def run_job(config: ProcessingConfig, job_name: str, base_dir: Path) -> int:
    job = config.jobs[job_name]
    raw_records = read_jsonl(job.input_uri, base_dir)

    if job.mode == JobMode.RECORDS:
        output = process_records(job_name, job, raw_records, config.defaults.metadata)
    else:
        output = process_documents(job_name, job, raw_records, config.defaults.metadata)

    return write_jsonl(job.output_uri, base_dir, output)


def run_all(config: ProcessingConfig, base_dir: Path) -> dict[str, int]:
    return {job_name: run_job(config, job_name, base_dir) for job_name in config.jobs}


def process_records(
    job_name: str,
    job: ProcessingJobConfig,
    records: Iterable[dict],
    default_metadata: MetadataConfig,
) -> list[ProcessedRecord]:
    metadata_config = job.metadata or default_metadata
    processed: list[ProcessedRecord] = []

    for record in records:
        payload = transform_record(record, job.transformations)
        record_id = str(payload[job.primary_key])
        metadata_text = build_text(payload, job.text_fields)
        processed.append(
            ProcessedRecord(
                record_id=record_id,
                source_job=job_name,
                payload=payload,
                metadata=extract_metadata(metadata_text, metadata_config),
            )
        )

    return processed


def process_documents(
    job_name: str,
    job: ProcessingJobConfig,
    records: Iterable[dict],
    default_metadata: MetadataConfig,
) -> list[DocumentChunk]:
    if not job.document_text_field:
        raise ValueError(f"Document job {job_name} must define document_text_field")

    chunking = job.chunking
    metadata_config = job.metadata or default_metadata
    chunks: list[DocumentChunk] = []

    for record in records:
        payload = transform_record(record, job.transformations)
        document_id = str(payload[job.primary_key])
        title = str(payload.get(job.document_title_field or "", ""))
        text = str(payload[job.document_text_field])
        chunk_config = chunking
        if chunk_config is None:
            raise ValueError(f"Document job {job_name} must have chunking defaults or override")

        import hashlib

        content_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
        for index, chunk in enumerate(
            chunk_text(text, chunk_config.max_tokens, chunk_config.overlap_tokens)
        ):
            metadata_text = " ".join(value for value in [title, chunk] if value)
            metadata = extract_metadata(metadata_text, metadata_config)
            metadata["document_title"] = title
            metadata["source_primary_key"] = document_id
            metadata["content_hash"] = content_hash
            chunks.append(
                DocumentChunk(
                    chunk_id=f"{document_id}:{index}",
                    document_id=document_id,
                    source_job=job_name,
                    chunk_index=index,
                    text=chunk,
                    metadata=metadata,
                )
            )

    return chunks


def hydrate_job_defaults(config: ProcessingConfig) -> ProcessingConfig:
    for job in config.jobs.values():
        if job.chunking is None:
            job.chunking = config.defaults.chunking
        if job.metadata is None:
            job.metadata = config.defaults.metadata
    return config
