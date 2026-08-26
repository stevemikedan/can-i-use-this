"""
Cache-first HTTP for Tier 2 sources.

    fetched = get_json(url, params, cache_key="mb:recording:<mbid>:work-rels")
    if fetched.ok: ... fetched.data ...
    else:          ... degrade to Tier 3; fetched.error says why ...

Rules (PROJECT.md §4.7):
  - Every successful response is cached indefinitely under cache_key.
  - Per-host minimum interval (MusicBrainz ~1 req/s), enforced across threads.
  - 429/5xx and connection errors are retried with exponential backoff,
    honouring Retry-After. Attempts are bounded; the call FAILS SOFT and
    returns Fetched(error=...) rather than raising.
  - 5-second timeout by default.

Fetched carries url + retrieved_at + from_cache so every value derived from
it can be turned into a schemas.Source (Hard rule 4: no unsourced facts).
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import httpx

from .cache import Cache, get_cache

log = logging.getLogger("sources.http")

UA = "CanIUseThis/0.1 ( https://github.com/stevemikedan/can-i-use-this )"
DEFAULT_TIMEOUT_S = 5.0
DEFAULT_ATTEMPTS = 3
DEFAULT_BACKOFF_S = 1.0
RETRY_STATUSES = {429, 500, 502, 503, 504}
MIN_INTERVAL_S = {
    "musicbrainz.org": 1.1,
    "www.wikidata.org": 0.25,
}


@dataclass
class Fetched:
    data: Any
    url: str
    retrieved_at: datetime
    from_cache: bool = False
    error: Optional[str] = None
    attempts: int = 0

    @property
    def ok(self) -> bool:
        return self.error is None and self.data is not None


# --- injectable plumbing (tests swap these) ---------------------------------

_client: Optional[httpx.Client] = None
_sleep: Callable[[float], None] = time.sleep
_last_call: dict[str, float] = {}
_throttle_lock = threading.Lock()


def configure(client: Optional[httpx.Client] = None,
              sleep: Optional[Callable[[float], None]] = None) -> None:
    global _client, _sleep
    if client is not None:
        _client = client
    if sleep is not None:
        _sleep = sleep
    _last_call.clear()


def _get_client() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(headers={"User-Agent": UA, "Accept": "application/json"},
                               timeout=DEFAULT_TIMEOUT_S)
    return _client


def _throttle(host: str) -> None:
    interval = MIN_INTERVAL_S.get(host, 0.0)
    if interval <= 0:
        return
    with _throttle_lock:
        wait = interval - (time.monotonic() - _last_call.get(host, -1e9))
        # Reserve the slot before sleeping so concurrent callers queue up.
        _last_call[host] = time.monotonic() + max(wait, 0.0)
    if wait > 0:
        _sleep(wait)


def _retry_after(resp: httpx.Response, fallback: float) -> float:
    ra = resp.headers.get("Retry-After")
    if ra and ra.isdigit():
        return float(ra)
    return fallback


# --- the one entry point ----------------------------------------------------

def get_json(url: str, params: Optional[dict] = None, *, cache_key: str,
             cache: Optional[Cache] = None, max_age_s: Optional[float] = None,
             timeout_s: float = DEFAULT_TIMEOUT_S, attempts: int = DEFAULT_ATTEMPTS,
             backoff_s: float = DEFAULT_BACKOFF_S) -> Fetched:
    cache = cache or get_cache()
    params = params or {}

    entry = cache.get(cache_key, max_age_s=max_age_s)
    if entry is not None:
        return Fetched(entry.value, str(httpx.URL(url, params=params)),
                       datetime.fromtimestamp(entry.fetched_at, tz=timezone.utc),
                       from_cache=True)

    host = httpx.URL(url).host or ""
    client = _get_client()
    full_url = str(httpx.URL(url, params=params))
    last_error = "no attempts"
    for attempt in range(1, attempts + 1):
        _throttle(host)
        try:
            resp = client.get(url, params=params, timeout=timeout_s,
                              headers={"User-Agent": UA, "Accept": "application/json"})
        except httpx.HTTPError as e:
            last_error = f"{type(e).__name__}: {e}"
            log.warning("attempt %d/%d %s -> %s", attempt, attempts, full_url, last_error)
            if attempt < attempts:
                _sleep(backoff_s * (2 ** (attempt - 1)))
            continue

        if resp.status_code == 200:
            try:
                data = resp.json()
            except ValueError as e:
                return Fetched(None, full_url, datetime.now(timezone.utc),
                               error=f"invalid JSON: {e}", attempts=attempt)
            cache.set(cache_key, data)
            return Fetched(data, full_url, datetime.now(timezone.utc), attempts=attempt)

        last_error = f"http {resp.status_code}"
        log.warning("attempt %d/%d %s -> %s", attempt, attempts, full_url, last_error)
        if resp.status_code in RETRY_STATUSES and attempt < attempts:
            _sleep(_retry_after(resp, backoff_s * (2 ** (attempt - 1))))
            continue
        if resp.status_code not in RETRY_STATUSES:
            break  # 4xx other than 429: retrying won't help

    return Fetched(None, full_url, datetime.now(timezone.utc),
                   error=last_error, attempts=attempts)


def as_source(fetched: Fetched, name: str, *, authoritative: bool = False,
              excerpt: Optional[str] = None):
    """Build a schemas.Source for a value derived from this fetch."""
    from schemas import ResearchMethod, Source  # lazy: keep sources importable alone

    return Source(name=name, url=fetched.url, method=ResearchMethod.DIRECT_API,
                  retrieved_at=fetched.retrieved_at, excerpt=excerpt,
                  authoritative=authoritative)
