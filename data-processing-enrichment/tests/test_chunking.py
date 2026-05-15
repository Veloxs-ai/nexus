from nexus_processing.chunking import chunk_text


def test_chunk_text_preserves_overlap():
    text = " ".join(f"token{i}" for i in range(10))

    chunks = chunk_text(text, max_tokens=4, overlap_tokens=1)

    assert chunks == [
        "token0 token1 token2 token3",
        "token3 token4 token5 token6",
        "token6 token7 token8 token9",
    ]


def test_chunk_text_returns_empty_for_blank_text():
    assert chunk_text("   ", max_tokens=10, overlap_tokens=2) == []

