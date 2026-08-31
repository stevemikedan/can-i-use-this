"""
Tier 3 research for the music path. Both functions call Parallel SEARCH on
the primary request path (COMPLIANCE.md §1):

  search_renewal          — US works published 1931-1963 needed a year-28
                            renewal. Search the Catalog of Copyright Entries
                            scans and related records for the renewal entry.
  search_recording_date   — recordings with only a first-release-date (may
                            be a reissue). Search DAHR, discographies and
                            session logs for the original release.

Each returns the SearchOutcome plus HandoffLinks built from the hits, so an
UnresolvedQuestion can point at the actual pages a human should open.
Deciding the fact from the excerpts (was it renewed? what year?) is a
reading task for the Gemini step in agent/ — this module gathers evidence,
it does not assert facts.
"""

from __future__ import annotations

import re
from typing import Optional

from schemas import HandoffLink, LinkTier

from .parallel_client import SearchOutcome, search

# Pre-1978 renewals: "R290123". From 1978: "RE0000342857", "RE 342-857", "RE342857".
_R_NUMBER = re.compile(r"\bRE\s?0*\d{3}-?\d{3}\b|\bR\s?\d{5,7}\b")

# Renewals received by the Copyright Office from 1 January 1978 are in its
# online public catalog; earlier ones only in the scanned Catalog of Copyright
# Entries volumes. The scans are what web search excerpts can reach.
RENEWAL_ONLINE_FROM = 1978


def renewal_record_system(pub_year: int) -> str:
    """
    Which record system holds a work's year-28 renewal: "online" (window
    1978 or later — the Copyright Office online catalog), "scans" (window
    ends before 1978 — the scanned CCE volumes), or "both" (the window
    straddles 1978).
    """
    y28 = pub_year + 27
    if y28 >= RENEWAL_ONLINE_FROM:
        return "online"
    if y28 + 1 >= RENEWAL_ONLINE_FROM:
        return "both"
    return "scans"


def _surname(name: str) -> str:
    return name.split()[-1] if name else ""


def _links(outcome: SearchOutcome, purpose: str, description: str, limit: int = 5) -> list[HandoffLink]:
    links = []
    for hit in outcome.hits[:limit]:
        if not hit.url.startswith(("http://", "https://")):
            continue
        links.append(HandoffLink(
            source_name=hit.title or hit.url.split("/")[2],
            url=hit.url,
            tier=LinkTier.DEEP_LINK,
            purpose=purpose,
            description=description,
        ))
    return links


def search_renewal(title: str, writers: list[str], pub_year: int,
                   announce=None) -> tuple[SearchOutcome, list[HandoffLink]]:
    y28 = pub_year + 27
    who = ", ".join(writers) if writers else "unknown writers"
    objective = (
        f'Determine whether the US copyright in the musical composition "{title}" '
        f'(written by {who}, published {pub_year}) was renewed in its 28th year, '
        f'{y28}-{y28 + 1}. Look for a renewal registration (an "R" number) in the '
        f'Catalog of Copyright Entries, Third Series, Music, {y28}-{y28 + 1} renewals, '
        f'or in US Copyright Office renewal records.'
    )
    queries = [
        f'"{title}" copyright renewal {y28}',
        f'"{title}" {_surname(writers[0]) if writers else ""} renewal registration R'.strip(),
        f'Catalog of Copyright Entries music renewals {y28 + 1} "{title}"',
        # publisher / rightsholder notices read "copyright 1934, renewed 1961"
        f'"{title}" "renewed {y28}" OR "renewed {y28 + 1}"',
    ]
    if renewal_record_system(pub_year) == "online":
        # The scanned CCE ends in 1977; this window's record is in the online catalog.
        objective += (
            f' The window is 1978 or later, so the renewal record is a renewal registration '
            f'(an "RE" number) in the US Copyright Office online public catalog, not in the '
            f'scanned Catalog of Copyright Entries.'
        )
        queries[2] = f'"{title}" renewal registration RE copyright.gov'
    if announce:
        announce(queries)
    out = search(objective, queries)
    links = _links(out, "resolve",
                   f"Search hit for the {y28}-{y28 + 1} renewal of \"{title}\"")
    return out, links


def search_recording_date(title: str, artist: str, year_on_file: Optional[str],
                          announce=None) -> tuple[SearchOutcome, list[HandoffLink]]:
    objective = (
        f'Find the original first release (publication) year of the sound recording '
        f'"{title}" performed by {artist}: original record label, catalog number, '
        f'recording session date and release date. MusicBrainz only lists a release '
        f'from {year_on_file or "an unknown year"}, which may be a reissue. Prefer the '
        f'Discography of American Historical Recordings (DAHR), label discographies '
        f'and session logs.'
    )
    queries = [
        f'"{title}" {artist} discography original release',
        f'"{title}" {artist} 78 rpm catalog number',
        f'DAHR "{title}" {artist}',
    ]
    if announce:
        announce(queries)
    out = search(objective, queries)
    links = _links(out, "resolve",
                   f"Search hit for the original release of \"{title}\" by {artist}")
    return out, links


def search_writers(title: str, year: Optional[int], candidates: list[str],
                   announce=None) -> tuple[SearchOutcome, list[HandoffLink]]:
    """
    Parallel SEARCH for writer credits (primary request path). Runs when the
    writer list could not be corroborated against Wikidata: ASCAP/BMI
    repertories, Catalog of Copyright Entries registrations, sheet-music
    credits. The reader may then corroborate individual candidates — never
    conclude the list is complete.
    """
    who = "; ".join(candidates) if candidates else "unknown"
    objective = (
        f'Confirm the credited writers (composer and lyricist) of the musical composition '
        f'"{title}"{f" ({year})" if year else ""}. Candidate writers from MusicBrainz: {who}. '
        f'Prefer ASCAP or BMI repertory entries, Catalog of Copyright Entries registrations, '
        f'and published sheet music credits that name the writers.'
    )
    queries = [f'"{title}" composer lyricist credits']
    queries += [f'"{title}" {c}' for c in candidates[:2]]
    queries.append(f'"{title}" sheet music' + (f' {year}' if year else ''))
    if announce:
        announce(queries)
    out = search(objective, queries)
    links = _links(out, "resolve", f'Search hit for the writer credits of "{title}"')
    return out, links


def renewal_numbers(outcome: SearchOutcome) -> list[str]:
    """R-numbers mentioned in excerpts — evidence a human (or Gemini) should check."""
    found = []
    for hit in outcome.hits:
        for ex in hit.excerpts:
            found.extend(_R_NUMBER.findall(ex))
    return list(dict.fromkeys(found))
