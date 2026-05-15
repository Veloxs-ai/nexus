from nexus_guardrails.rag import compose_grounded_answer, retrieve_context


def test_retrieve_context_returns_relevant_citation(sample_config, tmp_path):
    citations = retrieve_context(sample_config, "MFA security", tmp_path)

    assert citations[0].source_id == "doc-1:0"
    assert citations[0].score > 0


def test_compose_grounded_answer_requires_citations():
    assert compose_grounded_answer("query", []) == "I do not have enough trusted context to answer this request."


def test_compose_grounded_answer_includes_context(sample_config, tmp_path):
    citations = retrieve_context(sample_config, "MFA security", tmp_path)

    answer = compose_grounded_answer("MFA security", citations)

    assert "MFA" in answer

