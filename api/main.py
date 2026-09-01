"""
FastAPI over the ADK graph: one query in, a RightsResponse out, with the
staged progress streamed as Server-Sent Events while it runs.

    GET  /api/health                  liveness, and which backends are live:
                                      cache (with a real read/write probe),
                                      the reader, Parallel. Not /healthz: the
                                      Cloud Run edge answers that path itself
                                      with a 404 and the request never reaches
                                      the container.
    POST /api/query                   {title, artist?, intent?, jurisdiction?}
                                      -> RightsResponse (waits for the result)
    GET  /api/query/stream?title=&artist=&intent=&jurisdiction=
                                      text/event-stream:
                                        event: progress   data: PipelineEvent
                                        event: response   data: RightsResponse
                                        event: error      data: {"error": ...}
    GET  /                            the frontend (web/dist) once built

The query runs through agent.workflow.run_workflow — the google-adk graph —
in a worker thread; the pipeline's Emitter feeds the SSE stream. Nothing
here decides anything: no model, no rule, no fact.

    python -m uvicorn api.main:app --reload
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import AsyncIterator, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from agent.reader import default_reader
from agent.workflow import run_workflow
from pipeline.events import Emitter
from research import parallel_client as pc
from schemas import AssetQuery, AssetType, Intent, Jurisdiction, PipelineEvent, RightsResponse, UserAnswer
from sources.cache import get_cache

log = logging.getLogger("api")

WEB_DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "dist")
KEEPALIVE_S = 15          # SSE comment lines keep proxies from closing a quiet stream

app = FastAPI(title="Can I Use This?", version="0.1",
              description="Rights determination for a music cue — a cited verdict per layer per jurisdiction.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])

_reader = None


def reader():
    """The reading step, built once. GeminiReader when GOOGLE_CLOUD_PROJECT is set, else NullReader."""
    global _reader
    if _reader is None:
        _reader = default_reader()
    return _reader


# --- request shape ---------------------------------------------------------------

class QueryIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    artist: Optional[str] = Field(None, max_length=200)
    intent: Intent = Intent.FILM_TV
    jurisdiction: Jurisdiction = Jurisdiction.US
    # question_id -> the user's answer to an open question, on a re-run.
    # POST-only; the SSE stream does not carry answers.
    answers: dict[str, UserAnswer] = Field(default_factory=dict)

    def to_query(self) -> AssetQuery:
        raw = self.title.strip() + (f" — {self.artist.strip()}" if self.artist and self.artist.strip() else "")
        return AssetQuery(raw_input=raw, intent=self.intent, jurisdiction=self.jurisdiction,
                          asset_type_hint=AssetType.MUSIC, user_answers=self.answers)


def _check_jurisdiction(j: Jurisdiction) -> None:
    if j is Jurisdiction.OTHER:
        raise HTTPException(422, "jurisdiction must be US, UK or EU")


# --- endpoints -------------------------------------------------------------------

PROBE_URLS = {
    "musicbrainz": "https://musicbrainz.org/ws/2/recording?query=recording:%22test%22&limit=1&fmt=json",
    "wikidata": "https://www.wikidata.org/w/api.php?action=wbsearchentities&search=test&language=en&format=json",
}


@app.get("/api/probe")
async def probe() -> dict:
    """Live GETs to the upstream sources, no cache: separates 'source is down'
    from 'source refuses this egress'. The MusicBrainz TLS-EOF incident of
    31 Aug is exactly what this exists to see from inside the container."""
    import httpx
    from sources.http import UA
    out: dict = {}
    async with httpx.AsyncClient(headers={"User-Agent": UA}, timeout=8) as client:
        for name, url in PROBE_URLS.items():
            t0 = time.time()
            try:
                r = await client.get(url)
                out[name] = {"status": r.status_code, "ms": int((time.time() - t0) * 1000)}
            except Exception as e:
                out[name] = {"error": f"{type(e).__name__}: {e}"[:200], "ms": int((time.time() - t0) * 1000)}
    return out


@app.get("/api/health")
async def health() -> dict:
    """Liveness plus a real probe of each backend. On Cloud Run this is the proof the Firestore cache works."""
    cache = get_cache()
    probe = {"roundtrip": False}
    try:
        key, value = "health:probe", {"t": time.time()}
        await asyncio.to_thread(cache.set, key, value)
        got = await asyncio.to_thread(cache.get, key)
        probe["roundtrip"] = bool(got and got.value == value)
        probe.update(await asyncio.to_thread(cache.stats))
    except Exception as e:                       # report, never crash the health check
        probe["error"] = f"{type(e).__name__}: {e}"
    return {
        "ok": True,
        "cache": probe,
        "reader": {"available": reader().available, "model": getattr(reader(), "model", None)},
        "parallel": {"available": pc.available()},
        "project": os.environ.get("GOOGLE_CLOUD_PROJECT"),
    }


@app.get("/api/clearance")
async def clearance(title: str = Query(min_length=1, max_length=200),
                    artist: Optional[str] = Query(None, max_length=200),
                    intent: Intent = Intent.FILM_TV,
                    jurisdiction: Jurisdiction = Jurisdiction.US) -> dict:
    """
    Rights-holder enrichment for the layers that need clearing. Runs AFTER
    the verdict is on screen (the Result screen fetches this), so verdict
    latency is untouched: the query re-run is warm (<1s) and the Task result
    is cached 7 days. Only protected/license-required layers are researched;
    a clear verdict returns an empty layers map.
    """
    _check_jurisdiction(jurisdiction)
    from pipeline.clearance import enrich_response
    q = QueryIn(title=title, artist=artist, intent=intent, jurisdiction=jurisdiction)
    resp, _ = await asyncio.to_thread(run_workflow, q.to_query(), reader=reader())
    return await asyncio.to_thread(enrich_response, resp)


@app.post("/api/query", response_model=RightsResponse)
async def query(q: QueryIn) -> RightsResponse:
    _check_jurisdiction(q.jurisdiction)
    resp, _ = await asyncio.to_thread(run_workflow, q.to_query(), reader=reader())
    return resp


@app.get("/api/query/stream")
async def query_stream(
    title: str = Query(min_length=1, max_length=200),
    artist: Optional[str] = Query(None, max_length=200),
    intent: Intent = Intent.FILM_TV,
    jurisdiction: Jurisdiction = Jurisdiction.US,
) -> StreamingResponse:
    _check_jurisdiction(jurisdiction)
    q = QueryIn(title=title, artist=artist, intent=intent, jurisdiction=jurisdiction).to_query()
    return StreamingResponse(_stream(q), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _sse(event: str, data) -> str:
    payload = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


async def _stream(q: AssetQuery) -> AsyncIterator[str]:
    """Run the graph in a thread; forward every PipelineEvent as it happens, then the response."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def on_event(ev: PipelineEvent) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, ("progress", ev.model_dump(mode="json")))

    async def run() -> None:
        try:
            resp, _ = await asyncio.to_thread(run_workflow, q, emitter=Emitter(on_event), reader=reader())
            await queue.put(("response", resp.model_dump(mode="json")))
        except Exception as e:
            log.exception("query failed")
            await queue.put(("error", {"error": f"{type(e).__name__}: {e}"}))
        finally:
            await queue.put(None)

    task = asyncio.create_task(run())
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_S)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                continue
            if item is None:
                break
            yield _sse(*item)
    finally:
        if not task.done():
            task.cancel()


# --- the frontend, once built ------------------------------------------------------
# Not a flat mount: client-side routes (/about) must fall back to index.html,
# while real files (assets, narrow.html) are served as themselves.

@app.get("/{rest:path}", include_in_schema=False)
async def spa(rest: str):
    if os.path.isdir(WEB_DIST):
        candidate = os.path.normpath(os.path.join(WEB_DIST, rest))
        if rest and candidate.startswith(os.path.normpath(WEB_DIST)) and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(WEB_DIST, "index.html"))
    return JSONResponse({"service": "can-i-use-this", "api": ["/api/health", "POST /api/query", "GET /api/query/stream"],
                         "docs": "/docs"})
