"""Tests for embedder (requires running Ollama with bge-m3)."""

import pytest

from anytype_rag.embedder import embed, embed_query
from anytype_rag import config


@pytest.fixture(autouse=True)
def check_ollama():
    """Skip if Ollama is not reachable."""
    import httpx

    try:
        httpx.get(f"{config.OLLAMA_URL}/api/tags", timeout=5)
    except (httpx.ConnectError, httpx.TimeoutException):
        pytest.skip("Ollama not reachable")


class TestEmbed:
    def test_single_text(self):
        vectors = embed(["Hello world"])
        assert len(vectors) == 1
        assert len(vectors[0]) == config.EMBED_DIMS

    def test_batch(self):
        texts = ["First text", "Second text", "Third text"]
        vectors = embed(texts)
        assert len(vectors) == 3
        assert all(len(v) == config.EMBED_DIMS for v in vectors)

    def test_empty_list(self):
        assert embed([]) == []


class TestEmbedQuery:
    def test_returns_single_vector(self):
        vec = embed_query("test query")
        assert isinstance(vec, list)
        assert len(vec) == config.EMBED_DIMS

    def test_different_queries_different_vectors(self):
        v1 = embed_query("capoeira governance")
        v2 = embed_query("quantum physics")
        # Vectors should differ meaningfully
        diff = sum(abs(a - b) for a, b in zip(v1, v2))
        assert diff > 1.0  # not identical
