import httpx

from sources import musicbrainz as mb

WORK = "a97c426c-c138-4531-9d4a-e2eb0bca7961"


def rel(work_id, begin=None, title="West End Blues", iswcs=None, attrs=None):
    return {"target-type": "work", "type": "performance", "begin": begin, "end": begin,
            "attributes": attrs or [],
            "work": {"id": work_id, "title": title, "iswcs": iswcs or [], "disambiguation": ""}}


def browse_page(offset, total, work_id=WORK):
    recs = []
    for i in range(offset, min(offset + mb.PAGE, total)):
        recs.append({
            "id": f"rec-{i:04d}",
            "title": "West End Blues",
            "first-release-date": "1975",
            "artist-credit": [{"name": "Louis Armstrong", "joinphrase": " and His Hot Five"}],
            # recording #150 is the dated session, deliberately on page 2
            "relations": [rel(work_id, begin="1928-06-28" if i == 150 else None)],
        })
    return {"recording-count": total, "recording-offset": offset, "recordings": recs}


def router(total=250):
    def handler(req: httpx.Request):
        p = req.url.params
        if req.url.path == "/ws/2/recording" and "query" in p:
            return httpx.Response(200, json={"recordings": [
                {"id": "r1", "title": "West End Blues", "score": 100, "first-release-date": "1996",
                 "artist-credit": [{"name": "Louis Armstrong"}]},
                {"id": "r2", "title": "West End Blues", "score": 90,
                 "artist-credit": [{"name": "Ella", "joinphrase": " & "}, {"name": "Louis Armstrong"}]},
            ]})
        if req.url.path == "/ws/2/recording" and "work" in p:
            return httpx.Response(200, json=browse_page(int(p.get("offset", 0)), total))
        if req.url.path == "/ws/2/recording/r1":
            return httpx.Response(200, json={"id": "r1", "title": "West End Blues",
                                             "first-release-date": "1996",
                                             "relations": [rel(WORK), rel("other", title="Other")]})
        if req.url.path == f"/ws/2/work/{WORK}":
            return httpx.Response(200, json={
                "id": WORK, "title": "West End Blues", "iswcs": ["T-1"],
                "relations": [
                    {"target-type": "artist", "type": "composer", "begin": "1928",
                     "artist": {"id": "a1", "name": "King Oliver"}},
                    {"target-type": "artist", "type": "arranger",
                     "artist": {"id": "a2", "name": "Nobody"}},
                    {"target-type": "url", "type": "wikidata",
                     "url": {"resource": "https://www.wikidata.org/wiki/Q4019073"}},
                ]})
        return httpx.Response(404)
    return handler


def test_search_recordings_parses_candidates(cache, transport):
    calls = transport(router())
    f = mb.search_recordings("West End Blues", "Louis Armstrong")
    assert f.ok
    assert f.data[0] == {"mbid": "r1", "title": "West End Blues", "artist": "Louis Armstrong",
                         "date": "1996", "score": 100}
    assert f.data[1]["artist"] == "Ella & Louis Armstrong"
    q = calls[0].url.params["query"]
    assert q == 'recording:"West End Blues" AND artist:"Louis Armstrong"'


def test_search_escapes_quotes(cache, transport):
    calls = transport(router())
    mb.search_recordings('Say "Hi"')
    assert calls[0].url.params["query"] == 'recording:"Say \\"Hi\\""'


def test_recording_works_parses_work_rels(cache, transport):
    transport(router())
    f = mb.recording_works("r1")
    assert f.ok
    assert [w["work_mbid"] for w in f.data["works"]] == [WORK, "other"]
    assert f.data["date"] == "1996"


def test_work_details_filters_writer_roles_and_finds_wikidata(cache, transport):
    transport(router())
    f = mb.work_details(WORK)
    assert f.ok
    assert f.data["writers"] == [{"name": "King Oliver", "mbid": "a1", "role": "composer",
                                  "begin": "1928", "end": None}]
    assert f.data["wikidata"] == "Q4019073" and f.data["iswcs"] == ["T-1"]


def test_work_recordings_pages_to_completion_and_stores_derived(cache, transport):
    calls = transport(router(total=250))
    r = mb.work_recordings(WORK)
    assert r.complete and r.total == 250 and len(r.recordings) == 250 and r.pages_fetched == 3
    assert not r.from_cache and r.error is None
    dated = [x for x in r.recordings if x["perf_begin"]]
    assert dated == [{"mbid": "rec-0150", "title": "West End Blues",
                      "artist": "Louis Armstrong and His Hot Five", "date": "1975",
                      "perf_begin": "1928-06-28", "perf_end": "1928-06-28",
                      "attributes": [], "work_mbid": WORK}]
    assert cache.get(f"mb:derived:work-recordings:{WORK}") is not None
    n = len(calls)
    r2 = mb.work_recordings(WORK)
    assert r2.from_cache and r2.complete and len(r2.recordings) == 250
    assert len(calls) == n                          # zero requests


def test_work_recordings_early_stop_is_partial_and_not_derived(cache, transport):
    calls = transport(router(total=250))
    r = mb.work_recordings(WORK, stop_when=mb.dated_match_for("Louis Armstrong"))
    assert not r.complete and r.pages_fetched == 2 and len(r.recordings) == 200
    assert cache.get(f"mb:derived:work-recordings:{WORK}") is None
    assert len(calls) == 2
    # pages are still cached individually: a full pass later only fetches page 3
    r2 = mb.work_recordings(WORK)
    assert r2.complete and len(calls) == 3


def test_work_recordings_max_pages_cap(cache, transport):
    transport(router(total=250))
    r = mb.work_recordings(WORK, max_pages=1)
    assert not r.complete and r.pages_fetched == 1 and len(r.recordings) == 100


def test_work_recordings_http_error_fails_soft_with_partial(cache, transport):
    def handler(req):
        if int(req.url.params.get("offset", 0)) >= 100:
            return httpx.Response(503)
        return httpx.Response(200, json=browse_page(0, 250))
    transport(handler)
    r = mb.work_recordings(WORK)
    assert not r.complete and r.error == "http 503" and len(r.recordings) == 100


def test_credited_to():
    assert mb.credited_to("Louis Armstrong and His Hot Five", "louis armstrong")
    assert not mb.credited_to("Ella Fitzgerald", "Louis Armstrong")


# --- name matching and loose search terms (Aug 31: the blink-182 front-door bug) ---

def test_credited_to_folds_typographic_punctuation():
    from sources.musicbrainz import credited_to
    assert credited_to("blink\u2010182", "blink-182")          # MB credits use U+2010
    assert credited_to("blink\u2010182", "blink 182")
    assert credited_to("blink\u2010182", "BLINK182")
    assert credited_to("JAY\u2010Z featuring Beyonc\u00e9", "Jay-Z")
    assert credited_to("X\u2010Ray Spex", "x-ray spex")
    assert credited_to("U2", "U2")
    assert not credited_to("The Marcels", "blink-182")
    assert not credited_to("anyone", "")


def test_loose_terms_strip_punctuation():
    from sources.musicbrainz import _loose_terms, _match_norm
    assert _loose_terms("alien's exist") == "alien AND s AND exist"
    assert _loose_terms("blink-182") == "blink AND 182"
    assert _loose_terms("aliens exist", suffix="~") == "aliens~ AND exist~"
    assert _match_norm("blink\u2010182") == "blink182"
