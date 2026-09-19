# Data Processing & Enrichment Layer

> Part of **[Nexus — Enterprise Intelligence Framework](../README.md)**, the open-source framework for secure, governed AI applications.
> This layer provides the **Processing & Enrichment** capability.

Transforms raw, ingested data into structured, standardized, and AI-ready formats. This layer features native, **zero-dependency binary and text decoders** for office documents, media streams, source code, databases, and structured records, preparing content for downstream 3072D vector embedding with grounded citations.

---

## 🛠️ Capabilities

- **Office Documents (`nexus_processing.office`)**:
  - **Word (`.docx`)**: OpenXML archive decompression, heading hierarchy (`Heading1..6`), paragraph ordering, bullet lists, and markdown tables.
  - **Excel (`.xlsx`)**: Shared string table resolution, multi-sheet cell matrices, formula handling, and row-level grounded narratives.
  - **PowerPoint (`.pptx`)**: Slide shape graph extraction, text boxes, and speaker notes resolution.
- **Documents & Text (`nexus_processing.pdf`, `nexus_processing.chunking`)**:
  - **PDF (`.pdf`)**: ISO 32000-1 object graph parser, FlateDecode decompression, font encoding resolution, and page-grounded citations (`[Page N]`).
  - **CSV (`.csv`)**: Tabular row narrative serialization (`[Row ID: x] col: val | ...`), preserving column-value relationships.
  - **Markdown (`.md`) & Text (`.txt`)**: Paragraph (`\n\n`) and sentence (`. `) boundary splitting to prevent severed sentences.
  - **JSON (`.json`, `.jsonl`)**: Structural object and array serialization.
- **Audio & Speech (`nexus_processing.audio`)**:
  - Python 3.13-safe decoders for WAV, AIFF, and MP3 ID3 metadata.
  - Acoustic signal metrics: RMS Loudness, Zero-Crossing Rate (ZCR), Voice Activity Detection (VAD).
  - 7-band spectral decomposition (Sub-bass to Brilliance: 20Hz–20kHz), spectral centroid, and temporal window framing (`[00:00 - 00:10]`).
- **Video & Computer Vision (`nexus_processing.media`)**:
  - **Video (`.mp4`, `.mov`)**: ISO BMFF box parser, temporal scene chunking, and motion variance.
  - **Images (`.png`, `.jpeg`, `.bmp`)**: 8×8 luminance grid, 64-bin RGB color distribution, and 64-bit dHash perceptual hashing.
- **Source Code AST & OpenAPI (`nexus_processing.code`)**:
  - **Python AST (`.py`)**: Standard library `ast` parsing, class/function hierarchy, decorators, typed signatures, and cyclomatic complexity.
  - **Polyglot Code (`.ts`, `.js`, `.go`, `.rs`, `.java`, `.cpp`, `.cs`)**: Deterministic regex scanners for function/class extraction.
  - **OpenAPI 3.0 / 3.1 & Swagger 2.0**: Operation routes, parameters, request bodies, and schema model extraction.
- **Databases & Messaging (`nexus_processing.sqlite`, `nexus_processing.mysql`, `nexus_processing.mongodb`, `nexus_processing.email_chat`)**:
  - **SQLite (`.db`, `.sqlite`)**: Binary SQLite header parsing, page decoding, and table extraction.
  - **MySQL**: Relational row serialization and CDC binlog change event normalizer.
  - **MongoDB**: BSON document deserialization and dot-notation document flattener.
  - **Email (`.eml`) & Chat (`slack`, `teams`)**: Multipart MIME decoder, DKIM/SPF headers, and threaded conversation turns.
- **PII Scrubbing & Tokenization**:
  - Configurable regex redaction for emails, phone numbers, SSNs, and credit cards.
  - Format-preserving encryption (FF1) tokenization for sensitive enterprise data fields.

---

## 📂 Project Layout

```text
data-processing-enrichment/
  configs/
    processing.json
  data/
    raw/
    processed/
  docs/
    architecture.md
  src/nexus_processing/
    audio.py            # WAV, AIFF, MP3, VAD & 7-band spectral analysis
    chunking.py         # Format-aware CSV, JSON, smart text & word chunkers
    cli.py              # Layer CLI commands
    code.py             # Python AST, Polyglot code & OpenAPI spec parsers
    config.py           # Pydantic configuration models
    email_chat.py       # RFC 822 MIME emails & threaded chat conversations
    enrichment.py       # Metadata, entity, and hash tracking
    io.py               # JSONL and file I/O utilities
    media.py            # MP4/MOV video scene framing & image perceptual hashing
    models.py           # Internal data structures
    mongodb.py          # BSON document deserializer & dot-notation flattener
    mysql.py            # MySQL relational tables & CDC change event normalizer
    office.py           # OpenXML Word (.docx), Excel (.xlsx), PowerPoint (.pptx)
    pdf.py              # ISO 32000-1 PDF parser & page-grounded extraction
    pipeline.py         # Batch processing runner
    sqlite.py           # SQLite binary database parser
    tokenization.py     # FF1 format-preserving encryption tokenization
    transforms.py       # ETL/ELT record transformers
  tests/
    test_audio.py
    test_code.py
    test_email_chat.py
    test_media.py
    test_mongodb.py
    test_mysql.py
    test_office.py
    test_pdf.py
    test_pipeline.py
    test_sqlite.py
  pyproject.toml
```
