"""
Freeze the pipeline's RightsResponse for the five acceptance cases.

    python -m agent.freeze_fixtures

Runs pipeline.music.run_music against the mock world (no network, no key)
and writes agent/fixtures/<case>.json with timestamps stripped. The graph
in agent/workflow.py must reproduce these byte-for-byte (after
normalisation); if it can't, the pipeline stays canonical.

Re-freeze deliberately, after a behaviour change you intend, never to make
a failing test pass.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager

import httpx

from pipeline import mockworld
from pipeline.music import run_music
from research import parallel_client as pc
from schemas import AssetQuery, AssetType, Intent, Jurisdiction
from sources import http
from sources.cache import MemoryCache, set_default

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


@contextmanager
def mock_environment():
    """Isolated cache, mock MusicBrainz/Wikidata transport, fake Parallel, no sleeping."""
    set_default(MemoryCache())
    http.configure(client=httpx.Client(transport=httpx.MockTransport(mockworld.handler)),
                   sleep=lambda s: None)
    http._last_call.clear()
    pc.configure(mockworld.FakeParallel())
    try:
        yield
    finally:
        set_default(None)
        http.configure(client=httpx.Client(), sleep=lambda s: None)
        http._last_call.clear()
        pc.configure(None)
        pc._client_checked = False


def query_for(case: dict) -> AssetQuery:
    return AssetQuery(raw_input=case["raw_input"], intent=Intent(case["intent"]),
                      jurisdiction=Jurisdiction(case["jurisdiction"]), asset_type_hint=AssetType.MUSIC)


def freeze() -> dict[str, dict]:
    os.makedirs(FIXTURES, exist_ok=True)
    out = {}
    for name, case in mockworld.CASES.items():
        with mock_environment():
            resp, _ = run_music(query_for(case))
        data = mockworld.normalize(resp)
        path = os.path.join(FIXTURES, f"{name}.json")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)
            f.write("\n")
        out[name] = data
        print(f"{name:<8} {data['overall_verdict']:<17} -> {os.path.relpath(path)}")
    return out


if __name__ == "__main__":
    freeze()
