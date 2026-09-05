"""
User-supplied answers to open questions, on a re-run.

The product hands people a research task — the open question says exactly what
to check and where. This is where the answer comes back in: a resubmitted
query carries `AssetQuery.user_answers` keyed by question_id, and the research
stage that owns the question turns the answer into a ResearchedFact instead of
searching.

CONFIDENCE POLICY (decided 31 Aug 2026)
=======================================
MEDIUM is the CEILING for anything user-supplied.

- A bare yes/no is an opinion -> LOW.
- An answer with an attestation is a research finding with a method behind
  it -> MEDIUM. For "renewed" that means an RE number and date: specific,
  falsifiable, verifiable by whoever reads the record later. For "not
  renewed" it means naming what was searched and where ("Copyright Office
  online catalog, by title and claimant, no renewal record") — the
  difference between an assertion and a finding.
- HIGH stays reserved for records we retrieved and read ourselves. A user
  citing "RE-123456, 12 Jan 1982" is about as reliable as a rightsholder
  notice, which is exactly where the calibration puts MEDIUM.

The Source is authoritative=False regardless: we did not retrieve it.

Direction still runs through LOW_CONFIDENCE_PD_RULE in determine.py: a bare
"not renewed" stays a lead and the verdict stays withheld; an attested one
may support a public-domain verdict at medium confidence.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional

from schemas import (
    AssetQuery, Confidence, ResearchMethod, ResearchedFact, Source, UserAnswer,
)

# The name every user-supplied Source carries. The UI keys its
# "asserted by you" marking off ResearchMethod.USER_PROVIDED, not this
# string, but the name is what a reader of the raw record sees.
USER_SOURCE_NAME = "Asserted by you"


def user_fact(ans: UserAnswer, says_yes: str, says_no: str) -> ResearchedFact:
    """One UserAnswer -> a ResearchedFact sourced to the user."""
    att = (ans.attestation or "").strip()
    conf = Confidence.MEDIUM if att else Confidence.LOW
    return ResearchedFact(
        value=ans.answer,
        confidence=conf,
        sources=[Source(
            name=USER_SOURCE_NAME, url=None, method=ResearchMethod.USER_PROVIDED,
            retrieved_at=datetime.now(timezone.utc),
            excerpt=att[:200] or None, authoritative=False,
        )],
        reasoning=(says_yes if ans.answer else says_no)
                  + (f" Attested: {att}" if att else " No source was given."),
    )


def _renewal(ans: UserAnswer) -> ResearchedFact:
    return user_fact(ans,
                     "You report the copyright was renewed.",
                     "You report that no renewal record was found.")


def user_year_fact(ans: UserAnswer, lead: str) -> ResearchedFact:
    """A user-supplied year -> a ResearchedFact[int] sourced to the user.
    MEDIUM with an attestation, LOW without; same policy as the boolean case."""
    att = (ans.attestation or "").strip()
    conf = Confidence.MEDIUM if att else Confidence.LOW
    return ResearchedFact(
        value=ans.value, confidence=conf,
        sources=[Source(name=USER_SOURCE_NAME, url=None, method=ResearchMethod.USER_PROVIDED,
                        retrieved_at=datetime.now(timezone.utc),
                        excerpt=att[:200] or None, authoritative=False)],
        reasoning=f"{lead} {ans.value}." + (f" Attested: {att}" if att else " No source was given."))


def _publication_year(ans: UserAnswer) -> ResearchedFact:
    return user_year_fact(ans, "You report the composition was first published in")


def _recording_year(ans: UserAnswer) -> ResearchedFact:
    return user_year_fact(ans, "You report the recording was first released in")


# question_id -> handler. One entry today (renewal is the flagship and the
# only boolean question); publication year and the rest are entries here,
# not a redesign.
HANDLERS: dict[str, Callable[[UserAnswer], ResearchedFact]] = {
    "composition:renewal": _renewal,
    "composition:publication_year": _publication_year,
    "sound_recording:first_publication": _recording_year,
}


def answered_fact(query: AssetQuery, question_id: str) -> Optional[ResearchedFact]:
    """The user's answer to this question as a fact, or None if unanswered."""
    ans = query.user_answers.get(question_id)
    handler = HANDLERS.get(question_id)
    if ans is None or handler is None:
        return None
    # A value question needs a value; a boolean question needs an answer.
    if handler in (_publication_year, _recording_year) and ans.value is None:
        return None
    if handler is _renewal and ans.answer is None:
        return None
    return handler(ans)
