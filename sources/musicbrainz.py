"""
MusicBrainz Tier 2 client. Cache-first, throttled, fails soft.

Spike findings baked in (PROJECT.md §3):
  - `first-release-date` is the earliest release ON FILE; it is exposed as
    `date` but callers must treat it as RecordingDateBasis.FIRST_RELEASE_DATE.
  - The dated `performance` relation (`perf_begin`) is the session date and
    the only MB field that may drive a confident recording determination.
  - One composition is often several MB work entities; recording selection
    must look at all of them (work_recordings per work).
  - Popular standards have 600-1800 linked recordings. work_recordings
    pages 100 at a time, caches every page, stores the complete list as a
    derived entry, and supports early stop via a predicate.
"""

from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

from .cache import get_cache
from .http import Fetched, get_json

MB = "https://musicbrainz.org/ws/2"
PAGE = 100
SEARCH_MAX_AGE_S = 7 * 86400          # search results drift; entities don't
WRITER_REL_TYPES = {"composer", "lyricist", "writer", "librettist"}


def _mb(path: str, params: dict, cache_key: str, **kw) -> Fetched:
    return get_json(f"{MB}/{path}", {**params, "fmt": "json"}, cache_key=cache_key, **kw)


def _lucene_phrase(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def credit_string(artist_credit: list) -> str:
    return "".join(
        (ac.get("name") or ac.get("artist", {}).get("name") or "") + (ac.get("joinphrase") or "")
        for ac in (artist_credit or [])
    )


def _match_norm(s: str) -> str:
    """Fold for name matching: NFKD, casefold, alphanumerics only. MusicBrainz
    credits use typographic punctuation — 'blink‐182' carries U+2010, not
    the ASCII hyphen anyone types — so matching must ignore punctuation."""
    return "".join(c for c in unicodedata.normalize("NFKD", s or "").casefold() if c.isalnum())


def credited_to(credit: str, artist: str) -> bool:
    a = _match_norm(artist)
    return bool(a) and a in _match_norm(credit)


# --- search -------------------------------------------------------------------

def _loose_terms(s: str, joiner: str = " AND ", suffix: str = "") -> str:
    """Tokens for an unquoted Lucene field group, punctuation dropped so the
    analyzer bridges apostrophes and hyphens. AND-joined by default: Lucene
    ORs bare tokens, and artist:(the beatles) would otherwise match every
    "The ..." band through the article alone. suffix="~" makes tokens fuzzy."""
    cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in s or "")
    return joiner.join(t + suffix for t in cleaned.split())


def search_recordings(title: str, artist: Optional[str] = None, limit: int = 25) -> Fetched:
    """
    /recording?query=... Top candidates as
    {mbid, title, artist, date, score}. `date` is first-release-date.

    Strict phrase first. If that matches nothing, one loose tokenized retry:
    "alien's exist" then finds "Aliens Exist". This is the app's front door,
    so it also gets 5 attempts against MusicBrainz's routine 503 bursts.
    """
    def run(q: str) -> Fetched:
        return _run_recording_query(q, limit, attempts=5)

    q = f'recording:"{_lucene_phrase(title)}"'
    if artist:
        q += f' AND artist:"{_lucene_phrase(artist)}"'
    f = run(q)
    if f.ok and not f.data:
        lt, la = _loose_terms(title), _loose_terms(artist) if artist else ""
        if lt:
            q2 = f"recording:({lt})" + (f" AND artist:({la})" if la else "")
            f2 = run(q2)
            if f2.ok and f2.data:
                return f2
    return f


def _run_recording_query(q: str, limit: int, attempts: int = 3) -> Fetched:
    key = f"mb:search:recording:{hashlib.sha1(q.encode()).hexdigest()[:16]}:{limit}"
    f = _mb("recording", {"query": q, "limit": limit}, key, max_age_s=SEARCH_MAX_AGE_S, attempts=attempts)
    if f.ok:
        f.data = [{
            "mbid": r["id"],
            "title": r.get("title"),
            "artist": credit_string(r.get("artist-credit")),
            "date": r.get("first-release-date"),
            "score": r.get("score"),
        } for r in f.data.get("recordings", [])]
    return f


def suggest_recordings(title: str, limit: int = 25) -> list[dict]:
    """
    Real MusicBrainz hits for a search that found nothing: the title alone
    (strict, then loose), then Lucene fuzzy per token. Every suggestion is an
    actual index entry — an invented suggestion would be the same failure
    class as an uncited fact. Returns [] when even fuzzy finds nothing.
    """
    f = search_recordings(title, None, limit)
    if f.ok and f.data:
        return f.data
    fuzzy = _loose_terms(title, suffix="~")
    if not fuzzy:
        return []
    q = f"recording:({fuzzy})"
    f2 = _run_recording_query(q, limit)
    return f2.data if f2.ok and f2.data else []


