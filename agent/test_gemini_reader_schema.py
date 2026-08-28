"""
The Gemini reader's flat output schema — Gemini can't represent the
discriminated union, so Rule 4 is enforced by a validator on a flat model.
These tests lock that enforcement without calling Gemini.
"""

import pydantic
import pytest

from agent.gemini_reader import _FlatRecordingYear, _FlatRenewal
from agent.reader_schema import RenewalFinding, Unresolved
from schemas import Confidence


def cite():
    return {"url": "https://archive.org/details/cce-1962", "source_name": "CCE 1962",
            "excerpt": "BLUE MOON ... R290123 12Jan62", "supports": "renewal registration"}


def test_found_without_citation_is_rejected():
    with pytest.raises(pydantic.ValidationError):
        _FlatRenewal(status="found", renewal_filed=True, confidence="high", reasoning="x", citations=[])


def test_found_without_confidence_is_rejected():
    with pytest.raises(pydantic.ValidationError):
        _FlatRenewal(status="found", renewal_filed=True, reasoning="x", citations=[cite()])


def test_found_without_the_value_is_rejected():
    with pytest.raises(pydantic.ValidationError):
        _FlatRenewal(status="found", confidence="high", reasoning="x", citations=[cite()])


def test_bad_status_is_rejected():
    with pytest.raises(pydantic.ValidationError):
        _FlatRenewal(status="guessed", renewal_filed=True, confidence="high", reasoning="x", citations=[cite()])


def test_found_converts_to_a_cited_finding():
    ans = _FlatRenewal(status="found", renewal_filed=True, confidence="medium",
                       reasoning="R290123", citations=[cite()]).to_answer()
    assert isinstance(ans, RenewalFinding) and ans.renewal_filed is True
    assert ans.confidence is Confidence.MEDIUM.value or ans.confidence == "medium"
    assert len(ans.citations) == 1 and str(ans.citations[0].url).startswith("https://archive.org")


def test_unresolved_without_reason_is_accepted_with_a_default():
    # Rule 4 governs FOUND facts; an unresolved carries no fact, so a missing
    # reason is filled rather than rejected.
    ans = _FlatRenewal(status="unresolved").to_answer()
    assert isinstance(ans, Unresolved) and ans.reason


def test_found_year_out_of_era_is_rejected():
    with pytest.raises(pydantic.ValidationError):
        _FlatRecordingYear(status="found", first_published_year=1850, confidence="high",
                           reasoning="x", citations=[cite()])


def test_found_year_with_invalid_url_is_discarded_on_conversion():
    flat = _FlatRecordingYear(status="found", first_published_year=1961, confidence="high",
                              reasoning="Colpix 186", citations=[{**cite(), "url": "not-a-url"}])
    with pytest.raises(pydantic.ValidationError):
        flat.to_answer()      # canonical Citation validates the URL — no fact without a real source
