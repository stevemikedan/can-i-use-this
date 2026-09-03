"""Pipeline tests on the mock MusicBrainz + Wikidata + Parallel world (pipeline/mockworld.py)."""

import httpx

from pipeline.mockworld import WEB_WORK, handler
from pipeline.music import parse_query, run_music
from schemas import (
    AssetQuery, AssetType, Confidence, DeterminationStatus, Intent, Jurisdiction,
    RecordingDateBasis, Verdict,
)


def q(raw, intent=Intent.FILM_TV, j=Jurisdiction.US):
    return AssetQuery(raw_input=raw, intent=intent, jurisdiction=j, asset_type_hint=AssetType.MUSIC)


def det(resp, layer, j):
    return next(d for d in resp.all_determinations if d.layer_id == layer and d.jurisdiction == j)


def test_parse_query():
    assert parse_query("West End Blues — Louis Armstrong") == ("West End Blues", "Louis Armstrong")
    assert parse_query("Blue Moon by The Marcels") == ("Blue Moon", "The Marcels")
    assert parse_query('"Take Five"') == ("Take Five", None)


def test_blocked_case_west_end_blues(cache, transport, no_parallel):
    transport(handler)
    resp, em = run_music(q("West End Blues — Louis Armstrong"))
    assert not resp.stop_for_disambiguation
    assert resp.overall_verdict is Verdict.LICENSE_REQUIRED
    blocking = [lv for lv in resp.layer_verdicts if lv.verdict is Verdict.LICENSE_REQUIRED]
    assert [lv.layer_id for lv in blocking] == ["sound_recording"]
    rec_us = det(resp, "sound_recording", Jurisdiction.US)
    assert rec_us.status is DeterminationStatus.PROTECTED and rec_us.expiry_year == 2029
    assert rec_us.rule_id == "us_sr_mma_1923_1946" and rec_us.confidence is Confidence.HIGH
    comp_us = det(resp, "composition", Jurisdiction.US)
    assert comp_us.status is DeterminationStatus.PUBLIC_DOMAIN and comp_us.expiry_year == 2024
    assert comp_us.confidence is Confidence.HIGH        # P577 1928 corroborated by MB begin 1928
    # picked the dated 1928 session, not the 1996 reissue entity that ranked first
    rec_layer = next(l for l in resp.entity.layers if l.layer_id == "sound_recording")
    assert rec_layer.identifiers[0].value == "web-1928"
    assert rec_layer.term_facts.recording_date_basis is RecordingDateBasis.DATED_PERFORMANCE
    assert resp.entity.resolution_confidence is Confidence.MEDIUM   # a 1939 session + undated entities exist
    # writers uncorroborated => UK/EU composition is BLOCKED, not merely low-confidence:
    # King Oliver alone gives 1938 -> PD 2009, but the sibling work credits Clarence
    # Williams (d. 1965) -> 2036. A partial list must never yield a confident verdict.
    comp_uk = det(resp, "composition", Jurisdiction.UK)
    assert comp_uk.status is DeterminationStatus.UNDETERMINED
    assert comp_uk.rule_id == "life_plus_70_writers_uncorroborated"
    assert comp_uk.blocked_by == ["composition:writers"]
    assert [u.question_id for u in resp.unresolved] == ["composition:writers"]
    qn = resp.unresolved[0]
    assert "Clarence Williams (d. 1965)" in qn.why_it_matters
    assert "2036" in qn.if_yes and "2009" in qn.if_no
    comp_layer = next(l for l in resp.entity.layers if l.layer_id == "composition")
    assert not comp_layer.term_facts.writer_list_corroborated
    assert comp_layer.term_facts.author_death_year.conflicting_values == ["1965 (Clarence Williams, per sibling MusicBrainz work)"]
    assert not any(l.source_name.startswith(("Catalog", "DAHR")) for l in resp.handoff_links)
    assert resp.cache_key == f"music:{WEB_WORK}:web-1928"
    assert resp.overall_confidence is Confidence.HIGH
    assert [e.stage.value for e in em.events][:2] == ["classify", "identify"]


def test_clean_case_rhapsody(cache, transport, no_parallel):
    transport(handler)
    resp, _ = run_music(q("Rhapsody in Blue — Paul Whiteman"))
    assert resp.overall_verdict is Verdict.CLEAR and resp.overall_confidence is Confidence.HIGH
    assert det(resp, "sound_recording", Jurisdiction.US).expiry_year == 2025
    assert det(resp, "composition", Jurisdiction.US).expiry_year == 2020
    assert det(resp, "composition", Jurisdiction.EU).expiry_year == 2008   # Gershwin d. 1937, corroborated
    assert resp.unresolved == []


def test_ambiguity_stops_before_research(cache, transport, no_parallel):
    calls = transport(handler)
    resp, em = run_music(q("Blue Moon"))
    assert resp.stop_for_disambiguation and resp.overall_verdict is Verdict.UNDETERMINED
    labels = [c.label for c in resp.entity.alternate_candidates]
    assert len(labels) == 3 and labels[-1].startswith("Tony Bennett")   # ordered by earliest release; 1999 last
    assert resp.entity.resolution_confidence is Confidence.LOW
    assert all(c.likelihood is Confidence.LOW for c in resp.entity.alternate_candidates)
    # One search plus one cached dated-performance probe per shown row -
    # the candidate dates must not come from reissue release dates. Still
    # no research, no rules.
    assert 1 + len(labels) <= len(calls) <= 1 + 2 * len(labels)
    assert not any(e.stage.value in ("research", "rules") for e in em.events)


