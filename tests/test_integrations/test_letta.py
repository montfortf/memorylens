from __future__ import annotations

from unittest.mock import patch

from memorylens._core.processor import SimpleSpanProcessor
from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.tracer import TracerProvider
from memorylens.integrations.letta.instrumentor import LettaInstrumentor
from tests.test_core.test_processor import CollectingExporter


class FakeBlocks:
    """Simulates Letta's agents.blocks resource interface."""

    def retrieve(self, agent_id, block_label):
        return {"label": block_label, "value": "memory content"}

    def update(self, agent_id, block_label, value):
        return {"label": block_label, "value": value}

    def delete(self, agent_id, block_label):
        return None

    def list(self, agent_id):
        return [{"label": "human", "value": "user info"}]


class TestLettaInstrumentor:
    def _setup(self):
        provider = TracerProvider.get()
        exporter = CollectingExporter()
        provider.add_processor(SimpleSpanProcessor(exporter))
        return exporter

    @patch(
        "memorylens.integrations.letta.instrumentor._get_blocks_class",
        return_value=FakeBlocks,
    )
    def test_instrument_retrieve(self, mock_cls):
        exporter = self._setup()
        instrumentor = LettaInstrumentor()
        instrumentor.instrument()

        blocks = FakeBlocks()
        result = blocks.retrieve("agent_1", "human")
        assert result["label"] == "human"

        assert len(exporter.spans) == 1
        span = exporter.spans[0]
        assert span.operation == MemoryOperation.READ
        assert span.status == SpanStatus.OK

        instrumentor.uninstrument()

    @patch(
        "memorylens.integrations.letta.instrumentor._get_blocks_class",
        return_value=FakeBlocks,
    )
    def test_instrument_update(self, mock_cls):
        exporter = self._setup()
        instrumentor = LettaInstrumentor()
        instrumentor.instrument()

        blocks = FakeBlocks()
        result = blocks.update("agent_1", "human", "updated user info")
        assert result["value"] == "updated user info"

        assert len(exporter.spans) == 1
        span = exporter.spans[0]
        assert span.operation == MemoryOperation.UPDATE

        instrumentor.uninstrument()

    @patch(
        "memorylens.integrations.letta.instrumentor._get_blocks_class",
        return_value=FakeBlocks,
    )
    def test_instrument_delete(self, mock_cls):
        exporter = self._setup()
        instrumentor = LettaInstrumentor()
        instrumentor.instrument()

        blocks = FakeBlocks()
        blocks.delete("agent_1", "human")

        assert len(exporter.spans) == 1
        span = exporter.spans[0]
        assert span.operation == MemoryOperation.WRITE
        assert span.status == SpanStatus.DROPPED
        assert span.attributes["drop_reason"] == "explicit_delete"

        instrumentor.uninstrument()

    @patch(
        "memorylens.integrations.letta.instrumentor._get_blocks_class",
        return_value=FakeBlocks,
    )
    def test_instrument_list(self, mock_cls):
        exporter = self._setup()
        instrumentor = LettaInstrumentor()
        instrumentor.instrument()

        blocks = FakeBlocks()
        result = blocks.list("agent_1")
        assert len(result) == 1

        assert len(exporter.spans) == 1
        span = exporter.spans[0]
        assert span.operation == MemoryOperation.READ

        instrumentor.uninstrument()

    @patch(
        "memorylens.integrations.letta.instrumentor._get_blocks_class",
        return_value=FakeBlocks,
    )
    def test_uninstrument_restores(self, mock_cls):
        exporter = self._setup()
        instrumentor = LettaInstrumentor()
        instrumentor.instrument()
        instrumentor.uninstrument()

        blocks = FakeBlocks()
        blocks.retrieve("agent_1", "human")

        assert len(exporter.spans) == 0
