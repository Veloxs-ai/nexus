from nexus_retrieval.embeddings import HashingEmbedder, cosine_similarity, tokenize


def test_hashing_embedder_is_deterministic_and_normalized():
    embedder = HashingEmbedder(dimensions=16, normalize=True)

    first = embedder.embed("MFA access policy")
    second = embedder.embed("MFA access policy")

    assert first == second
    assert round(cosine_similarity(first, first), 6) == 1.0


def test_tokenize_lowercases_words():
    assert tokenize("MFA, Access!") == ["mfa", "access"]

