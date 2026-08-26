"""PipelineEvent emitter — feeds the staged progress UI (and the CLI ledger)."""

from __future__ import annotations

import time
from typing import Callable, Optional

from schemas import PipelineEvent, PipelineStage

Listener = Callable[[PipelineEvent], None]


class Emitter:
    def __init__(self, listener: Optional[Listener] = None) -> None:
        self._t0 = time.monotonic()
        self._listeners: list[Listener] = [listener] if listener else []
        self.events: list[PipelineEvent] = []
        self.sources_consulted = 0

    def consulted(self, n: int = 1) -> None:
        self.sources_consulted += n

    def emit(self, stage: PipelineStage, status: str, message: str, *, detail: Optional[str] = None,
             degraded: bool = False, error_message: Optional[str] = None,
             partial: Optional[dict] = None) -> PipelineEvent:
        ev = PipelineEvent(stage=stage, status=status, message=message, detail=detail,
                           sources_consulted=self.sources_consulted,
                           elapsed_ms=int((time.monotonic() - self._t0) * 1000),
                           degraded=degraded, error_message=error_message, partial=partial)
        self.events.append(ev)
        for fn in self._listeners:
            fn(ev)
        return ev
