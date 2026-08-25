"""
Spike: can free, keyless sources produce a correct two-layer determination?

For each (title, artist):
  1. MusicBrainz recording search. No artist + several artists in the
     results = ambiguous -> STOP and surface candidates. No research.
  2. Recording selection. Among the top K matching candidates, find one with
     a work relation (RAW work-rels JSON printed for every lookup). Then
     enumerate every recording MB links to that work, keep the ones credited
     to the artist, and pick the earliest DATED performance relation.
       dated performance relation  -> recording year, HIGH
       first-release-date only     -> LOW, UnresolvedQuestion, recording
                                      layer left UNDETERMINED (never a
                                      confident expiry from a reissue date)
  3. Writers: MB artist-rels cross-checked against Wikidata P86/P676 on the
     work item. Identical -> HIGH. Wikidata adds names -> MEDIUM, union used.
     Nothing to check against -> LOW and flagged.
  4. Composition year from Wikidata P577 (P1191/P571 fallback, flagged).
  5. rules: us_sound_recording / us_standard_term / roll_up, both required.
     life_plus_70 printed for information, tagged with writer confidence.

Nothing is inferred. If a step yields nothing, it says so and moves on.

Run:  python spike/spike.py                       (the batch below)
      python spike/spike.py "Take Five" "The Dave Brubeck Quartet"

The dicts named resolution / unresolved mirror field names in the
(pending) schemas.py — resolution_confidence, stop_for_disambiguation,
UnresolvedQuestion — and should be replaced by the real types when it lands.
"""

import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rules import (  # noqa: E402
    Determination, life_plus_70, roll_up, status_to_verdict,
    us_sound_recording, us_standard_term,
)
from spike.sources import (  # noqa: E402
    browse_recordings_for_work, get_death_year, get_work_dates,
    get_work_for_recording, get_work_writers_wikidata, get_writers,
    linked_works, search_recording,
)

QUERIES = [
    ("West End Blues", "Louis Armstrong"),        # demo: blocked case
    ("Rhapsody in Blue", "Paul Whiteman"),        # demo: clean case
    ("Take Five", None),
    ("Mack the Knife", None),
    ("Summertime", None),
    ("Blue Moon", None),
]

K_WORK_LOOKUPS = 10     # candidates to check for a work relation
SEARCH_LIMIT = 25


def hr(ch="=", n=78):
    print(ch * n)


def show(label, det, conf=None):
    tag = f"  [{conf}]" if conf else ""
    print(f"  {label:<12} {det.status:<14} expiry={det.expiry_year!s:<6} rule={det.rule_id}{tag}")
    print(f"  {'':<12} {det.explanation}")
    if det.blocked_by:
        print(f"  {'':<12} blocked_by={det.blocked_by}")


def new_row(title, artist):
    return {"title": title, "artist": artist, "resolution": None, "stop": False,
            "recording": None, "rec_year": None, "rec_src": None, "rec_conf": None,
            "work": None, "iswc": None, "writers": [], "writer_conf": None,
            "deaths": [], "comp_year": None, "comp_year_prop": None,
            "verdict": None, "blocking": None, "complete": False, "unresolved": []}


def unresolved(question, why, layers, search_terms, where, effort="minutes"):
    return {"question": question, "why_it_matters": why, "affects_layers": layers,
            "search_terms": search_terms, "where": where, "effort": effort}


def credited_to(cand, artist):
    return artist.lower() in (cand["artist"] or "").lower()


# ---------------------------------------------------------------------------

