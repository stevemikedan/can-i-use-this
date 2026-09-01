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
from typing import Any, Callable, Optional

from agent.reader_schema import recording_year_to_fact, renewal_to_fact
from research import parallel_client as pc
from research.music import renewal_numbers, renewal_record_system, search_recording_date, search_renewal, search_writers
from rules import CURRENT_YEAR
from schemas import (
    AssetQuery, AssetType, Candidate, Confidence, HandoffLink, Identifier, LinkTier,
    PipelineStage as S, RecordingDateBasis, ResearchMethod, ResearchedFact, ResolvedEntity,
    RightsLayer, RightsLayerKind, RightsResponse, Source, TermFacts, UnresolvedQuestion,
)
from sources import musicbrainz as mb
from sources import wikidata as wd
from sources.http import as_source, plain_error

from .assemble import assemble, failed_response, stop_response
from .consistency import run_checks as run_consistency_checks
from .user_facts import answered_fact
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
                                     f"MusicBrainz could not be reached: {plain_error(s.error)}. "
                                     "This is usually transient; run the inquiry again.",
                                     upstream=True)
    cands = s.data
    if not cands:
        em.emit(S.IDENTIFY, "failed", "No recordings found — searching for close matches")
        sugg = _suggestion_candidates(mb.suggest_recordings(title))
        why = (f'No recording of "{title}" credited to {artist} was found.' if artist
               else "No recording with that title was found in MusicBrainz.")
        return None, failed_response(
            query, title, artist, em,
            why + (" The closest real entries in the index are listed below." if sugg else ""),
            suggestions=sugg)

    if artist is None:
        by_artist: dict[str, list] = defaultdict(list)
        for c in cands:
            by_artist[c["artist"]].append(c)
        if len(by_artist) > 1:
            # Most-issued first: the artist with the most recording entities is
            # almost always the one the user means (and the composition
            # shortcut resolves the work through the first candidate).
            rows = sorted(by_artist.items(),
                          key=lambda kv: (-len(kv[1]), min((c["date"] or "9999") for c in kv[1])))
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
            em.emit(S.IDENTIFY, "failed", f'No recording credited to "{artist}" — listing artists who did record it')
            sugg = _suggestion_candidates(cands)
            return None, failed_response(
                query, title, artist, em,
                f'The title was found, but no recording of it is credited to {artist}. '
                + ("Artists who did record it are listed below." if sugg
                   else "Try the artist name as it appears on the release."),
                suggestions=sugg)
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
    # Selection must be deterministic: the same query gives the same record
    # every run. Every ordering below breaks ties on MBID, never on API
    # response order — MusicBrainz search scores tie constantly, and a
    # degraded sub-fetch must not reshuffle what the next run picks.
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
    for c in sorted(cands, key=lambda c: (-(c.get("score") or 0), c["mbid"]))[:K_WORK_LOOKUPS]:
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
    ordered = sorted(works.items(), key=lambda kv: (-(kv[1].get("score") or 0), kv[0]))
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

    # Guard: a dated relation only marks the ORIGINAL if nothing was released
    # before it. MusicBrainz often dates a later take (a live version, a
    # re-recording) while the studio original carries only a release date —
    # Aliens Exist's 1999 album track is undated, a 2001 take is dated. If an
    # artist-matched candidate was released before the earliest dated session,
    # the session cannot be the original's: fall to the release-date path,
    # which sends the true first release to Tier 3 research.
    guard_note = None
    if dated:
        session_year = int(dated[0][:4])
        min_release = min((int(r["date"][:4]) for r in mine if r["date"]), default=None)
        if min_release is not None and min_release < session_year:
            guard_note = (f"a dated {dated[0]} session exists but a release from {min_release} predates it; "
                          f"the dated relation belongs to a later take, not the original")
            dated = []

    if dated:
        # The earliest dated session is the original; everything later is a
        # live take, compilation or reissue. Ties break on release date, then
        # MBID — never on response order.
        k = dated[0]
        pick = min(sessions[k], key=lambda r: (r["date"] or "9999", r["mbid"]))
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
        pick = min(mine, key=lambda r: (r["date"] or "9999", r["mbid"]))
        year = int(pick["date"][:4]) if pick["date"] else None
        basis = RecordingDateBasis.FIRST_RELEASE_DATE if year else RecordingDateBasis.UNKNOWN
        rec_conf, resolution = Confidence.LOW, Confidence.LOW
        excerpt = guard_note or f"no dated session; earliest release on file {pick['date']}"
    source = Source(name="MusicBrainz", url=f"https://musicbrainz.org/recording/{pick['mbid']}",
                    method=ResearchMethod.DIRECT_API, retrieved_at=src_at, excerpt=excerpt[:200])
    return Selection(pick, pick["work"], year, basis, rec_conf, resolution, dated, undated, complete, works, source)