def test_reissue_only_path_leaves_recording_undetermined(cache, transport, fake_parallel):
    transport(handler)
    resp, em = run_music(q("Blue Moon — The Marcels"))
    rec_us = det(resp, "sound_recording", Jurisdiction.US)
    assert rec_us.status is DeterminationStatus.UNDETERMINED
    assert rec_us.rule_id == "recording_pub_year_unconfirmed"
    assert rec_us.blocked_by == ["sound_recording:first_publication"]
    rec_layer = next(l for l in resp.entity.layers if l.layer_id == "sound_recording")
    assert rec_layer.term_facts.recording_date_basis is RecordingDateBasis.FIRST_RELEASE_DATE
    assert rec_layer.term_facts.recording_first_published_year.value == 1961      # earliest on file, LOW
    assert rec_layer.term_facts.recording_first_published_year.confidence is Confidence.LOW
    assert resp.entity.resolution_confidence is Confidence.LOW
    # Parallel Search ran on the primary path and its hits became resolution links
    assert any("DAHR" in c["objective"] for c in fake_parallel.calls)
    qn = next(u for u in resp.unresolved if u.question_id == "sound_recording:first_publication")
    assert [str(l.url) for l in qn.resolution_links][0].startswith("https://archive.org")
    assert any(l.source_name.startswith("DAHR") for l in resp.handoff_links)
    assert resp.overall_verdict is Verdict.UNDETERMINED


def test_renewal_question_names_the_record_system():
    from pipeline.music import renewal_extras, renewal_question
    scans = renewal_question("Blue Moon", 1934, [], ["R290123"])
    assert "scanned catalogs" in scans.why_it_matters and "R290123" in scans.why_it_matters
    assert scans.estimated_effort == "hours"
    assert renewal_extras("Blue Moon", 1934) == {"year": 1961, "year_after": 1962, "renewal_title": "Blue Moon"}

    online = renewal_question("Take Five", 1959, [], [])
    assert "1986–1987" in online.question
    assert "online public catalog" in online.why_it_matters and "RE-numbered" in online.why_it_matters
    assert "scanned Catalog of Copyright Entries" in online.why_it_matters   # says why the scans won't have it
    assert online.estimated_effort == "minutes"
    assert renewal_extras("Take Five", 1959) == {"year": 1986, "year_after": 1987, "renewal_online_title": "Take Five"}

    both = renewal_question("x", 1950, [], [])
    assert "straddles 1978" in both.why_it_matters
    assert set(renewal_extras("x", 1950)) == {"year", "year_after", "renewal_title", "renewal_online_title"}


def test_renewal_window_composition(cache, transport, fake_parallel):
    transport(handler)
    resp, em = run_music(q("Blue Moon — Ella Fitzgerald"))
    comp_us = det(resp, "composition", Jurisdiction.US)
    assert comp_us.status is DeterminationStatus.UNDETERMINED and comp_us.rule_id == "us_renewal_unknown"
    assert comp_us.blocked_by == ["composition:renewal"]
    qn = next(u for u in resp.unresolved if u.question_id == "composition:renewal")
    assert "1961–1962" in qn.question and qn.estimated_effort == "hours"
    assert "R290123" in qn.why_it_matters                       # renewal number spotted in a Search excerpt
    assert any("renewal" in c["objective"] for c in fake_parallel.calls)
    assert any(l.source_name.startswith("Catalog") for l in resp.handoff_links)
    # corroborated writers => UK/EU life+70 is confident and no writers question
    comp_uk = det(resp, "composition", Jurisdiction.UK)
    assert comp_uk.status is DeterminationStatus.PROTECTED and comp_uk.expiry_year == 2050
    assert comp_uk.confidence is Confidence.HIGH
    assert "composition:writers" not in [u.question_id for u in resp.unresolved]
    # Ella's dated 1961 session: protected to 2067 in the US; in the EU the 50-year
    # term expired 2012 and the 2013 extension did not revive it
    assert det(resp, "sound_recording", Jurisdiction.US).expiry_year == 2067
    eu = det(resp, "sound_recording", Jurisdiction.EU)
    assert eu.status is DeterminationStatus.PUBLIC_DOMAIN and eu.expiry_year == 2012 and eu.rule_id == "eu_sr_pre_1963"
    assert resp.overall_verdict is Verdict.UNDETERMINED
    assert "renewal" in resp.overall_headline.lower() or "blocked" in resp.overall_headline.lower()


def test_tier3_degrades_without_key(cache, transport, no_parallel):
    transport(handler)
    resp, em = run_music(q("Blue Moon — The Marcels"))
    degraded = [e for e in em.events if e.degraded]
    assert degraded and all("PARALLEL_API_KEY" in (e.error_message or "") for e in degraded)
    qn = next(u for u in resp.unresolved if u.question_id == "sound_recording:first_publication")
    assert qn.resolution_links == [] and qn.search_terms          # question still emitted, just without hits


