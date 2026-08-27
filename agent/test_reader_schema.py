"""
The reader schema makes an unsourced fact unrepresentable. These tests are
the enforcement of Rule 4 at the model boundary — they must never be relaxed
to accommodate a model that returns a fact without a citation.
"""

import pydantic
import pytest

from agent.reader_schema import (
    Citation, RecordingYearFinding, RenewalAnswer, RenewalFinding, Unresolved,
    recording_year_to_fact, renewal_to_fact,
)
from schemas import Confidence


def cite(url="https://archive.org/details/cce-1962"):
    return Citation(url=url, source_name="CCE 1962", excerpt="BLUE MOON ... R290123 12Jan62",
                    supports="Renewal registration R290123 for Blue Moon in 1962.")


# --- the core invariant: a found fact MUST carry evidence ----------------------

def test_found_finding_requires_at_least_one_citation():
    with pytest.raises(pydantic.ValidationError):
        RenewalFinding(renewal_filed=True, confidence="high", reasoning="renewed", citations=[])


def test_found_finding_rejects_missing_citations_field():
    with pytest.raises(pydantic.ValidationError):
        RenewalFinding(renewal_filed=True, confidence="high", reasoning="renewed")


def test_confidence_none_is_not_a_valid_found_confidence():
    # A fact asserted with no confidence is not a fact — "none" is not in the Literal.
    with pytest.raises(pydantic.ValidationError):
        RenewalFinding(renewal_filed=True, confidence="none", reasoning="x", citations=[cite()])


def test_citation_requires_a_nonempty_excerpt():
    with pytest.raises(pydantic.ValidationError):
        Citation(url="https://x.org", source_name="S", excerpt="", supports="y")


def test_citation_requires_a_real_url():
    with pytest.raises(pydantic.ValidationError):
        Citation(url="not-a-url", source_name="S", excerpt="e", supports="y")


def test_recording_year_is_bounded_to_the_recording_era():
    with pytest.raises(pydantic.ValidationError):
        RecordingYearFinding(first_published_year=1850, confidence="high", reasoning="x", citations=[cite()])


# --- no third option: the answer is a discriminated union of exactly two shapes --

def test_answer_is_found_or_unresolved_only():
    ta = pydantic.TypeAdapter(RenewalAnswer)
    found = ta.validate_python({"status": "found", "renewal_filed": True, "confidence": "high",
                                "reasoning": "R290123 filed 1962",
                                "citations": [cite().model_dump(mode="json")]})
    assert isinstance(found, RenewalFinding)
    un = ta.validate_python({"status": "unresolved", "reason": "no renewal record found in the searched volumes"})
    assert isinstance(un, Unresolved)
    with pytest.raises(pydantic.ValidationError):
        ta.validate_python({"status": "guessed", "renewal_filed": True})


def test_unresolved_has_no_slot_for_an_uncited_value():
    # There is no field on Unresolved to carry a value; an uncited answer cannot be expressed.
    assert "renewal_filed" not in Unresolved.model_fields
    assert set(Unresolved.model_fields) == {"status", "reason"}


# --- conversion to a pipeline fact preserves the sources -----------------------

def test_found_renewal_becomes_a_sourced_fact():
    fact = renewal_to_fact(RenewalFinding(renewal_filed=True, confidence="medium",
                                          reasoning="R290123", citations=[cite(), cite("https://cocatalog.loc.gov/x")]))
    assert fact is not None and fact.value is True and fact.confidence is Confidence.MEDIUM
    assert len(fact.sources) == 2 and all(s.method.value == "parallel_search" for s in fact.sources)
    assert all(s.retrieved_at is not None for s in fact.sources)   # Rule 4: sourced and dated


def test_unresolved_renewal_becomes_no_fact():
    assert renewal_to_fact(Unresolved(reason="not in the searched volumes")) is None


def test_recording_year_finding_becomes_a_sourced_int_fact():
    fact = recording_year_to_fact(RecordingYearFinding(first_published_year=1928, confidence="high",
                                                       reasoning="Victor matrix", citations=[cite()]))
    assert fact.value == 1928 and fact.sources
