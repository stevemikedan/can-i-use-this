"""
A small, deterministic mock of MusicBrainz + Wikidata + Parallel for tests
and for freezing acceptance fixtures. Shared by pipeline/ and agent/ tests.

World: three songs.
  "West End Blues" — selected work credits King Oliver (MB begin 1928);
      Wikidata P577 1928 but NO P86 => writers uncorroborated. A sibling
      work credits Oliver + Clarence Williams (d. 1965). Armstrong has a
      dated 1928-06-28 session, a 1939 one, and two undated entities.
      => the BLOCKED case (US license required; UK/EU composition blocked).
  "Rhapsody in Blue" — Gershwin, P577 1924 corroborated by MB begin 1924,
      P86 present. Whiteman has a dated 1924-06-10 session released 1924-10.
      => the CLEAN case.
  "Blue Moon" — Rodgers/Hart, P577 1934 (renewal window), P86/P676 present.
      The Marcels have NO dated session (reissue-only path); Ella has a
      dated 1961 session (renewal case). No artist => STOP.
"""

from __future__ import annotations

from typing import Any

import httpx

WEB_WORK = "a97c426c-0000-0000-0000-000000000001"
WEB_WORK2 = "ec12be9a-0000-0000-0000-000000000003"   # sibling: same title, Oliver + Clarence Williams
BM_WORK = "3c339d3d-0000-0000-0000-000000000002"
OTR_WORK = "f4a81d77-0000-0000-0000-000000000005"
CC_WORK = "9d3e5b21-0000-0000-0000-000000000006"
CC_URI = "https://creativecommons.org/licenses/by-sa/4.0/"
GS_WORK = "1e7c9a44-0000-0000-0000-000000000007"
GS_WORK2 = "2f8d0b55-0000-0000-0000-000000000008"
GS_URI = "https://creativecommons.org/licenses/by-nc-sa/3.0/"
# Release-level license sets, keyed by recording mbid: one list per release
# on file. Ghost Signal is the NIN Ghosts pattern (every release licensed);
# Half Signal is the Aliens Exist trap (one licensed release among plain
# ones), which must NOT settle the layer.
RELEASE_SETS = {"gs-1": [[GS_URI]],
                "hs-1": [[GS_URI], [], []]}
RIB_WORK = "60b22df4-0000-0000-0000-000000000004"


