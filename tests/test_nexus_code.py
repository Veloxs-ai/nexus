# SPDX-License-Identifier: Apache-2.0
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

"""Integration tests for NexusClient Code AST, Polyglot, and OpenAPI processing."""

import json
import math

from nexus.client import NexusClient


def _norm(vec: list[float]) -> float:
    return math.sqrt(sum(x * x for x in vec))


def test_nexus_client_process_code_python():
    client = NexusClient(in_memory_only=True)

    py_source = """
import os

def calculate_checksum(file_path: str) -> str:
    \"\"\"Calculates cryptographic hash of given file.\"\"\"
    if not os.path.exists(file_path):
        raise FileNotFoundError(file_path)
    return "mock_hash"

class TelemetryExporter:
    \"\"\"Transmits runtime metrics to remote collector.\"\"\"
    def flush(self) -> int:
        return 0
"""
    doc = client.process_code(
        code_id="code_metrics_01",
        name="telemetry.py",
        code_input=py_source,
        language="python",
        metadata={"repo": "nexus-core"},
    )

    assert doc.document_id == "code_metrics_01"
    assert doc.file_type == "code"
    assert doc.metadata["language"] == "python"
    assert doc.metadata["repo"] == "nexus-core"
    assert doc.metadata["total_functions"] == 2
    assert doc.metadata["total_classes"] == 1
    assert len(doc.execution_trace) == 5

    # Check 5 telemetry traces
    assert doc.execution_trace[0].stage_name == "Source Code Ingestion & Format Identification"
    assert doc.execution_trace[4].stage_name == "AST-Grounded 3072D Vector Projection"

    # Verify chunks and 3072D embeddings
    assert len(doc.chunks) >= 2
    for chunk in doc.chunks:
        assert len(chunk.embedding) == 3072
        assert abs(_norm(chunk.embedding) - 1.0) < 1e-4
        assert chunk.metadata["is_code"] is True


def test_nexus_client_process_openapi():
    client = NexusClient(in_memory_only=True)

    spec = {
        "openapi": "3.1.0",
        "info": {"title": "Billing API", "version": "1.0.0"},
        "paths": {
            "/v1/invoices/{id}": {
                "get": {
                    "operationId": "getInvoice",
                    "summary": "Fetch customer invoice by ID",
                    "parameters": [{"name": "id", "in": "path", "required": True}],
                    "responses": {"200": {"description": "Invoice details"}},
                }
            }
        },
        "components": {
            "schemas": {
                "Invoice": {
                    "type": "object",
                    "properties": {"id": {"type": "string"}, "amount": {"type": "number"}},
                }
            }
        },
    }

    doc = client.process_openapi(
        spec_id="spec_billing",
        name="billing_openapi.json",
        spec_data=spec,
        metadata={"environment": "production"},
    )

    assert doc.document_id == "spec_billing"
    assert doc.file_type == "openapi"
    assert doc.metadata["total_endpoints"] == 1
    assert doc.metadata["total_schemas"] == 1
    assert len(doc.execution_trace) == 5

    for chunk in doc.chunks:
        assert len(chunk.embedding) == 3072
        assert abs(_norm(chunk.embedding) - 1.0) < 1e-4
        assert chunk.metadata["is_openapi"] is True


def test_nexus_client_process_document_routing():
    client = NexusClient(in_memory_only=True)

    # Route Python source code
    py_code = "def add(x: int, y: int) -> int:\n    return x + y\n"
    doc_py = client.process_document(
        document_id="doc_py",
        name="calculator.py",
        text=py_code,
    )
    assert doc_py.file_type == "code"
    assert doc_py.metadata["language"] == "python"
    assert len(doc_py.chunks) >= 1

    # Route TypeScript source code
    ts_code = "export function multiply(a: number, b: number): number {\n    return a * b;\n}\n"
    doc_ts = client.process_document(
        document_id="doc_ts",
        name="math.ts",
        text=ts_code,
    )
    assert doc_ts.file_type == "code"
    assert doc_ts.metadata["language"] == "typescript"

    # Route OpenAPI spec via filename
    api_spec = json.dumps(
        {
            "openapi": "3.0.0",
            "info": {"title": "Users API"},
            "paths": {
                "/users": {
                    "get": {
                        "operationId": "listUsers",
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            },
        }
    )
    doc_api = client.process_document(
        document_id="doc_api",
        name="users_openapi.json",
        text=api_spec,
    )
    assert doc_api.file_type == "openapi"
    assert doc_api.metadata["total_endpoints"] == 1
