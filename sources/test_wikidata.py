import httpx

from sources import wikidata as wd


def ent(qid, label, **claims):
    def time_claim(y):
        return {"mainsnak": {"datavalue": {"value": {"time": f"+{y:04d}-00-00T00:00:00Z"}}}}

    def item_claim(q, rank="normal"):
        return {"rank": rank, "mainsnak": {"datavalue": {"value": {"id": q}}}}

    c = {}
    for prop, val in claims.items():
        c[prop] = [time_claim(v) if isinstance(v, int) else item_claim(*v) if isinstance(v, tuple)
                   else item_claim(v) for v in (val if isinstance(val, list) else [val])]
    return {"id": qid, "labels": {"en": {"value": label}}, "claims": c}


DATA = {
    "Q1": ent("Q1", "West End Blues", P577=1928, P86="Q2", P676=[("Q9", "deprecated"), "Q3"]),
    "Q2": ent("Q2", "King Oliver", P570=1938),
    "Q3": ent("Q3", "Clarence Williams", P570=1965),
    "Q9": ent("Q9", "Wrong Person", P570=1900),
}


def handler(req: httpx.Request):
    p = req.url.params
    if p.get("action") == "wbgetentities":
        ids = p["ids"].split("|")
        return httpx.Response(200, json={"entities": {
            q: DATA.get(q, {"id": q, "missing": ""}) for q in ids}})
    if p.get("action") == "wbsearchentities":
        return httpx.Response(200, json={"search": [
            {"id": "Q2", "label": "King Oliver", "description": "cornetist"}]})
    return httpx.Response(404)


def test_entities_batch_then_per_entity_cache(cache, transport):
    calls = transport(handler)
    out = wd.entities(["Q2", "Q3", "Q2"])
    assert len(calls) == 1 and calls[0].url.params["ids"] == "Q2|Q3"
    assert out["Q2"].ok and wd.label(out["Q2"].data) == "King Oliver"
    out2 = wd.entities(["Q3", "Q1"])
    assert len(calls) == 2 and calls[1].url.params["ids"] == "Q1"   # Q3 from cache
    assert out2["Q3"].from_cache and not out2["Q1"].from_cache
    assert cache.get("wd:entity:Q1") is not None
    assert not any(k.startswith("wd:batch") for k in cache._d)      # batches not persisted


def test_missing_entity_fails_soft(cache, transport):
    transport(handler)
    f = wd.entity("Q404")
    assert not f.ok and "missing" in f.error


def test_claim_helpers_respect_rank():
    e = DATA["Q1"]
    assert wd.claim_year(e, "P577") == 1928
    assert wd.claim_year(e, "P571") is None
    assert wd.claim_items(e, "P676") == ["Q3", "Q9"]     # deprecated sorts last
    assert wd.claim_items(e, "P86") == ["Q2"]


def test_work_dates_and_writers(cache, transport):
    transport(handler)
    d = wd.work_dates("Q1")
    assert d["P577_publication"] == 1928 and d["label"] == "West End Blues"
    w = wd.work_writers("Q1")
    got = {(x["qid"], x["role"], x["label"], x["death_year"]) for x in w["writers"]}
    assert got == {("Q2", "composer", "King Oliver", 1938),
                   ("Q3", "lyricist", "Clarence Williams", 1965),
                   ("Q9", "lyricist", "Wrong Person", 1900)}


def test_search_entities(cache, transport):
    transport(handler)
    f = wd.search_entities("King Oliver")
    assert f.ok and f.data == [{"id": "Q2", "label": "King Oliver", "description": "cornetist"}]
