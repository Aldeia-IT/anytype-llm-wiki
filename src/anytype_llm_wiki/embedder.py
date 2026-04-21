"""Ollama embedding client."""

import httpx

from . import config


def embed(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts via Ollama API. Returns list of vectors."""
    if not texts:
        return []

    with httpx.Client(timeout=120) as c:
        resp = c.post(
            f"{config.OLLAMA_URL}/api/embed",
            json={"model": config.EMBED_MODEL, "input": texts},
        )
        resp.raise_for_status()
        return resp.json()["embeddings"]


def embed_query(query: str) -> list[float]:
    """Embed a single search query. Returns one vector."""
    return embed([query])[0]