def _announce_search(em: Emitter, label: str):
    """Each Parallel Search query becomes its own ledger line, emitted before
    the search runs — the mandated integration, legible in the demo."""
    def announce(queries: list[str]) -> None:
        for q in queries:
            em.emit(S.RESEARCH, "progress", f"Parallel Search — {label}", detail=q,
                    partial={"search_query": q})
    return announce


def _search_result_line(em: Emitter, label: str, out) -> None:
    em.consulted(len(out.hits))
    if out.ok:
        em.emit(S.RESEARCH, "progress",
                f"Parallel Search — {label}: {len(out.hits)} source passages returned",
                partial={"hits": len(out.hits), "search_id": out.search_id})


def _cite_sources(citations, retrieved_at) -> list[Source]:
    return [Source(name=c.source_name, url=c.url, method=ResearchMethod.PARALLEL_SEARCH,
                   retrieved_at=retrieved_at, excerpt=c.excerpt[:200],
                   authoritative=c.source_class == "primary_record") for c in citations]


def corroborate_writers(cf: CompositionFacts, em: Emitter, reader, title: str) -> None:
    """
    Wikidata could not cross-check the writer list — but writer credits are a
    researchable question: ASCAP/BMI repertories, Catalog of Copyright Entries
    registrations, sheet-music credits. Parallel Search gathers the evidence
    (primary request path); the reader corroborates INDIVIDUAL candidates.

    The asymmetry, again: a corroborated addition lengthens a life+70 term —
    errs toward protected, safe. A completeness claim could shorten it, so
    completeness is unrepresentable in the answer schema, no candidate is
    ever dropped, and the block lifts only when EVERY candidate — each
    credited writer and each sibling-work extra — is corroborated.
    """
    candidates = [w.name for w in cf.writers] + [s.name for s in cf.sibling_extra]
    if not candidates:
        return
    em.emit(S.RESEARCH, "progress",
            "Writer list uncorroborated; searching repertories and credits (Parallel Search)")
    out, links = search_writers(title, cf.year, candidates, announce=_announce_search(em, "writer credits"))
    _search_result_line(em, "writer credits", out)
    cf.writer_links = links
    if not out.ok:
        em.emit(S.RESEARCH, "progress", "Parallel Search unavailable; writer list stays uncorroborated",
                degraded=True, error_message=out.error)
    answer = reader.read_writers(title=title, year=cf.year, candidates=candidates, evidence=out)
    if answer.status != "found":
        return
    retrieved = out.retrieved_at or datetime.now(timezone.utc)
    conf_map = {"high": Confidence.HIGH, "medium": Confidence.MEDIUM, "low": Confidence.LOW}
    by_fold = {mb._match_norm(w.name): w for w in answer.writers}
    confs: list[Confidence] = []
    every_candidate = True
    for w in cf.writers:
        hit = by_fold.get(mb._match_norm(w.name))
        if hit is None:
            every_candidate = False
            continue
        w.sources.extend(_cite_sources(hit.citations, retrieved))
        w.src += "+search"
        confs.append(conf_map[hit.confidence])
    still_extra: list[Writer] = []
    for s in cf.sibling_extra:
        hit = by_fold.get(mb._match_norm(s.name))
        if hit is None:
            every_candidate = False
            still_extra.append(s)
            continue
        s.sources.extend(_cite_sources(hit.citations, retrieved))
        s.src += "+search"
        confs.append(conf_map[hit.confidence])
        cf.writers.append(s)
        cf.notes.append(f"{s.name} corroborated as co-writer by searched evidence")
        em.emit(S.RESEARCH, "progress",
                f"Writer corroborated from evidence: {s.name} ({hit.confidence} confidence)")
    cf.sibling_extra = still_extra
    if every_candidate:
        cf.corroborated = True
        cf.writer_conf = min(confs, key=_rank) if confs else Confidence.MEDIUM
        em.emit(S.RESEARCH, "progress",
                f"Writer list corroborated from evidence, every candidate confirmed ({len(cf.writers)} writers)")


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
    writer_links: list[HandoffLink] = field(default_factory=list)
    licenses: list[str] = field(default_factory=list)


def tier1_license(urls: list[str], where: str) -> Optional[ResearchedFact]:
    """
    Tier 1: the first recognized license URI among a record's license
    relations, as a fact. MEDIUM: MusicBrainz is a single community source
    asserting the license; the table match itself is deterministic.
    """
    from rules.licenses import parse_license
    for url in urls or []:
        lic = parse_license(url)
        if lic is not None:
            return ResearchedFact(
                value=url, confidence=Confidence.MEDIUM,
                sources=[Source(name="MusicBrainz", url=url, method=ResearchMethod.RIGHTS_URI,
                                retrieved_at=datetime.now(timezone.utc),
                                excerpt=f"license relation on the {where}: {lic.label}")],
                reasoning=f"License relation on the MusicBrainz {where}, matched to {lic.label} "
                          f"in the static license table (Tier 1).")
    return None


