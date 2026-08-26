"""
Pre-warm the Tier 2 cache for a title/artist and report timings.

    python -m sources.warm "West End Blues" "Louis Armstrong"
    python -m sources.warm --stats

Does the full recording-selection sweep (search -> work-rels on the top K
candidates -> every recording of every distinct work -> work details ->
Wikidata work item + writers) so a later query is all cache hits.
PROJECT.md §4.6: pre-warming demo assets before recording is legitimate —
the results are real — but show one cold run too.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time

from . import musicbrainz as mb
from . import wikidata as wd
from .cache import get_cache


def warm(title: str, artist: str | None, k: int = 10) -> dict:
    t0 = time.monotonic()
    report: dict = {"title": title, "artist": artist, "steps": []}

    def step(name, fn):
        s = time.monotonic()
        out = fn()
        report["steps"].append({"step": name, "seconds": round(time.monotonic() - s, 2)})
        return out

    search = step("search", lambda: mb.search_recordings(title, artist))
    if not search.ok:
        report["error"] = f"search: {search.error}"
        return report
    cands = search.data
    if artist:
        cands = [c for c in cands if mb.credited_to(c["artist"], artist)]
    report["candidates"] = len(cands)

    works: dict[str, dict] = {}
    for c in cands[:k]:
        f = step(f"work-rels {c['mbid'][:8]}", lambda c=c: mb.recording_works(c["mbid"]))
        if f.ok:
            for w in f.data["works"]:
                works.setdefault(w["work_mbid"], w)
    report["works"] = list(works)

    for wid in works:
        wr = step(f"browse {wid[:8]}", lambda wid=wid: mb.work_recordings(wid))
        report["steps"][-1].update({"recordings": len(wr.recordings), "total": wr.total,
                                    "complete": wr.complete, "pages": wr.pages_fetched,
                                    "from_cache": wr.from_cache, "error": wr.error})
        det = step(f"work {wid[:8]}", lambda wid=wid: mb.work_details(wid))
        if det.ok and det.data["wikidata"]:
            qid = det.data["wikidata"]
            step(f"wikidata {qid}", lambda qid=qid: wd.work_writers(qid))
            for w in det.data["writers"]:
                step(f"wd search {w['name']}", lambda w=w: wd.search_entities(w["name"]))

    report["total_seconds"] = round(time.monotonic() - t0, 2)
    report["cache"] = get_cache().stats()
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("title", nargs="?")
    p.add_argument("artist", nargs="?")
    p.add_argument("--k", type=int, default=10, help="candidates to sweep for work-rels")
    p.add_argument("--stats", action="store_true", help="print cache stats and exit")
    p.add_argument("-v", action="store_true", help="log HTTP retries")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.WARNING if a.v else logging.ERROR, format="%(name)s %(message)s")
    if a.stats or not a.title:
        print(json.dumps(get_cache().stats(), indent=2))
        return 0
    print(json.dumps(warm(a.title, a.artist, a.k), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
