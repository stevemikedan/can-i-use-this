"""
Spike: can free, keyless sources produce a correct two-layer determination?

For each (title, artist):
  1. MusicBrainz recording search      -> pick a recording, take its year
  2. /recording/{mbid}?inc=work-rels   -> RAW JSON printed, then parsed
  3. /work/{mbid}?inc=artist-rels      -> writers; url-rels -> Wikidata item
  4. Wikidata                          -> composition year (P577/P1191/P571)
                                          and each writer's death year (P570)
  5. rules: us_sound_recording(rec_year), us_standard_term(comp_year),
            roll_up with both layers required. life_plus_70 shown for info.

Nothing is inferred. If a step yields nothing, it says so and moves on.

Run:  python spike/spike.py                       (the six titles)
      python spike/spike.py "Summertime" "Billie Holiday"
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rules import (  # noqa: E402
    Determination, life_plus_70, roll_up, status_to_verdict,
    us_sound_recording, us_standard_term,
)
from spike.sources import (  # noqa: E402
    get_death_year, get_work_dates, get_work_for_recording, get_writers,
    linked_works, search_recording,
)

QUERIES = [
    ("West End Blues", "Louis Armstrong"),
    ("Rhapsody in Blue", None),
    ("Take Five", None),
    ("Mack the Knife", None),
    ("Summertime", None),
    ("Blue Moon", None),
]


def hr(ch="=", n=78):
    print(ch * n)


def show(label, det):
    print(f"  {label:<12} {det.status:<14} expiry={det.expiry_year!s:<6} rule={det.rule_id}")
    print(f"  {'':<12} {det.explanation}")
    if det.blocked_by:
        print(f"  {'':<12} blocked_by={det.blocked_by}")


def run(title, artist):
    row = {"title": title, "artist": artist, "recording": None, "rec_year": None,
           "rec_src": None, "work": None, "work_fetch_failed": False, "iswc": None,
           "writers": [], "deaths": [], "comp_year": None, "comp_year_prop": None,
           "verdict": None, "blocking": None, "complete": False}

    hr()
    print(f"{title}" + (f"  —  {artist}" if artist else "  —  (no artist given)"))
    hr()

    # 1. recording ---------------------------------------------------------
    print("\n[1] search_recording")
    cands = search_recording(title, artist)
    if cands is None:
        print("  SEARCH REQUEST FAILED (see status above). Nothing known. Stopping here.")
        row["rec_src"] = "ERR"
        return row
    if not cands:
        print("  NO RECORDING CANDIDATES. Stopping here.")
        return row
    for c in cands:
        print(f"  {c['score']!s:>3}  {c['date'] or '----------':<10}  {c['mbid']}  {c['title']}  ·  {c['artist']}")

    dated = [c for c in cands if c["date"]]
    if not dated:
        print("  No candidate has a first-release-date. Cannot pick a recording year. Stopping here.")
        return row
    pick = min(dated, key=lambda c: c["date"])
    rec_year = int(pick["date"][:4])
    row["recording"] = pick["mbid"]
    row["rec_year"], row["rec_src"] = rec_year, "first-release-date"
    print(f"\n  picked {pick['mbid']} ({pick['date']}, {pick['artist']}) — earliest first-release-date among the top {len(cands)}")
    print(f"  NOTE: first-release-date is MusicBrainz's earliest *release* on file, not the session date.")

    # 2. work link — the critical call --------------------------------------
    print("\n[2] get_work_for_recording — RAW RESPONSE")
    raw = get_work_for_recording(pick["mbid"])
    print(json.dumps(raw, indent=2, ensure_ascii=False))

    if "_error" in raw:
        print(f"\n  >>> REQUEST FAILED ({raw['_error']}). Cannot tell whether a work is linked. <<<")
        row["work_fetch_failed"] = True
        row["verdict"], row["blocking"] = "undetermined", "composition"
        return row

    works = linked_works(raw)
    if works and works[0]["begin"]:
        # The performance relation itself is dated — that's the recording
        # date MB knows, and it beats the earliest-release proxy.
        rec_year, row["rec_year"], row["rec_src"] = int(works[0]["begin"][:4]), int(works[0]["begin"][:4]), "performance-rel"
        print(f"\n  recording year: {rec_year} from the dated performance relation (begin={works[0]['begin']}), overriding first-release-date {pick['date']}")
    if not works:
        print("\n  >>> NO LINKED WORK on this recording. Composition layer cannot be resolved from MusicBrainz. <<<")
        rec = us_sound_recording(rec_year)
        print("\n[5] determination (recording layer only)")
        show("recording", rec)
        comp = Determination("undetermined", None, "spike_no_work_link",
                             "Recording has no work relationship in MusicBrainz.",
                             blocked_by="work_link")
        verdict, blocking = roll_up([
            ("composition", status_to_verdict(comp.status), True),
            ("recording", status_to_verdict(rec.status), True),
        ])
        row["verdict"], row["blocking"] = verdict, blocking
        print(f"\n  ROLL-UP: {verdict.upper()}  (blocking layer: {blocking})")
        return row

    if len(works) > 1:
        print(f"\n  {len(works)} linked works; using the first. All of them:")
    for w in works:
        print(f"  work {w['work_mbid']}  {w['title']}  iswc={w['iswcs']}  rel={w['rel_type']} {w['attributes']}")
    work = works[0]
    row["work"] = work["work_mbid"]

    # 3. writers ----------------------------------------------------------
    print("\n[3] get_writers")
    wr = get_writers(work["work_mbid"])
    iswcs = work["iswcs"] or wr["iswcs"]
    row["iswc"] = iswcs[0] if iswcs else None
    print(f"  iswc={iswcs}  wikidata={wr['wikidata']}")
    if not wr["writers"]:
        print("  NO WRITER RELATIONS on this work.")
    for w in wr["writers"]:
        dates = f"  ({w['begin']}..{w['end']})" if (w["begin"] or w["end"]) else ""
        print(f"  {w['role']:<10} {w['name']}  {w['mbid']}{dates}")
    row["writers"] = [w["name"] for w in wr["writers"]]

    # 4a. composition year ------------------------------------------------
    print("\n[4a] composition year")
    comp_year = None
    if wr["wikidata"]:
        d = get_work_dates(wr["wikidata"])
        print(f"  {wr['wikidata']} \"{d['label']}\": P577={d['P577_publication']} P1191={d['P1191_first_performance']} P571={d['P571_inception']}")
        for prop in ("P577_publication", "P1191_first_performance", "P571_inception"):
            if d[prop]:
                comp_year, row["comp_year_prop"] = d[prop], prop
                break
        if comp_year and row["comp_year_prop"] != "P577_publication":
            print(f"  WARNING: no P577 publication date; using {row['comp_year_prop']} = {comp_year}")
    else:
        print("  Work has no Wikidata link in MusicBrainz.")
    if comp_year is None:
        print("  NO COMPOSITION YEAR FOUND. Composition layer will be undetermined.")
    row["comp_year"] = comp_year

    # 4b. death years -------------------------------------------------------
    print("\n[4b] get_death_year")
    deaths = []
    for name in row["writers"]:
        r = get_death_year(name)
        deaths.append(r["death_year"])
        print(f"  {name:<24} -> {r['qid']}  \"{r['label']}\" — {r['description']}  P570={r['death_year']}")
        if len(r["candidates"]) > 1:
            others = "; ".join(f"{q} {l} ({desc})" for q, l, desc in r["candidates"][1:])
            print(f"  {'':<24}    other hits: {others}")
    row["deaths"] = deaths

    # 5. rules -------------------------------------------------------------
    print("\n[5] determination")
    rec = us_sound_recording(rec_year)
    if comp_year is not None:
        comp = us_standard_term(comp_year)
    else:
        comp = Determination("undetermined", None, "spike_no_composition_year",
                             "No publication/composition year found for the work.",
                             blocked_by="composition_year")
    show("composition", comp)
    show("recording", rec)
    show("life+70 (EU, info only)", life_plus_70(deaths, "EU"))

    verdict, blocking = roll_up([
        ("composition", status_to_verdict(comp.status), True),
        ("recording", status_to_verdict(rec.status), True),
    ])
    row["verdict"], row["blocking"] = verdict, blocking
    row["complete"] = comp.status != "undetermined" and rec.status != "undetermined"
    print(f"\n  ROLL-UP: {verdict.upper()}  (blocking layer: {blocking})")
    return row


def table(rows):
    hr()
    print("SUMMARY")
    hr()
    cols = ("title", "rec_year", "work", "writers", "deaths", "comp_year", "complete", "verdict")
    hdr = f"{'title / artist':<36} {'rec':<7} {'work':<5} {'iswc':<5} {'writers':<8} {'deaths':<14} {'comp':<10} {'2-layer':<8} {'verdict'}"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        deaths = ",".join("?" if d is None else str(d) for d in r["deaths"]) or "-"
        comp = f"{r['comp_year']}" + ("" if r["comp_year_prop"] in (None, "P577_publication") else "*")
        label = r["title"] + (f" / {r['artist']}" if r["artist"] else "")
        rec = ("ERR" if r["rec_src"] == "ERR" else
               f"{r['rec_year']}{'r' if r['rec_src'] == 'performance-rel' else 'f'}" if r["rec_year"] else "-")
        work = "ERR" if r["work_fetch_failed"] else ("yes" if r["work"] else ("NO" if r["rec_year"] else "-"))
        print(f"{label:<36} {rec:<7} "
              f"{work:<5} "
              f"{'yes' if r['iswc'] else 'no':<5} "
              f"{len(r['writers']) if r['work'] else '-':<8} "
              f"{deaths:<14} "
              f"{comp if r['comp_year'] else '-':<10} "
              f"{'YES' if r['complete'] else 'no':<8} "
              f"{r['verdict'] or '-'}" + (f" ({r['blocking']})" if r["blocking"] else ""))
    print("\n  rec     = recording year; 'r' = dated performance relation, 'f' = MB first-release-date (earliest release on file)")
    print("  comp*   = year came from P1191 first-performance or P571 inception, not P577 publication")
    print("  ERR     = the HTTP request failed; says nothing about the data")
    print("  2-layer = both composition and recording layers determined (neither undetermined)")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        queries = [(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)]
    else:
        queries = QUERIES
    results = [run(t, a) for t, a in queries]
    print()
    table(results)