def run(title, artist):
    row = new_row(title, artist)
    hr()
    print(f"{title}" + (f"  —  {artist}" if artist else "  —  (no artist given)"))
    hr()

    # 1. search + ambiguity gate ---------------------------------------------
    print("\n[1] search_recording")
    cands = search_recording(title, artist, limit=SEARCH_LIMIT)
    if cands is None:
        print("  SEARCH REQUEST FAILED (see status above). Nothing known. Stopping here.")
        row["resolution"] = "ERR"
        return row
    if not cands:
        print("  NO RECORDING CANDIDATES. Stopping here.")
        row["resolution"] = "none"
        return row
    for c in cands[:10]:
        print(f"  {c['score']!s:>3}  {c['date'] or '----------':<10}  {c['mbid']}  {c['title']}  ·  {c['artist']}")
    if len(cands) > 10:
        print(f"  ... {len(cands) - 10} more")

    by_artist = defaultdict(list)
    for c in cands:
        by_artist[c["artist"]].append(c)

    if artist is None and len(by_artist) > 1:
        print(f"\n  >>> AMBIGUOUS: {len(by_artist)} different artists in the results and no artist given. <<<")
        print("  stop_for_disambiguation=True, resolution_confidence=LOW. No research done. Candidates:")
        for a, cs in sorted(by_artist.items(), key=lambda kv: min(c["date"] or "9999" for c in kv[1])):
            earliest = min((c["date"] for c in cs if c["date"]), default=None)
            titles = sorted({c["title"] for c in cs})
            print(f"    {earliest or '----':<10} {a:<40} {len(cs)} recording(s)  {titles}")
        row["resolution"], row["stop"] = "STOP", True
        row["verdict"] = "undetermined"
        return row

    if artist is not None:
        matched = [c for c in cands if credited_to(c, artist)]
        if not matched:
            print(f"\n  No candidate is credited to \"{artist}\". Not resolved. Stopping here.")
            row["resolution"] = "none"
            return row
        cands = matched

    # 2. find the work(s) the candidates link to -------------------------------
    # One composition can be several MB work entities (arrangements, "original
    # version", translations). Look at all top-K candidates and keep every
    # distinct work; the recording picked in step 3 decides which one counts.
    print(f"\n[2] get_work_for_recording — RAW RESPONSE for the top {K_WORK_LOOKUPS} candidates")
    works_seen = {}
    for c in cands[:K_WORK_LOOKUPS]:
        print(f"\n  -- {c['mbid']}  ({c['date']}, {c['artist']})")
        raw = get_work_for_recording(c["mbid"])
        print(json.dumps(raw, indent=2, ensure_ascii=False))
        if "_error" in raw:
            print(f"  >>> REQUEST FAILED ({raw['_error']}); this candidate tells us nothing. <<<")
            continue
        ws = linked_works(raw)
        if not ws:
            print("  no work relation on this candidate")
            continue
        for w in ws:
            works_seen.setdefault(w["work_mbid"], w)

    if not works_seen:
        print(f"\n  >>> NO LINKED WORK on any of the top {min(K_WORK_LOOKUPS, len(cands))} candidates. <<<")
        print("  Composition layer cannot be resolved from MusicBrainz.")
        row["resolution"] = "no_work"
        # Recording year would only be a release date -> LOW, not usable.
        dated = [c for c in cands if c["date"]]
        if dated:
            c0 = min(dated, key=lambda c: c["date"])
            row["recording"], row["rec_year"] = c0["mbid"], int(c0["date"][:4])
            row["rec_src"], row["rec_conf"] = "first-release-date", "LOW"
        return finish(row, comp=Determination(
            "undetermined", None, "spike_no_work_link",
            "Recording has no work relationship in MusicBrainz.", blocked_by="work_link"))

    print(f"\n  {len(works_seen)} distinct work(s) among the top candidates:")
    for w in works_seen.values():
        print(f"    {w['work_mbid']}  {w['title']}  iswc={w['iswcs']}")

    # 3. recording selection among every recording linked to those works ---------
    print("\n[3] browse_recordings_for_work — recording selection")
    mine, browse_failed = [], False
    for wid, w in works_seen.items():
        linked = browse_recordings_for_work(wid)
        if linked is None:
            print(f"  BROWSE REQUEST FAILED for work {wid}; its recordings are unknown.")
            browse_failed = True
            continue
        for r in linked:
            r["work"] = w
        m = [r for r in linked if artist is None or credited_to(r, artist)]
        print(f"  work {wid}: {len(linked)} recordings linked; {len(m)} credited to \"{artist}\"")
        mine.extend(m)

    sessions = defaultdict(list)
    for r in mine:
        sessions[r["perf_begin"]].append(r)
    dated_keys = sorted(k for k in sessions if k)
    undated = sessions.get(None, [])
    for k in dated_keys:
        rs = sessions[k]
        print(f"  session {k:<10}  {len(rs)} entity(ies)  earliest release on file {min((r['date'] or '----') for r in rs)}  "
              f"e.g. {rs[0]['mbid']}  {rs[0]['artist']}  [work {rs[0]['work']['work_mbid'][:8]}]")
    if undated:
        print(f"  undated        {len(undated)} entity(ies)  releases on file: {sorted({(r['date'] or '----')[:4] for r in undated})}")

    if dated_keys:
        k = dated_keys[0]
        pick = min(sessions[k], key=lambda r: r["date"] or "9999")
        work = pick["work"]
        row["recording"], row["rec_year"] = pick["mbid"], int(k[:4])
        row["rec_src"], row["rec_conf"] = "performance-rel", "HIGH"
        print(f"\n  picked {pick['mbid']} — earliest dated session {k} ({pick['artist']}); recording year {row['rec_year']} [HIGH]")
        print(f"  its work: {work['work_mbid']}  {work['title']}  iswc={work['iswcs']}")
        if len(dated_keys) == 1 and not undated:
            row["resolution"] = "HIGH"
        else:
            row["resolution"] = "MEDIUM"
            print(f"  resolution_confidence=MEDIUM: {len(dated_keys)} dated session(s) ({', '.join(dated_keys)}) and "
                  f"{len(undated)} undated entity(ies) for this artist; earliest dated chosen, the rest are alternates.")
    elif mine:
        pick = min(mine, key=lambda r: r["date"] or "9999")
        work = pick["work"]
        print(f"  its work: {work['work_mbid']}  {work['title']}  iswc={work['iswcs']}")
        if pick["date"]:
            row["recording"], row["rec_year"] = pick["mbid"], int(pick["date"][:4])
            row["rec_src"], row["rec_conf"] = "first-release-date", "LOW"
        row["resolution"] = "LOW"
        print(f"\n  NO DATED SESSION for this artist. Earliest release on file is {pick['date']} ({pick['mbid']}) — "
              "that may be a reissue. Recording year is LOW confidence and will NOT drive a determination.")
        row["unresolved"].append(unresolved(
            f"In what year was the recording of \"{title}\" by {pick['artist']} first published?",
            "The CLASSICS Act term runs from first publication. MusicBrainz only has the earliest "
            f"release on file ({pick['date']}), which may be a reissue decades after the session.",
            ["recording"],
            [f'"{title}" "{pick["artist"]}" discography', f'"{title}" {pick["artist"]} 78 rpm'],
            ["https://adp.library.ucsb.edu/ (Discography of American Historical Recordings) — search title + artist",
             f"https://musicbrainz.org/recording/{pick['mbid']}"],
        ))
    else:
        work = next(iter(works_seen.values()))
        if browse_failed:
            print("\n  Browse failed, so the work's recordings are unknown. Cannot select. (Not a data finding.)")
            row["resolution"] = "ERR"
        else:
            print("\n  Work has no recordings credited to this artist. Nothing to select.")
            row["resolution"] = "none"

    return finish(row, comp=None, work_info=work)


