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

"""OpenAPI / Swagger specifications (JSON or YAML) to path, operation and schema chunks."""

from __future__ import annotations

import json
from typing import Any

from .code_model import CodeChunk, CodeMetadata, CodeProcessingPayload, CodeSymbol


def process_openapi_spec(
    spec_data: str | dict[str, Any],
    file_name: str = "openapi.json",
) -> CodeProcessingPayload:
    """Parses OpenAPI 3.0 / 3.1 or Swagger 2.0 specifications into semantic chunks."""
    if isinstance(spec_data, str):
        try:
            doc = json.loads(spec_data)
        except json.JSONDecodeError:
            # Try YAML parsing if pyyaml is available
            try:
                import yaml

                doc = yaml.safe_load(spec_data)
                if not isinstance(doc, dict):
                    doc = {"info": {"title": file_name}, "paths": {}}
            except ImportError:
                # Fallback: try to detect YAML structure via basic parsing
                doc = {"info": {"title": file_name}, "paths": {}}
            except Exception:
                doc = {"info": {"title": file_name}, "paths": {}}
    elif isinstance(spec_data, dict):
        doc = spec_data
    else:
        raise ValueError("spec_data must be JSON string or parsed dict")

    info = doc.get("info", {})
    api_title = info.get("title", file_name)
    api_version = info.get("version", "1.0.0")

    symbols: list[CodeSymbol] = []
    chunks: list[CodeChunk] = []

    paths = doc.get("paths", {})
    http_methods = {"get", "post", "put", "delete", "patch", "head", "options", "trace"}

    total_endpoints = 0

    for path_str, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method, op in path_item.items():
            if method.lower() not in http_methods or not isinstance(op, dict):
                continue

            total_endpoints += 1
            op_id = op.get("operationId") or f"{method.upper()}_{path_str}"
            summary = op.get("summary", "")
            description = op.get("description", "")
            tags = op.get("tags", [])

            # Introspect parameters
            raw_params = op.get("parameters", [])
            param_labels: list[str] = []
            for p in raw_params:
                if isinstance(p, dict):
                    p_name = p.get("name", "")
                    p_in = p.get("in", "query")
                    p_req = "required" if p.get("required") else "optional"
                    p_type = p.get("schema", {}).get("type", "string")
                    param_labels.append(f"{p_name} ({p_in}, {p_type}, {p_req})")

            # Introspect requestBody
            req_body_label = ""
            rb = op.get("requestBody")
            if isinstance(rb, dict):
                content = rb.get("content", {})
                req_types = list(content.keys())
                req_body_label = f"Body: {', '.join(req_types)}"

            # Introspect responses
            responses = op.get("responses", {})
            resp_labels: list[str] = []
            for code, r_data in responses.items():
                if isinstance(r_data, dict):
                    r_desc = r_data.get("description", "")
                    resp_labels.append(f"{code}: {r_desc}")

            sig = f"{method.upper()} {path_str}"

            narrative = (
                f"[OpenAPI: {api_title} v{api_version} | Operation: {op_id} | {sig}]\n"
                f"Summary: {summary}\n"
            )
            if description:
                narrative += f"Description: {description}\n"
            if tags:
                narrative += f"Tags: {', '.join(tags)}\n"
            if param_labels:
                narrative += f"Parameters: {', '.join(param_labels)}\n"
            if req_body_label:
                narrative += f"{req_body_label}\n"
            if resp_labels:
                narrative += f"Responses: {', '.join(resp_labels)}\n"

            body_json = json.dumps(op, indent=2)

            sym = CodeSymbol(
                name=op_id,
                symbol_type="endpoint",
                language="openapi",
                signature=sig,
                start_line=1,
                end_line=1,
                docstring=summary or description,
                parameters=param_labels,
            )
            symbols.append(sym)

            chunks.append(
                CodeChunk(
                    chunk_id=f"{api_title}_{op_id}",
                    symbol_name=op_id,
                    symbol_type="endpoint",
                    language="openapi",
                    file_name=file_name,
                    start_line=1,
                    end_line=1,
                    signature=sig,
                    docstring=summary or description,
                    body_text=body_json,
                    narrative_text=narrative,
                    metadata={
                        "path": path_str,
                        "method": method.upper(),
                        "tags": tags,
                        "operation_id": op_id,
                    },
                )
            )

    # Introspect schemas (OpenAPI 3 components.schemas or Swagger 2 definitions)
    schemas = doc.get("components", {}).get("schemas", {}) or doc.get("definitions", {})
    total_schemas = 0
    if isinstance(schemas, dict):
        for s_name, s_def in schemas.items():
            if not isinstance(s_def, dict):
                continue
            total_schemas += 1
            s_type = s_def.get("type", "object")
            props = s_def.get("properties", {})
            req_fields = s_def.get("required", [])

            prop_summaries: list[str] = []
            for p_name, p_schema in props.items():
                if isinstance(p_schema, dict):
                    ptype = p_schema.get("type", "any")
                    req_mark = " (required)" if p_name in req_fields else ""
                    prop_summaries.append(f"{p_name}: {ptype}{req_mark}")

            s_sig = f"model {s_name} ({s_type})"
            s_desc = s_def.get("description", "")
            narrative = f"[OpenAPI: {api_title} | Model Schema: {s_name}]\nType: {s_type}\n"
            if s_desc:
                narrative += f"Description: {s_desc}\n"
            if prop_summaries:
                narrative += f"Properties: {', '.join(prop_summaries)}\n"

            sym = CodeSymbol(
                name=s_name,
                symbol_type="schema",
                language="openapi",
                signature=s_sig,
                start_line=1,
                end_line=1,
                docstring=s_desc,
            )
            symbols.append(sym)

            chunks.append(
                CodeChunk(
                    chunk_id=f"{api_title}_schema_{s_name}",
                    symbol_name=s_name,
                    symbol_type="schema",
                    language="openapi",
                    file_name=file_name,
                    start_line=1,
                    end_line=1,
                    signature=s_sig,
                    docstring=s_desc,
                    body_text=json.dumps(s_def, indent=2),
                    narrative_text=narrative,
                    metadata={"model_name": s_name, "required": req_fields},
                )
            )

    meta = CodeMetadata(
        file_name=file_name,
        language="openapi",
        format="openapi_spec",
        total_lines=len(json.dumps(doc, indent=2).splitlines()),
        total_symbols=len(symbols),
        total_functions=total_endpoints,
        total_classes=total_schemas,
        total_endpoints=total_endpoints,
    )
    return CodeProcessingPayload(metadata=meta, chunks=chunks, symbols=symbols)
