from nexus_retrieval.config import GraphMappingConfig
from nexus_retrieval.graph import KnowledgeGraph
from nexus_retrieval.models import IndexedDocument


def test_knowledge_graph_adds_entities_tags_and_parent(tmp_path):
    graph = KnowledgeGraph("graph.json", tmp_path)
    document = IndexedDocument(
        id="doc-1:0",
        collection="docs",
        text="MFA security policy",
        metadata={"tags": ["security"]},
        source={
            "document_id": "doc-1",
            "metadata": {"tags": ["security"], "entities": ["Security Policy"]},
        },
    )

    graph.add_document(
        document,
        GraphMappingConfig(
            entity_fields=["metadata.entities"],
            tag_fields=["metadata.tags"],
            parent_field="document_id",
        ),
    )

    assert "document:doc-1:0" in graph.nodes
    assert graph.score("doc-1:0", ["security"]) > 0


def test_knowledge_graph_persists(tmp_path):
    graph = KnowledgeGraph("graph.json", tmp_path)
    graph.add_edge("document:a", "TAGGED_AS", "tag:security")
    graph.nodes["document:a"] = {"type": "document", "id": "a"}
    graph.nodes["tag:security"] = {"type": "tag", "value": "security"}
    graph.save()

    loaded = KnowledgeGraph("graph.json", tmp_path)
    loaded.load()

    assert loaded.score("a", ["security"]) == 1.0

