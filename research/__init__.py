"""
Tier 3 — Parallel (parallel-web SDK).

COMPLIANCE.md §1: the Search API must be called on the primary request path.
`research.parallel_client.search` is that call; `research.music` puts it on
the path for renewal research and recording first-publication research.
Task is used for structured multi-field research where output.basis
citations earn their place. Both fail soft when PARALLEL_API_KEY is unset.
"""