def test_rerecord_intent_excludes_the_master(cache, transport, no_parallel):
    transport(handler)
    resp, _ = run_music(q("West End Blues — Louis Armstrong", intent=Intent.RERECORD))
    rec = next(lv for lv in resp.layer_verdicts if lv.layer_id == "sound_recording")
    assert not rec.is_required and rec.intent_note
    assert resp.overall_verdict is Verdict.CLEAR


def test_uk_jurisdiction_flip(cache, transport, no_parallel):
    """US blocks on the recording; the UK/EU would block on the composition — and
    with an uncorroborated writer list the composition is UNDETERMINED, never CLEAR."""
    transport(handler)
    resp, _ = run_music(q("West End Blues — Louis Armstrong", j=Jurisdiction.UK))
    rec = next(lv for lv in resp.layer_verdicts if lv.layer_id == "sound_recording")
    assert rec.verdict is Verdict.CLEAR                              # 1928 recording: 50-year term long expired
    comp = next(lv for lv in resp.layer_verdicts if lv.layer_id == "composition")
    assert comp.verdict is Verdict.UNDETERMINED
    assert resp.overall_verdict is Verdict.UNDETERMINED and resp.overall_confidence is Confidence.NONE
    assert "composition" in resp.overall_headline


def test_work_search_failure_falls_back_to_sweep(cache, transport, no_parallel):
    def h(req):
        if req.url.path == "/ws/2/work" and "query" in req.url.params:
            return httpx.Response(503)
        return handler(req)
    transport(h)
    resp, em = run_music(q("West End Blues — Louis Armstrong"))
    assert resp.overall_verdict is Verdict.LICENSE_REQUIRED
    assert any("sweep" in e.message for e in em.events)


def test_artist_not_credited(cache, transport, no_parallel):
    transport(handler)
    resp, _ = run_music(q("West End Blues — Nobody"))
    assert resp.overall_verdict is Verdict.UNDETERMINED and "was found" in resp.overall_headline
    assert resp.unresolved[0].question_id == "resolve:not_found"


# --- upstream failure vs not-found, and the post-1978 publication floor (Aug 31) ---

def test_upstream_failure_is_not_not_found(cache, transport, sleeps, no_parallel):
    """A 503 from MusicBrainz routes to retry, never to 'refine your query'."""
    import httpx
    from pipeline.music import run_music
    from schemas import AssetQuery, AssetType, Intent, Jurisdiction
    transport(lambda req: httpx.Response(503, text="service unavailable"))
    resp, _ = run_music(AssetQuery(raw_input="Aliens Exist — blink-182", intent=Intent.FILM_TV,
                                   jurisdiction=Jurisdiction.US, asset_type_hint=AssetType.MUSIC))
    assert "could not be reached" in resp.overall_headline
    assert resp.unresolved[0].question_id == "resolve:upstream_failure"
    assert "transient" in resp.unresolved[0].why_it_matters
    assert "_ssl" not in resp.unresolved[0].why_it_matters and "ConnectError" not in resp.unresolved[0].why_it_matters


def test_publication_floor_only_post_1978_dated():
    from datetime import datetime, timezone
    from pipeline.music import publication_floor
    from schemas import Confidence, RecordingDateBasis, ResearchMethod, ResearchedFact, Source, TermFacts
    src = Source(name="MusicBrainz", url="https://musicbrainz.org/recording/x",
                 method=ResearchMethod.DIRECT_API, retrieved_at=datetime.now(timezone.utc))
    def tf(year, basis):
        t = TermFacts()
        if year is not None:
            t.recording_first_published_year = ResearchedFact(value=year, confidence=Confidence.MEDIUM, sources=[src])
        t.recording_date_basis = basis
        return t
    f = publication_floor(tf(1999, RecordingDateBasis.DATED_PERFORMANCE))
    assert f is not None and f.value == 1999 and f.confidence is Confidence.LOW
    assert "17 U.S.C." in f.reasoning
    # the researched original release counts too — the Aliens Exist regression
    f2 = publication_floor(tf(1999, RecordingDateBasis.RESEARCHED))
    assert f2 is not None and f2.value == 1999
    # pre-1978: the 1909-Act premise fails, so no inference is made
    assert publication_floor(tf(1960, RecordingDateBasis.DATED_PERFORMANCE)) is None
    # untrustworthy basis or no year: never
    assert publication_floor(tf(1999, RecordingDateBasis.FIRST_RELEASE_DATE)) is None
    assert publication_floor(tf(None, RecordingDateBasis.DATED_PERFORMANCE)) is None


def test_not_found_wrong_artist_suggests_real_artists(cache, transport, sleeps, no_parallel):
    """Title exists, artist doesn't match: suggest the artists who did record it — real MB hits only."""
    from pipeline.mockworld import handler
    from pipeline.music import run_music
    from schemas import AssetQuery, AssetType, Intent, Jurisdiction
    transport(handler)
    resp, _ = run_music(AssetQuery(raw_input="West End Blues — The Beatles", intent=Intent.FILM_TV,
                                   jurisdiction=Jurisdiction.US, asset_type_hint=AssetType.MUSIC))
    assert resp.unresolved[0].question_id == "resolve:not_found"
    assert "Artists who did record it are listed below" in resp.overall_headline
    sugg = resp.entity.alternate_candidates
    assert sugg and any("Armstrong" in c.label for c in sugg)
    assert all(c.identifiers and c.identifiers[0].scheme == "musicbrainz_recording" for c in sugg)


