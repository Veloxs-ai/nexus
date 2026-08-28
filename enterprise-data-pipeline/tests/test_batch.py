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

from nexus_pipeline.batch import FileDropConnector, run_batch
from nexus_pipeline.integrity import CheckpointStore
from nexus_pipeline.models import IngestionMode


class FakeFileDropConnector:
    def __init__(self, source):
        self.source = source

    def read(self, checkpoint=None):
        assert checkpoint == "2026-05-06T00:00:00+00:00"
        return [
            {"id": "1", "updated_at": "2026-05-06T01:00:00Z"},
            {"id": "2", "updated_at": "2026-05-06T02:00:00Z"},
        ]


def test_run_batch_reads_checkpoint_and_writes_latest(monkeypatch, tmp_path, make_source):
    monkeypatch.setattr("nexus_pipeline.batch.FileDropConnector", FakeFileDropConnector)
    source = make_source(mode=IngestionMode.BATCH, connector="file_drop")
    checkpoint_store = CheckpointStore(str(tmp_path))
    checkpoint_store.write("finance_transactions", "2026-05-06T00:00:00+00:00")

    count = run_batch("finance_transactions", source, checkpoint_store)

    assert count == 2
    assert checkpoint_store.read("finance_transactions") == "2026-05-06T02:00:00+00:00"


def test_file_drop_connector_reads_jsonl(tmp_path, make_source):
    input_path = tmp_path / "finance_transactions.jsonl"
    input_path.write_text(
        '{"transaction_id":"t1","amount":10,"currency":"USD","posted_at":"2026-05-06T00:00:00Z"}\n',
        encoding="utf-8",
    )
    source = make_source(
        mode=IngestionMode.BATCH,
        connector="file_drop",
        primary_key="transaction_id",
        event_time_field="posted_at",
        required_fields=["transaction_id", "amount", "currency", "posted_at"],
        connection={"source_uri": str(input_path), "file_format": "jsonl"},
    )

    records = FileDropConnector(source).read()

    assert records[0]["transaction_id"] == "t1"
