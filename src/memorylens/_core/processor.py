from __future__ import annotations

import threading
from collections import deque
from typing import Protocol

from memorylens._core.span import MemorySpan
from memorylens._exporters.base import SpanExporter


class SpanProcessor(Protocol):
    """Interface for span processors."""

    def on_start(self, span: MemorySpan) -> None: ...
    def on_end(self, span: MemorySpan) -> None: ...
    def shutdown(self) -> None: ...
    def force_flush(self, timeout_ms: int = 30000) -> bool: ...


class SimpleSpanProcessor:
    """Exports each span synchronously on on_end(). For debugging/testing."""

    def __init__(self, exporter: SpanExporter) -> None:
        self._exporter = exporter

    def on_start(self, span: MemorySpan) -> None:
        pass

    def on_end(self, span: MemorySpan) -> None:
        self._exporter.export([span])

    def shutdown(self) -> None:
        self._exporter.shutdown()

    def force_flush(self, timeout_ms: int = 30000) -> bool:
        return True


class BatchSpanProcessor:
    """Batches spans and exports in a background thread. Non-blocking."""

    def __init__(
        self,
        exporter: SpanExporter,
        max_batch_size: int = 512,
        schedule_delay_ms: int = 5000,
        max_queue_size: int = 2048,
    ) -> None:
        self._exporter = exporter
        self._max_batch_size = max_batch_size
        self._schedule_delay_s = schedule_delay_ms / 1000.0
        self._max_queue_size = max_queue_size
        self._queue: deque[MemorySpan] = deque(maxlen=max_queue_size)
        self._lock = threading.Lock()
        self._flush_event = threading.Event()
        self._shutdown_event = threading.Event()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def on_start(self, span: MemorySpan) -> None:
        pass

    def on_end(self, span: MemorySpan) -> None:
        with self._lock:
            self._queue.append(span)
            if len(self._queue) >= self._max_batch_size:
                self._flush_event.set()

    def shutdown(self) -> None:
        self._shutdown_event.set()
        self._flush_event.set()
        self._worker.join(timeout=10)
        self._flush_batch()
        self._exporter.shutdown()

    def force_flush(self, timeout_ms: int = 30000) -> bool:
        self._flush_event.set()
        self._worker.join(timeout=timeout_ms / 1000.0)
        if self._worker.is_alive():
            self._flush_batch()
        return True

    def _run(self) -> None:
        while not self._shutdown_event.is_set():
            self._flush_event.wait(timeout=self._schedule_delay_s)
            self._flush_event.clear()
            self._flush_batch()

    def _flush_batch(self) -> None:
        with self._lock:
            batch = list(self._queue)
            self._queue.clear()
        if batch:
            for i in range(0, len(batch), self._max_batch_size):
                chunk = batch[i : i + self._max_batch_size]
                self._exporter.export(chunk)
