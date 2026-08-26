"""
Thin, cache-aware wrapper over the official parallel-web SDK.

    from research.parallel_client import search
    out = search("Was 'Blue Moon' (Rodgers/Hart, 1934) renewed in 1961-62?",
                 ['"Blue Moon" copyright renewal 1962', ...])
    for hit in out.hits: hit.url, hit.title, hit.excerpts

Search (mandatory for the track) and Task (structured, cited) both live
here. Results are cached like every other external response. With no
PARALLEL_API_KEY the wrappers return an outcome with .error set and the
pipeline degrades — it never raises.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from sources.cache import get_cache

log = logging.getLogger("research.parallel")

SEARCH_MAX_AGE_S = 7 * 86400
TASK_MAX_AGE_S = 7 * 86400
DEFAULT_SEARCH_MODE = "fast"          # ~1s budget; "advanced" is the SDK default
DEFAULT_TASK_PROCESSOR = "base-fast"  # never pro/ultra in the request path (docs/PROJECT.md §4.6)


# --- client -----------------------------------------------------------------

_client: Any = None
_client_checked = False


def configure(client: Any) -> None:
    """Inject a client (tests)."""
    global _client, _client_checked
    _client, _client_checked = client, True


def get_client() -> Any:
    """Real SDK client, or None when PARALLEL_API_KEY is unset."""
    global _client, _client_checked
    if _client_checked:
        return _client
    _client_checked = True
    if os.environ.get("PARALLEL_API_KEY"):
        from parallel import Parallel  # official SDK: parallel-web
        _client = Parallel()
    else:
        log.warning("PARALLEL_API_KEY not set; Tier 3 research is unavailable")
        _client = None
    return _client


def available() -> bool:
    return get_client() is not None


# --- search -------------------------------------------------------------------

@dataclass
class SearchHit:
    url: str
    title: Optional[str]
    excerpts: list[str]
    publish_date: Optional[str] = None


@dataclass
class SearchOutcome:
    objective: str
    queries: list[str]
    hits: list[SearchHit] = field(default_factory=list)
    search_id: Optional[str] = None
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    from_cache: bool = False
    error: Optional[str] = None
    elapsed_s: float = 0.0

    @property
    def ok(self) -> bool:
        return self.error is None


def _hits_from(payload: dict) -> list[SearchHit]:
    return [SearchHit(url=r.get("url", ""), title=r.get("title"),
                      excerpts=list(r.get("excerpts") or []),
                      publish_date=r.get("publish_date"))
            for r in payload.get("results", [])]


def search(objective: str, queries: list[str], *, mode: str = DEFAULT_SEARCH_MODE,
           max_chars_total: int = 8000) -> SearchOutcome:
    """
    Parallel Search API. This is the call COMPLIANCE.md §1 requires on the
    primary request path. Cached 7 days by (objective, queries, mode).
    """
    cache = get_cache()
    key = "parallel:search:" + hashlib.sha1(
        json.dumps([objective, queries, mode, max_chars_total]).encode()).hexdigest()
    entry = cache.get(key, max_age_s=SEARCH_MAX_AGE_S)
    if entry is not None:
        return SearchOutcome(objective, queries, _hits_from(entry.value),
                             entry.value.get("search_id"),
                             datetime.fromtimestamp(entry.fetched_at, tz=timezone.utc),
                             from_cache=True)

    client = get_client()
    if client is None:
        return SearchOutcome(objective, queries, error="PARALLEL_API_KEY not set")

    t0 = time.monotonic()
    try:
        result = client.search(objective=objective, search_queries=queries,
                               mode=mode, max_chars_total=max_chars_total)
    except Exception as e:  # SDK errors: auth, rate limit, network. Fail soft.
        log.warning("parallel search failed: %s", e)
        return SearchOutcome(objective, queries, error=f"{type(e).__name__}: {e}",
                             elapsed_s=time.monotonic() - t0)
    payload = result.model_dump() if hasattr(result, "model_dump") else dict(result)
    cache.set(key, payload)
    return SearchOutcome(objective, queries, _hits_from(payload), payload.get("search_id"),
                         elapsed_s=time.monotonic() - t0)


# --- task ---------------------------------------------------------------------

@dataclass
class TaskOutcome:
    input: Any
    content: Any = None                 # parsed output (dict for JSON schemas)
    basis: list[dict] = field(default_factory=list)   # per-field citations
    run_id: Optional[str] = None
    processor: str = DEFAULT_TASK_PROCESSOR
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    from_cache: bool = False
    error: Optional[str] = None
    elapsed_s: float = 0.0

    @property
    def ok(self) -> bool:
        return self.error is None


def run_task(input: Any, output_schema: dict, *, processor: str = DEFAULT_TASK_PROCESSOR,
             timeout_s: int = 90) -> TaskOutcome:
    """
    Parallel Task API: structured research with output.basis citations.
    Used for multi-field layer research (publishers, administrators,
    shares). Cached 7 days by (input, schema, processor).
    """
    if processor in ("pro", "ultra") or processor.startswith(("pro", "ultra")):
        return TaskOutcome(input, processor=processor,
                           error=f"processor {processor} is not allowed in the request path")
    cache = get_cache()
    key = "parallel:task:" + hashlib.sha1(
        json.dumps([input, output_schema, processor], sort_keys=True, default=str).encode()).hexdigest()
    entry = cache.get(key, max_age_s=TASK_MAX_AGE_S)
    if entry is not None:
        v = entry.value
        return TaskOutcome(input, v.get("content"), v.get("basis", []), v.get("run_id"),
                           processor, datetime.fromtimestamp(entry.fetched_at, tz=timezone.utc),
                           from_cache=True)

    client = get_client()
    if client is None:
        return TaskOutcome(input, processor=processor, error="PARALLEL_API_KEY not set")

    t0 = time.monotonic()
    try:
        run = client.task_run.create(
            input=input, processor=processor,
            task_spec={"output_schema": {"type": "json", "json_schema": output_schema}},
        )
        # api_timeout: how long the server blocks for the run; timeout: HTTP.
        result = client.task_run.result(run.run_id, api_timeout=timeout_s, timeout=timeout_s + 15)
    except Exception as e:
        log.warning("parallel task failed: %s", e)
        return TaskOutcome(input, processor=processor, error=f"{type(e).__name__}: {e}",
                           elapsed_s=time.monotonic() - t0)
    payload = result.model_dump() if hasattr(result, "model_dump") else dict(result)
    output = payload.get("output") or {}
    stored = {"content": output.get("content"), "basis": output.get("basis") or [],
              "run_id": payload.get("run", {}).get("run_id") or getattr(run, "run_id", None)}
    cache.set(key, stored)
    return TaskOutcome(input, stored["content"], stored["basis"], stored["run_id"], processor,
                       elapsed_s=time.monotonic() - t0)


# --- provenance ---------------------------------------------------------------

def hit_source(hit: SearchHit, outcome: SearchOutcome):
    """schemas.Source for one search hit (method PARALLEL_SEARCH)."""
    from schemas import ResearchMethod, Source

    excerpt = (hit.excerpts[0] if hit.excerpts else "")[:200] or None
    url = hit.url if hit.url.startswith(("http://", "https://")) else None
    return Source(name=hit.title or hit.url, url=url, method=ResearchMethod.PARALLEL_SEARCH,
                  retrieved_at=outcome.retrieved_at, excerpt=excerpt, authoritative=False)
