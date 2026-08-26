"""
Tier 2 — direct API clients (MusicBrainz, Wikidata, ...).

Everything goes through sources.http.get_json, which is cache-first,
throttled per host, retries with backoff, and FAILS SOFT: a Tier 2 miss
returns a Fetched with .error set, never raises. Callers degrade to Tier 3.
"""
