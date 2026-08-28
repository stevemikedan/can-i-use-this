"""
ADK tools for the reading step.

`parallel_search` is exposed to the reader agent so it can gather more
evidence when the material the pipeline already fetched is thin (e.g. reach
the Stanford Copyright Renewal Database for a 1923-1963 work). Parallel's
Search API is therefore called both on the pipeline's primary request path
and, when needed, from inside the agent — visible in the agent definition.

The tool returns a dict with a `status` key so the model reacts to a failure
instead of inventing around it, and every result carries its URL so a claim
built on it can be cited (Rule 4).
"""

from __future__ import annotations

from research import parallel_client as pc


def parallel_search(objective: str, queries: list[str]) -> dict:
    """Search the web for evidence using Parallel's Search API.

    Use this to find primary records that establish a fact — copyright
    renewal entries, discographies, session logs. Prefer authoritative
    catalogs (Catalog of Copyright Entries, Stanford Copyright Renewal
    Database, DAHR) over commercial or streaming pages.

    Args:
      objective: A self-contained description of what you are trying to
        establish, with enough context to judge relevance.
      queries: Two or three short keyword queries (3-6 words each).

    Returns:
      A dict with "status" ("ok" or "error") and "results": a list of
      {"url", "title", "excerpts"} ordered by relevance. Each excerpt is a
      passage you may quote as a citation; the url is its source.
    """
    out = pc.search(objective, queries)
    if not out.ok:
        return {"status": "error", "error": out.error, "results": []}
    return {
        "status": "ok",
        "results": [{"url": h.url, "title": h.title, "excerpts": h.excerpts} for h in out.hits],
    }