def test_not_found_unknown_title_suggests_nothing_invented(cache, transport, sleeps, no_parallel):
    """A title even fuzzy search can't find yields an empty suggestion list, never a guess."""
    from pipeline.mockworld import handler
    from pipeline.music import run_music
    from schemas import AssetQuery, AssetType, Intent, Jurisdiction
    transport(handler)
    resp, _ = run_music(AssetQuery(raw_input="Zxqvzzz Nonesuch Blues", intent=Intent.FILM_TV,
                                   jurisdiction=Jurisdiction.US, asset_type_hint=AssetType.MUSIC))
    assert resp.unresolved[0].question_id == "resolve:not_found"
    assert resp.entity.alternate_candidates == []


# --- Search-backed writer corroboration (31 Aug): add or abstain, never conclude complete ---

def _writer_finding(*names):
    from agent.reader_schema import Citation, WriterCorroboration, WritersFinding
    def cite(n):
        return Citation(url="https://www.ascap.com/repertory", source_name="ASCAP ACE repertory",
                        source_class="primary_record", excerpt=f"{n} credited on this work",
                        supports="repertory entry names the writer")
    return WritersFinding(reasoning="repertory entries name the writers",
                          writers=[WriterCorroboration(name=n, confidence="high", citations=[cite(n)]) for n in names])


def test_writer_corroboration_lifts_the_uk_block(cache, transport, sleeps, fake_parallel):
    """Every candidate corroborated: the union list stands, life+70 runs from Williams (d. 1965)."""
    from agent.reader import FakeReader
    from pipeline.mockworld import handler
    from pipeline.music import run_music
    from schemas import AssetQuery, AssetType, DeterminationStatus, Intent, Jurisdiction
    transport(handler)
    reader = FakeReader(writers=_writer_finding("King Oliver", "Clarence Williams"))
    resp, em = run_music(AssetQuery(raw_input="West End Blues — Louis Armstrong", intent=Intent.FILM_TV,
                                    jurisdiction=Jurisdiction.UK, asset_type_hint=AssetType.MUSIC), reader=reader)
    uk = next(d for d in resp.all_determinations if d.layer_id == "composition" and d.jurisdiction == Jurisdiction.UK)
    assert uk.status is DeterminationStatus.PROTECTED and uk.expiry_year == 2036   # 1965 + 71
    assert not any(u.question_id == "composition:writers" for u in resp.unresolved)
    comp = next(l for l in resp.entity.layers if l.layer_id == "composition")
    assert comp.term_facts.writer_list_corroborated is True
    assert comp.term_facts.author_death_year.value == 1965
    names = {h.name.value for h in comp.holders}
    assert names == {"King Oliver", "Clarence Williams"}
    # the mandated integration, legible: one ledger line per search query, then the hit count
    q_lines = [e for e in em.events if e.message.startswith("Parallel Search — writer credits") and e.detail]
    assert len(q_lines) >= 3 and any("West End Blues" in e.detail for e in q_lines)
    assert any("source passages returned" in e.message for e in em.events)


def test_partial_corroboration_never_lifts_the_block(cache, transport, sleeps, fake_parallel):
    """Only Oliver corroborated: Williams stays a candidate, the block and the question stay."""
    from agent.reader import FakeReader
    from pipeline.mockworld import handler
    from pipeline.music import run_music
    from schemas import AssetQuery, AssetType, DeterminationStatus, Intent, Jurisdiction
    transport(handler)
    reader = FakeReader(writers=_writer_finding("King Oliver"))
    resp, _ = run_music(AssetQuery(raw_input="West End Blues — Louis Armstrong", intent=Intent.FILM_TV,
                                   jurisdiction=Jurisdiction.UK, asset_type_hint=AssetType.MUSIC), reader=reader)
    uk = next(d for d in resp.all_determinations if d.layer_id == "composition" and d.jurisdiction == Jurisdiction.UK)
    assert uk.status is DeterminationStatus.UNDETERMINED
    qn = next(u for u in resp.unresolved if u.question_id == "composition:writers")
    assert "Clarence Williams" in qn.why_it_matters
    assert qn.resolution_links                                  # the search hits ride the question


# --- the dead-author derivative signal (31 Aug): detect and disclose ---

def test_writer_dead_before_publication_flags_a_likely_original():
    from pipeline.music import Writer, derivative_question
    q = derivative_question("Mack the Knife", 1954, [Writer("Kurt Weill", "composer", death_year=1950)])
    assert q.question_id == "composition:derivative"
    assert "Kurt Weill (d. 1950)" in q.why_it_matters and "1954" in q.why_it_matters
    assert "translation" in q.why_it_matters
    assert "cleared (or found expired) separately" in q.if_yes
    assert q.estimated_effort == "minutes"


