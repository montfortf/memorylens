from __future__ import annotations

from memorylens._core.schema import MemoryOperation, SpanStatus


class TestMemoryOperation:
    def test_write_value(self):
        assert MemoryOperation.WRITE == "memory.write"
        assert MemoryOperation.WRITE.value == "memory.write"

    def test_read_value(self):
        assert MemoryOperation.READ == "memory.read"

    def test_compress_value(self):
        assert MemoryOperation.COMPRESS == "memory.compress"

    def test_update_value(self):
        assert MemoryOperation.UPDATE == "memory.update"

    def test_is_string(self):
        assert isinstance(MemoryOperation.WRITE, str)

    def test_all_members(self):
        members = {m.value for m in MemoryOperation}
        assert members == {"memory.write", "memory.read", "memory.compress", "memory.update"}


class TestSpanStatus:
    def test_ok_value(self):
        assert SpanStatus.OK == "ok"

    def test_error_value(self):
        assert SpanStatus.ERROR == "error"

    def test_dropped_value(self):
        assert SpanStatus.DROPPED == "dropped"

    def test_is_string(self):
        assert isinstance(SpanStatus.OK, str)

    def test_all_members(self):
        members = {m.value for m in SpanStatus}
        assert members == {"ok", "error", "dropped"}
