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

_R_NUMBER = re.compile(r"\bR\s?\d{5,7}\b")


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


def search_renewal(title: str, writers: list[str], pub_year: int) -> tuple[SearchOutcome, list[HandoffLink]]:
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
    ]
    out = search(objective, queries)
    links = _links(out, "resolve",
                   f"Search hit for the {y28}-{y28 + 1} renewal of \"{title}\"")
    return out, links


def search_recording_date(title: str, artist: str, year_on_file: Optional[str]) -> tuple[SearchOutcome, list[HandoffLink]]:
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
    out = search(objective, queries)
    links = _links(out, "resolve",
                   f"Search hit for the original release of \"{title}\" by {artist}")
    return out, links


def renewal_numbers(outcome: SearchOutcome) -> list[str]:
    """R-numbers mentioned in excerpts — evidence a human (or Gemini) should check."""
    found = []
    for hit in outcome.hits:
        for ex in hit.excerpts:
            found.extend(_R_NUMBER.findall(ex))
    return list(dict.fromkeys(found))
