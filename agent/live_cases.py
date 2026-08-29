"""
Run the full pipeline with the live GeminiReader over REAL Parallel Search on
the renewal-window and reissue cases, and report what the reader concluded and
from what sources.

    python -m agent.live_cases            (needs PARALLEL_API_KEY + GCP + ADC)
    python -m agent.live_cases --model gemini-3.7-flash
    python -m agent.live_cases --case marcels --all-raw     (one case, every raw read)

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
    # The Marcels' Blue Moon resolves at Tier 2 (MusicBrainz has a dated 1961
    # performance), so it never reaches the reader. Billy Stewart's Summertime
    # has only a first-release-date on file, so read_recording_year must
    # establish the original release from evidence.
    ("reissue", "Summertime", "Billy Stewart"),
]


def fact_line(fact) -> str:
    if fact is None:
        return "no fact"
    srcs = ", ".join(str(s.url) for s in fact.sources) or "(no source)"
    return f"value={fact.value!r} confidence={fact.confidence.value} citations={len(fact.sources)} sources=[{srcs}]"


def run(kind, title, artist, reader, shown, all_raw=False):
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
    comp = next((l for l in resp.entity.layers if l.layer_id == "composition"), None)
    rec = next((l for l in resp.entity.layers if l.layer_id == "sound_recording"), None)
    if comp is None or rec is None:
        # Resolution failed before any layer existed (e.g. MusicBrainz 503 x3).
        # The pipeline degraded honestly; there is nothing for the reader to read.
        print("  no layers resolved: " + "; ".join(u.question_id + ": " + u.question for u in resp.unresolved))
        return
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
    p.add_argument("--case", default=None,
                   help="only run cases whose title or artist contains this (case-insensitive)")
    p.add_argument("--all-raw", action="store_true", help="print the raw model output for every case")
    a = p.parse_args(argv)
    if not os.environ.get("PARALLEL_API_KEY"):
        print("PARALLEL_API_KEY not set — cannot run the live Parallel Search. Aborting.")
        return 1
    reader = GeminiReader(model=a.model) if a.model else GeminiReader()
    print(f"reader model: {reader.model}")
    shown: set = set()
    for kind, title, artist in CASES:
        if a.case and a.case.lower() not in f"{title} {artist}".lower():
            continue
        try:
            run(kind, title, artist, reader, shown, all_raw=a.all_raw)
        except Exception as e:
            print(f"  CASE ERROR: {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
