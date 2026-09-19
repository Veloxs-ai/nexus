# Nexus: Upcoming Feature Implementation Roadmap

This document outlines upcoming feature implementations, architecture designs, and data processing capabilities planned for the **Nexus Enterprise Intelligence Platform**. Open source contributors are invited to review specifications, claim features, and submit pull requests following our strict zero-dependency and 3072D vector normalization standards.

---

## 📋 General Architectural Constraints for All New Features
1. **Zero External Dependencies**: All core processing engines must rely exclusively on Python standard library modules (e.g. `zipfile`, `tarfile`, `struct`, `xml.etree.ElementTree`, `json`, `math`, `hashlib`, `ast`, `io`).
2. **Unified 3072D Vector Projections**: All generated chunks must project into normalized 3072-dimensional vector space with exact IEEE 754 $L_2$ unit normalization ($\|V\|_2 = 1.0$).
3. **5-Stage Execution Telemetry**: Every processing method must emit structured `ProcessingStageTrace` events with millisecond-accurate benchmarks, summaries, and stage details.
4. **Safety & Governance Guardrails**: All extracted narratives must integrate with `GuardrailsEngine` for automated PII masking and secret scrubbing before vector embedding.
5. **Format-Aware Grounded Citations**: All chunks must provide structured human-readable source citations (e.g. `[Archive: bundle.zip | File: docs/report.pdf | Page: 2]`).

---

## 🚀 Upcoming Features Under Active Design

### 1. Multi-File Archive Ingestion Pipelines (`.zip`, `.tar`, `.tar.gz`, `.tar.bz2`, `.tar.xz`)
* **Status**: **Pending Implementation**
* **Technical Lead / Target Milestone**: v0.2.0
* **Target Modalities**: Compressed archives containing mixed document collections.
* **Standard Library Modules**: `zipfile`, `tarfile`, `gzip`, `bz2`, `lzma`, `pathlib`, `os`.

#### Core Capabilities:
- **Security & Hazard Mitigation**:
  - **Zip Slip Protection**: Sanitizes archive member paths against directory traversal attacks (`../` or leading `/`). Rejects or normalizes paths attempting to escape target base directory.
  - **Compression Bomb (Zip Bomb) Guard**: Imposes strict expansion ratios (default max 100:1) and total uncompressed byte limits to prevent denial-of-service memory exhaustion.
- **Hierarchical Manifest & Topology Extraction**:
  - Generates comprehensive file manifests: path hierarchies, MIME classifications, uncompressed byte sizes, and CRC32/MD5 checksums.
- **Recursive Multi-Modal Dispatching**:
  - Unpacks files into memory buffers and automatically routes each file to its respective Nexus processor:
    - `.docx` $\to$ Word Document Engine
    - `.xlsx`, `.pptx` $\to$ Office OpenXML Engine
    - `.pdf` $\to$ ISO 32000-1 PDF Engine
    - `.wav`, `.mp3`, `.aiff` $\to$ Spatio-Acoustic Audio Engine
    - `.sqlite`, `.db` $\to$ Embedded SQLite Engine
    - `.py`, `.ts`, `.go`, `.rs` $\to$ Code AST Engine
    - `.openapi.json` $\to$ OpenAPI Engine
    - `.csv`, `.md`, `.txt`, `.json` $\to$ Universal Chunker
- **Unified Archive Payload (`ArchivePayload`)**:
  - Aggregates processed document chunks into a single searchable document collection with cross-file citations:
    `[Archive: project_release.tar.gz | Member: src/auth.py | Function: login | Lines: 12-25]`
- **Client API**:
  ```python
  payload = client.process_archive(
      archive_id="release_bundle_v1",
      name="release_v1.tar.gz",
      archive_bytes=raw_tar_bytes,
      max_total_bytes=100 * 1024 * 1024,
  )
  ```

---

### 2. Redis RESP Wire Protocol & Real-Time Key-Value Stream Ingestion
* **Status**: **Pending Implementation**
* **Technical Lead / Target Milestone**: v0.2.0
* **Target Modalities**: Real-time Redis cache dumps, RESP2/RESP3 wire streams, Pub/Sub message logs.
* **Standard Library Modules**: `io`, `struct`, `json`, `datetime`.

#### Core Capabilities:
- **Zero-Dependency RESP2 / RESP3 Frame Decoder**:
  - Parses Redis wire protocol data types natively:
    - Simple Strings (`+OK\r\n`)
    - Simple Errors (`-Error message\r\n`)
    - Integers (`:1000\r\n`)
    - Bulk Strings (`$6\r\nfoobar\r\n`)
    - Arrays (`*2\r\n...`)
    - Null values (`$-1\r\n`, `*-1\r\n`)
    - RESP3 Maps (`%2\r\n...`), Sets (`~3\r\n...`), and Booleans (`#t\r\n`, `#f\r\n`).
- **In-Memory Cache & Session State Indexing**:
  - Transforms cached user sessions, shopping carts, feature flags, and conversational memory states into structured, vector-projected chunks.
- **Pub/Sub Event Log Chunking**:
  - Formats channel events with temporal timestamps:
    `[Redis: cluster-cache | Channel: user:events | Key: session:usr_9921] Action: checkout | Total: $149.50`
- **Client API**:
  ```python
  payload = client.process_redis_stream(
      stream_id="redis_events_01",
      name="cache_dump.resp",
      stream_bytes=resp_wire_bytes,
  )
  ```

---

### 3. OpenDocument Text (`.odt`) & OpenDocument Spreadsheet (`.ods`)
* **Status**: **Pending Implementation**
* **Technical Lead / Target Milestone**: v0.2.1
* **Target Modalities**: OASIS OpenDocument format files (LibreOffice, Apache OpenOffice).
* **Standard Library Modules**: `zipfile`, `xml.etree.ElementTree`.

#### Core Capabilities:
- Extracts `content.xml` and `meta.xml`.
- Parses heading styles (`text:h text:outline-level="1"`), paragraph text (`text:p`), and tables (`table:table`, `table:table-row`, `table:table-cell`).
- Unifies styling and table formatting with Nexus Office representations.

---

### 4. Apache Parquet & Arrow Columnar File Ingestion (Zero-Dependency)
* **Status**: **Pending Research**
* **Technical Lead / Target Milestone**: v0.2.2
* **Target Modalities**: Big data columnar storage formats (`.parquet`).
* **Standard Library Modules**: `struct`, `io`, `zlib`.

#### Core Capabilities:
- Pure-Python binary Thrift header parser and dictionary page decoder for uncompressed and Snappy/Gzip compressed Parquet column chunks.
- Row group batched serialization into tabular vector narratives.

---

## 🤝 How to Contribute
1. Review the open issues and architectural guidelines above.
2. Check existing implementations in `data-processing-enrichment/src/nexus_processing/` (e.g. `office.py`, `code.py`, `sqlite.py`, `audio.py`) for reference designs.
3. Write unit tests with 100% assertion coverage under `data-processing-enrichment/tests/` and integration tests under `tests/`.
4. Ensure all vectors pass exact $L_2$ unit normalization ($\|V\|_2 = 1.0$).
5. Run `ruff check .` and `ruff format --check .` before submitting PRs.
