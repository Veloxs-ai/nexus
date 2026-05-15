from nexus_guardrails.config import OffTopicConfig
from nexus_guardrails.offtopic import detect_off_topic, tokenize


def test_detect_off_topic_blocks_unrelated_query():
    config = OffTopicConfig(allowed_keywords=["security", "invoice"], min_keyword_overlap=1)

    findings = detect_off_topic("Tell me a cooking recipe", config)

    assert findings[0].severity == "block"


def test_detect_off_topic_allows_relevant_query():
    config = OffTopicConfig(allowed_keywords=["security", "invoice"], min_keyword_overlap=1)

    assert detect_off_topic("Explain security access", config) == []


def test_tokenize_normalizes_terms():
    assert tokenize("MFA, Security!") == {"mfa", "security"}

