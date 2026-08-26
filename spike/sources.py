"""
Throwaway Tier 2 clients for the spike. httpx + a JSON-file cache.

MusicBrainz: descriptive User-Agent, ~1 request/second, everything cached to
spike/cache/<sha1>.json so reruns cost nothing. Wikidata: wbsearchentities
then wbgetentities, property P570 (date of death).

No classes, no retries. Non-200 responses are printed and returned as
{"_error": status, "_body": text} and are NOT cached.
"""

import hashlib
import json
import os
import time

import httpx

# MusicBrainz wants an app name + contact (URL or email).
UA = "CanIUseThis/0.1 ( https://github.com/stevemikedan/can-i-use-this )"

MB = "https://musicbrainz.org/ws/2"
WD = "https://www.wikidata.org/w/api.php"
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")

_last_call = {}  # host -> monotonic time of the last LIVE request


def _get(url, params, min_interval):
    os.makedirs(CACHE_DIR, exist_ok=True)
    key = hashlib.sha1((url + "?" + json.dumps(params, sort_keys=True)).encode()).hexdigest()
    path = os.path.join(CACHE_DIR, key + ".json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    host = httpx.URL(url).host
    wait = min_interval - (time.monotonic() - _last_call.get(host, 0.0))
    if wait > 0:
        time.sleep(wait)
    try:
        r = httpx.get(url, params=params,
                      headers={"User-Agent": UA, "Accept": "application/json"},
                      timeout=30)
    except httpx.HTTPError as e:
        # e.g. MusicBrainz resetting the TCP connection. Not a data finding.
        _last_call[host] = time.monotonic()
        print(f"    [{type(e).__name__}] {url} — {e}")
        return {"_error": type(e).__name__, "_body": str(e)}
    _last_call[host] = time.monotonic()
    print(f"    [http {r.status_code}] {r.url}")
    if r.status_code == 503:
        # MusicBrainz says "busy" when it wants you to slow down. One retry, loudly.
        print("    [503 — sleeping 5s and retrying once]")
        time.sleep(5)
        r = httpx.get(url, params=params,
                      headers={"User-Agent": UA, "Accept": "application/json"},
                      timeout=30)
        _last_call[host] = time.monotonic()
        print(f"    [http {r.status_code}] retry")
    if r.status_code != 200:
        print(f"    [body] {r.text[:500]}")
        return {"_error": r.status_code, "_body": r.text[:500]}
    data = r.json()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    return data


def _mb(path, params):
    return _get(f"{MB}/{path}", {**params, "fmt": "json"}, min_interval=1.1)


def _wd(params):
    return _get(WD, {**params, "format": "json"}, min_interval=0.25)


# ---------------------------------------------------------------------------
# MusicBrainz
# ---------------------------------------------------------------------------

def search_recording(title, artist=None, limit=10):
    """Top candidates from /recording?query=... with MBID, date, artist."""
    q = f'recording:"{title}"'
    if artist:
        q += f' AND artist:"{artist}"'
    data = _mb("recording", {"query": q, "limit": limit})
    if "_error" in data:
        return None  # request failed — distinct from "no candidates"
    out = []
    for rec in data.get("recordings", []):
        credit = "".join(
            (ac.get("name") or ac["artist"]["name"]) + (ac.get("joinphrase") or "")
            for ac in rec.get("artist-credit", [])
        )
        out.append({
            "mbid": rec["id"],
            "title": rec.get("title"),
            "date": rec.get("first-release-date"),
            "artist": credit,
            "score": rec.get("score"),
        })
    return out


def get_work_for_recording(mbid):
    """
    /recording/{mbid}?inc=work-rels — the critical call. Returns the RAW
    response so the caller can print it before anything is parsed.
    """
    return _mb(f"recording/{mbid}", {"inc": "work-rels"})


def linked_works(recording_json):
    """Extract linked Work MBIDs + ISWCs from a raw get_work_for_recording response."""
    works = []
    for rel in recording_json.get("relations", []):
        if rel.get("target-type") != "work":
            continue
        w = rel.get("work", {})
        works.append({
            "work_mbid": w.get("id"),
            "title": w.get("title"),
            "iswcs": w.get("iswcs", []),
            "rel_type": rel.get("type"),
            "attributes": rel.get("attributes", []),
            # MB sometimes dates the performance relation itself ("recorded 1961").
            "begin": rel.get("begin"),
            "end": rel.get("end"),
        })
    return works


def browse_recordings_for_work(work_mbid, max_pages=20):
    """
    /recording?work={mbid}&inc=work-rels+artist-credits — every recording MB
    has linked to this work, each with its own dated performance relation
    (when MB has one) and first-release-date. This is how you find the 1928
    session when the search top-N only shows reissues. Paginated 100 at a
    time (popular standards have 1000+). Returns None on error.
    """
    recs, offset, total = [], 0, None
    for _ in range(max_pages):
        data = _mb("recording", {"work": work_mbid, "inc": "work-rels+artist-credits",
                                 "limit": 100, "offset": offset})
        if "_error" in data:
            return None
        total = data.get("recording-count", 0)
        recs.extend(data.get("recordings", []))
        offset += 100
        if offset >= total:
            break
    if total and len(recs) < total:
        print(f"    NOTE: work has {total} linked recordings; only the first {len(recs)} were fetched")
    out = []
    for r in recs:
        rels = [x for x in r.get("relations", [])
                if x.get("target-type") == "work" and x.get("work", {}).get("id") == work_mbid]
        dated = [x for x in rels if x.get("begin")]
        credit = "".join(
            (ac.get("name") or ac["artist"]["name"]) + (ac.get("joinphrase") or "")
            for ac in r.get("artist-credit", [])
        )
        out.append({
            "mbid": r["id"],
            "title": r.get("title"),
            "artist": credit,
            "date": r.get("first-release-date"),
            "perf_begin": dated[0]["begin"] if dated else None,
            "perf_end": dated[0].get("end") if dated else None,
            "attributes": rels[0].get("attributes", []) if rels else [],
        })
    return out


WRITER_REL_TYPES = {"composer", "lyricist", "writer", "librettist"}


def get_writers(work_mbid):
    """
    /work/{mbid}?inc=artist-rels — composer and lyricist relations.
    Also pulls url-rels so we can find the work's Wikidata item (used for the
    composition year). Returns the raw JSON alongside the parsed pieces.
    """
    raw = _mb(f"work/{work_mbid}", {"inc": "artist-rels+url-rels"})
    writers, wikidata = [], None
    for rel in raw.get("relations", []):
        if rel.get("target-type") == "artist" and rel.get("type") in WRITER_REL_TYPES:
            writers.append({
                "name": rel["artist"]["name"],
                "mbid": rel["artist"]["id"],
                "role": rel["type"],
                "begin": rel.get("begin"),
                "end": rel.get("end"),
            })
        if rel.get("target-type") == "url" and rel.get("type") == "wikidata":
            wikidata = rel["url"]["resource"].rstrip("/").rsplit("/", 1)[-1]
    return {
        "raw": raw,
        "writers": writers,
        "iswcs": raw.get("iswcs", []),
        "wikidata": wikidata,
    }


# ---------------------------------------------------------------------------
# Wikidata
# ---------------------------------------------------------------------------

def _claim_year(entity, prop):
    """First time-valued claim for prop -> int year, or None."""
    for claim in entity.get("claims", {}).get(prop, []):
        t = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("time")
        if t:
            return int(t[1:5])  # "+1938-04-10T00:00:00Z"
    return None


def get_entity(qid):
    data = _wd({"action": "wbgetentities", "ids": qid,
                "props": "claims|labels|descriptions", "languages": "en"})
    return data.get("entities", {}).get(qid, {})


def get_death_year(artist_name):
    """
    wbsearchentities on the name, take the FIRST hit, read P570.
    Returns the hit's label/description too so a wrong-person match is
    visible rather than silent.
    """
    s = _wd({"action": "wbsearchentities", "search": artist_name,
             "language": "en", "type": "item", "limit": 5})
    hits = s.get("search", [])
    if not hits:
        return {"name": artist_name, "qid": None, "label": None,
                "description": None, "death_year": None, "candidates": []}
    top = hits[0]
    entity = get_entity(top["id"])
    return {
        "name": artist_name,
        "qid": top["id"],
        "label": top.get("label"),
        "description": top.get("description"),
        "death_year": _claim_year(entity, "P570"),
        "candidates": [(h["id"], h.get("label"), h.get("description")) for h in hits],
    }


def get_entities(qids):
    """Batch wbgetentities. {qid: entity}."""
    if not qids:
        return {}
    data = _wd({"action": "wbgetentities", "ids": "|".join(sorted(qids)),
                "props": "claims|labels|descriptions", "languages": "en"})
    return data.get("entities", {})


def get_work_writers_wikidata(qid):
    """
    Writers as Wikidata records them on the WORK item: P86 composer, P676
    lyricist. Used to corroborate (or extend) MusicBrainz's writer list.
    Each entry carries the writer's own P570 so no name search is needed.
    """
    e = get_entity(qid)
    roles = {}
    for prop, role in (("P86", "composer"), ("P676", "lyricist")):
        for c in e.get("claims", {}).get(prop, []):
            v = c.get("mainsnak", {}).get("datavalue", {}).get("value", {})
            if isinstance(v, dict) and v.get("id"):
                roles[v["id"]] = role
    ents = get_entities(list(roles))
    return [{
        "qid": q,
        "role": role,
        "label": ents.get(q, {}).get("labels", {}).get("en", {}).get("value"),
        "death_year": _claim_year(ents.get(q, {}), "P570"),
    } for q, role in roles.items()]


def get_work_dates(qid):
    """
    Date properties on the work's Wikidata item:
      P577 publication date, P1191 date of first performance, P571 inception.
    """
    e = get_entity(qid)
    return {
        "label": e.get("labels", {}).get("en", {}).get("value"),
        "P577_publication": _claim_year(e, "P577"),
        "P1191_first_performance": _claim_year(e, "P1191"),
        "P571_inception": _claim_year(e, "P571"),
    }