def _norm_title(s: str) -> str:
    return "".join(ch for ch in (s or "").lower() if ch.isalnum() or ch == " ").strip()


def search_works(title: str, limit: int = 25, min_score: int = 85) -> Fetched:
    """
    /work?query=work:"title" — every MB work entity with (nearly) this title,
    in one call. Aug 26 measurement: for all six spike titles this returned
    every work the 10-call recording sweep had found, at rank <= 7. Do NOT
    filter on type — instrumental works have type null.

    Returns [{work_mbid, title, disambiguation, iswcs, score, composers}]
    limited to exact (normalised) title matches with score >= min_score.
    """
    q = f'work:"{_lucene_phrase(title)}"'
    key = f"mb:search:work:{hashlib.sha1(q.encode()).hexdigest()[:16]}:{limit}"
    f = _mb("work", {"query": q, "limit": limit}, key, max_age_s=SEARCH_MAX_AGE_S)
    if not f.ok:
        return f
    want = _norm_title(title)
    out = []
    for w in f.data.get("works", []):
        if (w.get("score") or 0) < min_score or _norm_title(w.get("title")) != want:
            continue
        out.append({
            "work_mbid": w["id"],
            "title": w.get("title"),
            "disambiguation": w.get("disambiguation") or "",
            "iswcs": w.get("iswcs") or [],
            "score": w.get("score"),
            "composers": [r["artist"]["name"] for r in w.get("relations", [])
                          if r.get("type") in WRITER_REL_TYPES and r.get("artist")],
        })
    f.data = out
    return f


# --- recording -> work(s) -----------------------------------------------------

def _parse_work_rels(relations: list, only_work: Optional[str] = None) -> list[dict]:
    out = []
    for rel in relations or []:
        if rel.get("target-type") != "work":
            continue
        w = rel.get("work", {})
        if only_work and w.get("id") != only_work:
            continue
        out.append({
            "work_mbid": w.get("id"),
            "title": w.get("title"),
            "disambiguation": w.get("disambiguation") or "",
            "iswcs": w.get("iswcs") or [],
            "rel_type": rel.get("type"),
            "attributes": rel.get("attributes") or [],
            "begin": rel.get("begin"),
            "end": rel.get("end"),
        })
    return out


def recording_licenses(mbid: str) -> Fetched:
    """/recording/{mbid}?inc=url-rels -> list of license URLs (Tier 1 input)."""
    f = _mb(f"recording/{mbid}", {"inc": "url-rels"}, f"mb:recording:{mbid}:url-rels")
    if not f.ok:
        return f
    f.data = [rel["url"]["resource"] for rel in f.data.get("relations") or []
              if rel.get("target-type") == "url" and rel.get("type") == "license"]
    return f


def release_licenses(recording_mbid: str) -> Fetched:
    """
    /release?recording={mbid}&inc=url-rels -> license URLs across the
    recording's releases. The pattern most CC albums follow: the license
    relation sits on the release (NIN's Ghosts is the canonical case), not
    on the recording or work entities.
    """
    f = _mb("release", {"recording": recording_mbid, "inc": "url-rels", "limit": "25"},
            f"mb:release-licenses:{recording_mbid}:v2")
    if not f.ok:
        return f
    out = []
    for release in f.data.get("releases") or []:
        urls = [rel["url"]["resource"] for rel in release.get("relations") or []
                if rel.get("target-type") == "url" and rel.get("type") == "license"]
        out.append({"id": release.get("id"), "licenses": urls})
    f.data = out
    return f


def recording_works(mbid: str) -> Fetched:
    """/recording/{mbid}?inc=work-rels -> {mbid, title, date, works: [...]}."""
    f = _mb(f"recording/{mbid}", {"inc": "work-rels"}, f"mb:recording:{mbid}:work-rels")
    if not f.ok:
        return f
    raw = f.data
    f.data = {
        "mbid": raw.get("id"),
        "title": raw.get("title"),
        "date": raw.get("first-release-date"),
        "works": _parse_work_rels(raw.get("relations")),
    }
    return f


# --- work details -------------------------------------------------------------

