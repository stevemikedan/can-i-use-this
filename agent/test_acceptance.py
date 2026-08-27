"""
The contract the ADK graph must meet: for each frozen case, the response
must equal the pipeline's, timestamps aside. Written before the graph.

    pipeline.music.run_music   -> fixture   (freezes the current behaviour)
    agent.workflow (graph)     -> fixture   (the graph must match it exactly)
"""

import json
import os

import pytest

from pipeline import mockworld
from pipeline.music import run_music

from .freeze_fixtures import FIXTURES, mock_environment, query_for

CASES = sorted(mockworld.CASES)
EXPECTED_VERDICT = {"blocked": "license_required", "clean": "clear", "stop": "undetermined",
                    "reissue": "undetermined", "renewal": "undetermined"}


def load(name: str) -> dict:
    with open(os.path.join(FIXTURES, f"{name}.json"), encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("name", CASES)
def test_fixture_verdicts_are_the_known_answers(name):
    assert load(name)["overall_verdict"] == EXPECTED_VERDICT[name]


@pytest.mark.parametrize("name", CASES)
def test_pipeline_matches_fixture(name):
    with mock_environment():
        resp, _ = run_music(query_for(mockworld.CASES[name]))
    assert mockworld.normalize(resp) == load(name)


def test_fixtures_cover_the_failure_modes():
    blocked, reissue, renewal, stop = load("blocked"), load("reissue"), load("renewal"), load("stop")
    # blocked: US blocks on the recording; UK/EU composition blocked by the writer list
    assert [lv["layer_id"] for lv in blocked["layer_verdicts"] if lv["verdict"] == "license_required"] == ["sound_recording"]
    uk = next(d for d in blocked["all_determinations"] if d["layer_id"] == "composition" and d["jurisdiction"] == "UK")
    assert uk["rule_id"] == "life_plus_70_writers_uncorroborated"
    # reissue: recording undetermined, basis first_release_date
    rec = next(l for l in reissue["entity"]["layers"] if l["layer_id"] == "sound_recording")
    assert rec["term_facts"]["recording_date_basis"] == "first_release_date"
    # renewal: composition undetermined by renewal, with the search hit attached
    q = next(u for u in renewal["unresolved"] if u["question_id"] == "composition:renewal")
    assert q["resolution_links"] and "R290123" in q["why_it_matters"]
    # stop: no research ran
    assert stop["stop_for_disambiguation"] and stop["entity"]["layers"] == []