def test_derivative_signal_not_raised_for_ordinary_works(cache, transport, sleeps, fake_parallel):
    """Oliver died 1938, ten years after the 1928 publication — no flag."""
    from pipeline.mockworld import handler
    from pipeline.music import run_music
    from schemas import AssetQuery, AssetType, Intent, Jurisdiction
    transport(handler)
    resp, _ = run_music(AssetQuery(raw_input="West End Blues — Louis Armstrong", intent=Intent.FILM_TV,
                                   jurisdiction=Jurisdiction.US, asset_type_hint=AssetType.MUSIC))
    assert not any(u.question_id == "composition:derivative" for u in resp.unresolved)


def test_dated_later_take_does_not_outrank_an_earlier_release(cache, transport, sleeps, fake_parallel):
    """Only a 2001 live take is dated; the studio original was released 1999.
    The guard falls to the release-date path instead of crowning the live take."""
    from pipeline.mockworld import handler
    from pipeline.music import run_music
    from schemas import AssetQuery, AssetType, Intent, Jurisdiction, RecordingDateBasis
    transport(handler)
    resp, _ = run_music(AssetQuery(raw_input="Later Take — The Guards", intent=Intent.FILM_TV,
                                   jurisdiction=Jurisdiction.US, asset_type_hint=AssetType.MUSIC))
    rec = next(l for l in resp.entity.layers if l.layer_id == "sound_recording")
    tf = rec.term_facts
    assert tf.recording_date_basis is RecordingDateBasis.FIRST_RELEASE_DATE
    assert tf.recording_first_published_year.value == 1999
    assert "belongs to a later take" in tf.recording_first_published_year.sources[0].excerpt
    # the release-date path keeps its honesty: question open, Tier 3 asked
    assert any(u.question_id == "sound_recording:first_publication" for u in resp.unresolved)


def test_every_blocked_determination_has_an_open_question():
    """The core promise: a blocked layer always names what would unblock it."""
    from agent.freeze_fixtures import mock_environment, query_for
    from pipeline import mockworld
    from pipeline.music import run_music
    from schemas import DeterminationStatus
    for name, case in mockworld.CASES.items():
        with mock_environment():
            resp, _ = run_music(query_for(case))
        if resp.stop_for_disambiguation or not resp.entity.layers:
            continue
        qids = {u.question_id for u in resp.unresolved}
        for det in resp.all_determinations:
            if det.status is DeterminationStatus.UNDETERMINED:
                assert det.blocked_by, f"{name}: {det.layer_id}/{det.jurisdiction} blocked with no question"
                assert set(det.blocked_by) <= qids, f"{name}: blocked_by points at a missing question"


def test_derivative_flag_gates_life_plus_70():
    """A confident life+70 from disputed authors is the reissue-date failure class."""
    from pipeline.determine import determine_composition
    from schemas import (Confidence, DeterminationStatus, Jurisdiction, ResearchedFact,
                         RightsLayer, RightsLayerKind, Source, ResearchMethod)
    from datetime import datetime, timezone
    layer = RightsLayer(layer_id="composition", kind=RightsLayerKind.COMPOSITION, label="Composition")
    layer.term_facts.writer_list_corroborated = True
    layer.term_facts.author_death_year = ResearchedFact(
        value=1956, confidence=Confidence.HIGH,
        sources=[Source(name="Wikidata", url="https://www.wikidata.org/wiki/Q",
                        method=ResearchMethod.DIRECT_API, retrieved_at=datetime.now(timezone.utc))])
    qids = {"derivative": "composition:derivative", "author_death_year": "composition:writers"}
    det = determine_composition(layer, Jurisdiction.UK, qids, [1950, 1956])
    assert det.status is DeterminationStatus.UNDETERMINED
    assert det.rule_id == "life_plus_70_authorship_disputed"
    assert det.blocked_by == ["composition:derivative"]
    # without the flag, the same facts compute normally
    det2 = determine_composition(layer, Jurisdiction.UK, {"author_death_year": "x"}, [1950, 1956])
    assert det2.status is DeterminationStatus.PROTECTED and det2.expiry_year == 2027


# --- user-supplied answers (pipeline/user_facts.py) -------------------------------
#
# The renewal question, answered on a re-run. MEDIUM ceiling with an
# attestation, LOW without; authoritative=False always; a bare "not renewed"
# stays withheld by LOW_CONFIDENCE_PD_RULE.

def q_answered(answer, attestation=None):
    from schemas import UserAnswer
    return AssetQuery(raw_input="Blue Moon \u2014 Ella Fitzgerald", intent=Intent.FILM_TV,
                      jurisdiction=Jurisdiction.US, asset_type_hint=AssetType.MUSIC,
                      user_answers={"composition:renewal": UserAnswer(answer=answer, attestation=attestation)})


def test_user_answer_renewed_attested(cache, transport, no_parallel):
    # "Yes, renewed. RE-123-456, 12 Jan 1962" -> protected at MEDIUM, no
    # search run (no_parallel would degrade if it were), question closed.
    transport(handler)
    resp, em = run_music(q_answered(True, "RE-123-456, renewed 12 Jan 1962"))
    comp = det(resp, "composition", Jurisdiction.US)
    assert comp.status is DeterminationStatus.PROTECTED and comp.expiry_year == 2030
    assert comp.rule_id == "us_renewal_filed" and comp.confidence is Confidence.MEDIUM
    assert "composition:renewal" not in [u.question_id for u in resp.unresolved]
    layer = next(l for l in resp.entity.layers if l.layer_id == "composition")
    src = layer.term_facts.renewal_filed.sources[0]
    assert src.method.value == "user_provided" and not src.authoritative
    assert "RE-123-456" in src.excerpt


