"""
The reading step, wired into the pipeline via a FakeReader (no Gemini).

Proves the two windows the reader exists to close — renewal (1931-1963) and
the reissue-only recording date — resolve to real determinations when the
reader returns a cited finding, and stay undetermined when it returns
Unresolved. The NullReader default (fixtures) is covered by the acceptance
suite; here we exercise the resolving path.
"""

from agent.reader import FakeReader, NullReader
from agent.reader_schema import Citation, RecordingYearFinding, RenewalFinding, Unresolved
from pipeline.mockworld import handler
from pipeline.music import run_music
from schemas import (
    AssetQuery, AssetType, Confidence, DeterminationStatus, Intent, Jurisdiction, RecordingDateBasis,
    Verdict,
)


def q(raw, intent=Intent.FILM_TV, j=Jurisdiction.US):
    return AssetQuery(raw_input=raw, intent=intent, jurisdiction=j, asset_type_hint=AssetType.MUSIC)


def det(resp, layer, j):
    return next(d for d in resp.all_determinations if d.layer_id == layer and d.jurisdiction == j)


def cite(url="https://archive.org/details/cce-1962"):
    return Citation(url=url, source_name="CCE 1962", excerpt="BLUE MOON ... R290123 12Jan62",
                    supports="Renewal registration R290123 in the 1962 renewals volume.")


def test_renewal_renewed_makes_composition_protected(cache, transport, fake_parallel):
    transport(handler)
    reader = FakeReader(renewal=RenewalFinding(renewal_filed=True, confidence="high",
                                               reasoning="R290123 filed 1962", citations=[cite()]))
    resp, em = run_music(q("Blue Moon — Ella Fitzgerald"), reader=reader)
    comp = det(resp, "composition", Jurisdiction.US)
    assert comp.status is DeterminationStatus.PROTECTED and comp.expiry_year == 2030   # 1934 + 96
    assert comp.rule_id == "us_renewal_filed"
    assert comp.confidence is Confidence.HIGH
    # the renewal question is gone; the fact carries the citation (Rule 4)
    assert not any(u.question_id == "composition:renewal" for u in resp.unresolved)
    layer = next(l for l in resp.entity.layers if l.layer_id == "composition")
    assert layer.term_facts.renewal_filed.value is True
    assert layer.term_facts.renewal_filed.sources and layer.term_facts.renewal_filed.sources[0].url is not None
    assert reader.calls[0][0] == "renewal"
    assert any("Renewal resolved from evidence" in e.message for e in em.events)


def test_renewal_not_renewed_makes_composition_public_domain(cache, transport, fake_parallel):
    transport(handler)
    reader = FakeReader(renewal=RenewalFinding(renewal_filed=False, confidence="medium",
                                               reasoning="No renewal in the 1961-62 volumes", citations=[cite()]))
    resp, _ = run_music(q("Blue Moon — Ella Fitzgerald"), reader=reader)
    comp = det(resp, "composition", Jurisdiction.US)
    assert comp.status is DeterminationStatus.PUBLIC_DOMAIN and comp.expiry_year == 1963   # 1934 + 29
    assert comp.rule_id == "us_renewal_not_filed"


def _low(renewal_filed):
    return FakeReader(renewal=RenewalFinding(
        renewal_filed=renewal_filed, confidence="low", reasoning="a licensing-site FAQ says so",
        citations=[Citation(url="https://www.audiosparx.com/sa/faq_article.cfm/kbarticle_iid.2388",
                            source_name="AudioSparx knowledge-base article", source_class="secondary",
                            excerpt="The copyright was renewed for an additional 28 years", supports="states renewal")]))


def test_low_confidence_not_renewed_stays_open_as_a_lead(cache, transport, fake_parallel):
    """Asymmetry: low-confidence evidence never produces a public-domain verdict."""
    transport(handler)
    resp, _ = run_music(q("Blue Moon — Ella Fitzgerald"), reader=_low(False))
    comp = det(resp, "composition", Jurisdiction.US)
    assert comp.status is DeterminationStatus.UNDETERMINED
    assert comp.rule_id == "public_domain_withheld_low_confidence"
    assert comp.blocked_by == ["composition:renewal"]
    assert "us_renewal_not_filed" in comp.rule_explanation           # says which rule was withheld
    qn = next(u for u in resp.unresolved if u.question_id == "composition:renewal")
    assert "Lead, low confidence" in qn.why_it_matters and "not renewed" in qn.why_it_matters
    assert "audiosparx.com" in str(qn.resolution_links[0].url)      # the evidence, as a lead
    layer = next(l for l in resp.entity.layers if l.layer_id == "composition")
    assert layer.term_facts.renewal_filed.value is False              # the fact is kept, cited, low
    assert resp.overall_verdict is Verdict.UNDETERMINED
    assert "lead, not an answer" in resp.overall_headline


