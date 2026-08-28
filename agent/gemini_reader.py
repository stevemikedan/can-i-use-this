"""
GeminiReader — the reading step, backed by Gemini via Vertex AI (ADK LlmAgent).

Reads the Tier 3 search evidence into a cited fact or leaves the question
open. Its output_schema is the discriminated union from reader_schema, so the
model cannot return a fact without a citation: an uncited answer fails schema
validation and is treated as no finding (the question stays open), never as a
low-confidence fact. The model extracts; the rules engine computes the term.

Model: gemini-flash-latest by default — this is extraction from provided text,
not hard reasoning, and Flash keeps the latency budget. Override for quality.

Credential-gated: needs GOOGLE_CLOUD_PROJECT + GOOGLE_CLOUD_LOCATION + ADC and
GOOGLE_GENAI_USE_VERTEXAI=1. Importing this module does not require them; only
constructing GeminiReader and calling read_* does.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import pydantic
from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import BaseModel, Field, model_validator

from research.parallel_client import SearchOutcome
from rules import CURRENT_YEAR

from .reader_schema import (
    Citation, RecordingYearAnswer, RecordingYearFinding, RenewalAnswer, RenewalFinding, Unresolved,
)
from .tools import parallel_search

log = logging.getLogger("agent.gemini_reader")

# Vertex has no "gemini-flash-latest" alias; the current Flash line runs
# gemini-2.5-flash .. gemini-3.7-flash. 2.5-flash is the most established for
# structured output + tools; bump the constructor arg for newer if quality warrants.
DEFAULT_MODEL = "gemini-2.5-flash"

# Gemini's response_schema (google.genai Schema) does not support discriminated
# unions (oneOf/discriminator). So the model emits a FLAT object, and Rule 4 is
# enforced by a validator on that object: a "found" answer with no citation
# raises, so an uncited fact can never validate. The flat answer is then
# converted to the canonical discriminated-union type from reader_schema, which
# the rest of the pipeline uses.

_CONF = pydantic.constr(pattern="^(high|medium|low)$")


class _FlatCitation(BaseModel):
    url: str = Field(description="The source URL the excerpt came from.")
    source_name: str = Field(description="e.g. 'Catalog of Copyright Entries, 1962'.")
    excerpt: str = Field(description="The exact passage that establishes the value.")
    supports: str = Field(description="One line: how this passage establishes the value.")


class _FlatRenewal(BaseModel):
    """Flat, Gemini-representable renewal answer. Rule 4 enforced below."""

    status: str = Field(description="'found' if a passage establishes the answer, else 'unresolved'.")
    renewal_filed: Optional[bool] = Field(None, description="Whether a year-28 renewal was registered.")
    confidence: Optional[str] = Field(None, description="high, medium, or low. Required when found.")
    reasoning: Optional[str] = Field(None, description="How the evidence establishes the answer.")
    citations: list[_FlatCitation] = Field(default_factory=list,
                                           description="Required when found: >= 1 supporting passage.")
    reason: Optional[str] = Field(None, description="When unresolved: why the evidence did not settle it.")

    @model_validator(mode="after")
    def _rule4(self):
        if self.status == "found":
            if self.renewal_filed is None:
                raise ValueError("a found renewal requires renewal_filed")
            if self.confidence not in ("high", "medium", "low"):
                raise ValueError("a found renewal requires confidence high/medium/low")
            if not self.citations:
                raise ValueError("a found renewal requires at least one citation")
            if not (self.reasoning and self.reasoning.strip()):
                raise ValueError("a found renewal requires reasoning")
        elif self.status == "unresolved":
            if not (self.reason and self.reason.strip()):   # unresolved carries no fact; a missing reason is fine
                self.reason = "The searched evidence did not establish the renewal status."
        else:
            raise ValueError("status must be 'found' or 'unresolved'")
        return self

    def to_answer(self) -> RenewalAnswer:
        if self.status == "unresolved":
            return Unresolved(reason=self.reason)
        return RenewalFinding(renewal_filed=self.renewal_filed, confidence=self.confidence,
                              reasoning=self.reasoning, citations=[_to_citation(c) for c in self.citations])


class _FlatRecordingYear(BaseModel):
    """Flat, Gemini-representable recording-year answer. Rule 4 enforced below."""

    status: str = Field(description="'found' if a passage establishes the year, else 'unresolved'.")
    first_published_year: Optional[int] = Field(None, description="Original first-release year. Required when found.")
    confidence: Optional[str] = Field(None, description="high, medium, or low. Required when found.")
    reasoning: Optional[str] = Field(None)
    citations: list[_FlatCitation] = Field(default_factory=list)
    reason: Optional[str] = Field(None)

    @model_validator(mode="after")
    def _rule4(self):
        if self.status == "found":
            if self.first_published_year is None:
                raise ValueError("a found year requires first_published_year")
            if not (1877 <= self.first_published_year <= CURRENT_YEAR):
                raise ValueError("first_published_year out of the recording era")
            if self.confidence not in ("high", "medium", "low"):
                raise ValueError("a found year requires confidence high/medium/low")
            if not self.citations:
                raise ValueError("a found year requires at least one citation")
            if not (self.reasoning and self.reasoning.strip()):
                raise ValueError("a found year requires reasoning")
        elif self.status == "unresolved":
            if not (self.reason and self.reason.strip()):
                self.reason = "The searched evidence did not establish the first-publication year."
        else:
            raise ValueError("status must be 'found' or 'unresolved'")
        return self

    def to_answer(self) -> RecordingYearAnswer:
        if self.status == "unresolved":
            return Unresolved(reason=self.reason)
        return RecordingYearFinding(first_published_year=self.first_published_year, confidence=self.confidence,
                                    reasoning=self.reasoning, citations=[_to_citation(c) for c in self.citations])


def _to_citation(c: _FlatCitation) -> Citation:
    # Canonical Citation validates the URL (HttpUrl); an invalid URL raises here
    # and the whole finding is discarded — no fact without a real source.
    return Citation(url=c.url, source_name=c.source_name, excerpt=c.excerpt, supports=c.supports)


COMMON_RULES = """\
You establish a single fact from evidence. You do not compute copyright terms.

