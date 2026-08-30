"""
The Gemini reader's flat output schema — Gemini can't represent the
discriminated union, so Rule 4 is enforced by a validator on a flat model.
These tests lock that enforcement without calling Gemini.
"""

import pydantic
import pytest

from agent.gemini_reader import _FlatRecordingYear, _FlatRenewal
from agent.reader_schema import RenewalFinding, Unresolved, renewal_to_fact
from schemas import Confidence


def cite(source_class="primary_record", **over):
    return {"url": "https://archive.org/details/cce-1962", "source_name": "CCE 1962",
            "source_class": source_class,
            "excerpt": "BLUE MOON ... R290123 12Jan62", "supports": "renewal registration", **over}


NOTICE = dict(url="https://api.pageplace.de/preview/x.pdf",
              source_name="permissions page of an Oxford University Press songbook",
              excerpt='"Blue Moon," copyright 1934, renewed 1961 Metro-Goldwyn-Mayer Inc.',
              supports="states the renewal")


def found(conf, cites):
    return _FlatRenewal(status="found", renewal_filed=True, confidence=conf, reasoning="x", citations=cites)


def test_confidence_is_capped_by_source_class():
    assert found("high", [cite("primary_record")]).confidence == "high"
    assert found("high", [cite("rightsholder_notice", **NOTICE)]).confidence == "medium"
    assert found("high", [cite("secondary")]).confidence == "low"
    assert found("medium", [cite("secondary")]).confidence == "low"
    # the best cited class sets the ceiling; a lower claim is left alone
    assert found("high", [cite("secondary"), cite("primary_record")]).confidence == "high"
    assert found("low", [cite("primary_record")]).confidence == "low"


def test_not_renewed_needs_a_primary_record():
    ok = _FlatRenewal(status="found", renewal_filed=False, confidence="high", reasoning="no entry",
                      citations=[cite("primary_record")])
    assert ok.renewal_filed is False and ok.confidence == "high"
    for cls in ("rightsholder_notice", "secondary"):
        with pytest.raises(pydantic.ValidationError):
            _FlatRenewal(status="found", renewal_filed=False, confidence="low", reasoning="a blog says so",
                         citations=[cite(cls, **(NOTICE if cls == "rightsholder_notice" else {}))])
    # the protected direction is conservative: a secondary source may still support it, at low
    assert found("high", [cite("secondary")]).confidence == "low"


def test_cap_applies_to_recording_year_too():
    flat = _FlatRecordingYear(status="found", first_published_year=1961, confidence="high",
                              reasoning="Colpix 186", citations=[cite("secondary")])
    assert flat.confidence == "low"


def test_unknown_source_class_is_rejected():
    with pytest.raises(pydantic.ValidationError):
        found("high", [cite("authoritative")])
    with pytest.raises(pydantic.ValidationError):
        found("high", [{k: v for k, v in cite().items() if k != "source_class"}])


def test_filename_source_name_is_rejected():
    for bad in ["0195305698.pdf", "index.html", "cce-1962",       # third = the URL's final path segment
                "0195305698.pdf (likely a songbook's permissions page)"]:
        with pytest.raises(pydantic.ValidationError):
            found("high", [cite(source_name=bad)])
    ok = found("high", [cite(source_name="Catalog of Copyright Entries, Music, Jan-Jun 1962")])
    assert ok.citations[0].source_name.startswith("Catalog")


def test_reader_answers_are_cached(monkeypatch):
    import agent.gemini_reader as gr
    from sources.cache import MemoryCache, set_default
    set_default(MemoryCache())
    calls = []
    raw = ('{"status": "found", "renewal_filed": true, "confidence": "high", "reasoning": "r", '
           '"citations": [{"url": "https://archive.org/x", "source_name": "CCE 1962", '
           '"source_class": "primary_record", "excerpt": "e", "supports": "s"}]}')
    monkeypatch.setattr(gr, "_run_agent_sync", lambda agent, prompt: (calls.append(1), raw)[1])
    try:
        r = gr.GeminiReader(use_search_tool=False)
        ev = None
        a1 = r.read_renewal(title="Blue Moon", writers=["Rodgers"], year=1934, evidence=ev)
        a2 = r.read_renewal(title="Blue Moon", writers=["Rodgers"], year=1934, evidence=ev)
        assert len(calls) == 1                      # the second read came from the cache
        assert a1 == a2 and a1.renewal_filed is True
        r2 = gr.GeminiReader(model="gemini-3.0-flash", use_search_tool=False)
        r2.read_renewal(title="Blue Moon", writers=["Rodgers"], year=1934, evidence=ev)
        assert len(calls) == 2                      # a different model is a different key
    finally:
        set_default(None)


def test_source_class_reaches_the_pipeline_source():
    primary = renewal_to_fact(found("high", [cite("primary_record")]).to_answer())
    notice = renewal_to_fact(found("high", [cite("rightsholder_notice", **NOTICE)]).to_answer())
    assert primary.sources[0].authoritative is True and primary.confidence is Confidence.HIGH
    assert notice.sources[0].authoritative is False and notice.confidence is Confidence.MEDIUM


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