def rec(mbid, title, credit, date=None, work=None, begin=None, license=None):
    r = {"id": mbid, "title": title, "first-release-date": date, "score": 100,
         "artist-credit": [{"name": credit}], "relations": []}
    if license:
        r["relations"].append({"target-type": "url", "type": "license", "url": {"resource": license}})
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
    rec("rib-whiteman-1924", "Rhapsody in Blue", "Paul Whiteman and His Concert Orchestra", "1924-10", RIB_WORK, "1924-06-10"),
    rec("rib-whiteman-1995", "Rhapsody in Blue", "Paul Whiteman & His Orchestra", "1995", RIB_WORK),
    rec("rib-jando", "Rhapsody in Blue", "Jenő Jandó", "1989", RIB_WORK),
    rec("bm-marcels-1995", "Blue Moon", "The Marcels", "1995", BM_WORK),
    rec("bm-marcels-1961", "Blue Moon", "The Marcels", "1961-01", BM_WORK),
    rec("bm-ella", "Blue Moon", "Ella Fitzgerald", "1961", BM_WORK, "1961"),
    rec("bm-bennett", "Blue Moon", "Tony Bennett", "1999", BM_WORK),
    # "Later Take": studio original released 1999-06, undated; a 2001 live take
    # carries the only dated performance relation. The selection guard must
    # fall to the release-date path, not crown the live take the original.
    # "Over the Rainbow": Garland's session is dated October 1938; the film
    # released August 1939 and Wikidata carries 1939 as P577. Both defensible,
    # the pair impossible - the consistency layer's acceptance case.
    rec("otr-garland", "Over the Rainbow", "Judy Garland", "1939-09", OTR_WORK, "1938-10-07"),
    # "Golden Hour": a CC BY-SA release; license relations on the recording
    # and the work. Tier 1 settles both layers with no research at all.
    rec("cc-golden", "Golden Hour", "Night Owl Static", "2019-03", CC_WORK, license=CC_URI),
    rec("gs-1", "Ghost Signal", "Night Owl Static", "2020-01", GS_WORK),
    rec("hs-1", "Half Signal", "Night Owl Static", "2021-01", GS_WORK2, begin="2020-11-05"),
    rec("otr-garland-1993", "Over the Rainbow", "Judy Garland", "1993", OTR_WORK),
    rec("lt-studio", "Later Take", "The Guards", "1999-06", "w-latertake"),
    rec("lt-live", "Later Take", "The Guards", "2001-11", "w-latertake", "2001-06-15"),
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
    RIB_WORK: {"id": RIB_WORK, "title": "Rhapsody in Blue", "score": 100, "iswcs": [], "relations": [
        {"target-type": "artist", "type": "composer", "begin": "1924", "artist": {"id": "a-gershwin", "name": "George Gershwin"}},
        {"target-type": "url", "type": "wikidata", "url": {"resource": "https://www.wikidata.org/wiki/Q722599"}},
    ]},
    GS_WORK: {"id": GS_WORK, "title": "Ghost Signal", "score": 100, "iswcs": [], "relations": []},
    GS_WORK2: {"id": GS_WORK2, "title": "Half Signal", "score": 100, "iswcs": [], "relations": []},
    CC_WORK: {"id": CC_WORK, "title": "Golden Hour", "score": 100, "iswcs": [], "relations": [
        {"target-type": "url", "type": "license", "url": {"resource": CC_URI}},
    ]},
    OTR_WORK: {"id": OTR_WORK, "title": "Over the Rainbow", "score": 100, "iswcs": [], "relations": [
        {"target-type": "artist", "type": "composer", "begin": "1939", "artist": {"id": "a-arlen", "name": "Harold Arlen"}},
        {"target-type": "artist", "type": "lyricist", "begin": "1939", "artist": {"id": "a-harburg", "name": "Yip Harburg"}},
        {"target-type": "url", "type": "wikidata", "url": {"resource": "https://www.wikidata.org/wiki/Q898765"}},
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
    "Q722599": {"id": "Q722599", "labels": {"en": {"value": "Rhapsody in Blue"}},
                "claims": {"P577": [wd_time(1924)], "P86": [wd_item("Q123829")]}},
    "Q804574": {"id": "Q804574", "labels": {"en": {"value": "Blue Moon"}},
                "claims": {"P577": [wd_time(1934)], "P86": [wd_item("Q269094")], "P676": [wd_item("Q725828")]}},
    "Q313368": {"id": "Q313368", "labels": {"en": {"value": "King Oliver"}}, "claims": {"P570": [wd_time(1938)]}},
    "Q2977727": {"id": "Q2977727", "labels": {"en": {"value": "Clarence Williams"}}, "claims": {"P570": [wd_time(1965)]}},
    "Q123829": {"id": "Q123829", "labels": {"en": {"value": "George Gershwin"}}, "claims": {"P570": [wd_time(1937)]}},
    "Q269094": {"id": "Q269094", "labels": {"en": {"value": "Richard Rodgers"}}, "claims": {"P570": [wd_time(1979)]}},
    "Q725828": {"id": "Q725828", "labels": {"en": {"value": "Lorenz Hart"}}, "claims": {"P570": [wd_time(1943)]}},
    "Q898765": {"id": "Q898765", "labels": {"en": {"value": "Over the Rainbow"}},
                "claims": {"P577": [wd_time(1939)], "P86": [wd_item("Q315011")], "P676": [wd_item("Q551819")]}},
    "Q315011": {"id": "Q315011", "labels": {"en": {"value": "Harold Arlen"}}, "claims": {"P570": [wd_time(1986)]}},
    "Q551819": {"id": "Q551819", "labels": {"en": {"value": "Yip Harburg"}}, "claims": {"P570": [wd_time(1981)]}},
}

# MusicBrainz artist -> Wikidata link (the exact person). The name search
# deliberately returns the WRONG Clarence Williams so tests prove the link is used.
ARTIST_WD = {"a-oliver": "Q313368", "a-williams": "Q2977727", "a-gershwin": "Q123829",
             "a-rodgers": "Q269094", "a-hart": "Q725828",
             "a-arlen": "Q315011", "a-harburg": "Q551819"}
WD_SEARCH = {"King Oliver": "Q313368", "George Gershwin": "Q123829", "Richard Rodgers": "Q269094",
             "Lorenz Hart": "Q725828", "Clarence Williams": "Q-actor"}


def handler(req: httpx.Request) -> httpx.Response:
    """httpx.MockTransport handler for MusicBrainz + Wikidata."""
    p, path = req.url.params, req.url.path
    if req.url.host == "www.wikidata.org":
        if p.get("action") == "wbgetentities":
            ids = p["ids"].split("|")
            return httpx.Response(200, json={"entities": {q: WD.get(q, {"id": q, "missing": ""}) for q in ids}})
        q = WD_SEARCH.get(p.get("search"))
        return httpx.Response(200, json={"search": [{"id": q, "label": p["search"], "description": "x"}] if q else []})
    if path == "/ws/2/release" and "recording" in p:
        sets = RELEASE_SETS.get(p["recording"], [])
        releases = [{"id": f"rel-{i}", "relations": [
            {"target-type": "url", "type": "license", "url": {"resource": u}} for u in urls]}
            for i, urls in enumerate(sets)]
        return httpx.Response(200, json={"releases": releases})
    if path == "/ws/2/recording" and "query" in p:
        parts = p["query"].split('"')
        title = parts[1] if len(parts) > 1 else None   # loose/fuzzy queries are unquoted: no mock matches
        hits = [r for r in RECORDINGS if title and r["title"] == title]
        return httpx.Response(200, json={"recordings": [dict(r, relations=[]) for r in hits]})
    if path == "/ws/2/work" and "query" in p:
        wparts = p["query"].split('"')
        title = wparts[1] if len(wparts) > 1 else None
        return httpx.Response(200, json={"works": [w for w in WORKS.values() if w["title"] == title]})
    if path == "/ws/2/recording" and "work" in p:
        hits = [r for r in RECORDINGS if any(x.get("target-type") == "work" and x["work"]["id"] == p["work"] for x in r["relations"])]
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


class FakeParallel:
    """Stand-in for the parallel-web client with canned Search hits."""

    class _Result:
        def __init__(self, hits):
            self._d = {"search_id": "s1", "session_id": "x", "results": hits}

        def model_dump(self):
            return self._d

    def __init__(self):
        self.calls: list[dict] = []

    def search(self, **kw):
        self.calls.append(kw)
        return self._Result([
            {"url": "https://archive.org/details/cce-1962", "title": "CCE 1962 renewals",
             "excerpts": ["BLUE MOON; w Lorenz Hart, m Richard Rodgers. R290123 12Jan62"]},
            {"url": "https://adp.library.ucsb.edu/x", "title": "DAHR", "excerpts": ["Victor 1961"]},
        ])

    # --- Task API: canned rights-holder research -----------------------------
    class _TaskRun:
        def __init__(self, outer):
            self.outer = outer

        def create(self, **kw):
            self.outer.task_calls.append(kw)
            class R: run_id = "tr1"
            return R()

        def result(self, run_id, **kw):
            class R:
                @staticmethod
                def model_dump():
                    return {"run": {"run_id": "tr1"}, "output": {
                        "content": {"parties": [
                            {"name": "Bluebird Songs", "role": "publisher", "is_administrator": True,
                             "share_percent": 50, "territory": "world", "founded_year": None,
                             "evidence": "Bluebird Songs administers the catalog"}],
                            "one_stop": None, "notes": ""},
                        "basis": [{"field": "parties", "citations": [
                            {"url": "https://example.com/trade", "title": "Trade press",
                             "excerpts": ["Bluebird Songs administers the catalog"]}]}]}}
            return R()

    @property
    def task_run(self):
        if not hasattr(self, "_task_run"):
            self.task_calls: list[dict] = []
            self._task_run = self._TaskRun(self)
        return self._task_run


# --- the five acceptance cases --------------------------------------------------

WORKS["w-latertake"] = {"id": "w-latertake", "title": "Later Take", "score": 100, "iswcs": [], "relations": []}


CASES = {
    "blocked": {"raw_input": "West End Blues — Louis Armstrong", "jurisdiction": "US", "intent": "film_tv"},
    "clean": {"raw_input": "Rhapsody in Blue — Paul Whiteman", "jurisdiction": "US", "intent": "film_tv"},
    "stop": {"raw_input": "Blue Moon", "jurisdiction": "US", "intent": "film_tv"},
    "reissue": {"raw_input": "Blue Moon — The Marcels", "jurisdiction": "US", "intent": "film_tv"},
    "renewal": {"raw_input": "Blue Moon — Ella Fitzgerald", "jurisdiction": "US", "intent": "film_tv"},
    "rainbow": {"raw_input": "Over the Rainbow — Judy Garland", "jurisdiction": "US", "intent": "film_tv"},
    "cc": {"raw_input": "Golden Hour — Night Owl Static", "jurisdiction": "US", "intent": "film_tv"},
}

# run_log timings differ run to run; the log is real but not comparable.
VOLATILE_KEYS = {"generated_at", "retrieved_at", "run_log"}


def normalize(obj: Any) -> Any:
    """A RightsResponse (or its dump) with timestamps removed, for comparison."""
    if hasattr(obj, "model_dump"):
        obj = obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return {k: normalize(v) for k, v in obj.items() if k not in VOLATILE_KEYS}
    if isinstance(obj, list):
        return [normalize(v) for v in obj]
    return obj
