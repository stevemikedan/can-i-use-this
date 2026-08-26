"""
Determinations -> LayerVerdicts -> RightsResponse.

Roll-up is data-driven: REQUIRED_LAYERS and VERDICT_ORDER from schemas.py,
map_status_to_verdict for status -> verdict. UNDETERMINED is most
restrictive; if we don't know, we don't say clear.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from registry import handoff_links
from schemas import (
    DEFAULT_ALL_LAYERS_REQUIRED, REQUIRED_LAYERS, VERDICT_ORDER, AssetQuery, AssetType, Candidate,
    Confidence, Determination, DeterminationStatus, Intent, Jurisdiction, LayerVerdict,
    ResolvedEntity, RightsLayer, RightsResponse, UnresolvedQuestion, Verdict,
    map_status_to_verdict,
)

from .events import Emitter

_RANK = {Confidence.HIGH: 3, Confidence.MEDIUM: 2, Confidence.LOW: 1, Confidence.NONE: 0}

COST_BANDS = {
    Intent.FILM_TV: {"composition": "$500–$5,000 sync fee for an indie film; more for major releases",
                     "sound_recording": "$500–$5,000 master use fee for an indie film; often matched to the sync fee"},
    Intent.COMMERCIAL: {"composition": "$5,000–$50,000+ sync fee for advertising, by reach and term",
                        "sound_recording": "$5,000–$50,000+ master fee, typically matched to the sync fee"},
    Intent.SOCIAL_VIDEO: {"composition": "Tens to low hundreds of dollars via a licensing service, or platform library terms",
                          "sound_recording": "Tens to low hundreds of dollars via a licensing service, or platform library terms"},
    Intent.PODCAST: {"composition": "Low hundreds of dollars per episode or a blanket production-music deal",
                     "sound_recording": "Low hundreds of dollars per episode; labels rarely license single episodes"},
    Intent.GAME: {"composition": "$1,000–$10,000+ sync for an indie game, by territory and term",
                  "sound_recording": "$1,000–$10,000+ master fee for an indie game"},
    Intent.RERECORD: {"composition": "Compulsory mechanical (statutory rate) for audio; sync still negotiated for video"},
}

UNDETERMINED_WHY = {
    "us_renewal_unknown": "its year-28 renewal status is unknown",
    "recording_pub_year_unconfirmed": "the only date on file may be a reissue",
    "life_plus_70_writers_uncorroborated": "the writer list could not be corroborated, and a missing co-writer changes the term",
    "us_publication_year_unknown": "its publication year is unknown",
    "spike_no_work_link": "the recording is not linked to a composition",
}

LICENSING_PATH = {
    "composition": "Sync license from the publisher(s) / administrator — find them via MLC, ASCAP or BMI (handoff links)",
    "sound_recording": "Master use license from the label or current rights holder of this recording",
}


def required_layers(asset_type: AssetType, intent: Intent, layers: list[RightsLayer]) -> set[str]:
    kinds = REQUIRED_LAYERS.get((asset_type, intent))
    if kinds is None:
        return {l.layer_id for l in layers} if DEFAULT_ALL_LAYERS_REQUIRED else set()
    return {l.layer_id for l in layers if l.kind in kinds}


def _headline_for(det: Determination, j: Jurisdiction) -> str:
    if det.status is DeterminationStatus.PUBLIC_DOMAIN:
        return f"Public domain in the {j.value}" + (f" since 1 January {det.expiry_year}" if det.expiry_year else "")
    if det.status is DeterminationStatus.PROTECTED:
        return f"Protected in the {j.value}" + (f" until 1 January {det.expiry_year}" if det.expiry_year else "")
    why = UNDETERMINED_WHY.get(det.rule_id) or det.rule_explanation.split(".")[0].split(";")[0]
    return ("Undetermined — " + why)[:120]


def layer_verdicts(entity: ResolvedEntity, dets: list[Determination], jurisdiction: Jurisdiction,
                   intent: Intent) -> list[LayerVerdict]:
    req = required_layers(entity.asset_type, intent, entity.layers)
    out = []
    for layer in entity.layers:
        det = next(d for d in dets if d.layer_id == layer.layer_id and d.jurisdiction == jurisdiction)
        verdict = map_status_to_verdict(det.status)
        is_required = layer.layer_id in req
        note = None
        if not is_required and intent is Intent.RERECORD and layer.layer_id == "sound_recording":
            note = "Not required for a re-recording — you would license the composition only."
        out.append(LayerVerdict(
            layer_id=layer.layer_id, layer_label=layer.label, verdict=verdict, is_required=is_required,
            headline=_headline_for(det, jurisdiction)[:120], reasoning=det.rule_explanation,
            determination=det, holders=layer.holders, clearance=layer.clearance,
            licensing_path=LICENSING_PATH.get(layer.layer_id) if verdict is Verdict.LICENSE_REQUIRED else None,
            cost_band=COST_BANDS.get(intent, {}).get(layer.layer_id) if verdict is Verdict.LICENSE_REQUIRED else None,
            intent_note=note,
        ))
    return out


def roll_up(lvs: list[LayerVerdict]) -> tuple[Verdict, Optional[LayerVerdict]]:
    req = [lv for lv in lvs if lv.is_required]
    if not req:
        return Verdict.UNDETERMINED, None
    worst = max(req, key=lambda lv: VERDICT_ORDER[lv.verdict])
    return worst.verdict, worst


def overall_headline(verdict: Verdict, blocking: Optional[LayerVerdict], lvs: list[LayerVerdict],
                     j: Jurisdiction) -> str:
    req = [lv for lv in lvs if lv.is_required]
    if verdict is Verdict.CLEAR:
        names = " and ".join(lv.layer_label.split(" (")[0].lower() for lv in req)
        return f"Clear: the {names} are in the public domain in the {j.value}."
    if blocking is None:
        return "No layer applies to this purpose."
    b = blocking.layer_label.split(" (")[0].lower()
    others = [lv for lv in req if lv is not blocking]
    if verdict is Verdict.UNDETERMINED:
        why = UNDETERMINED_WHY.get(blocking.determination.rule_id) or \
            blocking.determination.rule_explanation.split(".")[0].split(";")[0][:70]
        return f"Not yet determined: the {b} layer is blocked — {why}."[:160]
    exp = blocking.determination.expiry_year
    tail = ""
    if others:
        o = others[0]
        st = ("public domain" if o.verdict is Verdict.CLEAR else
              "also protected" if o.verdict is Verdict.LICENSE_REQUIRED else o.verdict.value.replace("_", " "))
        tail = f" The {o.layer_label.split(' (')[0].lower()} is {st}."
    return (f"License required: the {b} is protected in the {j.value}"
            + (f" until 1 January {exp}" if exp else "") + "." + tail)[:160]


def overall_confidence(lvs: list[LayerVerdict]) -> Confidence:
    req = [lv.determination.confidence for lv in lvs if lv.is_required]
    if not req:
        return Confidence.NONE
    return min(req, key=lambda c: _RANK[c])


def cache_key(entity: ResolvedEntity) -> Optional[str]:
    prim = sorted(i.value for l in entity.layers for i in l.identifiers if i.is_primary)
    return f"{entity.asset_type.value}:" + ":".join(prim) if prim else None


def assemble(query: AssetQuery, entity: ResolvedEntity, dets: list[Determination],
             questions: list[UnresolvedQuestion], em: Emitter, *, extra: Optional[dict] = None) -> RightsResponse:
    lvs = layer_verdicts(entity, dets, query.jurisdiction, query.intent)
    verdict, blocking = roll_up(lvs)
    headline = overall_headline(verdict, blocking, lvs, query.jurisdiction)
    ids = [i for l in entity.layers for i in l.identifiers]
    links = handoff_links(ids, entity.asset_type, extra=extra)
    return RightsResponse(
        query=query, entity=entity, stop_for_disambiguation=False,
        overall_verdict=verdict, overall_headline=headline, overall_confidence=overall_confidence(lvs),
        layer_verdicts=lvs, all_determinations=dets, unresolved=questions, handoff_links=links,
        generated_at=datetime.now(timezone.utc), cache_key=cache_key(entity),
    )


def stop_response(query: AssetQuery, title: str, candidates: list[Candidate], n_artists: int,
                  em: Emitter) -> RightsResponse:
    entity = ResolvedEntity(canonical_title=title, asset_type=AssetType.MUSIC,
                            resolution_confidence=Confidence.LOW, alternate_candidates=candidates)
    return RightsResponse(
        query=query, entity=entity, stop_for_disambiguation=True,
        overall_verdict=Verdict.UNDETERMINED,
        overall_headline=f'Which recording of "{title}" did you mean? {n_artists} artists have recorded it — add the artist.'[:160],
        overall_confidence=Confidence.NONE, generated_at=datetime.now(timezone.utc),
    )


def failed_response(query: AssetQuery, title: str, artist: Optional[str], em: Emitter,
                    why: str) -> RightsResponse:
    entity = ResolvedEntity(canonical_title=title, asset_type=AssetType.MUSIC,
                            resolution_confidence=Confidence.NONE)
    q = UnresolvedQuestion(
        question_id="resolve:not_found",
        question=f'Which recording of "{title}"' + (f" by {artist}" if artist else "") + " is meant?",
        why_it_matters=why, if_yes="Research can run once the recording is identified.",
        if_no="Nothing can be determined without a resolved recording.",
        search_terms=[f'"{title}" {artist or ""} musicbrainz'.strip()], estimated_effort="minutes",
    )
    return RightsResponse(
        query=query, entity=entity, overall_verdict=Verdict.UNDETERMINED,
        overall_headline=f"Not found: {why}"[:160], overall_confidence=Confidence.NONE,
        unresolved=[q], generated_at=datetime.now(timezone.utc),
    )