def tier1_label(fact: ResearchedFact) -> str:
    from rules.licenses import parse_license
    lic = parse_license(fact.value)
    return lic.label if lic else "recognized license"


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
    licenses = (det.data.get("licenses") or []) if det.ok else []
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
                            year_sources, qid, iswcs, title, notes, sibling_extra, licenses=licenses)


def _suggestion_candidates(hits: list[dict], limit: int = 5) -> list[Candidate]:
    """
    "Did you mean" rows from real MusicBrainz hits, grouped by artist credit,
    most-issued first. The label carries MB's own spelling of the title, so a
    near-miss query surfaces the exact string that will match.
    """
    by_artist: dict[str, list[dict]] = defaultdict(list)
    for h in hits:
        if h.get("artist") and h.get("title"):
            by_artist[h["artist"]].append(h)
    # Artists who recorded the dominant title first, then most-issued: a
    # search for "West End Blues" must not rank a band with many "West End"
    # entities above the artists who actually recorded the queried title.
    titles = [h["title"] for h in hits if h.get("title")]
    top_title = mb._norm_title(max(set(titles), key=titles.count)) if titles else ""

    def has_top(cs: list[dict]) -> bool:
        return any(mb._norm_title(c["title"]) == top_title for c in cs)

    rows = sorted(by_artist.items(),
                  key=lambda kv: (not has_top(kv[1]), -len(kv[1]),
                                  min((c["date"] or "9999") for c in kv[1])))
    out = []
    for a, cs in rows[:limit]:
        earliest = min((c["date"] for c in cs if c["date"]), default=None)
        c0 = min(cs, key=lambda c: c["date"] or "9999")
        out.append(Candidate(
            label=f"{a} — {c0['title']}",
            disambiguator=(f"earliest release on file {earliest}" if earliest else "no release date on file")
                          + f"; {len(cs)} recording entit{'y' if len(cs) == 1 else 'ies'}",
            identifiers=[Identifier(scheme="musicbrainz_recording", value=c0["mbid"],
                                    layer_id=RECORDING, confidence=Confidence.LOW)],
            likelihood=Confidence.LOW,
        ))
    return out


# --- the renewal question -------------------------------------------------------

_RENEWAL_WHY = "Works published 1931–1963 lost protection after 28 years unless renewed."


def _lead(fact: Optional[ResearchedFact], says: str) -> tuple[str, list[HandoffLink]]:
    """
    A low-confidence fact shown as a lead on the open question, not as the
    answer (see LOW_CONFIDENCE_PD_RULE in determine.py). Returns the sentence
    for why_it_matters and deep links to the sources.
    """
    if fact is None:
        return "", []
    srcs = fact.sources[:3]
    if srcs and all(s.method is ResearchMethod.USER_PROVIDED for s in srcs):
        return (f" You answered: {says}, without naming a source. Recorded as a low-confidence "
                f"lead; the question stays open until a record confirms it."), []
    where = "; ".join(dict.fromkeys(s.name for s in srcs))
    text = (f" Lead, low confidence: {where} states {says}. Not an official record; "
            f"verify it against one before relying on it.")
    links = [HandoffLink(source_name=s.name, url=s.url, tier=LinkTier.DEEP_LINK, purpose="resolve",
                         description=f"Low-confidence lead: states {says}") for s in srcs]
    return text, links


def renewal_question(title: str, year: int, links, numbers: list[str],
                     lead: Optional[ResearchedFact] = None) -> UnresolvedQuestion:
    """
    The open year-28 question, pointed at the record system that actually
    holds the answer. Windows of 1978 or later are in the Copyright Office
    online catalog — the scanned CCE volumes web search reaches end in 1977,
    so sending someone there is a dead end, not a handoff.

    lead: a low-confidence reader finding, attached as a lead rather than
    taken as the answer.
    """
    y28 = year + 27
    lead_text, lead_links = _lead(lead, "it was renewed" if lead and lead.value else "it was not renewed")
    system = renewal_record_system(year)
    if system == "online":
        where = (f" The {y28}–{y28 + 1} renewal window falls after 1977, so the record is in the US Copyright "
                 f"Office online public catalog (renewals received since 1978, RE-numbered), not in the scanned "
                 f"Catalog of Copyright Entries volumes that web search reaches. Search the online catalog by "
                 f"title and claimant.")
        effort = "minutes"
    elif system == "both":
        where = (f" The {y28}–{y28 + 1} renewal window straddles 1978: a {y28} renewal is in the scanned Catalog "
                 f"of Copyright Entries, a {y28 + 1} renewal in the US Copyright Office online public catalog "
                 f"(RE-numbered). Check both.")
        effort = "hours"
    else:
        where = " Renewal records are scanned catalogs, not a queryable database."
        effort = "hours"
    return UnresolvedQuestion(
        question_id=f"{COMPOSITION}:renewal",
        question=f'Was the {year} US copyright in "{title}" renewed in {y28}–{y28 + 1}?',
        why_it_matters=_RENEWAL_WHY + where
                       + (f" Search found renewal-style registration numbers {numbers[:3]}. Check them." if numbers else "")
                       + lead_text,
        if_yes=f"Protected until 1 January {year + 96}.",
        if_no=f"Entered the public domain 1 January {year + 29}.",
        affects_layer_ids=[COMPOSITION],
        resolution_links=lead_links + list(links),
        search_terms=[f'"{title}" renewal {y28}', f'"{title}" renewal {y28 + 1}'],
        estimated_effort=effort,
    )


