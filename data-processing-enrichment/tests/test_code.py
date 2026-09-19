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

"""Tests for pure-Python Code AST, Polyglot, and OpenAPI Specification Processing."""

import math

from nexus_processing.code import (
    process_code,
    process_openapi_spec,
    process_polyglot_source,
    process_python_source,
)


def _vec_norm(vec: list[float]) -> float:
    return math.sqrt(sum(x * x for x in vec))


def test_python_ast_processing():
    py_code = '''"""Module docstring for test sample."""

import math
from typing import Optional

def compute_tax(amount: float, rate: float = 0.05) -> float:
    """Calculates tax with given percentage rate."""
    if amount <= 0:
        return 0.0
    return amount * rate

class AccountManager:
    """Manages customer billing and account balances."""

    def __init__(self, owner: str):
        self.owner = owner
        self.balance = 0.0

    async def transfer(self, target: str, amount: float) -> bool:
        """Asynchronously transfers funds to another target account."""
        if amount > self.balance:
            return False
        self.balance -= amount
        return True
'''
    payload = process_python_source(py_code, file_name="accounts.py")

    assert payload.metadata.language == "python"
    assert payload.metadata.format == "python_ast"
    assert payload.metadata.total_classes == 1
    assert payload.metadata.total_functions == 3  # compute_tax, __init__, transfer
    assert "math" in payload.metadata.imports
    assert "typing.Optional" in payload.metadata.imports

    symbols = {s.name: s for s in payload.symbols}
    assert "compute_tax" in symbols
    assert "AccountManager" in symbols
    assert "AccountManager.__init__" in symbols
    assert "AccountManager.transfer" in symbols

    tax_sym = symbols["compute_tax"]
    assert tax_sym.symbol_type == "function"
    assert "amount: float" in tax_sym.signature
    assert "rate: float" in tax_sym.signature
    assert "-> float" in tax_sym.signature
    assert tax_sym.start_line == 6
    assert tax_sym.end_line == 10

    transfer_sym = symbols["AccountManager.transfer"]
    assert transfer_sym.symbol_type == "method"
    assert "async def transfer" in transfer_sym.signature
    assert transfer_sym.parent_scope == "AccountManager"

    # Verify vector embeddings
    for chunk in payload.chunks:
        assert len(chunk.embedding) == 3072
        assert abs(_vec_norm(chunk.embedding) - 1.0) < 1e-4
        assert chunk.file_name == "accounts.py"
        assert "[Code AST: accounts.py" in chunk.narrative_text


def test_python_ast_syntax_error_fallback():
    broken_code = "def broken( x y z { return 1"
    payload = process_python_source(broken_code, file_name="broken.py")

    assert payload.metadata.format == "python_ast"
    assert len(payload.chunks) == 1
    assert payload.chunks[0].symbol_type == "snippet"
    assert len(payload.chunks[0].embedding) == 3072
    assert abs(_vec_norm(payload.chunks[0].embedding) - 1.0) < 1e-4


def test_polyglot_typescript_and_go():
    # TypeScript
    ts_code = """
/**
 * Processes authentication token
 */
export async function authenticateUser(token: string, refresh: boolean): Promise<User> {
    if (!token) {
        throw new Error("Missing token");
    }
    return fetchUser(token);
}

export class OrderService {
    cancelOrder(orderId: string): void {
        this.orders.delete(orderId);
    }
}
"""
    ts_payload = process_polyglot_source(ts_code, file_name="auth.ts", language="typescript")
    assert ts_payload.metadata.language == "typescript"
    assert ts_payload.metadata.total_functions >= 1
    assert any(s.name == "authenticateUser" for s in ts_payload.symbols)
    assert any(s.name == "OrderService" for s in ts_payload.symbols)

    for chunk in ts_payload.chunks:
        assert len(chunk.embedding) == 3072
        assert abs(_vec_norm(chunk.embedding) - 1.0) < 1e-4

    # Go
    go_code = """
package main

// CalculateDiscount applies seasonal discount
func CalculateDiscount(price float64, code string) float64 {
    if code == "SUMMER" {
        return price * 0.8
    }
    return price
}

type CustomerProfile struct {
    ID   int
    Name string
}
"""
    go_payload = process_polyglot_source(go_code, file_name="discount.go", language="go")
    assert go_payload.metadata.language == "go"
    assert any(s.name == "CalculateDiscount" for s in go_payload.symbols)
    assert any(s.name == "CustomerProfile" for s in go_payload.symbols)


def test_openapi_specification_processing():
    openapi_spec = {
        "openapi": "3.0.3",
        "info": {
            "title": "Nexus Gateway API",
            "version": "2.4.0",
            "description": "Enterprise intelligence platform endpoints.",
        },
        "paths": {
            "/api/v1/query": {
                "post": {
                    "operationId": "submitQuery",
                    "summary": "Submits semantic vector query",
                    "description": "Performs cross-modal grounded vector search.",
                    "tags": ["intelligence", "search"],
                    "parameters": [
                        {
                            "name": "dry_run",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "boolean"},
                        }
                    ],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/QueryRequest"}
                            }
                        }
                    },
                    "responses": {
                        "200": {"description": "Successful vector search results."},
                        "400": {"description": "Invalid query payload."},
                    },
                }
            }
        },
        "components": {
            "schemas": {
                "QueryRequest": {
                    "type": "object",
                    "description": "Input payload for semantic retrieval",
                    "required": ["prompt"],
                    "properties": {
                        "prompt": {"type": "string"},
                        "top_k": {"type": "integer"},
                        "min_score": {"type": "number"},
                    },
                }
            }
        },
    }

    payload = process_openapi_spec(openapi_spec, file_name="gateway.json")

    assert payload.metadata.format == "openapi_spec"
    assert payload.metadata.total_endpoints == 1
    assert payload.metadata.total_classes == 1  # 1 schema model

    endpoint_chunks = [c for c in payload.chunks if c.symbol_type == "endpoint"]
    schema_chunks = [c for c in payload.chunks if c.symbol_type == "schema"]

    assert len(endpoint_chunks) == 1
    assert len(schema_chunks) == 1

    ep = endpoint_chunks[0]
    assert ep.symbol_name == "submitQuery"
    assert ep.signature == "POST /api/v1/query"
    assert "dry_run" in ep.narrative_text
    assert len(ep.embedding) == 3072
    assert abs(_vec_norm(ep.embedding) - 1.0) < 1e-4

    model = schema_chunks[0]
    assert model.symbol_name == "QueryRequest"
    assert "prompt: string (required)" in model.narrative_text
    assert len(model.embedding) == 3072
    assert abs(_vec_norm(model.embedding) - 1.0) < 1e-4


def test_process_code_generic_dispatcher():
    # Dispatch Python bytes
    raw_py = b"def greet(name: str) -> str:\n    return 'Hello ' + name\n"
    res = process_code(raw_py, file_name="greet.py")
    assert res.metadata.language == "python"
    assert len(res.chunks) == 1
    assert res.chunks[0].symbol_name == "greet"

    # Dispatch Rust
    rs_code = "pub fn add(a: i32, b: i32) -> i32 {\n    a + b\n}\n"
    res_rs = process_code(rs_code, file_name="math.rs")
    assert res_rs.metadata.language == "rust"
    assert any(s.name == "add" for s in res_rs.symbols)
