"""
Run the REAL GeminiReader on the mock world and diff against the frozen
(NullReader) fixtures. Deterministic cases must be identical; the renewal and
reissue windows may resolve where the mock evidence is conclusive — that is the
reader working, not the contract drifting.

    python -m agent.check_reader_on_mock    (needs GOOGLE_CLOUD_PROJECT + ADC)
"""

from __future__ import annotations

import json
import os

from agent.freeze_fixtures import FIXTURES, mock_environment, query_for
from agent.gemini_reader import GeminiReader
from pipeline import mockworld
from pipeline.music import run_music


def load(name):
    with open(os.path.join(FIXTURES, f"{name}.json"), encoding="utf-8") as f:
        return json.load(f)


def layer_summary(data):
    out = {}
    for d in data["all_determinations"]:
        if d["jurisdiction"] == "US":
            out[d["layer_id"]] = f'{d["status"]}' + (f' -> {d["expiry_year"]}' if d["expiry_year"] else "")
    return out


def main():
    reader = GeminiReader(use_search_tool=False)   # read only the mock's provided evidence
    for name, case in mockworld.CASES.items():
        with mock_environment():
            resp, _ = run_music(query_for(case), reader=reader)
        got = mockworld.normalize(resp)
        fixture = load(name)
        identical = got == fixture
        print(f"\n=== {name}  ({'IDENTICAL to fixture' if identical else 'DIFFERS — see below'})")
        print(f"   fixture US layers: {layer_summary(fixture)}")
        print(f"   reader  US layers: {layer_summary(got)}")
        print(f"   fixture verdict: {fixture['overall_verdict']}   reader verdict: {got['overall_verdict']}")


if __name__ == "__main__":
    main()
