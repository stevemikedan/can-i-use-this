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
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import pydantic
from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import BaseModel, Field, model_validator

import hashlib

from research.music import renewal_record_system
from research.parallel_client import SearchOutcome
from sources.cache import get_cache
from rules import CURRENT_YEAR

from .reader_schema import (
    CONFIDENCE_CEILING, Citation, RecordingYearAnswer, RecordingYearFinding, RenewalAnswer,
    RenewalFinding, Unresolved, WriterCorroboration, WritersAnswer, WritersFinding, cap_confidence,
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

# A source_name that is (or contains) a filename / document id rather than a description.
_FILENAME_LIKE = re.compile(r"(^|[\s(\[])[\w.\-]+\.(pdf|html?|txt|djvu|xml|json|jpe?g|png)(?=$|[\s)\],;:])",
                            re.IGNORECASE)
_CLASS_RANK = {"primary_record": 3, "rightsholder_notice": 2, "secondary": 1}


def _looks_like_filename(name: str, url: str) -> bool:
    n = name.strip()
    if _FILENAME_LIKE.search(n):
        return True
    last = url.rstrip("/").rsplit("/", 1)[-1].split("?")[0]
    return bool(last) and n.lower() == last.lower()


class _FlatCitation(BaseModel):
    url: str = Field(description="The source URL the excerpt came from.")
    source_name: str = Field(description="What the source is, in words a person would recognise, e.g. "
                                         "'Catalog of Copyright Entries, Music, Jan-Jun 1962' or "
                                         "'permissions page of an Oxford University Press songbook'. "
                                         "Never a filename, URL or document id.")
    source_class: str = Field(description="primary_record, rightsholder_notice, or secondary — see the rules.")
    excerpt: str = Field(description="The exact passage that establishes the value.")
    supports: str = Field(description="One line: how this passage establishes the value.")

    @model_validator(mode="after")
    def _descriptive(self):
        if self.source_class not in CONFIDENCE_CEILING:
            raise ValueError(f"source_class must be one of {sorted(CONFIDENCE_CEILING)}")
        if _looks_like_filename(self.source_name, self.url):
            raise ValueError(f"source_name {self.source_name!r} is a filename, not a description")
        return self


def _capped(claimed: str, citations: list[_FlatCitation], label: str) -> str:
    """Confidence cannot exceed what the cited source classes support."""
    capped = cap_confidence(claimed, [c.source_class for c in citations])
    if capped != claimed:
        best = max((c.source_class for c in citations), key=_CLASS_RANK.__getitem__)
        log.warning("%s: confidence %s lowered to %s — best cited source class is %s",
                    label, claimed, capped, best)
    return capped


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
            self.confidence = _capped(self.confidence, self.citations, "renewal")
            # Rule 6, applied to the reader: "not renewed" is the public-domain
            # direction, so only an official record may establish it. A
            # secondary claim of non-renewal leaves the question open.
            if self.renewal_filed is False and not any(c.source_class == "primary_record" for c in self.citations):
                raise ValueError("renewal_filed=false requires a primary_record citation")
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
            self.confidence = _capped(self.confidence, self.citations, "recording_year")
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
    return Citation(url=c.url, source_name=c.source_name, source_class=c.source_class,
                    excerpt=c.excerpt, supports=c.supports)


def _fold_name(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", s or "").casefold() if c.isalnum())


class _FlatWriter(BaseModel):
    name: str = Field(description="The writer's name, exactly as given in the candidate list.")
    confidence: Optional[str] = Field(None, description="high, medium, or low.")
    citations: list[_FlatCitation] = Field(default_factory=list)

    @model_validator(mode="after")
    def _rule4(self):
        if not self.citations:
            raise ValueError("a corroborated writer requires at least one citation")
        if self.confidence not in ("high", "medium", "low"):
            raise ValueError("a corroborated writer requires confidence high/medium/low")
        self.confidence = _capped(self.confidence, self.citations, "writer")
        return self


class _FlatWriters(BaseModel):
    """Corroborate individual candidates. There is deliberately no field for
    'the list is complete' — that assertion is unrepresentable (asymmetry:
    an added writer errs toward protected; a completeness claim can shorten
    a term)."""

    status: str = Field(description="'found' if at least one candidate is corroborated, else 'unresolved'.")
    writers: list[_FlatWriter] = Field(default_factory=list,
                                       description="Only candidates the evidence corroborates. Omit the rest.")
    reasoning: Optional[str] = Field(None)
    reason: Optional[str] = Field(None)

    @model_validator(mode="after")
    def _rule4(self):
        if self.status == "found":
            if not self.writers:
                raise ValueError("a found answer requires at least one corroborated writer")
            if not (self.reasoning and self.reasoning.strip()):
                # The substance lives in the per-writer citations; the prose
                # field must not be able to torpedo a valid, cited answer.
                self.reasoning = "Corroborated from the cited passages."
        elif self.status == "unresolved":
            if not (self.reason and self.reason.strip()):
                self.reason = "The searched evidence did not corroborate any of the candidate writers."
        else:
            raise ValueError("status must be 'found' or 'unresolved'")
        return self

    def to_answer(self) -> WritersAnswer:
        if self.status == "unresolved":
            return Unresolved(reason=self.reason)
        return WritersFinding(reasoning=self.reasoning, writers=[
            WriterCorroboration(name=w.name, confidence=w.confidence,
                                citations=[_to_citation(c) for c in w.citations])
            for w in self.writers])


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

Every citation carries a source_class:
  primary_record      an official record of the fact itself: a Catalog of
                      Copyright Entries entry, a Copyright Office catalog
                      record, a renewal number (R or RE) with its date; for
                      recordings, DAHR or a label ledger / discography giving
                      the catalog or matrix number and the date.
  rightsholder_notice a copyright or permissions notice from the publisher
                      or rightsholder that states the fact, e.g. a songbook
                      credit reading "copyright 1934, renewed 1961".
  secondary           anything more indirect: books, articles, databases,
                      Wikipedia, sheet-music, retail and streaming pages.

Confidence follows the best source class you cite and never exceeds it:
  high   = at least one primary_record citation
  medium = at least one rightsholder_notice citation, no primary record
  low    = secondary sources only
A clear sentence on a secondary page is still a secondary source.

source_name says what the source is, in words a person would recognise:
"Catalog of Copyright Entries, Music, Jan-Jun 1962", "permissions page of an
Oxford University Press songbook". Never a filename, a URL or a document id,
not even in parentheses. If you cannot tell which document it is, describe
what the page is: "permissions page of a songbook (publisher preview)".
"""

RENEWAL_INSTRUCTION = COMMON_RULES + """
Question: was the US copyright in this musical work RENEWED in its 28th year?
US works published 1931-1963 lost protection after 28 years unless a renewal
was registered in year 28. Return renewal_filed=true only if a passage states
that a renewal was registered for THIS work in that window; renewal_filed=false
only if an authoritative source states no renewal exists; otherwise unresolved.

Where the record lives depends on the window. Renewals received by the
Copyright Office from 1978 on (windows of 1978 or later) are in its online
public catalog and carry RE-prefixed numbers; the scanned Catalog of
Copyright Entries volumes that web search reaches end in 1977 and will not
contain them. Renewals before 1978 carry R-prefixed numbers and appear in
the scanned CCE renewal sections. A registration that renews a DIFFERENT
work, arrangement or version is not a renewal of this one.
"""

RECORDING_YEAR_INSTRUCTION = COMMON_RULES + """
Question: in what year was THIS sound recording FIRST PUBLISHED (released)?
Not reissued, not recorded — first commercially released. Return a year only
if a passage states the original release; a later reissue date is not it.
"""


WRITERS_INSTRUCTION = COMMON_RULES + """
Question: which of the CANDIDATE writers can you corroborate as credited
writers (composer / lyricist) of this musical work?
- Corroborate only names from the candidate list, and only when a passage
  credits that person on THIS work. Omit any candidate you cannot
  corroborate — omission is the honest answer, never a negative claim.
- NEVER conclude that the writer list is complete. Absence of a name from
  the evidence is not evidence of absence.
- Source classes here: an ASCAP/BMI/SESAC repertory entry, an MLC entry, or
  a Catalog of Copyright Entries registration naming the writers is a
  primary_record; a published sheet-music or songbook credit is a
  rightsholder_notice; discographies, encyclopedias and articles are
  secondary.
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
        system = {
            "online": "the Copyright Office online public catalog (RE-numbered renewals received from 1978)",
            "scans": "the scanned Catalog of Copyright Entries renewal sections (R-numbered, pre-1978)",
            "both": (f"the scanned Catalog of Copyright Entries for a {year + 27} renewal, "
                     f"the Copyright Office online catalog for a {year + 28} one"),
        }[renewal_record_system(year)]
        prompt = (
            f'WORK: "{title}"\nWRITERS: {", ".join(writers) or "unknown"}\n'
            f'US PUBLICATION YEAR: {year}\nRENEWAL WINDOW (year 28): {year + 27}-{year + 28}\n'
            f'WHERE THE RECORD LIVES: {system}\n\n'
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

    def read_writers(self, *, title, year, candidates, evidence) -> WritersAnswer:
        prompt = (
            f'WORK: "{title}"' + (f' ({year})' if year else '') + chr(10)
            + f'CANDIDATE WRITERS: {"; ".join(candidates)}' + chr(10) + chr(10)
            + f"EVIDENCE:{chr(10)}{_evidence_block(evidence)}"
        )
        out = self._read(prompt, WRITERS_INSTRUCTION, _FlatWriters, "writers")
        if out is None:
            return Unresolved(reason="The reader produced no schema-valid finding.")
        if out.status == "found":
            allowed = {_fold_name(c) for c in candidates}
            kept = [w for w in out.writers if _fold_name(w.name) in allowed]
            dropped = len(out.writers) - len(kept)
            if dropped:
                log.warning("read_writers: dropped %d name(s) not in the candidate list", dropped)
            if not kept:
                return Unresolved(reason="No candidate writer was corroborated by the evidence.")
            out = WritersFinding(reasoning=out.reasoning, writers=kept)
        return out

    # --- one agent run --------------------------------------------------------

    READ_MAX_AGE_S = 7 * 86400   # same freshness policy as the searches the evidence came from

    def _read(self, prompt: str, instruction: str, flat_model, label: str):
        cache = get_cache()
        key = "reader:" + hashlib.sha1(json.dumps([label, self.model, instruction, prompt]).encode()).hexdigest()
        entry = cache.get(key, max_age_s=self.READ_MAX_AGE_S)
        if entry is not None:
            self.last_raw = entry.value.get("raw")
            return self._validate(flat_model, self.last_raw)
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
        if raw and raw.strip():
            cache.set(key, {"raw": raw})
        return self._validate(flat_model, raw)

    @staticmethod
    def _validate(flat_model, raw: Optional[str]):
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
