"""
Run the full pipeline with the live GeminiReader over REAL Parallel Search on
the renewal-window and reissue cases, and report what the reader concluded and
from what sources.

    python -m agent.live_cases            (needs PARALLEL_API_KEY + GCP + ADC)
    python -m agent.live_cases --model gemini-3.7-flash

Reports per case: verdict, each layer's determination, and for every question
the reader touched — resolved or unresolved, the confidence, how many
citations, and the actual source URLs. Prints the raw model output for the
first resolved and first unresolved reads so the reasoning is visible.
"""

from __future__ import annotations

import argparse
import os
import sys

from agent.gemini_reader import GeminiReader
from pipeline.music import run_music
from schemas import AssetQuery, AssetType, Intent, Jurisdiction

CASES = [
    ("renewal", "Take Five", "The Dave Brubeck Quartet"),
    ("renewal", "Mack the Knife", "Bobby Darin"),
    ("renewal", "Summertime", "Billie Holiday"),
    ("renewal", "Blue Moon", "Ella Fitzgerald"),
    ("reissue", "Blue Moon", "The Marcels"),
]


def fact_line(fact) -> str:
    if fact is None:
        return "no fact"
    srcs = ", ".join(str(s.url) for s in fact.sources) or "(no source)"
    return f"value={fact.value!r} confidence={fact.confidence.value} citations={len(fact.sources)} sources=[{srcs}]"


def run(kind, title, artist, reader, shown):
    print("\n" + "=" * 78)
    print(f"{kind.upper()}: {title} — {artist}")
    print("=" * 78)
    q = AssetQuery(raw_input=f"{title} — {artist}", intent=Intent.FILM_TV,
                   jurisdiction=Jurisdiction.US, asset_type_hint=AssetType.MUSIC)
    reader.last_raw = None
    resp, em = run_music(q, reader=reader)
    print(f"VERDICT: {resp.overall_verdict.value}  (confidence {resp.overall_confidence.value})")
    print(f"  {resp.overall_headline}")
    for lv in resp.layer_verdicts:
        d = lv.determination
        print(f"  {lv.layer_id:<16} {d.status.value:<14} "
              + (f"-> {d.expiry_year} " if d.expiry_year else "")
              + f"[{d.rule_id}]" + (f" blocked_by={d.blocked_by}" if d.blocked_by else ""))
    comp = next(l for l in resp.entity.layers if l.layer_id == "composition")
    rec = next(l for l in resp.entity.layers if l.layer_id == "sound_recording")
    print(f"  renewal_filed fact:   {fact_line(comp.term_facts.renewal_filed)}")
    print(f"  recording_year fact:  {fact_line(rec.term_facts.recording_first_published_year)}")
    print(f"  recording_date_basis: {rec.term_facts.recording_date_basis.value if rec.term_facts.recording_date_basis else '-'}")
    if resp.unresolved:
        print("  still unresolved: " + ", ".join(u.question_id for u in resp.unresolved))
    # show raw model output for the first resolved and first unresolved read
    resolved = comp.term_facts.renewal_filed is not None or (
        rec.term_facts.recording_date_basis and rec.term_facts.recording_date_basis.value == "researched")
    tag = "resolved" if resolved else "unresolved"
    if reader.last_raw and tag not in shown:
        shown.add(tag)
        print(f"\n  --- RAW MODEL OUTPUT ({tag} read) ---")
        print("  " + (reader.last_raw or "").replace("\n", "\n  ")[:2000])


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--model", default=None)
    a = p.parse_args(argv)
    if not os.environ.get("PARALLEL_API_KEY"):
        print("PARALLEL_API_KEY not set — cannot run the live Parallel Search. Aborting.")
        return 1
    reader = GeminiReader(model=a.model) if a.model else GeminiReader()
    print(f"reader model: {reader.model}")
    shown: set = set()
    for kind, title, artist in CASES:
        try:
            run(kind, title, artist, reader, shown)
        except Exception as e:
            print(f"  CASE ERROR: {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