def test_low_confidence_renewed_may_still_say_protected(cache, transport, fake_parallel):
    """...but may support the protected direction — a wrong 'protected' costs a license, not a lawsuit."""
    transport(handler)
    resp, _ = run_music(q("Blue Moon — Ella Fitzgerald"), reader=_low(True))
    comp = det(resp, "composition", Jurisdiction.US)
    assert comp.status is DeterminationStatus.PROTECTED and comp.expiry_year == 2030
    assert comp.confidence is Confidence.LOW and comp.blocked_by == []
    # the question stays listed as a way to firm it up, with the lead attached
    qn = next(u for u in resp.unresolved if u.question_id == "composition:renewal")
    assert "Lead, low confidence" in qn.why_it_matters and "it was renewed" in qn.why_it_matters


def test_low_confidence_recording_year_withheld_only_where_it_means_public_domain(cache, transport, fake_parallel):
    transport(handler)
    reader = FakeReader(recording_year=RecordingYearFinding(
        first_published_year=1950, confidence="low", reasoning="Discogs user submission",
        citations=[Citation(url="https://www.discogs.com/release/1", source_name="Discogs",
                            source_class="secondary", excerpt="1950", supports="release year")]))
    resp, _ = run_music(q("Blue Moon — The Marcels"), reader=reader)
    us = det(resp, "sound_recording", Jurisdiction.US)          # 1947-1956: 110 years -> protected
    uk = det(resp, "sound_recording", Jurisdiction.UK)          # 70 years from 1950 -> would be PD
    assert us.status is DeterminationStatus.PROTECTED and us.confidence is Confidence.LOW
    assert uk.status is DeterminationStatus.UNDETERMINED and uk.rule_id == "public_domain_withheld_low_confidence"
    assert uk.blocked_by == ["sound_recording:first_publication"]
    qn = next(u for u in resp.unresolved if u.question_id == "sound_recording:first_publication")
    assert "original release was 1950" in qn.why_it_matters


def test_renewal_unresolved_keeps_the_question(cache, transport, fake_parallel):
    transport(handler)
    reader = FakeReader(renewal=Unresolved(reason="not found in the searched volumes"))
    resp, _ = run_music(q("Blue Moon — Ella Fitzgerald"), reader=reader)
    comp = det(resp, "composition", Jurisdiction.US)
    assert comp.status is DeterminationStatus.UNDETERMINED and comp.rule_id == "us_renewal_unknown"
    assert any(u.question_id == "composition:renewal" for u in resp.unresolved)


def test_reader_resolves_reissue_recording_year(cache, transport, fake_parallel):
    transport(handler)
    reader = FakeReader(recording_year=RecordingYearFinding(
        first_published_year=1961, confidence="high",
        reasoning="Colpix 186, released 1961", citations=[cite("https://adp.library.ucsb.edu/x")]))
    resp, _ = run_music(q("Blue Moon — The Marcels"), reader=reader)
    rec = det(resp, "sound_recording", Jurisdiction.US)
    assert rec.status is DeterminationStatus.PROTECTED and rec.expiry_year == 2067   # 1957-1972 fixed
    layer = next(l for l in resp.entity.layers if l.layer_id == "sound_recording")
    assert layer.term_facts.recording_date_basis is RecordingDateBasis.RESEARCHED
    assert layer.term_facts.recording_first_published_year.confidence is Confidence.HIGH
    assert not any(u.question_id == "sound_recording:first_publication" for u in resp.unresolved)


def test_null_reader_is_the_default_and_changes_nothing(cache, transport, fake_parallel):
    """Without a reader, both windows stay open — the acceptance-fixture baseline."""
    transport(handler)
    resp, _ = run_music(q("Blue Moon — Ella Fitzgerald"))          # default reader
    assert det(resp, "composition", Jurisdiction.US).rule_id == "us_renewal_unknown"
    assert isinstance(NullReader(), object) and NullReader().available is False
