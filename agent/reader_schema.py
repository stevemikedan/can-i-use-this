"""
Output schema for the reading step — the ONLY place a model touches the
determination path.

Rule 4 (no unsourced facts) is enforced structurally here, not by convention:
a reader answer is either a Finding that carries >= 1 Citation and a real
confidence, or an Unresolved. There is no third shape. A "found" answer with
an empty citation list, or a fabricated value with no citation, fails Pydantic
validation — which is exactly how ADK surfaces it (LlmAgent parses the model
output through `validate_schema(output_schema, text)`), so the run fails loudly
instead of quietly asserting an unestablished fact.

This is the same failure family as the reissue date and the wrong-person
match: a plausible answer built on a fact that was never established. The type
system makes that state unrepresentable.

The reader NEVER computes a copyright term. It reads evidence into a fact
(renewal filed? recording first published when?); the deterministic rules
engine turns that fact into a determination.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field, HttpUrl

from rules import CURRENT_YEAR
from schemas import Confidence, ResearchedFact, ResearchMethod, Source


class Citation(BaseModel):
    """A specific source passage that supports a claim. Required on every finding."""

    url: HttpUrl
    source_name: str = Field(min_length=1, description="e.g. 'Catalog of Copyright Entries, 1962'")
    excerpt: str = Field(
        min_length=1, max_length=500,
        description="The exact passage from the source that supports the value. "
                    "Not a paraphrase — the words that establish the fact.",
    )
    supports: str = Field(min_length=1, description="One line: how this passage establishes the value.")


# A found answer MUST carry evidence. confidence excludes NONE by construction:
# a fact asserted with no confidence is not a fact.
FoundConfidence = Literal["high", "medium", "low"]


class RenewalFinding(BaseModel):
    """The year-28 renewal question, answered from evidence."""

    status: Literal["found"] = "found"
    kind: Literal["renewal"] = "renewal"
    renewal_filed: bool
    confidence: FoundConfidence
    reasoning: str = Field(min_length=1)
    citations: list[Citation] = Field(min_length=1)


class RecordingYearFinding(BaseModel):
    """The recording's first-publication year, answered from evidence."""

    status: Literal["found"] = "found"
    kind: Literal["recording_year"] = "recording_year"
    first_published_year: int = Field(ge=1877, le=CURRENT_YEAR)  # 1877 = Edison's first recordings
    confidence: FoundConfidence
    reasoning: str = Field(min_length=1)
    citations: list[Citation] = Field(min_length=1)


class Unresolved(BaseModel):
    """
    The evidence did not settle the question. Carries no value and no
    citation — there is nothing to cite. This is a first-class answer, not a
    failure, and never a place to smuggle an uncited guess.
    """

    status: Literal["unresolved"] = "unresolved"
    reason: str = Field(min_length=1, description="Why the searched evidence did not establish the fact.")


RenewalAnswer = Annotated[Union[RenewalFinding, Unresolved], Field(discriminator="status")]
RecordingYearAnswer = Annotated[Union[RecordingYearFinding, Unresolved], Field(discriminator="status")]


# --- reader answer -> pipeline fact --------------------------------------------

def _sources(finding, retrieved_at: datetime) -> list[Source]:
    return [Source(name=c.source_name, url=c.url, method=ResearchMethod.PARALLEL_SEARCH,
                   retrieved_at=retrieved_at, excerpt=c.excerpt[:200], authoritative=False)
            for c in finding.citations]


def renewal_to_fact(answer, retrieved_at: Optional[datetime] = None) -> Optional[ResearchedFact]:
    """RenewalFinding -> ResearchedFact[bool]; Unresolved -> None (question stands)."""
    if answer.status != "found":
        return None
    return ResearchedFact(value=answer.renewal_filed, confidence=Confidence(answer.confidence),
                          sources=_sources(answer, retrieved_at or datetime.now(timezone.utc)),
                          reasoning=answer.reasoning)


def recording_year_to_fact(answer, retrieved_at: Optional[datetime] = None) -> Optional[ResearchedFact]:
    """RecordingYearFinding -> ResearchedFact[int]; Unresolved -> None."""
    if answer.status != "found":
        return None
    return ResearchedFact(value=answer.first_published_year, confidence=Confidence(answer.confidence),
                          sources=_sources(answer, retrieved_at or datetime.now(timezone.utc)),
                          reasoning=answer.reasoning)
