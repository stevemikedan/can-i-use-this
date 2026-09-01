"""
The API over the mock world: the JSON endpoint returns the fixture's
verdict, the SSE stream carries the staged progress and then the response,
and the health check reports the backends honestly.
"""

import json

import pytest
from fastapi.testclient import TestClient

from agent.freeze_fixtures import mock_environment
from agent.test_acceptance import load
from api.main import app
from pipeline import mockworld


@pytest.fixture
def client():
    with mock_environment():
        with TestClient(app) as c:
            yield c


def parse_sse(text: str) -> list[tuple[str, dict]]:
    out = []
    for block in text.split("\n\n"):
        lines = [l for l in block.splitlines() if l and not l.startswith(":")]
        if not lines:
            continue
        ev = next(l[len("event: "):] for l in lines if l.startswith("event: "))
        data = "".join(l[len("data: "):] for l in lines if l.startswith("data: "))
        out.append((ev, json.loads(data)))
    return out


def test_health_probes_the_cache(client):
    h = client.get("/api/health").json()
    assert h["ok"] is True
    assert h["cache"]["roundtrip"] is True and h["cache"]["backend"] == "memory"
    assert "available" in h["reader"] and "available" in h["parallel"]


def test_query_returns_the_fixture_verdict(client):
    r = client.post("/api/query", json={"title": "West End Blues", "artist": "Louis Armstrong"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["overall_verdict"] == load("blocked")["overall_verdict"] == "license_required"
    assert mockworld.normalize(body) == load("blocked")


def test_query_without_artist_stops_for_disambiguation(client):
    body = client.post("/api/query", json={"title": "Blue Moon"}).json()
    assert body["stop_for_disambiguation"] is True and body["entity"]["alternate_candidates"]


def test_stream_carries_progress_then_the_response(client):
    with client.stream("GET", "/api/query/stream", params={"title": "Rhapsody in Blue", "artist": "Paul Whiteman"}) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        events = parse_sse("".join(r.iter_text()))
    kinds = [k for k, _ in events]
    assert kinds[0] == "progress" and kinds[-1] == "response" and "error" not in kinds
    stages = [d["stage"] for k, d in events if k == "progress"]
    assert stages[0] == "classify" and stages[-1] == "assemble"
    resp = events[-1][1]
    assert resp["overall_verdict"] == "clear"
    assert mockworld.normalize(resp) == load("clean")


def test_bad_input_is_a_422(client):
    assert client.post("/api/query", json={"title": ""}).status_code == 422
    assert client.get("/api/query/stream", params={"title": "x", "jurisdiction": "MARS"}).status_code == 422
    assert client.post("/api/query", json={"title": "x", "jurisdiction": "other"}).status_code == 422


def test_spa_fallback_serves_client_routes(client):
    """/about is a client-side route: it must get index.html, not a 404; real files still serve as themselves."""
    r = client.get("/about")
    assert r.status_code == 200 and "<div id=\"root\"" in r.text
    assert client.get("/").status_code == 200
    assert client.get("/api/health").status_code == 200      # API routes win over the fallback


def test_clearance_enriches_only_blocking_layers(client):
    # West End Blues US/film_tv: recording license_required (enriched),
    # composition clear (skipped). The verdict endpoint is untouched.
    body = client.get("/api/clearance", params={"title": "West End Blues", "artist": "Louis Armstrong"}).json()
    assert "sound_recording" in body["layers"] and "composition" not in body["layers"]
    layer = body["layers"]["sound_recording"]
    h = layer["holders"][0]
    assert h["name"]["value"] == "Bluebird Songs"
    assert h["name"]["confidence"] == "medium"                 # the ceiling
    src = h["name"]["sources"][0]
    assert src["method"] == "parallel_task" and src["authoritative"] is False
    assert layer["clearance"]["unclaimed_share_percent"] is None   # never inferred
    assert "not necessarily unclaimed" in layer["completeness_note"]
    assert "MLC" in layer["mlc_note"]
    assert body["ledger"][0] == "Parallel Task \u2014 rights holders (sound recording)"


def test_clearance_skips_a_clear_verdict(client):
    body = client.get("/api/clearance", params={"title": "Rhapsody in Blue", "artist": "Paul Whiteman"}).json()
    assert body["layers"] == {} and body["ledger"] == []


def test_permalink_marker_written_and_read(client):
    # Before any run: not researched. After a run: researched and fresh.
    q = {"title": "West End Blues", "artist": "Louis Armstrong"}
    assert client.get("/api/cached", params=q).json() == {
        "researched": False, "researched_at": None, "fresh": False}
    client.post("/api/query", json=q)
    c = client.get("/api/cached", params=q).json()
    assert c["researched"] is True and c["fresh"] is True and c["researched_at"]


def test_disambiguation_stop_writes_no_marker(client):
    client.post("/api/query", json={"title": "Blue Moon"})
    c = client.get("/api/cached", params={"title": "Blue Moon"}).json()
    assert c["researched"] is False