def test_user_answer_not_renewed_attested(cache, transport, no_parallel):
    # An attested "no" is a finding, not an opinion: MEDIUM clears the
    # asymmetry guard and the composition resolves public domain at MEDIUM.
    transport(handler)
    resp, em = run_music(q_answered(False, "Copyright Office online catalog, searched by title and claimant, no renewal record"))
    comp = det(resp, "composition", Jurisdiction.US)
    assert comp.status is DeterminationStatus.PUBLIC_DOMAIN and comp.expiry_year == 1963
    assert comp.rule_id == "us_renewal_not_filed" and comp.confidence is Confidence.MEDIUM
    assert "composition:renewal" not in [u.question_id for u in resp.unresolved]


def test_user_answer_not_renewed_bare_stays_withheld(cache, transport, no_parallel):
    # A bare "no" is an opinion: LOW, withheld by LOW_CONFIDENCE_PD_RULE.
    # The verdict does not move to clear; the answer is recorded as a lead
    # on the still-open question.
    transport(handler)
    resp, em = run_music(q_answered(False))
    comp = det(resp, "composition", Jurisdiction.US)
    assert comp.status is DeterminationStatus.UNDETERMINED
    assert comp.rule_id == "public_domain_withheld_low_confidence"
    assert comp.blocked_by == ["composition:renewal"]
    qn = next(u for u in resp.unresolved if u.question_id == "composition:renewal")
    assert "You answered" in qn.why_it_matters and "without naming a source" in qn.why_it_matters


def test_user_answer_renewed_bare_protected_low(cache, transport, no_parallel):
    # A bare "yes" moves toward protected — the safe direction — at LOW,
    # and the question stays open with the answer as a lead.
    transport(handler)
    resp, em = run_music(q_answered(True))
    comp = det(resp, "composition", Jurisdiction.US)
    assert comp.status is DeterminationStatus.PROTECTED and comp.expiry_year == 2030
    assert comp.confidence is Confidence.LOW
    qn = next(u for u in resp.unresolved if u.question_id == "composition:renewal")
    assert "You answered" in qn.why_it_matters


# --- the consistency layer (pipeline/consistency.py) ------------------------------
#
# Two facts that constrain each other, each defensible alone, cannot be
# silently co-trusted. Conflicts degrade confidence and open a question.

def test_rainbow_recording_predates_composition(cache, transport, fake_parallel):
    # Garland's session is dated 1938; Wikidata says the composition was
    # published 1939. The pair is impossible as first-publication facts.
    transport(handler)
    resp, em = run_music(q("Over the Rainbow \u2014 Judy Garland"))
    qn = next(u for u in resp.unresolved if u.question_id == "consistency:recording_predates_composition")
    assert "1938" in qn.why_it_matters and "1939" in qn.why_it_matters
    assert "session" in qn.why_it_matters and "release" in qn.why_it_matters
    assert set(qn.affects_layer_ids) == {"composition", "sound_recording"}
    comp = next(l for l in resp.entity.layers if l.layer_id == "composition")
    rec_l = next(l for l in resp.entity.layers if l.layer_id == "sound_recording")
    assert comp.term_facts.first_publication_year.confidence is Confidence.LOW
    assert rec_l.term_facts.recording_first_published_year.confidence is Confidence.LOW
    assert "CONSISTENCY" in comp.term_facts.first_publication_year.reasoning
    # degrade, not block: the recording is still protected (the safe
    # direction), just at low confidence
    rec_us = det(resp, "sound_recording", Jurisdiction.US)
    assert rec_us.status is DeterminationStatus.PROTECTED and rec_us.confidence is Confidence.LOW


def test_consistency_invariant_across_cases(cache, transport, fake_parallel):
    # The invariant, run against every acceptance case: a recording dated
    # before its composition never passes without an open consistency
    # question. Modeled on blocked-implies-question.
    from pipeline.mockworld import CASES
    transport(handler)
    for name, kw in CASES.items():
        resp, em = run_music(AssetQuery(raw_input=kw["raw_input"], intent=Intent.FILM_TV,
                                        jurisdiction=Jurisdiction.US, asset_type_hint=AssetType.MUSIC))
        if resp.stop_for_disambiguation or not resp.entity.layers or resp.entity.layers[0] is None:
            continue
        comp = next((l for l in resp.entity.layers if l and l.layer_id == "composition"), None)
        rec_l = next((l for l in resp.entity.layers if l and l.layer_id == "sound_recording"), None)
        cy = comp.term_facts.first_publication_year if comp else None
        ry = rec_l.term_facts.recording_first_published_year if rec_l else None
        if cy is not None and ry is not None and ry.value < cy.value:
            assert any(u.question_id == "consistency:recording_predates_composition"
                       for u in resp.unresolved), f"case {name}: impossible pair passed silently"


