from __future__ import annotations

from memorylens._audit.scorer import CachedScorer, cosine_similarity
from memorylens._core.span import MemorySpan
from memorylens._exporters.sqlite import SQLiteExporter

_WRITE_OPS = {"memory.write", "memory.update"}
_DRIFT_ALERT_THRESHOLD = 0.3


class VersionTracker:
    """SpanProcessor that records memory versions and detects drift in real-time.

    Implements the SpanProcessor protocol (on_start, on_end, shutdown, force_flush).
    Enabled via memorylens.init(detect_drift=True).

    On each WRITE/UPDATE span completion:
    1. Extracts memory_key from span attributes
    2. Saves the version to memory_versions table
    3. Computes drift against cached previous embedding
    4. If drift > 0.3, sets drift_score and drift_detected on span attributes
    """

    def __init__(self, exporter: SQLiteExporter, scorer: CachedScorer) -> None:
        self._exporter = exporter
        self._scorer = scorer
        # In-memory cache: memory_key → last known embedding
        self._embedding_cache: dict[str, list[float]] = {}
        # In-memory version counter: memory_key → current version number
        self._version_cache: dict[str, int] = {}

    def on_start(self, span: MemorySpan) -> None:
        """No-op: version tracking happens on span completion."""
        pass

    def on_end(self, span: MemorySpan) -> None:
        """Process a completed span. Only acts on WRITE and UPDATE operations."""
        op = span.operation.value if hasattr(span.operation, "value") else str(span.operation)
        if op not in _WRITE_OPS:
            return

        # Extract memory_key from span attributes; skip if not identifiable
        memory_key = span.attributes.get("memory_key")
        if not memory_key:
            # Fallback: hash of input content
            content = span.input_content or span.output_content
            if not content:
                return
            import hashlib

            memory_key = hashlib.md5(content.encode()).hexdigest()[:16]

        content = span.output_content or span.input_content or ""

        # Determine version number
        version = self._version_cache.get(memory_key, 0) + 1
        self._version_cache[memory_key] = version

        # Save version to DB
        version_record = {
            "memory_key": memory_key,
            "version": version,
            "span_id": span.span_id,
            "operation": op,
            "content": content,
            "embedding": None,  # stored without embedding to minimize overhead
            "agent_id": span.agent_id,
            "session_id": span.session_id,
            "timestamp": span.end_time,
        }
        try:
            self._exporter.save_version(version_record)
        except Exception:
            pass  # Don't let storage errors disrupt tracing

        # Compute drift against cached prior embedding
        if not content:
            return

        try:
            new_embeddings = self._scorer.embed([content])
            new_embedding = new_embeddings[0]
        except Exception:
            return

        prior_embedding = self._embedding_cache.get(memory_key)
        self._embedding_cache[memory_key] = new_embedding

        if prior_embedding is not None:
            sim = cosine_similarity(prior_embedding, new_embedding)
            sim = max(0.0, min(1.0, sim))
            drift_score = round(1.0 - sim, 4)

            if drift_score > _DRIFT_ALERT_THRESHOLD:
                # Annotate span attributes with drift information
                try:
                    self._exporter.update_span_attributes(
                        span.span_id,
                        {
                            "drift_score": drift_score,
                            "drift_detected": True,
                            "memory_key": memory_key,
                        },
                    )
                except Exception:
                    pass

    def shutdown(self) -> None:
        """Clear in-memory caches. Exporter lifecycle managed externally."""
        self._embedding_cache.clear()
        self._version_cache.clear()

    def force_flush(self, timeout_ms: int = 30000) -> bool:
        """VersionTracker is synchronous; flush is a no-op."""
        return True
