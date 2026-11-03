"""QThread wrapper for long-running PDF operations."""
from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QThread, Signal


class FunctionWorker(QThread):
    progress = Signal(int, str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, function: Callable[..., Any], parent=None) -> None:
        super().__init__(parent)
        self.function = function
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled

    def run(self) -> None:
        try:
            result = self.function(self.progress.emit, self.is_cancelled)
            if not self._cancelled:
                self.done.emit(result)
        except Exception as exc:  # pragma: no cover - depends on external data
            if not self._cancelled:
                self.failed.emit(str(exc))