def test_consistency_death_year_implausible():
    from types import SimpleNamespace
    from pipeline.consistency import check_death_year_plausible
    from pipeline.music import Emitter
    from schemas import RightsLayer, RightsLayerKind
    layer = RightsLayer(layer_id="composition", kind=RightsLayerKind.COMPOSITION, label="Composition")
    w = SimpleNamespace(name="Clarence Williams", death_year=2021)
    run = SimpleNamespace(cf=SimpleNamespace(year=1900, writers=[w], title="X"), title="X",
                          composition=layer, comp_questions=[], comp_question_ids={}, em=Emitter())
    check_death_year_plausible(run)
    assert run.comp_questions and run.comp_questions[0].question_id == "consistency:death_year_implausible"
    assert "2021" in run.comp_questions[0].why_it_matters


def test_consistency_country_and_conflict_cap():
    from types import SimpleNamespace
    from pipeline.consistency import check_conflicting_values_cap, check_publication_country
    from pipeline.music import Emitter
    from schemas import ResearchedFact, ResearchMethod, RightsLayer, RightsLayerKind, Source
    from datetime import datetime, timezone
    src = Source(name="x", method=ResearchMethod.DIRECT_API, retrieved_at=datetime.now(timezone.utc))
    comp = RightsLayer(layer_id="composition", kind=RightsLayerKind.COMPOSITION, label="Composition")
    comp.term_facts.first_publication_country = ResearchedFact(value="DE", confidence=Confidence.MEDIUM, sources=[src])
    comp.term_facts.first_publication_year = ResearchedFact(
        value=1930, confidence=Confidence.HIGH, sources=[src], conflicting_values=["1929 (per X)"])
    run = SimpleNamespace(cf=SimpleNamespace(title="X"), title="X", composition=comp, recording=None,
                          comp_questions=[], comp_question_ids={}, em=Emitter())
    check_publication_country(run)
    assert any(u.question_id == "consistency:publication_country" for u in run.comp_questions)
    check_conflicting_values_cap(run)
    assert comp.term_facts.first_publication_year.confidence is Confidence.MEDIUM
    assert "disagreed" in comp.term_facts.first_publication_year.reasoning


# --- Tier 1: the static license table (rules/licenses.py) -------------------------

def test_cc_by_sa_clears_both_layers_with_conditions(cache, transport, no_parallel):
    # A CC BY-SA release: license relations on the recording and the work.
    # Tier 1 settles both layers instantly; no search, no reader, no dates.
    transport(handler)
    resp, em = run_music(q("Golden Hour \u2014 Night Owl Static"))
    assert resp.overall_verdict is Verdict.CLEAR_WITH_CONDITIONS
    for lv in resp.layer_verdicts:
        assert lv.verdict is Verdict.CLEAR_WITH_CONDITIONS
        assert lv.determination.rule_id == "license_cc_by_sa"
        assert lv.determination.confidence is Confidence.MEDIUM
        assert "credit the creator" in lv.determination.rule_explanation
    for layer in resp.entity.layers:
        assert layer.existing_license is not None
        assert layer.existing_license.sources[0].method.value == "rights_uri"
    assert "license" in resp.overall_headline.lower()
    assert not resp.unresolved


def test_cc_nc_depends_on_intent(cache, transport, no_parallel):
    # NC does not cover commercial use: the verdict flips with intent while
    # the determination itself stays intent-neutral.
    from rules.licenses import covers_intent, parse_license
    lic = parse_license("https://creativecommons.org/licenses/by-nc/3.0/")
    assert lic.code == "cc_by_nc" and lic.noncommercial
    assert covers_intent(lic, "education") and not covers_intent(lic, "film_tv")


def test_license_table_parses_the_family():
    from rules.licenses import parse_license
    assert parse_license("https://creativecommons.org/publicdomain/zero/1.0/").public_domain
    assert parse_license("http://creativecommons.org/licenses/by/2.0/").code == "cc_by"
    assert parse_license("https://creativecommons.org/licenses/by-nc-nd/4.0/").noderivatives
    assert parse_license("https://example.com/all-rights-reserved") is None


def test_release_level_license_and_nc_flips_with_intent(cache, transport, no_parallel):
    # The NIN Ghosts pattern: the CC license sits on the release. And NC does
    # not cover a commercial use, so the same record flips with intent.
    transport(handler)
    resp, em = run_music(q("Ghost Signal \u2014 Night Owl Static"))       # film_tv
    lv = next(x for x in resp.layer_verdicts if x.layer_id == "sound_recording")
    assert lv.verdict is Verdict.LICENSE_REQUIRED
    assert lv.determination.rule_id == "license_cc_by_nc_sa"
    layer = next(l for l in resp.entity.layers if l.layer_id == "sound_recording")
    assert layer.existing_license.sources[0].excerpt.startswith("license relation on the release")
    assert "does not cover commercial use" in lv.determination.rule_explanation

    resp2, em2 = run_music(q("Ghost Signal \u2014 Night Owl Static", intent=Intent.EDUCATION))
    lv2 = next(x for x in resp2.layer_verdicts if x.layer_id == "sound_recording")
    assert lv2.verdict is Verdict.CLEAR_WITH_CONDITIONS
    assert "non-commercial use only" in lv2.determination.rule_explanation


