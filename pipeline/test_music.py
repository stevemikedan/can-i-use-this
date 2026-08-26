"""
Pipeline tests on a mock MusicBrainz + Wikidata + Parallel.

World: two songs.
  "West End Blues" — one work (composer King Oliver, MB begin 1928; Wikidata
      P577 1928 but NO P86 => writers uncorroborated). Armstrong has a dated
      1928-06-28 session plus a 1939 one and two undated entities.
  "Blue Moon" — one work (Rodgers/Hart, P577 1934, P86/P676 present =>
      corroborated). The Marcels have NO dated session, only 1961/1995
      release dates => reissue-only path. Ella has a dated 1961 session.
"""

import httpx
import pytest

from pipeline.music import parse_query, run_music
from schemas import (
    AssetQuery, AssetType, Confidence, DeterminationStatus, Intent, Jurisdiction,
    RecordingDateBasis, Verdict,
)

WEB_WORK = "a97c426c-0000-0000-0000-000000000001"
WEB_WORK2 = "ec12be9a-0000-0000-0000-000000000003"   # sibling: same title, Oliver + Clarence Williams
BM_WORK = "3c339d3d-0000-0000-0000-000000000002"


def rec(mbid, title, credit, date=None, work=None, begin=None):
    r = {"id": mbid, "title": title, "first-release-date": date, "score": 100,
         "artist-credit": [{"name": credit}], "relations": []}
    if work:
        r["relations"].append({"target-type": "work", "type": "performance", "begin": begin, "end": begin,
                               "attributes": [], "work": {"id": work, "title": title, "iswcs": []}})
    return r


RECORDINGS = [
    rec("web-1996", "West End Blues", "Louis Armstrong", "1996", WEB_WORK),
    rec("web-1928", "West End Blues", "Louis Armstrong and His Hot Five", "1928-07", WEB_WORK, "1928-06-28"),
    rec("web-1939", "West End Blues", "Louis Armstrong and His Orchestra", "1957", WEB_WORK, "1939-04-05"),
    rec("web-2003", "West End Blues", "Louis Armstrong", "2003", WEB_WORK),
    rec("web-ethel", "West End Blues", "Ethel Waters", "1994", WEB_WORK2, "1928-08-23"),
    rec("bm-marcels-1995", "Blue Moon", "The Marcels", "1995", BM_WORK),
    rec("bm-marcels-1961", "Blue Moon", "The Marcels", "1961-01", BM_WORK),
    rec("bm-ella", "Blue Moon", "Ella Fitzgerald", "1961", BM_WORK, "1961"),
    rec("bm-bennett", "Blue Moon", "Tony Bennett", "1999", BM_WORK),
]

WORKS = {
    WEB_WORK: {"id": WEB_WORK, "title": "West End Blues", "score": 100, "iswcs": [], "relations": [
        {"target-type": "artist", "type": "composer", "begin": "1928", "artist": {"id": "a-oliver", "name": "King Oliver"}},
        {"target-type": "url", "type": "wikidata", "url": {"resource": "https://www.wikidata.org/wiki/Q4019073"}},
    ]},
    WEB_WORK2: {"id": WEB_WORK2, "title": "West End Blues", "score": 99, "iswcs": ["T-070.280.775-7"], "relations": [
        {"target-type": "artist", "type": "composer", "artist": {"id": "a-oliver", "name": "King Oliver"}},
        {"target-type": "artist", "type": "composer", "artist": {"id": "a-williams", "name": "Clarence Williams"}},
    ]},
    BM_WORK: {"id": BM_WORK, "title": "Blue Moon", "score": 100, "iswcs": ["T-070.011.746-9"], "relations": [
        {"target-type": "artist", "type": "composer", "begin": "1934", "artist": {"id": "a-rodgers", "name": "Richard Rodgers"}},
        {"target-type": "artist", "type": "lyricist", "begin": "1934", "artist": {"id": "a-hart", "name": "Lorenz Hart"}},
        {"target-type": "url", "type": "wikidata", "url": {"resource": "https://www.wikidata.org/wiki/Q804574"}},
    ]},
}


def wd_time(y):
    return {"mainsnak": {"datavalue": {"value": {"time": f"+{y}-00-00T00:00:00Z"}}}}


def wd_item(q):
    return {"mainsnak": {"datavalue": {"value": {"id": q}}}}


