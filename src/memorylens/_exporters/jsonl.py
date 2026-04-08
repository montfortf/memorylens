from __future__ import annotations

import json
import sys
from typing import IO

from memorylens._core.span import MemorySpan
from memorylens._exporters.base import ExportResult


class JSONLExporter:
    """Exports spans as JSON Lines to a file or stdout."""

    def __init__(self, file_path: str | None = None) -> None:
        self._file_path = file_path
        self._file_handle: IO[str] | None = None

    def _get_output(self) -> IO[str]:
        if self._file_path is None:
            return sys.stdout
        if self._file_handle is None:
            self._file_handle = open(self._file_path, "a")
        return self._file_handle

    def export(self, spans: list[MemorySpan]) -> ExportResult:
        try:
            output = self._get_output()
            for span in spans:
                line = json.dumps(span.to_dict(), default=str)
                output.write(line + "\n")
            if self._file_handle is not None:
                self._file_handle.flush()
            return ExportResult.SUCCESS
        except Exception:
            return ExportResult.FAILURE

    def shutdown(self) -> None:
        if self._file_handle is not None:
            self._file_handle.close()
            self._file_handle = None
