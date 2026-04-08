from __future__ import annotations

from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.span import MemorySpan


class TestMemorySpan:
    def test_create_write_span(self):
        span = MemorySpan(
            span_id="span-1",
            trace_id="trace-1",
            parent_span_id=None,
            operation=MemoryOperation.WRITE,
            status=SpanStatus.OK,
            start_time=1000.0,
            end_time=1012.0,
            duration_ms=12.0,
            agent_id="test-agent",
            session_id="sess-1",
            user_id="user-1",
            input_content="Store this fact",
            output_content="Stored successfully",
            attributes={"backend": "mem0", "memory_key": "pref_diet"},
        )
        assert span.operation == MemoryOperation.WRITE
        assert span.status == SpanStatus.OK
        assert span.duration_ms == 12.0
        assert span.attributes["backend"] == "mem0"

    def test_create_read_span_with_scores(self):
        span = MemorySpan(
            span_id="span-2",
            trace_id="trace-1",
            parent_span_id="span-1",
            operation=MemoryOperation.READ,
            status=SpanStatus.OK,
            start_time=1000.0,
            end_time=1045.0,
            duration_ms=45.0,
            agent_id=None,
            session_id=None,
            user_id=None,
            input_content="music preferences",
            output_content=None,
            attributes={
                "query": "music preferences",
                "results_count": 3,
                "scores": [0.92, 0.87, 0.65],
                "threshold": 0.7,
                "backend": "pinecone",
                "top_k": 5,
            },
        )
        assert span.parent_span_id == "span-1"
        assert span.attributes["scores"] == [0.92, 0.87, 0.65]

    def test_optional_fields_default_none(self):
        span = MemorySpan(
            span_id="span-3",
            trace_id="trace-2",
            parent_span_id=None,
            operation=MemoryOperation.COMPRESS,
            status=SpanStatus.OK,
            start_time=1000.0,
            end_time=1100.0,
            duration_ms=100.0,
            agent_id=None,
            session_id=None,
            user_id=None,
            input_content=None,
            output_content=None,
            attributes={},
        )
        assert span.agent_id is None
        assert span.input_content is None
        assert span.attributes == {}

    def test_to_dict(self):
        span = MemorySpan(
            span_id="span-4",
            trace_id="trace-3",
            parent_span_id=None,
            operation=MemoryOperation.UPDATE,
            status=SpanStatus.OK,
            start_time=1000.0,
            end_time=1008.0,
            duration_ms=8.0,
            agent_id="bot",
            session_id=None,
            user_id=None,
            input_content="new value",
            output_content="updated",
            attributes={"memory_key": "k1", "update_type": "replace"},
        )
        d = span.to_dict()
        assert isinstance(d, dict)
        assert d["span_id"] == "span-4"
        assert d["operation"] == "memory.update"
        assert d["status"] == "ok"
        assert d["attributes"]["update_type"] == "replace"

    def test_dropped_span(self):
        span = MemorySpan(
            span_id="span-5",
            trace_id="trace-4",
            parent_span_id=None,
            operation=MemoryOperation.WRITE,
            status=SpanStatus.DROPPED,
            start_time=1000.0,
            end_time=1005.0,
            duration_ms=5.0,
            agent_id=None,
            session_id=None,
            user_id=None,
            input_content="something",
            output_content=None,
            attributes={"drop_reason": "duplicate", "drop_policy": "dedup_filter"},
        )
        assert span.status == SpanStatus.DROPPED
        assert span.attributes["drop_reason"] == "duplicate"
