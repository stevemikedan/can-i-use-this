"""
Integration seams: combinations built in sequence, tested in isolation,
never run together. Each test pins one plausible interaction.
"""

from pipeline.mockworld import FakeParallel, handler
from pipeline.music import run_music
from research import parallel_client as pc
from schemas import (
    AssetQuery, AssetType, Confidence, DeterminationStatus, Duration, Intent,
    Jurisdiction, UserAnswer, Verdict,
)


def q(raw, intent=Intent.FILM_TV, j=Jurisdiction.US, duration=None, answers=None):
    return AssetQuery(raw_input=raw, intent=intent, jurisdiction=j, asset_type_hint=AssetType.MUSIC,
                      duration=duration, user_answers=answers or {})


def lv(resp, layer_id):
    return next(x for x in resp.layer_verdicts if x.layer_id == layer_id)


def det_of(resp, layer_id, j):
    return next(d for d in resp.all_determinations if d.layer_id == layer_id and d.jurisdiction == j)


def test_duration_with_rerecord(cache, transport, no_parallel):
    # Re-recording drops the master; the duration note still scales the
    # composition's band (UK, where Blue Moon's composition is protected).
    transport(handler)
    resp, _ = run_music(q("Blue Moon — Ella Fitzgerald", intent=Intent.RERECORD,
                          j=Jurisdiction.UK, duration=Duration.UNDER_10S))
    comp, rec = lv(resp, "composition"), lv(resp, "sound_recording")
    assert not rec.is_required and "composition only" in (rec.intent_note or "")
    assert comp.verdict is Verdict.LICENSE_REQUIRED
    assert "Compulsory mechanical" in comp.cost_band
    assert "low end" in comp.cost_band and "whether you need permission" in comp.cost_band


def test_print_with_answered_question(cache, transport, no_parallel):
    # Print requires the composition only; an attested not-renewed answer
    # resolves it public domain, and the roll-up goes clear even though the
    # recording (not required) stays protected.
    transport(handler)
    resp, _ = run_music(q("Blue Moon — Ella Fitzgerald", intent=Intent.PRINT,
                          answers={"composition:renewal": UserAnswer(
                              answer=False, attestation="Copyright Office online catalog, by title, no record")}))
    comp, rec = lv(resp, "composition"), lv(resp, "sound_recording")
    assert comp.verdict is Verdict.CLEAR and comp.determination.confidence is Confidence.MEDIUM
    assert not rec.is_required
    assert resp.overall_verdict is Verdict.CLEAR
    assert "composition:renewal" not in [u.question_id for u in resp.unresolved]


def test_enrichment_on_a_record_with_a_consistency_conflict(cache, transport, fake_parallel):
    # Over the Rainbow: the consistency conflict caps both dates; the
    # recording is still license_required, so enrichment runs. The conflict
    # question and the researched holders must coexist untouched.
    from pipeline.clearance import enrich_response
    transport(handler)
    resp, _ = run_music(q("Over the Rainbow — Judy Garland"))
    assert any(u.question_id == "consistency:recording_predates_composition" for u in resp.unresolved)
    pc.configure(FakeParallel())          # the task-capable fake
    try:
        out = enrich_response(resp)
    finally:
        pc.configure(None)
        pc._client_checked = False
    assert "sound_recording" in out["layers"]
    assert out["layers"]["sound_recording"]["holders"][0]["name"]["value"] == "Bluebird Songs"
    # enrichment did not disturb the record's own questions
    assert any(u.question_id == "consistency:recording_predates_composition" for u in resp.unresolved)


def test_user_answer_survives_jurisdiction_toggle(cache, transport, no_parallel):
    # The renewal answer is a US fact; toggling to the UK must neither crash
    # nor leak it into life+70. The US cell still reflects the answer.
    transport(handler)
    resp, _ = run_music(q("Blue Moon — Ella Fitzgerald", j=Jurisdiction.UK,
                          answers={"composition:renewal": UserAnswer(
                              answer=False, attestation="Copyright Office online catalog, by title, no record")}))
    uk = det_of(resp, "composition", Jurisdiction.UK)
    assert uk.status is DeterminationStatus.PROTECTED and uk.expiry_year == 2050
    assert uk.rule_id in ("uk_life_plus_70", "eu_life_plus_70")
    us = det_of(resp, "composition", Jurisdiction.US)
    assert us.status is DeterminationStatus.PUBLIC_DOMAIN and us.confidence is Confidence.MEDIUM
    assert "composition:renewal" not in [u.question_id for u in resp.unresolved]


def test_cc_layer_beside_a_blocked_layer(cache, transport, no_parallel):
    # Ghost Signal for education: the NC license covers the recording
    # (cleared with conditions), but the composition has no publication year
    # and blocks. A cleared layer must never mask a blocked one.
    transport(handler)
    resp, _ = run_music(q("Ghost Signal — Night Owl Static", intent=Intent.EDUCATION))
    rec, comp = lv(resp, "sound_recording"), lv(resp, "composition")
    assert rec.verdict is Verdict.CLEAR_WITH_CONDITIONS
    assert comp.verdict is Verdict.UNDETERMINED
    assert resp.overall_verdict is Verdict.UNDETERMINED
    assert "composition" in resp.overall_headline.lower()
