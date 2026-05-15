from nexus_guardrails.config import VerificationConfig
from nexus_guardrails.models import Citation
from nexus_guardrails.verification import verify_grounding


def test_verify_grounding_scores_overlap():
    confidence, findings = verify_grounding(
        "MFA is required for sensitive systems",
        [Citation(source_id="a", collection="docs", text="MFA sensitive systems", score=1.0)],
        VerificationConfig(min_confidence=0.1),
    )

    assert confidence > 0
    assert findings == []


def test_verify_grounding_blocks_without_citations():
    confidence, findings = verify_grounding("answer", [], VerificationConfig())

    assert confidence == 0.0
    assert findings[0].severity == "block"