def recording_question(title: str, artist: str, date_on_file: Optional[str], links,
                       lead: Optional[ResearchedFact] = None) -> UnresolvedQuestion:
    """The open first-publication question for a recording with no dated session."""
    lead_text, lead_links = _lead(lead, f"the original release was {lead.value}" if lead else "")
    return UnresolvedQuestion(
        question_id=f"{RECORDING}:first_publication",
        question=f'In what year was the recording of "{title}" by {artist} first released?',
        why_it_matters=f"The US term for pre-1972 recordings runs from first publication. MusicBrainz only has a release from {date_on_file or 'an unknown year'}, which may be a reissue."
                       + lead_text,
        if_yes="A confirmed year lets the CLASSICS Act schedule compute the expiry exactly.",
        if_no="Without a year the recording layer stays undetermined and the roll-up cannot be clear.",
        affects_layer_ids=[RECORDING],
        resolution_links=lead_links + list(links),
        search_terms=[f'"{title}" {artist} discography', f'"{title}" {artist} 78 rpm'],
        estimated_effort="minutes",
    )


def publication_floor(rec_tf: TermFacts) -> Optional[ResearchedFact]:
    """
    No publication record for the composition, but a trustworthy recording
    year of 1978 or later — a dated session or a researched original release:
    under 17 U.S.C. §101 distributing phonorecords publishes the work they
    embody, so the recording's year serves as the composition's publication
    year at LOW confidence, with the question left open as a lead. Pre-1978
    the premise fails — under the 1909 Act phonorecords did not publish the
    composition — so no inference is made there, and the layer stays
    undetermined honestly. The asymmetry rule in determine.py keeps a
    low-confidence year from ever supporting a public-domain verdict.

    Runs in the RULES stage: the researched recording year lands in the
    recording stage, which executes in parallel with the composition stage,
    so the composition stage structurally cannot see it.
    """
    f = rec_tf.recording_first_published_year
    basis = rec_tf.recording_date_basis
    if (f is not None and f.value >= 1978
            and basis in (RecordingDateBasis.DATED_PERFORMANCE, RecordingDateBasis.RESEARCHED)):
        return ResearchedFact(
            value=f.value, confidence=Confidence.LOW, sources=list(f.sources),
            reasoning=f"Inferred from the recording: distributing the {f.value} recording embodying "
                      f"the work published it (17 U.S.C. §101). No publication record found on Wikidata; "
                      f"verify against the copyright registration.")
    return None


def year_question(title: str, fact: Optional[ResearchedFact] = None) -> UnresolvedQuestion:
    """The composition's publication year is unknown, or rests on weak
    evidence (a lesser Wikidata property, or inference from the recording)."""
    lead_text, lead_links = _lead(fact, f"the year is {fact.value}" if fact else "")
    return UnresolvedQuestion(
        question_id=f"{COMPOSITION}:publication_year",
        question=f'In what year was "{title}" first published in the US?',
        why_it_matters="The US term runs from publication, and no publication record was found; "
                       "the year in use rests on weaker evidence." + lead_text,
        if_yes="A confirmed year lets the 95-year rule and the renewal window be applied exactly.",
        if_no="Without a year the composition stays undetermined and the roll-up cannot be clear.",
        affects_layer_ids=[COMPOSITION],
        resolution_links=lead_links,
        search_terms=[f'"{title}" first published', f'"{title}" copyright registration'],
        estimated_effort="minutes",
    )


