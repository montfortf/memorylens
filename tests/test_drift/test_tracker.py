from __future__ import annotations

import time

import pytest

from memorylens._audit.scorer import CachedScorer, MockScorer
from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.span import MemorySpan
from memorylens._drift.tracker import VersionTracker


def make_span(
    operation: str = "memory.write",
    content: str = "some content",
    memory_key: str | None = "key_1",
    session_id: str | None = "sess-1",
    span_id: str = "span-001",
) -> MemorySpan:
    attrs = {}
    if memory_key:
        attrs["memory_key"] = memory_key
    op = MemoryOperation(operation)
    return MemorySpan(
        span_id=span_id,
        trace_id="trace-001",
        parent_span_id=None,
        operation=op,
        status=SpanStatus.OK,
        start_time=time.time() - 0.1,
        end_time=time.time(),
        duration_ms=100.0,
        agent_id="agent-1",
        session_id=session_id,
        user_id=None,
        input_content=content,
        output_content=content,
        attributes=attrs,
    )


@pytest.fixture
def tracker(tmp_path):
    from memorylens._exporters.sqlite import SQLiteExporter

    exporter = SQLiteExporter(db_path=str(tmp_path / "test.db"))
    scorer = CachedScorer(MockScorer())
    t = VersionTracker(exporter=exporter, scorer=scorer)
    yield t, exporter
    exporter.shutdown()


class TestVersionTrackerOnStart:
    def test_on_start_is_noop(self, tracker):
        t, _ = tracker
        span = make_span()
        t.on_start(span)  # Should not raise


class TestVersionTrackerOnEnd:
    def test_write_span_saves_version(self, tracker):
        t, exporter = tracker
        span = make_span(operation="memory.write", memory_key="key_a", span_id="span-w1")
        t.on_end(span)
        versions = exporter.get_versions("key_a")
        assert len(versions) == 1
        assert versions[0]["memory_key"] == "key_a"
        assert versions[0]["operation"] == "memory.write"

    def test_update_span_saves_version(self, tracker):
        t, exporter = tracker
        span = make_span(operation="memory.update", memory_key="key_b", span_id="span-u1")
        t.on_end(span)
        versions = exporter.get_versions("key_b")
        assert len(versions) == 1
        assert versions[0]["operation"] == "memory.update"

    def test_read_span_skipped(self, tracker):
        t, exporter = tracker
        span = make_span(operation="memory.read", memory_key="key_c", span_id="span-r1")
        t.on_end(span)
        versions = exporter.get_versions("key_c")
        assert versions == []

    def test_compress_span_skipped(self, tracker):
        t, exporter = tracker
        span = make_span(operation="memory.compress", memory_key="key_d", span_id="span-c1")
        t.on_end(span)
        versions = exporter.get_versions("key_d")
        assert versions == []

    def test_version_increments_per_key(self, tracker):
        t, exporter = tracker
        for i in range(3):
            span = make_span(memory_key="incr_key", span_id=f"span-{i}")
            t.on_end(span)
        versions = exporter.get_versions("incr_key")
        assert len(versions) == 3
        assert [v["version"] for v in versions] == [1, 2, 3]

    def test_no_memory_key_uses_content_hash(self, tracker):
        t, exporter = tracker
        span = make_span(memory_key=None, content="hashable content", span_id="span-hash")
        t.on_end(span)
        all_versions = exporter.get_all_versions()
        assert len(all_versions) == 1
        # Key should be a 16-char hex hash
        assert len(all_versions[0]["memory_key"]) == 16

    def test_no_content_and_no_key_skipped(self, tracker):
        t, exporter = tracker
        span = MemorySpan(
            span_id="span-empty",
            trace_id="trace-001",
            parent_span_id=None,
            operation=MemoryOperation.WRITE,
            status=SpanStatus.OK,
            start_time=time.time() - 0.1,
            end_time=time.time(),
            duration_ms=10.0,
            agent_id=None,
            session_id=None,
            user_id=None,
            input_content=None,
            output_content=None,
            attributes={},  # no memory_key
        )
        t.on_end(span)
        assert exporter.get_all_versions() == []


class TestVersionTrackerShutdown:
    def test_shutdown_clears_caches(self, tracker):
        t, _ = tracker
        span = make_span(memory_key="key_s", span_id="span-s1")
        t.on_end(span)
        assert len(t._embedding_cache) > 0
        t.shutdown()
        assert t._embedding_cache == {}
        assert t._version_cache == {}

    def test_force_flush_returns_true(self, tracker):
        t, _ = tracker
        assert t.force_flush() is True
        assert t.force_flush(timeout_ms=100) is True
