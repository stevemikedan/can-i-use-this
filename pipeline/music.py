"""
Music path: "title — artist" -> RightsResponse, as plain Python.

  classify   music (given)
  identify   MusicBrainz search; no artist + several artists => STOP with
             candidates (Hard rule 6). Work-rels sweep of the top K
             candidates -> every distinct work -> every recording linked to
             each work -> the artist's earliest DATED session.
  decompose  composition + sound_recording layers with identifiers
  research   Tier 2: Wikidata publication year, writers cross-checked
             against MusicBrainz, death years.
             Tier 3: Parallel SEARCH for renewal records (1931-1963 window)
             and for the original release when only a reissue date exists.
  rules      rules/ arithmetic per (layer x jurisdiction)   (determine.py)
  assemble   verdicts, roll-up, unresolved questions, handoff (assemble.py)

Every value is a ResearchedFact with Sources or becomes an UnresolvedQuestion.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from agent.reader_schema import recording_year_to_fact, renewal_to_fact
from research import parallel_client as pc
from research.music import renewal_numbers, renewal_record_system, search_recording_date, search_renewal
from rules import CURRENT_YEAR
from schemas import (
    AssetQuery, AssetType, Candidate, Confidence, HandoffLink, Identifier, LinkTier,
    PipelineStage as S, RecordingDateBasis, ResearchMethod, ResearchedFact, ResolvedEntity,
    RightsLayer, RightsLayerKind, Source, TermFacts, UnresolvedQuestion,
)
from sources import musicbrainz as mb
from sources import wikidata as wd
from sources.http import as_source

from .assemble import assemble, failed_response, stop_response
from .determine import determine_all
from .events import Emitter

import os

K_WORK_LOOKUPS = 10       # recording work-rels sweep — fallback only
MAX_WORKS = 6             # same-title work entities to enumerate (arrangements, versions)
CORE_WORK_SCORE = 90      # works below this are only browsed if nothing dated was found above
MAX_PAGES = 10            # 1,000 linked recordings; beyond that the scan is flagged partial
USE_WORK_SEARCH = os.environ.get("CIUT_WORK_SEARCH", "1") != "0"   # =0 forces the old sweep (benchmarks)
MAX_CANDIDATES = 8
COMPOSITION, RECORDING = "composition", "sound_recording"


def parse_query(raw: str) -> tuple[str, Optional[str]]:
    for sep in (" — ", " – ", " - ", " by "):
        if sep in raw:
            title, artist = raw.split(sep, 1)
            return title.strip().strip('"'), (artist.strip() or None)
    return raw.strip().strip('"'), None


def _rank(c: Confidence) -> int:
    return {Confidence.HIGH: 3, Confidence.MEDIUM: 2, Confidence.LOW: 1, Confidence.NONE: 0}[c]


def _min(*cs: Confidence) -> Confidence:
    return min(cs, key=_rank)


@dataclass
class Writer:
    name: str
    role: str
    qid: Optional[str] = None
    mb_mbid: Optional[str] = None
    death_year: Optional[int] = None
    src: str = "MB"                       # MB | WD | MB+WD
    sources: list[Source] = field(default_factory=list)


# --- identify -----------------------------------------------------------------

def _search_and_gate(query: AssetQuery, title: str, artist: Optional[str], em: Emitter):
    """Returns (candidates, stop_or_failed_response)."""
    em.emit(S.IDENTIFY, "started", f'Searching MusicBrainz for "{title}"' + (f" — {artist}" if artist else ""))
    s = mb.search_recordings(title, artist)
    em.consulted()
    if not s.ok:
        em.emit(S.IDENTIFY, "failed", "MusicBrainz search failed", error_message=s.error, degraded=True)
        return None, failed_response(query, title, artist, em,
                                     f"MusicBrainz could not be reached ({s.error}).")
    cands = s.data
    if not cands:
        em.emit(S.IDENTIFY, "failed", "No recordings found")
        return None, failed_response(query, title, artist, em,
                                     "No recording with that title was found in MusicBrainz.")

    if artist is None:
        by_artist: dict[str, list] = defaultdict(list)
        for c in cands:
            by_artist[c["artist"]].append(c)
        if len(by_artist) > 1:
            rows = sorted(by_artist.items(), key=lambda kv: min((c["date"] or "9999") for c in kv[1]))
            candidates = []
            for a, cs in rows[:MAX_CANDIDATES]:
                earliest = min((c["date"] for c in cs if c["date"]), default=None)
                c0 = min(cs, key=lambda c: c["date"] or "9999")
                candidates.append(Candidate(
                    label=f"{a} — {c0['title']}",
                    disambiguator=(f"earliest release on file {earliest}" if earliest else "no release date on file")
                                  + f"; {len(cs)} recording entit{'y' if len(cs) == 1 else 'ies'}",
                    identifiers=[Identifier(scheme="musicbrainz_recording", value=c0["mbid"],
                                            layer_id=RECORDING, confidence=Confidence.LOW)],
                    likelihood=Confidence.LOW,
                ))
            em.emit(S.IDENTIFY, "complete", f"Ambiguous: {len(by_artist)} different artists match — stopping for disambiguation")
            return None, stop_response(query, title, candidates, len(by_artist), em)
    else:
        matched = [c for c in cands if mb.credited_to(c["artist"], artist)]
        if not matched:
            em.emit(S.IDENTIFY, "failed", f'No recording credited to "{artist}"')
            return None, failed_response(query, title, artist, em,
                                         f'No recording of "{title}" credited to {artist} was found. '
                                         "Try the artist name as it appears on the release.")
        cands = matched
    return cands, None


@dataclass
class Selection:
    pick: dict
    work: dict
    rec_year: Optional[int]
    basis: RecordingDateBasis
    rec_conf: Confidence
    resolution: Confidence
    sessions: list[str]
    undated: int
    complete: bool
    works: dict
    source: Source


def _find_works(title: str, cands: list[dict], em: Emitter) -> dict[str, dict]:
    """
    One work search by title (Aug 26: finds every work the sweep found, in a
    single call). Falls back to the recording work-rels sweep only when the
    search fails or returns nothing.
    """
    works: dict[str, dict] = {}
    ws = mb.search_works(title) if USE_WORK_SEARCH else None
    if ws is not None:
        em.consulted()
        if ws.ok:
            for w in ws.data[:MAX_WORKS]:
                works[w["work_mbid"]] = w
        if works:
            em.emit(S.IDENTIFY, "progress", f"{len(works)} composition entit{'y' if len(works) == 1 else 'ies'} titled \"{title}\" (work search)")
            return works
        if not ws.ok:
            em.emit(S.IDENTIFY, "progress", f"Work search failed ({ws.error}); falling back to a recording sweep", degraded=True)
    for c in cands[:K_WORK_LOOKUPS]:
        f = mb.recording_works(c["mbid"])
        em.consulted()
        if f.ok:
            for w in f.data["works"]:
                works.setdefault(w["work_mbid"], w)
    if works:
        em.emit(S.IDENTIFY, "progress", f"{len(works)} composition entit{'y' if len(works) == 1 else 'ies'} linked from the top candidates (sweep)")
    return works


def _select_recording(title: str, cands: list[dict], artist: Optional[str], em: Emitter) -> Optional[Selection]:
    works = _find_works(title, cands, em)
    if not works:
        em.emit(S.IDENTIFY, "failed", "No composition entity found for this title")
        return None

    mine: list[dict] = []
    complete = True
    src_url, src_at = None, datetime.now(timezone.utc)
    ordered = sorted(works.items(), key=lambda kv: -(kv[1].get("score") or 0))
    for wid, w in ordered:
        # Lower-ranked same-title works (score < 90) are usually stray
        # arrangements; only browse them if nothing dated has turned up yet.
        if (w.get("score") or 100) < CORE_WORK_SCORE and any(
                r["perf_begin"] for r in mine if artist is None or mb.credited_to(r["artist"], artist)):
            break
        wr = mb.work_recordings(wid, max_pages=MAX_PAGES)
        em.consulted(max(wr.pages_fetched, 1))
        if wr.error:
            em.emit(S.IDENTIFY, "progress", f"Could not list all recordings of work {wid[:8]} ({wr.error})",
                    degraded=True, error_message=wr.error)
        complete = complete and wr.complete
        for r in wr.recordings:
            if artist is None or mb.credited_to(r["artist"], artist):
                r["work"] = w
                mine.append(r)
        src_url, src_at = wr.url or src_url, wr.retrieved_at
    if not mine:
        em.emit(S.IDENTIFY, "failed", "None of the linked recordings is credited to this artist")
        return None

    sessions: dict[Optional[str], list[dict]] = defaultdict(list)
    for r in mine:
        sessions[r["perf_begin"]].append(r)
    dated = sorted(k for k in sessions if k)
    undated = len(sessions.get(None, []))

    if dated:
        k = dated[0]
        pick = min(sessions[k], key=lambda r: r["date"] or "9999")
        year = int(k[:4])
        basis = RecordingDateBasis.DATED_PERFORMANCE
        # Terms run from PUBLICATION; the dated relation is the session. It is
        # taken as the publication year only when the earliest release on file
        # is contemporaneous (same or next year); otherwise MEDIUM.
        rel_year = int(pick["date"][:4]) if pick["date"] else None
        rec_conf = Confidence.HIGH if rel_year is not None and 0 <= rel_year - year <= 1 else Confidence.MEDIUM
        resolution = Confidence.HIGH if (len(dated) == 1 and undated == 0 and complete) else Confidence.MEDIUM
        excerpt = f"performance relation dated {k}; earliest release on file {pick['date']}"
    else:
        pick = min(mine, key=lambda r: r["date"] or "9999")
        year = int(pick["date"][:4]) if pick["date"] else None
        basis = RecordingDateBasis.FIRST_RELEASE_DATE if year else RecordingDateBasis.UNKNOWN
        rec_conf, resolution = Confidence.LOW, Confidence.LOW
        excerpt = f"no dated session; earliest release on file {pick['date']}"
    source = Source(name="MusicBrainz", url=f"https://musicbrainz.org/recording/{pick['mbid']}",
                    method=ResearchMethod.DIRECT_API, retrieved_at=src_at, excerpt=excerpt[:200])
    return Selection(pick, pick["work"], year, basis, rec_conf, resolution, dated, undated, complete, works, source)


# --- research: composition ----------------------------------------------------

@dataclass
class CompositionFacts:
    writers: list[Writer]
    corroborated: bool
    writer_conf: Confidence
    year: Optional[int]
    year_conf: Confidence
    year_prop: Optional[str]
    year_sources: list[Source]
    wikidata: Optional[str]
    iswcs: list[str]
    title: str
    notes: list[str]
    sibling_extra: list[Writer] = field(default_factory=list)


def _writer_qid(wr: Writer, em: Emitter, notes: list[str]) -> Optional[str]:
    """
    The MusicBrainz artist's linked Wikidata item. Falls back to a name
    search only when MB has no link, and says so — a name search can land on
    the wrong person ("Clarence Williams" -> the actor, not the pianist).
    """
    if wr.mb_mbid:
        a = mb.artist_wikidata(wr.mb_mbid)
        em.consulted()
        if a.ok and a.data["wikidata"]:
            wr.sources.append(as_source(a, "MusicBrainz", excerpt=f"artist linked to Wikidata {a.data['wikidata']}"))
            return a.data["wikidata"]
    hit = wd.search_entities(wr.name)
    em.consulted()
    if hit.ok and hit.data:
        notes.append(f"{wr.name}: matched to Wikidata by name search ({hit.data[0]['id']}, "
                     f"{hit.data[0].get('description') or 'no description'}) — not via a MusicBrainz link")
        return hit.data[0]["id"]
    return None


def _research_composition(sel: Selection, em: Emitter) -> CompositionFacts:
    w = sel.work
    det = mb.work_details(w["work_mbid"])
    em.consulted()
    notes: list[str] = []
    mb_writers: list[Writer] = []
    mb_src = as_source(det, "MusicBrainz") if det.ok else None
    mb_begin_years: set[int] = set()
    if det.ok:
        for x in det.data["writers"]:
            mb_writers.append(Writer(x["name"], x["role"], mb_mbid=x["mbid"], sources=[mb_src]))
            if x.get("begin"):
                mb_begin_years.add(int(x["begin"][:4]))
    else:
        notes.append(f"MusicBrainz work lookup failed ({det.error})")
    qid = det.data["wikidata"] if det.ok else None
    iswcs = (w.get("iswcs") or (det.data["iswcs"] if det.ok else [])) or []
    title = (det.data["title"] if det.ok else None) or w.get("title") or ""

    # MB writer -> Wikidata QID via the artist's own Wikidata link (exact person).
    for wr in mb_writers:
        wr.qid = _writer_qid(wr, em, notes)

    wd_writers: list[dict] = []
    year, year_conf, year_prop, year_sources = None, Confidence.NONE, None, []
    if qid:
        dates = wd.work_dates(qid)
        em.consulted()
        wdf = dates["fetched"]
        for prop, conf in (("P577_publication", Confidence.MEDIUM),
                           ("P1191_first_performance", Confidence.LOW),
                           ("P571_inception", Confidence.LOW)):
            if dates[prop]:
                year, year_conf, year_prop = dates[prop], conf, prop
                break
        if wdf.ok:
            year_sources.append(as_source(wdf, "Wikidata", excerpt=f"{year_prop} = {year}" if year else None))
        if year and year in mb_begin_years and mb_src:
            year_conf = Confidence.HIGH          # two independent sources agree
            year_sources.append(mb_src)
        if year_prop and year_prop != "P577_publication":
            notes.append(f"No publication date on Wikidata; using {year_prop} = {year}")
        ww = wd.work_writers(qid)
        em.consulted(1 + len(ww["writers"]))
        wd_writers = ww["writers"]
    else:
        notes.append("Work has no Wikidata item linked from MusicBrainz")

    # Cross-check (PROJECT.md §3 rule 2)
    by_qid: dict[str, Writer] = {}
    for wr in mb_writers:
        if wr.qid:
            by_qid[wr.qid] = wr
    unmatched = [wr for wr in mb_writers if not wr.qid]
    wd_ids = {x["qid"] for x in wd_writers}
    for x in wd_writers:
        src = as_source(x["fetched"], "Wikidata", excerpt=f"P570 = {x['death_year']}") if x["fetched"].ok else None
        if x["qid"] in by_qid:
            wr = by_qid[x["qid"]]
            wr.death_year, wr.src = x["death_year"], "MB+WD"
            if src:
                wr.sources.append(src)
        else:
            by_qid[x["qid"]] = Writer(x["label"] or x["qid"], x["role"], qid=x["qid"],
                                      death_year=x["death_year"], src="WD", sources=[src] if src else [])
    for wr in list(by_qid.values()):
        if wr.death_year is None and wr.qid and wr.src == "MB":
            ent = wd.entity(wr.qid)
            em.consulted()
            if ent.ok:
                wr.death_year = wd.claim_year(ent.data, "P570")
                wr.sources.append(as_source(ent, "Wikidata", excerpt=f"P570 = {wr.death_year}"))
    writers = list(by_qid.values()) + unmatched

    # Sibling works: the same title in MusicBrainz is often several entities
    # (e.g. "West End Blues" and "West End Blues (Armstrong recording)"). When
    # a sibling shares a writer with this work, its extra credits are real
    # evidence of a missing co-writer — surfaced on the unresolved question,
    # never silently merged into the determination.
    sibling_extra: list[Writer] = []
    own_names = {wr.name.lower() for wr in mb_writers}
    for wid, w in sel.works.items():
        if wid == sel.work["work_mbid"] or not own_names:
            continue
        sd = mb.work_details(wid)
        em.consulted()
        if not sd.ok:
            continue
        names = {x["name"].lower() for x in sd.data["writers"]}
        if not (names & own_names):
            continue
        for x in sd.data["writers"]:
            if x["name"].lower() in own_names or any(x["name"].lower() == s.name.lower() for s in sibling_extra):
                continue
            extra = Writer(x["name"], x["role"], mb_mbid=x["mbid"], src=f"MB sibling work {wid[:8]}",
                           sources=[as_source(sd, "MusicBrainz", excerpt=f"{x['role']} on sibling work {sd.data['title']!r}")])
            extra.qid = _writer_qid(extra, em, notes)
            if extra.qid:
                ent = wd.entity(extra.qid)
                em.consulted()
                if ent.ok:
                    extra.death_year = wd.claim_year(ent.data, "P570")
            sibling_extra.append(extra)

    if not wd_writers:
        corroborated, writer_conf = False, Confidence.LOW
        notes.append("Writer list could not be cross-checked against Wikidata (no composer/lyricist on the item)"
                     if qid else "Writer list could not be cross-checked against Wikidata")
    elif wd_ids == set(by_qid) and not unmatched and {wr.qid for wr in mb_writers} == wd_ids:
        corroborated, writer_conf = True, Confidence.HIGH
    else:
        corroborated, writer_conf = False, Confidence.MEDIUM
        only_wd = [by_qid[q].name for q in wd_ids - {wr.qid for wr in mb_writers}]
        only_mb = [wr.name for wr in mb_writers if wr.qid not in wd_ids]
        notes.append(f"Writer lists differ — only Wikidata: {only_wd}; only MusicBrainz: {only_mb}; union used")
    if sibling_extra:
        notes.append("MusicBrainz sibling work also credits: " + ", ".join(
            f"{s.name} (d. {s.death_year})" if s.death_year else s.name for s in sibling_extra))
        corroborated = False
    return CompositionFacts(writers, corroborated, writer_conf, year, year_conf, year_prop,
                            year_sources, qid, iswcs, title, notes, sibling_extra)


# --- the renewal question -------------------------------------------------------

_RENEWAL_WHY = "Works published 1931–1963 lost protection after 28 years unless renewed."


def renewal_question(title: str, year: int, links, numbers: list[str]) -> UnresolvedQuestion:
    """
    The open year-28 question, pointed at the record system that actually
    holds the answer. Windows of 1978 or later are in the Copyright Office
    online catalog — the scanned CCE volumes web search reaches end in 1977,
    so sending someone there is a dead end, not a handoff.
    """
    y28 = year + 27
    system = renewal_record_system(year)
    if system == "online":
        where = (f" The {y28}–{y28 + 1} renewal window falls after 1977, so the record is in the US Copyright "
                 f"Office online public catalog (renewals received since 1978, RE-numbered), not in the scanned "
                 f"Catalog of Copyright Entries volumes that web search reaches — search the online catalog by "
                 f"title and claimant.")
        effort = "minutes"
    elif system == "both":
        where = (f" The {y28}–{y28 + 1} renewal window straddles 1978: a {y28} renewal is in the scanned Catalog "
                 f"of Copyright Entries, a {y28 + 1} renewal in the US Copyright Office online public catalog "
                 f"(RE-numbered) — check both.")
        effort = "hours"
    else:
        where = " Renewal records are scanned catalogs, not a queryable database."
        effort = "hours"
    return UnresolvedQuestion(
        question_id=f"{COMPOSITION}:renewal",
        question=f'Was the {year} US copyright in "{title}" renewed in {y28}–{y28 + 1}?',
        why_it_matters=_RENEWAL_WHY + where
                       + (f" Search found renewal-style registration numbers {numbers[:3]} — check them." if numbers else ""),
        if_yes=f"Protected until 1 January {year + 96}.",
        if_no=f"Entered the public domain 1 January {year + 29}.",
        affects_layer_ids=[COMPOSITION],
        resolution_links=links,
        search_terms=[f'"{title}" renewal {y28}', f'"{title}" renewal {y28 + 1}'],
        estimated_effort=effort,
    )


def renewal_extras(title: str, year: int) -> dict:
    """Registry extras that select the CCE-scans and/or online-catalog handoff links."""
    system = renewal_record_system(year)
    extra = {"year": year + 27, "year_after": year + 28}
    if system in ("scans", "both"):
        extra["renewal_title"] = title
    if system in ("online", "both"):
        extra["renewal_online_title"] = title
    return extra


# --- the pipeline ---------------------------------------------------------------

def run_music(query: AssetQuery, *, emitter: Optional[Emitter] = None, reader=None) -> tuple:
    """
    Returns (RightsResponse, Emitter).

    reader: the Tier 3 reading step (agent.reader.Reader). Defaults to the
    NullReader — no evidence is read into a fact, every open question stays
    open. A real reader resolves the renewal window and the recording-date
    window from the searched evidence, producing a cited fact for the rules
    engine. The reader never computes a term.
    """
    from agent.reader import NullReader
    reader = reader or NullReader()
    em = emitter or Emitter()
    title, artist = parse_query(query.raw_input)
    em.emit(S.CLASSIFY, "complete", "Music — a composition and a sound recording, owned separately",
            detail=f'"{title}"' + (f" — {artist}" if artist else " (no artist given)"))

    cands, early = _search_and_gate(query, title, artist, em)
    if early is not None:
        return early, em
    sel = _select_recording(title, cands, artist, em)
    if sel is None:
        return failed_response(query, title, artist, em,
                               "The recording could not be matched to a composition in MusicBrainz."), em
    when = sel.sessions[0] if sel.sessions else f"earliest release on file {sel.pick['date']}"
    em.emit(S.IDENTIFY, "complete",
            f"Resolved: {sel.pick['artist']}, {when}" + ("" if sel.complete else " (partial scan)"),
            partial={"recording": sel.pick["mbid"], "work": sel.work["work_mbid"],
                     "recording_year": sel.rec_year, "date_basis": sel.basis.value})

    # DECOMPOSE ------------------------------------------------------------------
    comp_ids = [Identifier(scheme="musicbrainz_work", value=sel.work["work_mbid"], layer_id=COMPOSITION,
                           confidence=sel.resolution, is_primary=True)]
    rec_ids = [Identifier(scheme="musicbrainz_recording", value=sel.pick["mbid"], layer_id=RECORDING,
                          confidence=sel.resolution, source=sel.source, is_primary=True)]
    composition = RightsLayer(layer_id=COMPOSITION, kind=RightsLayerKind.COMPOSITION,
                              label="Composition", identifiers=comp_ids)
    recording = RightsLayer(layer_id=RECORDING, kind=RightsLayerKind.SOUND_RECORDING,
                            label="Sound recording", identifiers=rec_ids)
    layers = [composition, recording]
    em.emit(S.DECOMPOSE, "complete", "Found 2 rights layers: composition and sound recording",
            partial={"layers": [COMPOSITION, RECORDING]})

    # RESEARCH ---------------------------------------------------------------------
    em.emit(S.RESEARCH, "started", "Researching both layers — Tier 2 first")
    cf = _research_composition(sel, em)
    for iswc in cf.iswcs:
        comp_ids.append(Identifier(scheme="iswc", value=iswc, layer_id=COMPOSITION, confidence=Confidence.MEDIUM))
    if cf.wikidata:
        comp_ids.append(Identifier(scheme="wikidata", value=cf.wikidata, layer_id=COMPOSITION, confidence=Confidence.MEDIUM))
    composition.label = f"Composition ({cf.year})" if cf.year else "Composition"
    recording.label = f"Sound recording ({sel.rec_year})" if sel.rec_year else "Sound recording"

    questions: list[UnresolvedQuestion] = []
    question_ids: dict[str, str] = {}
    writer_names = [w.name for w in cf.writers]
    death_years = [w.death_year for w in cf.writers] or [None]

    tf = composition.term_facts
    if cf.year:
        reasoning = f"Wikidata {cf.year_prop}" + (" corroborated by MusicBrainz composer-relation date" if cf.year_conf is Confidence.HIGH else "")
        tf.first_publication_year = ResearchedFact(value=cf.year, confidence=cf.year_conf,
                                                   sources=cf.year_sources,
                                                   reasoning=reasoning + ("; " + "; ".join(cf.notes) if cf.notes else ""))
    known = [w.death_year for w in cf.writers if w.death_year is not None]
    if cf.writers and known and len(known) == len(cf.writers):
        last = max(known)
        who = ", ".join(f"{w.name} d. {w.death_year}" for w in cf.writers)
        tf.author_death_year = ResearchedFact(value=last, confidence=cf.writer_conf,
                                              sources=[s for w in cf.writers for s in w.sources],
                                              reasoning=f"Last surviving author: {who}")
    tf.writer_list_corroborated = cf.corroborated
    for w in cf.writers:
        composition.holders.append(__import__("schemas").RightsHolder(
            name=ResearchedFact(value=w.name, confidence=cf.writer_conf, sources=w.sources,
                                reasoning=f"credited by {w.src}"),
            role="author"))

    if not cf.corroborated:
        qid_ = f"{COMPOSITION}:writers"
        question_ids["author_death_year"] = qid_
        listed = ", ".join(f"{w.name} (d. {w.death_year})" if w.death_year else w.name for w in cf.writers) or "none"
        listed_last = max((w.death_year for w in cf.writers if w.death_year), default=None)
        extra_last = max((s.death_year for s in cf.sibling_extra if s.death_year), default=None)
        why = (f"UK/EU terms run from the death of the LAST surviving author; a missing co-writer silently "
               f"shortens the term. Credited on the selected MusicBrainz work: {listed}; this list could not "
               f"be corroborated against Wikidata.")
        if cf.sibling_extra:
            why += (" MusicBrainz's other entry for this title also credits "
                    + ", ".join(f"{s.name} (d. {s.death_year})" if s.death_year else s.name for s in cf.sibling_extra) + ".")
        if_yes = (f"With {', '.join(s.name for s in cf.sibling_extra)} as co-writer the UK/EU term runs to "
                  f"1 January {extra_last + 71}." if extra_last and (listed_last is None or extra_last > listed_last)
                  else "The UK/EU expiry moves to 70 years after the death of the last of the full list of writers.")
        if_no = (f"With {listed} as the complete list the UK/EU term ended 1 January {listed_last + 71}."
                 if listed_last else "The UK/EU determination cannot be made without the writers' death years.")
        questions.append(UnresolvedQuestion(
            question_id=qid_,
            question=f'Who are all the credited writers of "{cf.title or title}"?',
            why_it_matters=why, if_yes=if_yes, if_no=if_no,
            affects_layer_ids=[COMPOSITION],
            search_terms=[f'"{cf.title or title}" composer lyricist', f'"{cf.title or title}" ISWC']
                         + [f'"{cf.title or title}" {s.name}' for s in cf.sibling_extra],
            estimated_effort="minutes",
        ))
        if cf.sibling_extra and tf.author_death_year is not None:
            tf.author_death_year.conflicting_values = [
                f"{s.death_year} ({s.name}, per sibling MusicBrainz work)" for s in cf.sibling_extra if s.death_year]

    # Renewal window -> Tier 3 SEARCH (primary path), then read the evidence
    cliff = CURRENT_YEAR - 95
    if cf.year and cliff <= cf.year <= 1963:
        em.emit(S.RESEARCH, "progress",
                f"Published {cf.year}: renewal in year 28 decides the US term — searching renewal records (Parallel Search)")
        out, links = search_renewal(cf.title or title, writer_names, cf.year)
        em.consulted(len(out.hits))
        if not out.ok:
            em.emit(S.RESEARCH, "progress", "Parallel Search unavailable — renewal left unresolved",
                    degraded=True, error_message=out.error)
        answer = reader.read_renewal(title=cf.title or title, writers=writer_names, year=cf.year, evidence=out)
        fact = renewal_to_fact(answer, retrieved_at=out.retrieved_at)
        if fact is not None:
            tf.renewal_filed = fact
            em.emit(S.RESEARCH, "progress",
                    f"Renewal resolved from evidence: {'renewed' if fact.value else 'not renewed'} "
                    f"({fact.confidence.value} confidence, {len(fact.sources)} citation(s))")
        else:
            qid_ = f"{COMPOSITION}:renewal"
            question_ids["renewal_filed"] = qid_
            questions.append(renewal_question(cf.title or title, cf.year, links, renewal_numbers(out)))

    # Recording layer facts
    rtf = recording.term_facts
    rtf.recording_date_basis = sel.basis
    sel_notes = []
    if len(sel.sessions) > 1:
        sel_notes.append(f"other dated sessions by this artist: {', '.join(sel.sessions[1:6])}")
    if sel.undated:
        sel_notes.append(f"{sel.undated} undated recording entities not used")
    if not sel.complete:
        sel_notes.append("not every linked recording could be scanned; earliest dated session among those scanned")
    if sel.rec_year:
        why = ("Dated performance relation in MusicBrainz; earliest release on file is contemporaneous"
               if sel.basis is RecordingDateBasis.DATED_PERFORMANCE and sel.rec_conf is Confidence.HIGH
               else "Dated performance relation in MusicBrainz; earliest release on file is later, so the "
                    "publication year is taken from the session"
               if sel.basis is RecordingDateBasis.DATED_PERFORMANCE
               else "Earliest release on file only — may be a reissue")
        rtf.recording_first_published_year = ResearchedFact(
            value=sel.rec_year, confidence=sel.rec_conf, sources=[sel.source],
            reasoning=why + ("; " + "; ".join(sel_notes) if sel_notes else ""))
    if sel.basis is not RecordingDateBasis.DATED_PERFORMANCE:
        em.emit(S.RESEARCH, "progress", "No dated session on file — searching for the original release (Parallel Search)")
        out, links = search_recording_date(title, sel.pick["artist"], sel.pick["date"])
        em.consulted(len(out.hits))
        if not out.ok:
            em.emit(S.RESEARCH, "progress", "Parallel Search unavailable — release year left unresolved",
                    degraded=True, error_message=out.error)
        answer = reader.read_recording_year(title=title, artist=sel.pick["artist"],
                                            year_on_file=sel.pick["date"], evidence=out)
        fact = recording_year_to_fact(answer, retrieved_at=out.retrieved_at)
        if fact is not None:
            rtf.recording_first_published_year = fact
            rtf.recording_date_basis = RecordingDateBasis.RESEARCHED
            em.emit(S.RESEARCH, "progress",
                    f"Recording first-publication year resolved from evidence: {fact.value} "
                    f"({fact.confidence.value} confidence, {len(fact.sources)} citation(s))")
        else:
            qid_ = f"{RECORDING}:first_publication"
            question_ids["recording_pub_year"] = qid_
            questions.append(UnresolvedQuestion(
                question_id=qid_,
                question=f'In what year was the recording of "{title}" by {sel.pick["artist"]} first released?',
                why_it_matters=f"The US term for pre-1972 recordings runs from first publication. MusicBrainz only has a release from {sel.pick['date'] or 'an unknown year'}, which may be a reissue.",
                if_yes="A confirmed year lets the CLASSICS Act schedule compute the expiry exactly.",
                if_no="Without a year the recording layer stays undetermined and the roll-up cannot be clear.",
                affects_layer_ids=[RECORDING],
                resolution_links=links,
                search_terms=[f'"{title}" {sel.pick["artist"]} discography', f'"{title}" {sel.pick["artist"]} 78 rpm'],
                estimated_effort="minutes",
            ))
    em.emit(S.RESEARCH, "complete", f"Consulted {em.sources_consulted} sources"
            + (" — Tier 3 degraded" if any(e.degraded for e in em.events) else ""))

    # RULES -----------------------------------------------------------------
    dets = determine_all(layers, question_ids, death_years)
    em.emit(S.RULES, "complete", f"{len(dets)} determinations: 2 layers × US / UK / EU")
    em.emit(S.COMPARE, "skipped", "No institutional rights statement to compare against")

    # ASSEMBLE ----------------------------------------------------------------
    entity = ResolvedEntity(
        canonical_title=cf.title or title, asset_type=AssetType.MUSIC,
        creators=[ResearchedFact(value=w.name, confidence=cf.writer_conf, sources=w.sources) for w in cf.writers],
        year=composition.term_facts.first_publication_year,
        layers=layers, resolution_confidence=sel.resolution,
    )
    extra = {"title": cf.title or title, "artist": artist or sel.pick["artist"]}
    if "renewal_filed" in question_ids:
        extra.update(renewal_extras(cf.title or title, cf.year))
    if "recording_pub_year" in question_ids:
        extra.update(unconfirmed_recording=title)
    resp = assemble(query, entity, dets, questions, em, extra=extra)
    em.emit(S.ASSEMBLE, "complete", resp.overall_headline)
    return resp, em
