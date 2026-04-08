from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from memorylens._audit.scorer import ScorerBackend, cosine_similarity
from memorylens._audit.splitter import split_sentences


@dataclass(frozen=True)
class SentenceAnalysis:
    """Analysis of a single sentence from pre-compression content."""

    text: str
    best_match_score: float
    status: str  # "preserved" or "lost"


@dataclass(frozen=True)
class CompressionAudit:
    """Complete audit result for a single COMPRESS span."""

    span_id: str
    semantic_loss_score: float
    compression_ratio: float
    pre_sentence_count: int
    post_sentence_count: int
    sentences: list[SentenceAnalysis]
    scorer_backend: str

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


_PRESERVED_THRESHOLD = 0.7


class CompressionAnalyzer:
    """Analyzes compression quality by comparing pre/post content at sentence level."""

    def __init__(self, scorer: ScorerBackend) -> None:
        self._scorer = scorer
        self._backend_name = type(scorer).__name__.lower().replace("scorer", "")

    def analyze(
        self,
        span_id: str,
        pre_content: str,
        post_content: str,
    ) -> CompressionAudit:
        pre_sentences = split_sentences(pre_content)
        post_sentences = split_sentences(post_content)

        if not pre_sentences:
            return CompressionAudit(
                span_id=span_id,
                semantic_loss_score=0.0,
                compression_ratio=0.0 if not pre_content else len(post_content) / len(pre_content),
                pre_sentence_count=0,
                post_sentence_count=len(post_sentences),
                sentences=[],
                scorer_backend=self._backend_name,
            )

        # Embed all sentences in one batch
        all_texts = pre_sentences + post_sentences
        all_embeddings = self._scorer.embed(all_texts)

        pre_embeddings = all_embeddings[: len(pre_sentences)]
        post_embeddings = all_embeddings[len(pre_sentences) :]

        # For each pre-sentence, find best match in post-sentences
        sentence_analyses: list[SentenceAnalysis] = []
        for i, pre_sent in enumerate(pre_sentences):
            if not post_embeddings:
                best_score = 0.0
            else:
                best_score = max(
                    cosine_similarity(pre_embeddings[i], post_emb)
                    for post_emb in post_embeddings
                )
            # Clamp to [0, 1]
            best_score = max(0.0, min(1.0, best_score))
            status = "preserved" if best_score >= _PRESERVED_THRESHOLD else "lost"
            sentence_analyses.append(
                SentenceAnalysis(
                    text=pre_sent,
                    best_match_score=round(best_score, 4),
                    status=status,
                )
            )

        # Compute overall loss score
        mean_score = sum(s.best_match_score for s in sentence_analyses) / len(sentence_analyses)
        semantic_loss = round(1.0 - mean_score, 4)

        compression_ratio = round(len(post_content) / len(pre_content), 4) if pre_content else 0.0

        return CompressionAudit(
            span_id=span_id,
            semantic_loss_score=semantic_loss,
            compression_ratio=compression_ratio,
            pre_sentence_count=len(pre_sentences),
            post_sentence_count=len(post_sentences),
            sentences=sentence_analyses,
            scorer_backend=self._backend_name,
        )