def work_details(work_mbid: str) -> Fetched:
    """/work/{mbid}?inc=artist-rels+url-rels -> writers, ISWCs, Wikidata QID."""
    f = _mb(f"work/{work_mbid}", {"inc": "artist-rels+url-rels"},
            f"mb:work:{work_mbid}:artist-rels+url-rels")
    if not f.ok:
        return f
    raw = f.data
    writers, wikidata = [], None
    for rel in raw.get("relations") or []:
        if rel.get("target-type") == "artist" and rel.get("type") in WRITER_REL_TYPES:
            writers.append({
                "name": rel["artist"]["name"],
                "mbid": rel["artist"]["id"],
                "role": rel["type"],
                "begin": rel.get("begin"),
                "end": rel.get("end"),
            })
        elif rel.get("target-type") == "url" and rel.get("type") == "wikidata":
            wikidata = rel["url"]["resource"].rstrip("/").rsplit("/", 1)[-1]
    licenses = [rel["url"]["resource"] for rel in raw.get("relations") or []
                if rel.get("target-type") == "url" and rel.get("type") == "license"]
    f.data = {
        "work_mbid": raw.get("id"),
        "licenses": licenses,
        "title": raw.get("title"),
        "disambiguation": raw.get("disambiguation") or "",
        "iswcs": raw.get("iswcs") or [],
        "writers": writers,
        "wikidata": wikidata,
    }
    return f


# --- artist -> Wikidata ---------------------------------------------------------

def artist_wikidata(artist_mbid: str) -> Fetched:
    """
    /artist/{mbid}?inc=url-rels -> the artist's Wikidata QID (or None).
    Identifies the exact person MusicBrainz credited. A Wikidata NAME search
    is not a substitute: "Clarence Williams" returns the actor (d. 2021), not
    the pianist who co-wrote West End Blues (d. 1965).
    """
    f = _mb(f"artist/{artist_mbid}", {"inc": "url-rels"}, f"mb:artist:{artist_mbid}:url-rels")
    if not f.ok:
        return f
    qid = None
    for rel in f.data.get("relations") or []:
        if rel.get("target-type") == "url" and rel.get("type") == "wikidata":
            qid = rel["url"]["resource"].rstrip("/").rsplit("/", 1)[-1]
            break
    f.data = {"mbid": artist_mbid, "name": f.data.get("name"), "wikidata": qid,
              "life_span_end": (f.data.get("life-span") or {}).get("end")}
    return f


# --- work -> recordings (paginated browse) ----------------------------------

@dataclass
class WorkRecordings:
    work_mbid: str
    recordings: list[dict] = field(default_factory=list)
    total: Optional[int] = None
    complete: bool = False          # every linked recording is in .recordings
    pages_fetched: int = 0
    from_cache: bool = False        # served from the derived complete map
    error: Optional[str] = None
    url: str = ""
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def _parse_browse_recording(r: dict, work_mbid: str) -> dict:
    rels = _parse_work_rels(r.get("relations"), only_work=work_mbid)
    dated = [x for x in rels if x["begin"]]
    return {
        "mbid": r["id"],
        "title": r.get("title"),
        "artist": credit_string(r.get("artist-credit")),
        "date": r.get("first-release-date"),
        "perf_begin": dated[0]["begin"] if dated else None,
        "perf_end": dated[0]["end"] if dated else None,
        "attributes": rels[0]["attributes"] if rels else [],
        "work_mbid": work_mbid,
    }


def dated_match_for(artist: str) -> Callable[[list[dict]], bool]:
    """Early-stop predicate: at least one dated session credited to artist."""
    return lambda recs: any(credited_to(r["artist"], artist) and r["perf_begin"] for r in recs)


def work_recordings(work_mbid: str, *, stop_when: Optional[Callable[[list[dict]], bool]] = None,
                    max_pages: int = 20) -> WorkRecordings:
    """
    Every recording MB links to the work: /recording?work={mbid} paginated.

    Each page is cached individually; once the whole list has been fetched it
    is stored as one derived entry so later calls cost zero requests. Pass
    stop_when to stop early (the result is then complete=False and is NOT
    stored as derived). Fails soft: on an HTTP error the partial result comes
    back with .error set.
    """
    cache = get_cache()
    derived_key = f"mb:derived:work-recordings:{work_mbid}"
    entry = cache.get(derived_key)
    if entry is not None:
        return WorkRecordings(work_mbid, entry.value["recordings"], entry.value["total"],
                              complete=True, from_cache=True,
                              retrieved_at=datetime.fromtimestamp(entry.fetched_at, tz=timezone.utc))

    res = WorkRecordings(work_mbid)
    offset = 0
    while res.pages_fetched < max_pages:
        f = _mb("recording", {"work": work_mbid, "inc": "work-rels+artist-credits",
                              "limit": PAGE, "offset": offset},
                f"mb:browse:recording:work:{work_mbid}:{offset}")
        res.url, res.retrieved_at = f.url, f.retrieved_at
        if not f.ok:
            res.error = f.error
            return res
        res.pages_fetched += 1
        res.total = f.data.get("recording-count", 0)
        res.recordings.extend(_parse_browse_recording(r, work_mbid) for r in f.data.get("recordings", []))
        offset += PAGE
        if offset >= res.total:
            res.complete = True
            break
        if stop_when is not None and stop_when(res.recordings):
            break
    if res.complete:
        cache.set(derived_key, {"recordings": res.recordings, "total": res.total})
    return res