WD = {
    "Q4019073": {"id": "Q4019073", "labels": {"en": {"value": "West End Blues"}}, "claims": {"P577": [wd_time(1928)]}},
    "Q804574": {"id": "Q804574", "labels": {"en": {"value": "Blue Moon"}},
                "claims": {"P577": [wd_time(1934)], "P86": [wd_item("Q269094")], "P676": [wd_item("Q725828")]}},
    "Q313368": {"id": "Q313368", "labels": {"en": {"value": "King Oliver"}}, "claims": {"P570": [wd_time(1938)]}},
    "Q2977727": {"id": "Q2977727", "labels": {"en": {"value": "Clarence Williams"}}, "claims": {"P570": [wd_time(1965)]}},
    "Q269094": {"id": "Q269094", "labels": {"en": {"value": "Richard Rodgers"}}, "claims": {"P570": [wd_time(1979)]}},
    "Q725828": {"id": "Q725828", "labels": {"en": {"value": "Lorenz Hart"}}, "claims": {"P570": [wd_time(1943)]}},
}
# MusicBrainz artist -> Wikidata link (the exact person). The name search below
# deliberately returns the WRONG Clarence Williams so the test proves the link is used.
ARTIST_WD = {"a-oliver": "Q313368", "a-williams": "Q2977727", "a-rodgers": "Q269094", "a-hart": "Q725828"}
WD_SEARCH = {"King Oliver": "Q313368", "Richard Rodgers": "Q269094", "Lorenz Hart": "Q725828",
             "Clarence Williams": "Q-actor"}


def handler(req: httpx.Request):
    p, path = req.url.params, req.url.path
    if req.url.host == "www.wikidata.org":
        if p.get("action") == "wbgetentities":
            ids = p["ids"].split("|")
            return httpx.Response(200, json={"entities": {q: WD.get(q, {"id": q, "missing": ""}) for q in ids}})
        q = WD_SEARCH.get(p.get("search"))
        return httpx.Response(200, json={"search": [{"id": q, "label": p["search"], "description": "x"}] if q else []})
    if path == "/ws/2/recording" and "query" in p:
        title = p["query"].split('"')[1]
        hits = [r for r in RECORDINGS if r["title"] == title]
        return httpx.Response(200, json={"recordings": [dict(r, relations=[]) for r in hits]})
    if path == "/ws/2/work" and "query" in p:
        title = p["query"].split('"')[1]
        return httpx.Response(200, json={"works": [w for w in WORKS.values() if w["title"] == title]})
    if path == "/ws/2/recording" and "work" in p:
        hits = [r for r in RECORDINGS if any(x["work"]["id"] == p["work"] for x in r["relations"])]
        return httpx.Response(200, json={"recording-count": len(hits), "recording-offset": 0, "recordings": hits})
    if path.startswith("/ws/2/recording/"):
        mbid = path.rsplit("/", 1)[1]
        r = next((r for r in RECORDINGS if r["id"] == mbid), None)
        return httpx.Response(200, json=r) if r else httpx.Response(404)
    if path.startswith("/ws/2/work/"):
        w = WORKS.get(path.rsplit("/", 1)[1])
        return httpx.Response(200, json=w) if w else httpx.Response(404)
    if path.startswith("/ws/2/artist/"):
        aid = path.rsplit("/", 1)[1]
        qid = ARTIST_WD.get(aid)
        rels = [{"target-type": "url", "type": "wikidata",
                 "url": {"resource": f"https://www.wikidata.org/wiki/{qid}"}}] if qid else []
        return httpx.Response(200, json={"id": aid, "name": aid, "relations": rels, "life-span": {}})
    return httpx.Response(404)


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


def test_ambiguity_stops_before_research(cache, transport, no_parallel):
    calls = transport(handler)
    resp, em = run_music(q("Blue Moon"))
    assert resp.stop_for_disambiguation and resp.overall_verdict is Verdict.UNDETERMINED
    labels = [c.label for c in resp.entity.alternate_candidates]
    assert len(labels) == 3 and labels[-1].startswith("Tony Bennett")   # ordered by earliest release; 1999 last
    assert resp.entity.resolution_confidence is Confidence.LOW
    assert all(c.likelihood is Confidence.LOW for c in resp.entity.alternate_candidates)
    assert len(calls) == 1                                           # ONE search, nothing else
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
    assert resp.overall_verdict is Verdict.UNDETERMINED and resp.overall_headline.startswith("Not found")
    assert resp.unresolved[0].question_id == "resolve:not_found"
