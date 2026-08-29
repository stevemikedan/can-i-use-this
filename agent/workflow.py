"""
The ADK graph: the pipeline's stages as agents.

    SequentialAgent  can_i_use_this
      classify                deterministic
      identify                deterministic — MusicBrainz; stops for disambiguation
      decompose               deterministic — composition + sound recording
      ParallelAgent  research
        research_composition  Tier 2, then Parallel Search for the renewal
                              window; the reader (an LlmAgent) reads the evidence
        research_recording    Tier 2, then Parallel Search for the original
                              release; the reader reads the evidence
      rules                   deterministic — rules/
      assemble                deterministic — verdicts, roll-up, handoff

Every stage agent calls the same pipeline.music stage function that
run_music calls, against one MusicRun shared through the session. The only
model on the determination path is the reader's LlmAgent
(agent/gemini_reader.py), whose output schema makes an unsourced fact
unrepresentable. No stage here asks a model anything.

The graph must reproduce the frozen fixtures in agent/fixtures byte-for-byte
(agent/test_acceptance.py). If it can't, the pipeline stays canonical.

    from agent.workflow import run_workflow
    response, emitter = run_workflow(query, reader=GeminiReader())

    python -m pipeline "West End Blues" "Louis Armstrong" --graph
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from typing import AsyncGenerator, Callable, Optional

from google.adk.agents import BaseAgent, ParallelAgent, SequentialAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.adk.runners import InMemoryRunner
from google.genai import types

from pipeline.events import Emitter
from pipeline.music import PARALLEL_STAGES, STAGE_FN, STAGES, MusicRun, new_run
from schemas import AssetQuery, RightsResponse

APP_NAME = "can-i-use-this"
USER_ID = "pipeline"

DESCRIPTIONS = {
    "classify": "Parse the query into title and artist; this path is music.",
    "identify": "Find the recording in MusicBrainz and select the artist's earliest dated session. "
                "A title with several artists and no artist given stops for disambiguation.",
    "decompose": "Split into the two separately-owned rights layers: composition and sound recording.",
    "research_composition": "Tier 2 (Wikidata publication year, writers cross-checked against MusicBrainz, "
                            "death years); Parallel Search for the year-28 renewal window, read by the reader.",
    "research_recording": "Recording date from the dated session; Parallel Search for the original release "
                          "when only a reissue date is on file, read by the reader.",
    "rules": "The deterministic rules engine: a determination per layer per jurisdiction.",
    "assemble": "Verdicts, conservative roll-up, unresolved questions, handoff links.",
}

# The MusicRun for each in-flight session. Stage agents look their run up by
# session id; run_workflow_async registers it before the runner starts and
# removes it after. The run itself is plain Python state, not session state —
# ADK session state must be JSON, and the run carries Pydantic models and the
# reader; the JSON-safe summary of each stage is written to state instead.
_runs: dict[str, MusicRun] = {}
_runs_lock = threading.Lock()


class StageAgent(BaseAgent):
    """One pipeline stage as a deterministic ADK agent. Never calls a model."""

    stage: str

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        with _runs_lock:
            run = _runs.get(ctx.session.id)
        if run is None:
            raise RuntimeError(f"no MusicRun registered for session {ctx.session.id}")
        if run.done:
            # An earlier stage produced the response (disambiguation stop or
            # not-found). Nothing to do; the graph runs to its end quietly.
            yield self._event(ctx, {"status": "skipped", "reason": "response already produced"})
            return
        before = len(run.em.events)
        # The stage is synchronous plain Python (Tier 2 HTTP, Parallel Search,
        # the reader). A thread keeps the event loop free so the ParallelAgent
        # really runs the two research stages concurrently.
        await asyncio.to_thread(STAGE_FN[self.stage], run)
        new = run.em.events[before:]
        last = new[-1] if new else None
        yield self._event(ctx, {
            "status": last.status if last else "complete",
            "message": last.message if last else "",
            "sources_consulted": run.em.sources_consulted,
            "degraded": any(e.degraded for e in new),
            "done": run.done,
        })

    def _event(self, ctx: InvocationContext, summary: dict) -> Event:
        text = f"{self.stage}: {summary.get('message') or summary['status']}"
        return Event(
            invocation_id=ctx.invocation_id, author=self.name, branch=ctx.branch,
            content=types.Content(role="model", parts=[types.Part(text=text)]),
            actions=EventActions(state_delta={f"stage.{self.stage}": summary}),
        )


def build_graph() -> SequentialAgent:
    """A fresh graph (an agent instance has one parent, so build one per run)."""
    def stage(name: str) -> StageAgent:
        return StageAgent(name=name, stage=name, description=DESCRIPTIONS[name])

    sub_agents = []
    parallel_done = False
    for name, _ in STAGES:
        if name in PARALLEL_STAGES:
            if not parallel_done:
                sub_agents.append(ParallelAgent(
                    name="research", description="Research both layers concurrently, cheapest tier first.",
                    sub_agents=[stage(n) for n in PARALLEL_STAGES]))
                parallel_done = True
            continue
        sub_agents.append(stage(name))
    return SequentialAgent(
        name="can_i_use_this",
        description="Rights determination for a song: classify, identify, decompose, research, rules, assemble.",
        sub_agents=sub_agents,
    )


async def run_workflow_async(query: AssetQuery, *, emitter: Optional[Emitter] = None, reader=None,
                             on_event: Optional[Callable[[Event], None]] = None) -> tuple[RightsResponse, Emitter]:
    """Run the graph for one query. Same contract as pipeline.music.run_music."""
    run = new_run(query, emitter=emitter, reader=reader)
    runner = InMemoryRunner(agent=build_graph(), app_name=APP_NAME)
    session = await runner.session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=uuid.uuid4().hex)
    with _runs_lock:
        _runs[session.id] = run
    try:
        message = types.Content(role="user", parts=[types.Part(text=query.raw_input)])
        async for event in runner.run_async(user_id=USER_ID, session_id=session.id, new_message=message):
            if on_event:
                on_event(event)
    finally:
        with _runs_lock:
            _runs.pop(session.id, None)
    if run.response is None:
        raise RuntimeError("the graph finished without producing a response")
    return run.response, run.em


def run_workflow(query: AssetQuery, *, emitter: Optional[Emitter] = None, reader=None,
                 on_event: Optional[Callable[[Event], None]] = None) -> tuple[RightsResponse, Emitter]:
    """Synchronous run_workflow_async; safe to call from inside a running loop."""
    coro = run_workflow_async(query, emitter=emitter, reader=reader, on_event=on_event)
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro)).result()