Hard rules:
- Cite or abstain. Every value you report MUST quote the exact passage that
  establishes it, with the URL it came from. If you cannot quote a passage
  that states the fact, return status "unresolved". There is no middle
  option and no uncited fact.
- Do not infer. Commercial availability, a streaming link, a reissue, a
  Wikipedia mention, or a bare catalog number is NOT proof of the fact.
  A registration number is only a renewal if the record says it renews an
  earlier registration.
- Prefer authoritative records: the Catalog of Copyright Entries, the
  Stanford Copyright Renewal Database (authoritative for 1923-1963 book
  renewals; music renewals are patchier and may legitimately stay
  unresolved), the Discography of American Historical Recordings.
- You may call parallel_search to look for a primary record if the evidence
  provided is not sufficient. Abstaining honestly is better than reaching.
"""

RENEWAL_INSTRUCTION = COMMON_RULES + """
Question: was the US copyright in this musical work RENEWED in its 28th year?
US works published 1931-1963 lost protection after 28 years unless a renewal
was registered in year 28. Return renewal_filed=true only if a passage states
that a renewal was registered for THIS work in that window; renewal_filed=false
only if an authoritative source states no renewal exists; otherwise unresolved.
"""

RECORDING_YEAR_INSTRUCTION = COMMON_RULES + """
Question: in what year was THIS sound recording FIRST PUBLISHED (released)?
Not reissued, not recorded — first commercially released. Return a year only
if a passage states the original release; a later reissue date is not it.
"""


def _evidence_block(evidence: SearchOutcome) -> str:
    if not evidence or not evidence.hits:
        return "(no evidence was pre-fetched; use parallel_search)"
    lines = []
    for h in evidence.hits:
        for ex in (h.excerpts or ["(no excerpt)"]):
            lines.append(f"- URL: {h.url}\n  TITLE: {h.title}\n  EXCERPT: {ex}")
    return "\n".join(lines)


class GeminiReader:
    """Reader backed by an ADK LlmAgent. Implements agent.reader.Reader."""

    available = True

    def __init__(self, model: str = DEFAULT_MODEL, *, use_search_tool: bool = True):
        self.model = model
        self.use_search_tool = use_search_tool
        # google-genai routes to Vertex when this is set; ADC provides auth.
        if os.environ.get("GOOGLE_CLOUD_PROJECT") and not os.environ.get("GOOGLE_GENAI_USE_VERTEXAI"):
            os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "1"
        self.last_raw: Optional[str] = None   # raw model JSON of the most recent read, for inspection

    # --- public API (Reader protocol) -----------------------------------------

    def read_renewal(self, *, title, writers, year, evidence) -> RenewalAnswer:
        prompt = (
            f'WORK: "{title}"\nWRITERS: {", ".join(writers) or "unknown"}\n'
            f'US PUBLICATION YEAR: {year}\nRENEWAL WINDOW (year 28): {year + 27}-{year + 28}\n\n'
            f"EVIDENCE:\n{_evidence_block(evidence)}"
        )
        out = self._read(prompt, RENEWAL_INSTRUCTION, _FlatRenewal, "renewal")
        return out or Unresolved(reason="The reader produced no schema-valid finding.")

    def read_recording_year(self, *, title, artist, year_on_file, evidence) -> RecordingYearAnswer:
        prompt = (
            f'RECORDING: "{title}" performed by {artist}\n'
            f"EARLIEST RELEASE ON FILE (may be a reissue): {year_on_file or 'unknown'}\n\n"
            f"EVIDENCE:\n{_evidence_block(evidence)}"
        )
        out = self._read(prompt, RECORDING_YEAR_INSTRUCTION, _FlatRecordingYear, "recording_year")
        return out or Unresolved(reason="The reader produced no schema-valid finding.")

    # --- one agent run --------------------------------------------------------

    def _read(self, prompt: str, instruction: str, flat_model, label: str):
        agent = LlmAgent(
            name=f"reader_{label}",
            model=self.model,
            instruction=instruction,
            tools=[parallel_search] if self.use_search_tool else [],
            output_schema=flat_model,
            output_key="answer",
            generate_content_config=types.GenerateContentConfig(temperature=0.0),
        )
        try:
            raw = _run_agent_sync(agent, prompt)
        except Exception as e:              # network, auth, quota — degrade, never crash the request
            log.warning("reader run failed: %s", e)
            self.last_raw = f"<error: {type(e).__name__}: {e}>"
            return None
        self.last_raw = raw
        if not raw or not raw.strip():
            return None
        try:
            flat = flat_model.model_validate_json(raw)   # Rule 4 enforced by the model_validator
            return flat.to_answer()                      # canonical Citation validates the URL
        except (pydantic.ValidationError, ValueError) as e:
            log.warning("reader output failed schema validation (treated as no finding): %s", e)
            return None


def _final_text(events) -> str:
    text = ""
    for event in events:
        content = getattr(event, "content", None)
        if content and getattr(content, "parts", None):
            for part in content.parts:
                if getattr(part, "text", None) and not getattr(part, "thought", False):
                    text = part.text          # keep the last non-thought text (the final answer)
    return text


async def _run_agent_async(agent, prompt: str) -> str:
    runner = InMemoryRunner(agent=agent, app_name="can-i-use-this-reader")
    user_id, session_id = "reader", uuid.uuid4().hex
    await runner.session_service.create_session(
        app_name="can-i-use-this-reader", user_id=user_id, session_id=session_id)
    message = types.Content(role="user", parts=[types.Part(text=prompt)])
    events = []
    async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=message):
        events.append(event)
    # Prefer the validated value ADK stored in state; fall back to final text.
    session = await runner.session_service.get_session(
        app_name="can-i-use-this-reader", user_id=user_id, session_id=session_id)
    stored = (session.state or {}).get("answer") if session else None
    if stored is not None:
        return stored if isinstance(stored, str) else json.dumps(stored)
    return _final_text(events)


def _run_agent_sync(agent, prompt: str) -> str:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_run_agent_async(agent, prompt))
    # Already inside a loop (e.g. FastAPI): run in a private loop on a thread.
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(_run_agent_async(agent, prompt))).result()
