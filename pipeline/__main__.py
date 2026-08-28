"""
Command line: one music query -> a cited two-layer verdict.

    python -m pipeline "West End Blues" "Louis Armstrong"
    python -m pipeline "Rhapsody in Blue" "Paul Whiteman" --intent film_tv --jurisdiction UK
    python -m pipeline "Take Five" --json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from schemas import AssetQuery, AssetType, Intent, Jurisdiction, RightsResponse, Verdict

from .events import Emitter
from .music import run_music

STAMP = {Verdict.CLEAR: "CLEAR", Verdict.CLEAR_WITH_CONDITIONS: "CLEAR — CONDITIONS",
         Verdict.LICENSE_REQUIRED: "LICENSE REQUIRED", Verdict.RESTRICTED: "RESTRICTED",
         Verdict.UNDETERMINED: "UNDETERMINED"}


def ledger(ev):
    flag = " ⚠ degraded" if ev.degraded else ""
    err = f" — {ev.error_message}" if ev.error_message else ""
    print(f"  {ev.elapsed_ms / 1000:6.1f}s  {ev.stage.value:<9} {ev.status:<9} {ev.message}{flag}{err}")


def render(r: RightsResponse) -> str:
    L = []
    q = r.query
    L.append("=" * 78)
    L.append(f"{STAMP[r.overall_verdict]}   [{q.jurisdiction.value} · {q.intent.value} · confidence {r.overall_confidence.value}]")
    L.append(r.overall_headline)
    L.append("=" * 78)
    if r.stop_for_disambiguation:
        L.append("Candidates:")
        for c in r.entity.alternate_candidates:
            L.append(f"  • {c.label}  —  {c.disambiguator}")
        return "\n".join(L)
    for lv in r.layer_verdicts:
        req = "REQUIRED" if lv.is_required else "not required for this purpose"
        d = lv.determination
        L.append(f"\n{STAMP[lv.verdict]:<20} {lv.layer_label}   ({req})")
        L.append(f"  {lv.headline}")
        L.append(f"  rule {d.rule_id} · confidence {d.confidence.value}" + (f" · blocked by {', '.join(d.blocked_by)}" if d.blocked_by else ""))
        L.append(f"  {lv.reasoning}")
        if lv.holders:
            L.append("  writers: " + "; ".join(f"{h.name.value} ({h.name.reasoning})" for h in lv.holders))
        if lv.licensing_path:
            L.append(f"  licensing: {lv.licensing_path}")
        if lv.cost_band:
            L.append(f"  cost band: {lv.cost_band}")
        if lv.intent_note:
            L.append(f"  note: {lv.intent_note}")
    layer_of = {l.layer_id: l for l in r.entity.layers}
    L.append("\nMatrix (layer × jurisdiction):")
    for lid, layer in layer_of.items():
        cells = []
        for j in (Jurisdiction.US, Jurisdiction.UK, Jurisdiction.EU):
            d = next((x for x in r.all_determinations if x.layer_id == lid and x.jurisdiction == j), None)
            if d is None:
                continue
            cells.append(f"{j.value}: {d.status.value}" + (f" → {d.expiry_year}" if d.expiry_year else ""))
        L.append(f"  {layer.label:<26} " + " · ".join(cells))
    if r.unresolved:
        L.append("\nUnresolved questions:")
        for u in r.unresolved:
            L.append(f"  ? {u.question}   [{u.estimated_effort}]")
            L.append(f"    why: {u.why_it_matters}")
            L.append(f"    if yes: {u.if_yes}  if no: {u.if_no}")
            L.append(f"    search: {u.search_terms}")
            for hl in u.resolution_links:
                L.append(f"    → {hl.source_name}: {hl.url}")
    if r.handoff_links:
        L.append("\nHandoff:")
        for hl in r.handoff_links:
            extra = f"  paste: {hl.paste_string}" if hl.paste_string else ""
            hint = f"  ({hl.navigation_hint})" if hl.navigation_hint else ""
            L.append(f"  [{hl.tier.value:<16}] {hl.purpose:<8} {hl.source_name}: {hl.url}{hint}{extra}")
    L.append(f"\nEvidence: {sum(len(f.sources) for l in r.entity.layers for f in _facts(l))} sources on {len(r.entity.layers)} layers · cache key {r.cache_key}")
    L.append(r.disclaimer)
    return "\n".join(L)


def _facts(layer):
    tf = layer.term_facts
    return [f for f in (tf.first_publication_year, tf.author_death_year, tf.recording_first_published_year) if f]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("title")
    p.add_argument("artist", nargs="?")
    p.add_argument("--intent", choices=[i.value for i in Intent], default=Intent.FILM_TV.value)
    p.add_argument("--jurisdiction", choices=[j.value for j in Jurisdiction if j is not Jurisdiction.OTHER], default="US")
    p.add_argument("--json", action="store_true", help="print the RightsResponse as JSON")
    p.add_argument("--read", action="store_true",
                   help="activate the Gemini reading step (needs GOOGLE_CLOUD_PROJECT + ADC + PARALLEL_API_KEY)")
    p.add_argument("--model", default=None, help="reader model (default gemini-2.5-flash)")
    p.add_argument("-q", "--quiet", action="store_true", help="no progress ledger")
    p.add_argument("-v", action="store_true", help="log HTTP retries")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.WARNING if a.v else logging.ERROR, format="%(name)s %(message)s")

    raw = a.title + (f" — {a.artist}" if a.artist else "")
    query = AssetQuery(raw_input=raw, intent=Intent(a.intent), jurisdiction=Jurisdiction(a.jurisdiction),
                       asset_type_hint=AssetType.MUSIC)
    reader = None
    if a.read:
        from agent.gemini_reader import GeminiReader
        reader = GeminiReader(model=a.model) if a.model else GeminiReader()
    em = Emitter(None if a.quiet else ledger)
    resp, _ = run_music(query, emitter=em, reader=reader)
    if a.json:
        print(resp.model_dump_json(indent=2))
    else:
        print()
        print(render(resp))
    return 0


if __name__ == "__main__":
    sys.exit(main())
