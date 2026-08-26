"""
Wikidata Tier 2 client. Cache-first (per entity), fails soft.

Used for: composition year (P577 publication, P1191 first performance,
P571 inception), writer cross-check (P86 composer / P676 lyricist on the
work item), and death years (P570). The spike found all of these clean.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Optional

from .cache import MemoryCache, get_cache
from .http import Fetched, get_json

WD = "https://www.wikidata.org/w/api.php"
ENTITY_MAX_AGE_S = 30 * 86400
SEARCH_MAX_AGE_S = 30 * 86400
BATCH = 50


# --- entities ---------------------------------------------------------------

def entities(qids: list[str]) -> dict[str, Fetched]:
    """
    wbgetentities for many QIDs. Cached per entity under wd:entity:{qid};
    only the misses go over the wire, batched 50 at a time.
    """
    cache = get_cache()
    out: dict[str, Fetched] = {}
    missing: list[str] = []
    for q in dict.fromkeys(qids):  # dedupe, keep order
        entry = cache.get(f"wd:entity:{q}", max_age_s=ENTITY_MAX_AGE_S)
        if entry is not None:
            out[q] = Fetched(entry.value, f"{WD}?action=wbgetentities&ids={q}",
                             datetime.fromtimestamp(entry.fetched_at, tz=timezone.utc),
                             from_cache=True)
        else:
            missing.append(q)

    for i in range(0, len(missing), BATCH):
        chunk = missing[i:i + BATCH]
        # The batch response itself is not worth keeping; entities are stored
        # individually below. A throwaway cache keeps get_json's contract.
        f = get_json(WD, {"action": "wbgetentities", "ids": "|".join(chunk),
                          "props": "claims|labels|descriptions", "languages": "en",
                          "format": "json"},
                     cache_key="wd:batch:" + hashlib.sha1("|".join(chunk).encode()).hexdigest(),
                     cache=MemoryCache())
        for q in chunk:
            ent = (f.data or {}).get("entities", {}).get(q) if f.ok else None
            if ent is None or "missing" in ent:
                out[q] = Fetched(None, f.url, f.retrieved_at,
                                 error=f.error or f"entity {q} missing")
            else:
                cache.set(f"wd:entity:{q}", ent)
                out[q] = Fetched(ent, f.url, f.retrieved_at)
    return out


def entity(qid: str) -> Fetched:
    return entities([qid])[qid]


def search_entities(text: str, limit: int = 5) -> Fetched:
    """wbsearchentities -> [{id, label, description}]."""
    key = f"wd:search:{hashlib.sha1(text.encode()).hexdigest()[:16]}:{limit}"
    f = get_json(WD, {"action": "wbsearchentities", "search": text, "language": "en",
                      "type": "item", "limit": limit, "format": "json"},
                 cache_key=key, max_age_s=SEARCH_MAX_AGE_S)
    if f.ok:
        f.data = [{"id": h["id"], "label": h.get("label"), "description": h.get("description")}
                  for h in f.data.get("search", [])]
    return f


# --- claim helpers ------------------------------------------------------------

def _claim_values(ent: dict, prop: str) -> list:
    vals = []
    for c in (ent or {}).get("claims", {}).get(prop, []):
        v = c.get("mainsnak", {}).get("datavalue", {}).get("value")
        if v is not None:
            vals.append((c.get("rank", "normal"), v))
    # preferred rank first, then normal; deprecated last
    order = {"preferred": 0, "normal": 1, "deprecated": 2}
    vals.sort(key=lambda rv: order.get(rv[0], 1))
    return [v for _, v in vals]


def claim_year(ent: dict, prop: str) -> Optional[int]:
    """First time-valued claim -> int year ('+1928-00-00T00:00:00Z' -> 1928)."""
    for v in _claim_values(ent, prop):
        t = v.get("time") if isinstance(v, dict) else None
        if t:
            return int(t[1:5])
    return None


def claim_items(ent: dict, prop: str) -> list[str]:
    return [v["id"] for v in _claim_values(ent, prop) if isinstance(v, dict) and v.get("id")]


def label(ent: dict) -> Optional[str]:
    return (ent or {}).get("labels", {}).get("en", {}).get("value")


def description(ent: dict) -> Optional[str]:
    return (ent or {}).get("descriptions", {}).get("en", {}).get("value")


# --- work-level helpers -------------------------------------------------------

def work_dates(qid: str) -> dict:
    """{P577_publication, P1191_first_performance, P571_inception, label, fetched}."""
    f = entity(qid)
    e = f.data or {}
    return {
        "label": label(e),
        "P577_publication": claim_year(e, "P577"),
        "P1191_first_performance": claim_year(e, "P1191"),
        "P571_inception": claim_year(e, "P571"),
        "fetched": f,
    }


def work_writers(qid: str) -> dict:
    """
    Writers as Wikidata records them on the WORK item, with each writer's
    own P570 death year. {writers: [{qid, role, label, death_year, fetched}],
    fetched: <the work fetch>}.
    """
    f = entity(qid)
    e = f.data or {}
    roles: dict[str, str] = {}
    for prop, role in (("P86", "composer"), ("P676", "lyricist")):
        for q in claim_items(e, prop):
            roles.setdefault(q, role)
    ents = entities(list(roles)) if roles else {}
    return {
        "writers": [{
            "qid": q,
            "role": role,
            "label": label(ents[q].data),
            "death_year": claim_year(ents[q].data, "P570"),
            "fetched": ents[q],
        } for q, role in roles.items()],
        "fetched": f,
    }
