from nexus_retrieval.models import VectorEntry
from nexus_retrieval.vector_store import LocalVectorStore


def test_vector_store_search_and_persistence(tmp_path):
    store = LocalVectorStore("vector.json", tmp_path)
    store.add(
        VectorEntry(
            id="a",
            collection="docs",
            text="security policy",
            embedding=[1.0, 0.0],
            metadata={"tags": ["security"]},
        )
    )
    store.add(
        VectorEntry(
            id="b",
            collection="docs",
            text="finance policy",
            embedding=[0.0, 1.0],
        )
    )
    store.save()

    loaded = LocalVectorStore("vector.json", tmp_path)
    loaded.load()
    results = loaded.search([1.0, 0.0], limit=1)

    assert results[0].id == "a"
    assert results[0].semantic_score == 1.0

