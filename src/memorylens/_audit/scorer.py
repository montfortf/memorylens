from __future__ import annotations

import hashlib
import math
from typing import Protocol


class ScorerBackend(Protocol):
    """Interface for embedding scorer backends."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return embedding vectors for a list of texts."""
        ...


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class MockScorer:
    """Deterministic scorer for testing. Produces hash-based embeddings."""

    def __init__(self, dim: int = 64) -> None:
        self._dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._text_to_embedding(t) for t in texts]

    def _text_to_embedding(self, text: str) -> list[float]:
        """Generate a deterministic embedding from text using character n-gram hashing."""
        vec = [0.0] * self._dim
        words = text.lower().split()
        for word in words:
            h = int(hashlib.md5(word.encode()).hexdigest(), 16)
            for i in range(self._dim):
                bit = (h >> (i % 128)) & 1
                vec[i] += 1.0 if bit else -1.0
        # Normalize
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec


class LocalScorer:
    """Uses sentence-transformers all-MiniLM-L6-v2. No API key needed."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "sentence-transformers not found. "
                "Install with: pip install memorylens[audit]"
            )
        self._model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts).tolist()


class OpenAIScorer:
    """Uses OpenAI text-embedding-3-small. Requires OPENAI_API_KEY."""

    def __init__(self, model: str = "text-embedding-3-small") -> None:
        try:
            import openai
        except ImportError:
            raise ImportError(
                "openai package not found. Install with: pip install openai"
            )
        self._client = openai.OpenAI()
        self._model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = self._client.embeddings.create(input=texts, model=self._model)
        return [item.embedding for item in response.data]


def create_scorer(name: str) -> ScorerBackend:
    """Factory function to create a scorer backend by name."""
    if name == "mock":
        return MockScorer()
    elif name == "local":
        return LocalScorer()
    elif name == "openai":
        return OpenAIScorer()
    else:
        raise ValueError(
            f"Unknown scorer '{name}'. Available: mock, local, openai"
        )
