"""
Clearance enrichment: rights-holder research for layers that need clearing.

Runs AFTER the verdict, never on its path — the caller is GET /api/clearance,
fetched by the Result screen once the verdict is already on screen. Nobody
waits longer for an answer because we're looking up publishers; that's
information read after deciding, not before.

Trigger policy: only layers whose verdict is LICENSE_REQUIRED or RESTRICTED,
and only required ones. A clear verdict has nothing to clear; an
undetermined one has a more basic question open. Cue sheets never call this.

Holder facts pass through the consistency layer like any other researched
fact (check_holders in pipeline/consistency.py): Task adds more new facts
than anything else in the product, and every new fact is a new opportunity
for a contradiction nobody notices.
"""

from __future__ import annotations

from typing import Any, Optional

from schemas import LayerVerdict, RightsResponse, Verdict

from .consistency import check_holders
from .music import parse_query

ENRICHABLE = {Verdict.LICENSE_REQUIRED, Verdict.RESTRICTED}


def should_enrich(lv: LayerVerdict) -> bool:
    return lv.is_required and lv.verdict in ENRICHABLE


def _names_and_year(resp: RightsResponse, layer_id: str) -> tuple[list[str], Optional[int]]:
    if layer_id == "composition":
        names = [c.value for c in resp.entity.creators]
        year = resp.entity.year.value if resp.entity.year else None
        return names, year
    _, artist = parse_query(resp.query.raw_input)
    layer = next((l for l in resp.entity.layers if l.layer_id == layer_id), None)
    tf = layer.term_facts if layer else None
    year = tf.recording_first_published_year.value if tf and tf.recording_first_published_year else None
    return [artist] if artist else [], year


def enrich_response(resp: RightsResponse) -> dict[str, Any]:
    """
    Rights-holder research for every enrichable layer of an assembled
    response. Task results are cached (7 days), so a repeat is instant.
    Import of research.holders is local so the verdict path never pays it.
    """
    from research.holders import research_holders

    title = resp.entity.canonical_title
    layers: dict[str, Any] = {}
    ledger: list[str] = []
    for lv in resp.layer_verdicts:
        if not should_enrich(lv):
            continue
        names, year = _names_and_year(resp, lv.layer_id)
        finding = research_holders(lv.layer_id, title, names, year)
        if not finding.ok:
            layers[lv.layer_id] = {"error": finding.error}
            continue
        questions = check_holders(finding.holders, finding.raw_parties, year)
        ledger.extend(finding.ledger)
        layers[lv.layer_id] = {
            "holders": [h.model_dump(mode="json") for h in finding.holders],
            "clearance": finding.clearance.model_dump(mode="json") if finding.clearance else None,
            "found_share_total": finding.found_share_total,
            "completeness_note": finding.completeness_note,
            "mlc_note": finding.mlc_note,
            "questions": [q.model_dump(mode="json") for q in questions],
        }
    return {"layers": layers, "ledger": ledger}