def derivative_question(title: str, year: int, dead: list[Writer]) -> UnresolvedQuestion:
    """
    A credited writer died before the stated publication year — a machine-
    detectable contradiction. The usual cause: the dated publication is a
    translation, arrangement or new edition of an earlier work, and each
    carries its own copyright with its own authors, term and country of
    origin. Four days from freeze this is detected and disclosed, not
    modelled: the verdict stands for the {year} publication, and the open
    question says exactly what else may exist.
    """
    who = "; ".join(f"{w.name} (d. {w.death_year})" for w in dead)
    return UnresolvedQuestion(
        question_id=f"{COMPOSITION}:derivative",
        question=f'Is the {year} "{title}" a translation or arrangement of an earlier work?',
        why_it_matters=f"{who} died before the stated {year} US publication, so this {year} copyright is "
                       f"likely a translation, arrangement or new edition of an earlier original with its "
                       f"own, separate copyright. The verdict on this record covers the {year} publication; "
                       f"the original would carry its own term, authors and country of origin.",
        if_yes=f"Two rights layers exist: the earlier original and the {year} version. Each must be "
               f"cleared (or found expired) separately.",
        if_no=f"The {year} publication is the original and this record's determination stands as computed.",
        affects_layer_ids=[COMPOSITION],
        search_terms=[f'"{title}" original version translation', f'"{title}" {dead[0].name} original'],
        estimated_effort="minutes",
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


# --- the pipeline, as stages ------------------------------------------------------
#
# run_music runs these stage functions in order. agent/workflow.py runs the
# same functions as ADK agents — the two research stages in parallel — against
# the same MusicRun. Both must produce the same RightsResponse; the frozen
# fixtures in agent/fixtures (agent/test_acceptance.py) pin it.

@dataclass
class MusicRun:
    """The state of one music query as it moves through the stages."""

    query: AssetQuery
    em: Emitter
    reader: Any
    title: str = ""
    artist: Optional[str] = None
    cands: Optional[list[dict]] = None
    sel: Optional[Selection] = None
    composition: Optional[RightsLayer] = None
    recording: Optional[RightsLayer] = None
    cf: Optional[CompositionFacts] = None
    # Each research stage owns its own questions so they can run concurrently;
    # the rules stage reads them in a fixed order (composition, then recording).
    comp_questions: list[UnresolvedQuestion] = field(default_factory=list)
    rec_questions: list[UnresolvedQuestion] = field(default_factory=list)
    comp_question_ids: dict[str, str] = field(default_factory=dict)
    rec_question_ids: dict[str, str] = field(default_factory=dict)
    dets: list = field(default_factory=list)
    response: Optional[RightsResponse] = None

    @property
    def done(self) -> bool:
        """An earlier stage produced the response (disambiguation stop, not found, or assembled)."""
        return self.response is not None

    @property
    def layers(self) -> list[RightsLayer]:
        return [self.composition, self.recording]

    @property
    def questions(self) -> list[UnresolvedQuestion]:
        return self.comp_questions + self.rec_questions

    @property
    def question_ids(self) -> dict[str, str]:
        return {**self.comp_question_ids, **self.rec_question_ids}


def stage_classify(run: MusicRun) -> None:
    run.title, run.artist = parse_query(run.query.raw_input)
    run.em.emit(S.CLASSIFY, "complete", "Music — a composition and a sound recording, owned separately",
                detail=f'"{run.title}"' + (f" — {run.artist}" if run.artist else " (no artist given)"))


def stage_identify(run: MusicRun) -> None:
    em, title, artist = run.em, run.title, run.artist
    cands, early = _search_and_gate(run.query, title, artist, em)
    if early is not None:
        run.response = early
        return
    run.cands = cands
    sel = _select_recording(title, cands, artist, em)
    if sel is None:
        run.response = failed_response(run.query, title, artist, em,
                                       "The recording could not be matched to a composition in MusicBrainz.")
        return
    run.sel = sel
    when = sel.sessions[0] if sel.sessions else f"earliest release on file {sel.pick['date']}"
    em.emit(S.IDENTIFY, "complete",
            f"Resolved: {sel.pick['artist']}, {when}" + ("" if sel.complete else " (partial scan)"),
            partial={"recording": sel.pick["mbid"], "work": sel.work["work_mbid"],
                     "recording_year": sel.rec_year, "date_basis": sel.basis.value})


def stage_decompose(run: MusicRun) -> None:
    sel = run.sel
    comp_ids = [Identifier(scheme="musicbrainz_work", value=sel.work["work_mbid"], layer_id=COMPOSITION,
                           confidence=sel.resolution, is_primary=True)]
    rec_ids = [Identifier(scheme="musicbrainz_recording", value=sel.pick["mbid"], layer_id=RECORDING,
                          confidence=sel.resolution, source=sel.source, is_primary=True)]
    run.composition = RightsLayer(layer_id=COMPOSITION, kind=RightsLayerKind.COMPOSITION,
                                  label="Composition", identifiers=comp_ids)
    run.recording = RightsLayer(layer_id=RECORDING, kind=RightsLayerKind.SOUND_RECORDING,
                                label="Sound recording", identifiers=rec_ids)
    run.em.emit(S.DECOMPOSE, "complete", "Found 2 rights layers: composition and sound recording",
                partial={"layers": [COMPOSITION, RECORDING]})
    run.em.emit(S.RESEARCH, "started", "Researching both layers — Tier 2 first")


def stage_research_composition(run: MusicRun) -> None:
    """Tier 2 facts for the composition; the renewal window goes to Parallel Search and the reader."""
    sel, em, composition, title, reader = run.sel, run.em, run.composition, run.title, run.reader
    cf = _research_composition(sel, em)
    if not cf.corroborated:
        corroborate_writers(cf, em, run.reader, cf.title or title)
    run.cf = cf
    comp_ids = composition.identifiers
    for iswc in cf.iswcs:
        comp_ids.append(Identifier(scheme="iswc", value=iswc, layer_id=COMPOSITION, confidence=Confidence.MEDIUM))
    if cf.wikidata:
        comp_ids.append(Identifier(scheme="wikidata", value=cf.wikidata, layer_id=COMPOSITION, confidence=Confidence.MEDIUM))
    composition.label = f"Composition ({cf.year})" if cf.year else "Composition"

    questions, question_ids = run.comp_questions, run.comp_question_ids
    writer_names = [w.name for w in cf.writers]

    tf = composition.term_facts
    if cf.year:
        reasoning = f"Wikidata {cf.year_prop}" + (" corroborated by MusicBrainz composer-relation date" if cf.year_conf is Confidence.HIGH else "")
        tf.first_publication_year = ResearchedFact(value=cf.year, confidence=cf.year_conf,
                                                   sources=cf.year_sources,
                                                   reasoning=reasoning + ("; " + "; ".join(cf.notes) if cf.notes else ""))
        if cf.year_conf is Confidence.LOW:
            # A lead, not an answer (LOW_CONFIDENCE_PD_RULE): the question stays open.
            question_ids["first_publication_year"] = f"{COMPOSITION}:publication_year"
            questions.append(year_question(cf.title or title, tf.first_publication_year))
    else:
        # No publication year at all: the question exists from the start —
        # a blocked determination without an open question is a broken
        # promise. The rules stage may later attach a §101 floor as a lead.
        question_ids["first_publication_year"] = f"{COMPOSITION}:publication_year"
        questions.append(year_question(cf.title or title))
    known = [w.death_year for w in cf.writers if w.death_year is not None]
    if cf.writers and known and len(known) == len(cf.writers):
        last = max(known)
        who = ", ".join(f"{w.name} d. {w.death_year}" for w in cf.writers)
        tf.author_death_year = ResearchedFact(value=last, confidence=cf.writer_conf,
                                              sources=[s for w in cf.writers for s in w.sources],
                                              reasoning=f"Last surviving author: {who}")
    tf.writer_list_corroborated = cf.corroborated
    # A missing death year is only an open QUESTION when it is researchable —
    # an old work whose writer's death went unrecorded. When the work is
    # recent enough that death >= work_year keeps the term running (the
    # living floor in rules/terms.py), UK/EU resolve to PROTECTED and there
    # is nothing a human could look up: you cannot research when a living
    # person will die.
    floor_covers = cf.year is not None and cf.year + 70 >= CURRENT_YEAR
    if cf.corroborated and not floor_covers and any(w.death_year is None for w in cf.writers):
        missing = ", ".join(w.name for w in cf.writers if w.death_year is None)
        question_ids["author_death_year"] = f"{COMPOSITION}:death_years"
        questions.append(UnresolvedQuestion(
            question_id=f"{COMPOSITION}:death_years",
            question=f"When did the credited writers of \"{cf.title or title}\" die — or are they living?",
            why_it_matters=f"UK/EU terms run 70 years past the death of the last surviving author, and no "
                           f"death year is on record for {missing}. A living author means the work stays "
                           f"protected for decades; an unrecorded death year leaves the term uncomputable.",
            if_yes="With every death year known, the UK/EU expiry is 70 years after the last of them.",
            if_no="While any writer may be living, the work is protected and no expiry can be stated.",
            affects_layer_ids=[COMPOSITION],
            search_terms=[f'"{w.name}"' for w in cf.writers if w.death_year is None],
            estimated_effort="minutes",
        ))
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
            resolution_links=cf.writer_links,
            search_terms=[f'"{cf.title or title}" composer lyricist', f'"{cf.title or title}" ISWC']
                         + [f'"{cf.title or title}" {s.name}' for s in cf.sibling_extra],
            estimated_effort="minutes",
        ))
        if cf.sibling_extra and tf.author_death_year is not None:
            tf.author_death_year.conflicting_values = [
                f"{s.death_year} ({s.name}, per sibling MusicBrainz work)" for s in cf.sibling_extra if s.death_year]

    # A writer dead before the stated publication year: disclose the likely
    # earlier original (translation / arrangement) rather than silently
    # attributing the later publication to them.
    if cf.year:
        dead_before = [w for w in cf.writers if w.death_year and w.death_year < cf.year]
        if dead_before:
            question_ids["derivative"] = f"{COMPOSITION}:derivative"
            questions.append(derivative_question(cf.title or title, cf.year, dead_before))
            if tf.first_publication_year is not None:
                tf.first_publication_year.reasoning = (
                    (tf.first_publication_year.reasoning or "")
                    + f" NOTE: {dead_before[0].name} died {dead_before[0].death_year}, before this "
                      f"publication — see the open question about an earlier original."
                )
            em.emit(S.RESEARCH, "progress",
                    f"Writer death year precedes the {cf.year} publication; flagged as a likely "
                    f"translation or arrangement of an earlier work")

    # Tier 1: a recognized license on the work settles this layer; renewal
    # and every other term question is moot for the licensed use.
    lic_fact = tier1_license(cf.licenses, "work")
    if lic_fact is not None:
        run.composition.existing_license = lic_fact
        # Term questions (publication year, writers, death years) are moot
        # for the licensed use: the license settles the layer.
        questions.clear()
        question_ids.clear()
        em.emit(S.RESEARCH, "progress",
                f"Tier 1: license relation on the work; {tier1_label(lic_fact)} from the static table, no research")

    # Renewal window -> the user's answer if they gave one on a re-run,
    # else Tier 3 SEARCH (primary path) and the reader
    cliff = CURRENT_YEAR - 95
    if run.composition.existing_license is None and cf.year and cliff <= cf.year <= 1963:
        supplied = answered_fact(run.query, f"{COMPOSITION}:renewal")
        if supplied is not None:
            # The user came back with the answer to the open question. The
            # fact is theirs and marked as such (ResearchMethod.USER_PROVIDED);
            # confidence policy in pipeline/user_facts.py: MEDIUM with an
            # attestation, LOW without. Direction still runs through
            # LOW_CONFIDENCE_PD_RULE — a bare "not renewed" stays a lead and
            # the question stays open.
            tf.renewal_filed = supplied
            attested = supplied.confidence is not Confidence.LOW
            em.emit(S.RESEARCH, "progress",
                    f"Renewal answered by you: {'renewed' if supplied.value else 'not renewed'}"
                    + (f" ({supplied.confidence.value} confidence, source attested)" if attested
                       else f" ({supplied.confidence.value} confidence; no source given, recorded as a lead)"))
            if supplied.confidence is Confidence.LOW:
                question_ids["renewal_filed"] = f"{COMPOSITION}:renewal"
                questions.append(renewal_question(cf.title or title, cf.year, [], [], lead=supplied))
        else:
            em.emit(S.RESEARCH, "progress",
                    f"Published {cf.year}. Renewal in year 28 decides the US term; searching renewal records (Parallel Search)")
            out, links = search_renewal(cf.title or title, writer_names, cf.year,
                                        announce=_announce_search(em, "renewal records"))
            _search_result_line(em, "renewal records", out)
            if not out.ok:
                em.emit(S.RESEARCH, "progress", "Parallel Search unavailable; renewal left unresolved",
                        degraded=True, error_message=out.error)
            answer = reader.read_renewal(title=cf.title or title, writers=writer_names, year=cf.year, evidence=out)
            fact = renewal_to_fact(answer, retrieved_at=out.retrieved_at)
            if fact is not None:
                tf.renewal_filed = fact
                em.emit(S.RESEARCH, "progress",
                        f"Renewal resolved from evidence: {'renewed' if fact.value else 'not renewed'} "
                        f"({fact.confidence.value} confidence, {len(fact.sources)} citation(s))")
            if fact is None or fact.confidence is Confidence.LOW:
                # No answer, or a low-confidence one: the question stays open. A
                # low-confidence finding rides along as a lead; the rules engine
                # lets it support "protected" but not "public domain"
                # (LOW_CONFIDENCE_PD_RULE in determine.py).
                question_ids["renewal_filed"] = f"{COMPOSITION}:renewal"
                questions.append(renewal_question(cf.title or title, cf.year, links, renewal_numbers(out), lead=fact))


