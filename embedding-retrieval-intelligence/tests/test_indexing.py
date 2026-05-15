from nexus_retrieval.indexing import build_document, build_indexes, extract_text


def test_build_document_extracts_nested_text_and_metadata(sample_config):
    collection = sample_config.collections["policy_documents"]
    record = {
        "chunk_id": "doc-1:0",
        "text": "security policy",
        "metadata": {"tags": ["security"]},
    }

    document = build_document("policy_documents", collection, record)

    assert document.id == "doc-1:0"
    assert document.text == "security policy"
    assert document.metadata == {"tags": ["security"]}


def test_extract_text_joins_multiple_fields(sample_config):
    collection = sample_config.collections["policy_documents"].model_copy(
        update={"text_field": None, "text_fields": ["payload.name", "payload.notes"]}
    )

    assert extract_text({"payload": {"name": "Acme", "notes": "renewal support"}}, collection) == (
        "Acme renewal support"
    )


def test_build_indexes_writes_all_indexes(sample_config, tmp_path):
    count = build_indexes(sample_config, tmp_path)

    assert count == 2
    assert (tmp_path / "vector.json").exists()
    assert (tmp_path / "lexical.json").exists()
    assert (tmp_path / "graph.json").exists()