# --- surfaced intents: notes, paths and layer requirements ------------------------

def test_social_video_note_and_podcast_path(cache, transport, no_parallel):
    transport(handler)
    resp, em = run_music(q("West End Blues \u2014 Louis Armstrong", intent=Intent.SOCIAL_VIDEO))
    rec = next(lv for lv in resp.layer_verdicts if lv.layer_id == "sound_recording")
    assert rec.verdict is Verdict.LICENSE_REQUIRED
    assert "Content ID" in rec.intent_note and "claim is not a license" in rec.intent_note
    assert "micro-licensing" in rec.licensing_path

    resp2, em2 = run_music(q("West End Blues \u2014 Louis Armstrong", intent=Intent.PODCAST))
    rec2 = next(lv for lv in resp2.layer_verdicts if lv.layer_id == "sound_recording")
    assert "no Content ID equivalent" in rec2.intent_note
    assert "label directly" in rec2.licensing_path


def test_print_needs_the_composition_only(cache, transport, no_parallel):
    transport(handler)
    resp, em = run_music(q("West End Blues \u2014 Louis Armstrong", intent=Intent.PRINT))
    rec = next(lv for lv in resp.layer_verdicts if lv.layer_id == "sound_recording")
    assert not rec.is_required and "through the composition only" in rec.intent_note
    # WEB's composition is public domain in the US, so print rolls up clear
    assert resp.overall_verdict is Verdict.CLEAR


def test_documentary_has_its_own_bands_and_note(cache, transport, no_parallel):
    transport(handler)
    resp, em = run_music(q("West End Blues \u2014 Louis Armstrong", intent=Intent.DOCUMENTARY))
    rec = next(lv for lv in resp.layer_verdicts if lv.layer_id == "sound_recording")
    assert rec.verdict is Verdict.LICENSE_REQUIRED
    assert "festival" in rec.cost_band
    assert "fair use" in rec.intent_note and "attorney" in rec.intent_note


def test_run_log_rides_on_the_record(cache, transport, no_parallel):
    # The accession log stays on the record: a warm query is legible after
    # the fact. Volatile timings keep it out of fixture comparison.
    transport(handler)
    resp, em = run_music(q("Golden Hour \u2014 Night Owl Static"))
    assert resp.run_log
    msgs = " | ".join(e.message for e in resp.run_log)
    assert "Tier 1" in msgs and "Consulted" in msgs
    assert all(e.elapsed_ms >= 0 for e in resp.run_log)
    from pipeline.mockworld import normalize
    assert "run_log" not in normalize(resp)


def test_minority_release_license_is_a_lead_not_an_answer(cache, transport, no_parallel):
    # The Aliens Exist trap: one licensed release among plain ones. The mark
    # must not settle the layer; it becomes an open question, and the
    # recording is determined by its term (dated 2020 session) as usual.
    transport(handler)
    resp, em = run_music(q("Half Signal \u2014 Night Owl Static"))
    layer = next(l for l in resp.entity.layers if l.layer_id == "sound_recording")
    assert layer.existing_license is None
    lv = next(x for x in resp.layer_verdicts if x.layer_id == "sound_recording")
    assert lv.determination.rule_id != "license_cc_by_nc_sa"
    qn = next(u for u in resp.unresolved if u.question_id == "sound_recording:license")
    assert "1 of 3 releases" in qn.why_it_matters
    assert "does not license the master generally" in qn.why_it_matters


def test_candidate_rows_prefer_the_dated_performance(cache, transport, no_parallel):
    # A reissue-dated entity must not make a 1920s recording read as modern:
    # the row says "recorded 1961" when a performance relation exists, and
    # falls back to the self-describing release wording when none does.
    transport(handler)
    resp, em = run_music(q("Blue Moon"))
    assert resp.stop_for_disambiguation
    by_artist = {c.label.split(" ")[0] + " " + c.label.split(" ")[1]: c.disambiguator
                 for c in resp.entity.alternate_candidates}
    assert any(d.startswith("recorded 1961") for d in by_artist.values())
    assert any(d.startswith("earliest release on file") for d in by_artist.values())


def test_duration_scales_the_band_never_the_verdict(cache, transport, no_parallel):
    # No short-use safe harbor: every determination is identical with and
    # without a duration; only the cost band carries the scaling note.
    from schemas import Duration
    transport(handler)
    base, _ = run_music(q("West End Blues \u2014 Louis Armstrong"))
    short, _ = run_music(AssetQuery(raw_input="West End Blues \u2014 Louis Armstrong",
                                    intent=Intent.FILM_TV, jurisdiction=Jurisdiction.US,
                                    asset_type_hint=AssetType.MUSIC, duration=Duration.UNDER_10S))
    assert short.overall_verdict is base.overall_verdict
    assert [d.model_dump() for d in short.all_determinations] == [d.model_dump() for d in base.all_determinations]
    rec = next(l for l in short.layer_verdicts if l.layer_id == "sound_recording")
    assert "low end" in rec.cost_band and "whether you need permission" in rec.cost_band
    rec_base = next(l for l in base.layer_verdicts if l.layer_id == "sound_recording")
    assert "low end" not in rec_base.cost_band
