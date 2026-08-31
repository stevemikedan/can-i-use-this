"""
The reading step: turn Tier 3 search evidence into a cited fact, or leave the
question open. This is the ONLY place a model touches the determination path.

The pipeline performs the Parallel Search on the primary request path and
hands the SearchOutcome here; a Reader reads that evidence and returns a
RenewalAnswer / RecordingYearAnswer (agent/reader_schema.py), whose type makes
an unsourced fact unrepresentable. The rules engine — never the reader —
computes the term from the resulting fact.

Implementations:
  NullReader   — no reading configured (no key / Tier 3 degraded). Always
                 Unresolved, so the pipeline's behaviour and the acceptance
                 fixtures are unchanged. The default.
  FakeReader   — canned answers for tests.
  GeminiReader — Gemini via Vertex, output_schema-constrained. Lives in
                 agent/gemini_reader.py and is only imported when built, so no
                 Google Cloud import is needed to run the pipeline. Credential-
                 gated; wired when GOOGLE_CLOUD_PROJECT / ADC are live.
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Protocol, runtime_checkable

from research.parallel_client import SearchOutcome

from .reader_schema import (
    RecordingYearAnswer, RenewalAnswer, Unresolved, WritersAnswer,
)


log = logging.getLogger("agent.reader")


@runtime_checkable
class Reader(Protocol):
    available: bool

    def read_renewal(self, *, title: str, writers: list[str], year: int,
                     evidence: SearchOutcome) -> RenewalAnswer: ...

    def read_recording_year(self, *, title: str, artist: str, year_on_file: Optional[str],
                            evidence: SearchOutcome) -> RecordingYearAnswer: ...

    def read_writers(self, *, title: str, year: Optional[int], candidates: list[str],
                     evidence: SearchOutcome) -> WritersAnswer: ...


class NullReader:
    """No reading step. Every question stays open — the credential-free baseline."""

    available = False
    _WHY = "No reading step configured; the searched evidence was not read into a fact."

    def read_renewal(self, **_) -> RenewalAnswer:
        return Unresolved(reason=self._WHY)

    def read_recording_year(self, **_) -> RecordingYearAnswer:
        return Unresolved(reason=self._WHY)

    def read_writers(self, **_) -> WritersAnswer:
        return Unresolved(reason=self._WHY)


class FakeReader:
    """
    Test double. Configure with the answers to return; records calls.

        FakeReader(renewal=RenewalFinding(...), recording_year=Unresolved(...))
    """

    available = True

    def __init__(self, *, renewal: Optional[RenewalAnswer] = None,
                 recording_year: Optional[RecordingYearAnswer] = None,
                 writers: Optional[WritersAnswer] = None):
        self._renewal = renewal or Unresolved(reason="fake: no renewal answer configured")
        self._recording_year = recording_year or Unresolved(reason="fake: no recording-year answer configured")
        self._writers = writers or Unresolved(reason="fake: no writers answer configured")
        self.calls: list[tuple[str, dict]] = []

    def read_renewal(self, **kw) -> RenewalAnswer:
        self.calls.append(("renewal", kw))
        return self._renewal

    def read_recording_year(self, **kw) -> RecordingYearAnswer:
        self.calls.append(("recording_year", kw))
        return self._recording_year

    def read_writers(self, **kw) -> WritersAnswer:
        self.calls.append(("writers", kw))
        return self._writers


def default_reader() -> Reader:
    """
    The reader the request path uses: GeminiReader when GOOGLE_CLOUD_PROJECT
    is set (Vertex via ADC locally, the service account on Cloud Run), else
    NullReader. CIUT_READER=off forces NullReader — e.g. to measure the
    pipeline without the model.
    """
    if os.environ.get("GOOGLE_CLOUD_PROJECT") and os.environ.get("CIUT_READER", "gemini").lower() != "off":
        try:
            from .gemini_reader import GeminiReader
            return GeminiReader()
        except Exception as e:                 # missing SDK, bad model name — degrade to no reading
            log.warning("GeminiReader unavailable (%s); using NullReader", e)
    return NullReader()
