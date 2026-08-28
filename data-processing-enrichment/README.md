# Data Processing & Enrichment Layer

> Part of **[Nexus — Enterprise Intelligence Framework](../README.md)**, the open-source framework for secure, governed AI applications.
> This layer provides the **Processing & Enrichment** capability.


Transforms raw, ingested data into structured, standardized, and AI-ready formats. This layer improves data quality, enriches records with contextual metadata, applies regex PII scrubbing, and prepares documents for downstream 3072D vector embedding.

---

## 🛠️ Capabilities

- **Format-Aware Document Chunking**:
  - `chunk_csv`: Tabular row narrative serialization (`[Row ID: x] col: val | ...`), preserving column-value relationships.
  - `chunk_json`: Discrete structural object and array serialization.
  - `chunk_smart_text`: Paragraph (`\n\n`) and sentence (`. `) boundary splitting to prevent severed sentences.
  - `chunk_words`: Token-preserving sliding window with configurable overlap.
- **PII Scrubbing**: Configurable regex redaction (`redact_pii: bool`) for emails (`[REDACTED_EMAIL]`) and phone numbers (`[REDACTED_PHONE]`).
- **Metadata & Hash Tracking**: Extracts entities, tags, dates, and calculates MD5 `content_hash` for incremental updates.
- **ETL/ELT Transformations**: String trimming, casing normalization, and default value mapping.

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
    chunking.py
    cli.py
    config.py
    enrichment.py
    io.py
    models.py
    pipeline.py
    tokenization.py
    transforms.py
  pyproject.toml
```