def stage_research_recording(run: MusicRun) -> None:
    """Recording facts from the selection; a reissue-only date goes to Parallel Search and the reader."""
    sel, em, recording, title, reader = run.sel, run.em, run.recording, run.title, run.reader
    recording.label = f"Sound recording ({sel.rec_year})" if sel.rec_year else "Sound recording"
    questions, question_ids = run.rec_questions, run.rec_question_ids

    rtf = recording.term_facts
    rtf.recording_date_basis = sel.basis

    # Tier 1: a license relation on the selected recording settles this
    # layer from the static table (rules/licenses.py); the date research
    # below is moot for the licensed use and is skipped.
    lf = mb.recording_licenses(sel.pick["mbid"])
    em.consulted()
    if lf.ok:
        lic_fact = tier1_license(lf.data, "recording")
        if lic_fact is not None:
            recording.existing_license = lic_fact
            em.emit(S.RESEARCH, "progress",
                    f"Tier 1: license relation on the recording; {tier1_label(lic_fact)} from the static table, no research")
    if recording.existing_license is None:
        # Most CC albums carry the license on the RELEASE, not the recording
        # (NIN's Ghosts). One extra cached call covers the common case.
        rf = mb.release_licenses(sel.pick["mbid"])
        em.consulted()
        if rf.ok:
            lic_fact = tier1_license(rf.data, "release")
            if lic_fact is not None:
                recording.existing_license = lic_fact
                em.emit(S.RESEARCH, "progress",
                        f"Tier 1: license relation on the release; {tier1_label(lic_fact)} from the static table, no research")
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
    if sel.basis is not RecordingDateBasis.DATED_PERFORMANCE and recording.existing_license is None:
        em.emit(S.RESEARCH, "progress", "No dated session on file; searching for the original release (Parallel Search)")
        out, links = search_recording_date(title, sel.pick["artist"], sel.pick["date"],
                                           announce=_announce_search(em, "original release"))
        _search_result_line(em, "original release", out)
        if not out.ok:
            em.emit(S.RESEARCH, "progress", "Parallel Search unavailable; release year left unresolved",
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
        if fact is None or fact.confidence is Confidence.LOW:
            # No answer, or a low-confidence one: the question stays open with
            # the finding as a lead (LOW_CONFIDENCE_PD_RULE in determine.py).
            question_ids["recording_pub_year"] = f"{RECORDING}:first_publication"
            questions.append(recording_question(title, sel.pick["artist"], sel.pick["date"], links, lead=fact))


def stage_consistency(run: MusicRun) -> None:
    """Cross-checks between facts that constrain each other; see
    pipeline/consistency.py for the five instances that motivated it."""
    run_consistency_checks(run)


def stage_rules(run: MusicRun) -> None:
    em = run.em
    # §101 publication floor — both research stages are done, so the
    # recording's year (dated or researched) is now known.
    comp_tf = run.composition.term_facts
    if comp_tf.first_publication_year is None:
        floor = publication_floor(run.recording.term_facts)
        if floor is not None:
            comp_tf.first_publication_year = floor
            run.composition.label = f"Composition ({floor.value})"
            title = run.cf.title or run.title
            run.comp_questions = [q for q in run.comp_questions
                                  if q.question_id not in (f"{COMPOSITION}:publication_year",
                                                           f"{COMPOSITION}:death_years")]
            run.comp_questions.append(year_question(title, floor))
            em.emit(S.RESEARCH, "progress",
                    f"No publication record; inferred {floor.value} from the recording (17 U.S.C. §101, low confidence)")
    em.emit(S.RESEARCH, "complete", f"Consulted {em.sources_consulted} sources"
            + (" — Tier 3 degraded" if any(e.degraded for e in em.events) else ""))
    death_years = [w.death_year for w in run.cf.writers] or [None]
    run.dets = determine_all(run.layers, run.question_ids, death_years)
    em.emit(S.RULES, "complete", f"{len(run.dets)} determinations: 2 layers × US / UK / EU")
    em.emit(S.COMPARE, "skipped", "No institutional rights statement to compare against")


def stage_assemble(run: MusicRun) -> None:
    cf, sel, title, artist = run.cf, run.sel, run.title, run.artist
    question_ids = run.question_ids
    entity = ResolvedEntity(
        canonical_title=cf.title or title, asset_type=AssetType.MUSIC,
        creators=[ResearchedFact(value=w.name, confidence=cf.writer_conf, sources=w.sources) for w in cf.writers],
        year=run.composition.term_facts.first_publication_year,
        layers=run.layers, resolution_confidence=sel.resolution,
    )
    extra = {"title": cf.title or title, "artist": artist or sel.pick["artist"]}
    if "renewal_filed" in question_ids:
        extra.update(renewal_extras(cf.title or title, cf.year))
    if "recording_pub_year" in question_ids:
        extra.update(unconfirmed_recording=title)
    resp = assemble(run.query, entity, run.dets, run.questions, run.em, extra=extra)
    run.em.emit(S.ASSEMBLE, "complete", resp.overall_headline)
    run.response = resp


# Name -> stage function, in run order. The two research stages are
# independent of each other and may run concurrently (agent/workflow.py does).
STAGES: list[tuple[str, Callable[[MusicRun], None]]] = [
    ("classify", stage_classify),
    ("identify", stage_identify),
    ("decompose", stage_decompose),
    ("research_composition", stage_research_composition),
    ("research_recording", stage_research_recording),
    ("consistency", stage_consistency),
    ("rules", stage_rules),
    ("assemble", stage_assemble),
]
STAGE_FN: dict[str, Callable[[MusicRun], None]] = dict(STAGES)
PARALLEL_STAGES = ("research_composition", "research_recording")


def new_run(query: AssetQuery, *, emitter: Optional[Emitter] = None, reader=None) -> MusicRun:
    """A MusicRun ready for the stages: NullReader unless a reader is given."""
    from agent.reader import NullReader
    return MusicRun(query, emitter or Emitter(), reader or NullReader())


def run_music(query: AssetQuery, *, emitter: Optional[Emitter] = None, reader=None) -> tuple:
    """
    Returns (RightsResponse, Emitter).

    reader: the Tier 3 reading step (agent.reader.Reader). Defaults to the
    NullReader — no evidence is read into a fact, every open question stays
    open. A real reader resolves the renewal window and the recording-date
    window from the searched evidence, producing a cited fact for the rules
    engine. The reader never computes a term.
    """
    run = new_run(query, emitter=emitter, reader=reader)
    for _, stage in STAGES:
        if run.done:
            break
        stage(run)
    return run.response, run.em