def finish(row, comp, work_info=None):
    """Steps 4-5: writers (cross-checked), composition year, rules, roll-up."""
    title, artist = row["title"], row["artist"]
    deaths = []

    if work_info is not None:
        # 4. writers + Wikidata cross-check ----------------------------------
        print("\n[4] get_writers + Wikidata cross-check (P86 composer / P676 lyricist)")
        row["work"] = work_info["work_mbid"]
        wr = get_writers(work_info["work_mbid"])
        iswcs = work_info["iswcs"] or wr["iswcs"]
        row["iswc"] = iswcs[0] if iswcs else None
        print(f"  iswc={iswcs}  wikidata={wr['wikidata']}")
        if not wr["writers"]:
            print("  MB: NO WRITER RELATIONS on this work.")
        for w in wr["writers"]:
            print(f"  MB  {w['role']:<10} {w['name']}  {w['mbid']}")

        mb_by_qid, mb_unmatched = {}, []
        for w in wr["writers"]:
            r = get_death_year(w["name"])
            print(f"      {w['name']:<24} -> {r['qid']}  \"{r['label']}\" — {r['description']}  P570={r['death_year']}")
            if r["qid"]:
                mb_by_qid[r["qid"]] = {"name": w["name"], "role": w["role"], "death_year": r["death_year"], "src": "MB"}
            else:
                mb_unmatched.append({"name": w["name"], "role": w["role"], "death_year": None, "src": "MB"})

        wd = get_work_writers_wikidata(wr["wikidata"]) if wr["wikidata"] else []
        for w in wd:
            print(f"  WD  {w['role']:<10} {w['label']}  {w['qid']}  P570={w['death_year']}")
        wd_by_qid = {w["qid"]: w for w in wd}

        if not wd:
            why = "no Wikidata item linked from MB" if not wr["wikidata"] else f"{wr['wikidata']} has no P86/P676"
            row["writer_conf"] = "LOW"
            print(f"  writer list UNCORROBORATED ({why}). Confidence LOW; the list may be incomplete.")
            row["unresolved"].append(unresolved(
                f"Who are all the credited writers of \"{title}\"?",
                "Life+70 runs from the death of the LAST surviving author; a missing co-writer "
                "silently shortens the term. MusicBrainz's list could not be cross-checked.",
                ["composition"],
                [f'"{title}" composer lyricist', f'"{title}" ISWC'],
                ["https://www.ascap.com/repertory", "https://repertoire.bmi.com/", "https://portal.themlc.com/search"],
            ))
        elif set(wd_by_qid) == set(mb_by_qid) and not mb_unmatched:
            row["writer_conf"] = "HIGH"
            print("  writer list CORROBORATED: MB and Wikidata agree exactly.")
        else:
            row["writer_conf"] = "MEDIUM"
            only_wd = [wd_by_qid[q]["label"] for q in wd_by_qid if q not in mb_by_qid]
            only_mb = [mb_by_qid[q]["name"] for q in mb_by_qid if q not in wd_by_qid] + [w["name"] for w in mb_unmatched]
            print(f"  writer lists DIFFER — only in Wikidata: {only_wd}; only in MB: {only_mb}. Using the union, confidence MEDIUM.")

        writers = {}
        for q, w in mb_by_qid.items():
            writers[q] = w
        for q, w in wd_by_qid.items():
            if q in writers:
                writers[q]["death_year"] = writers[q]["death_year"] or w["death_year"]
                writers[q]["src"] = "MB+WD"
            else:
                writers[q] = {"name": w["label"], "role": w["role"], "death_year": w["death_year"], "src": "WD"}
        all_writers = list(writers.values()) + mb_unmatched
        row["writers"] = [f"{w['name']} ({w['src']})" for w in all_writers]
        deaths = [w["death_year"] for w in all_writers]
        row["deaths"] = deaths

        # 4a. composition year --------------------------------------------------
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
        if comp_year is not None:
            comp = us_standard_term(comp_year)
        else:
            comp = Determination("undetermined", None, "spike_no_composition_year",
                                 "No publication/composition year found for the work.",
                                 blocked_by="composition_year")
        if comp.blocked_by == "renewal_filed":
            row["unresolved"].append(unresolved(
                f"Was the {comp_year} copyright in \"{title}\" renewed in year 28 ({comp_year + 27}–{comp_year + 28})?",
                "If not renewed, the composition entered the public domain "
                f"1 January {comp_year + 29}; if renewed, protected until 1 January {comp_year + 96}.",
                ["composition"],
                [f'"{title}" renewal {comp_year + 27}', f'"{title}" renewal {comp_year + 28}'],
                [f"https://archive.org/details/copyrightrecords — Catalog of Copyright Entries, Music, {comp_year + 27}–{comp_year + 28} renewals",
                 "https://cocatalog.loc.gov/ (post-1978 renewals only)"],
                effort="hours (scanned card catalog for pre-1978 renewals)",
            ))

    # 5. determination -----------------------------------------------------
    print("\n[5] determination")
    if row["rec_conf"] == "HIGH":
        rec = us_sound_recording(row["rec_year"])
    else:
        rec = Determination("undetermined", None, "spike_recording_year_unconfirmed",
                            "No dated recording session in MusicBrainz; the only date is an "
                            "earliest-release-on-file that may be a reissue.",
                            blocked_by="recording_pub_year")
        if row["rec_year"]:
            prov = us_sound_recording(row["rec_year"])
            print(f"  (provisional, LOW, NOT used: if {row['rec_year']} were the publication year -> "
                  f"{prov.status}, expiry {prov.expiry_year}, {prov.rule_id})")

    show("composition", comp)
    show("recording", rec, row["rec_conf"])
    if deaths:
        show("life+70 (EU, info only)", life_plus_70(deaths, "EU"), f"writers {row['writer_conf']}")

    verdict, blocking = roll_up([
        ("composition", status_to_verdict(comp.status), True),
        ("recording", status_to_verdict(rec.status), True),
    ])
    row["verdict"], row["blocking"] = verdict, blocking
    row["complete"] = comp.status != "undetermined" and rec.status != "undetermined"
    print(f"\n  ROLL-UP: {verdict.upper()}  (blocking layer: {blocking})")

    if row["unresolved"]:
        print("\n  UNRESOLVED QUESTIONS")
        for u in row["unresolved"]:
            print(f"  • {u['question']}")
            print(f"    why: {u['why_it_matters']}")
            print(f"    affects: {u['affects_layers']}  effort: {u['effort']}")
            print(f"    search: {u['search_terms']}")
            for w in u["where"]:
                print(f"    where: {w}")
    return row


