from __future__ import annotations

from memorylens._core.schema import MemoryOperation, SpanStatus
from memorylens._core.tracer import TracerProvider
from memorylens.testing import IntegrationTestHelper


class TestIntegrationTestHelper:
    def test_setup_creates_provider(self):
        helper = IntegrationTestHelper()
        assert len(helper.spans) == 0
        helper.reset()

    def test_collects_spans(self):
        helper = IntegrationTestHelper()
        tracer = TracerProvider.get().get_tracer("test")
        with tracer.start_span(operation=MemoryOperation.WRITE, attributes={"framework": "test"}):
            pass
        assert len(helper.spans) == 1
        helper.reset()

    def test_assert_span_count(self):
        helper = IntegrationTestHelper()
        tracer = TracerProvider.get().get_tracer("test")
        with tracer.start_span(operation=MemoryOperation.WRITE, attributes={"framework": "test"}):
            pass
        helper.assert_span_count(1)
        helper.reset()

    def test_assert_operation(self):
        helper = IntegrationTestHelper()
        tracer = TracerProvider.get().get_tracer("test")
        with tracer.start_span(operation=MemoryOperation.READ, attributes={"framework": "test"}):
            pass
        helper.assert_operation(0, MemoryOperation.READ)
        helper.reset()

    def test_assert_attribute_exists(self):
        helper = IntegrationTestHelper()
        tracer = TracerProvider.get().get_tracer("test")
        with tracer.start_span(
            operation=MemoryOperation.WRITE, attributes={"framework": "myfw", "backend": "db"}
        ):
            pass
        helper.assert_attribute(0, "framework")
        helper.assert_attribute(0, "backend", "db")
        helper.reset()

    def test_assert_status(self):
        helper = IntegrationTestHelper()
        tracer = TracerProvider.get().get_tracer("test")
        with tracer.start_span(operation=MemoryOperation.WRITE, attributes={"framework": "test"}):
            pass
        helper.assert_status(0, SpanStatus.OK)
        helper.reset()

    def test_reset_clears(self):
        helper = IntegrationTestHelper()
        tracer = TracerProvider.get().get_tracer("test")
        with tracer.start_span(operation=MemoryOperation.WRITE, attributes={"framework": "test"}):
            pass
        assert len(helper.spans) == 1
        helper.reset()
        # After reset, new helper should be clean
        helper2 = IntegrationTestHelper()
        assert len(helper2.spans) == 0
        helper2.reset()