# ---------------------------------------------------------------------------

def table(rows):
    hr()
    print("SUMMARY")
    hr()
    hdr = (f"{'title / artist':<34} {'resolve':<8} {'rec':<7} {'work':<5} {'iswc':<5} "
           f"{'writers':<8} {'wconf':<7} {'deaths':<14} {'comp':<7} {'2-layer':<8} {'verdict'}")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        label = r["title"] + (f" / {r['artist']}" if r["artist"] else "")
        rec = (f"{r['rec_year']}{'r' if r['rec_src'] == 'performance-rel' else 'f'}" if r["rec_year"] else "-")
        deaths = ",".join("?" if d is None else str(d) for d in r["deaths"]) or "-"
        comp = (f"{r['comp_year']}" + ("" if r["comp_year_prop"] in (None, "P577_publication") else "*")) if r["comp_year"] else "-"
        print(f"{label:<34} {r['resolution'] or '-':<8} {rec:<7} "
              f"{'yes' if r['work'] else ('-' if r['stop'] or r['resolution'] in ('ERR', 'none') else 'NO'):<5} "
              f"{'yes' if r['iswc'] else ('no' if r['work'] else '-'):<5} "
              f"{len(r['writers']) if r['work'] else '-':<8} "
              f"{r['writer_conf'] or '-':<7} "
              f"{deaths:<14} {comp:<7} "
              f"{'YES' if r['complete'] else 'no':<8} "
              f"{r['verdict'] or '-'}" + (f" ({r['blocking']})" if r["blocking"] else "")
              + (f"  [{len(r['unresolved'])} unresolved]" if r["unresolved"] else ""))
    print("\n  resolve = recording resolution confidence: HIGH one dated session · MEDIUM several dated sessions, earliest used ·")
    print("            LOW release date only · STOP ambiguous, no research · no_work no work relation in top candidates")
    print("  rec     = recording year; 'r' dated performance relation (used) · 'f' first-release-date (LOW, never used for a term)")
    print("  wconf   = writer-list confidence: HIGH MB=Wikidata · MEDIUM union · LOW uncorroborated")
    print("  comp*   = year from P1191 first-performance or P571 inception, not P577 publication")
    print("  2-layer = both layers determined (neither undetermined)")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        queries = [(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)]
    else:
        queries = QUERIES
    results = [run(t, a) for t, a in queries]
    print()
    table(results)
