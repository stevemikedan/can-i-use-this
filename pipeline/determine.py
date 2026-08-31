"""
Rules → schemas.Determination, for every (layer × jurisdiction) cell.

The arithmetic lives in rules/ (hand-written, tested, never a model). This
module only decides WHICH rule applies given the researched TermFacts, feeds
it the facts, and records confidence and what it depended on.
"""

from __future__ import annotations

from typing import Optional

from rules import eu_sound_recording, life_plus_70, us_sound_recording, us_standard_term
from rules import Determination as RuleResult
from schemas import (
    Confidence, Determination, DeterminationStatus, Jurisdiction, RecordingDateBasis,
    RightsLayer, RightsLayerKind, TRUSTWORTHY_DATE_BASES,
)

JURISDICTIONS = [Jurisdiction.US, Jurisdiction.UK, Jurisdiction.EU]

_STATUS = {
    "public_domain": DeterminationStatus.PUBLIC_DOMAIN,
    "protected": DeterminationStatus.PROTECTED,
    "undetermined": DeterminationStatus.UNDETERMINED,
}

_CONF_RANK = {Confidence.HIGH: 3, Confidence.MEDIUM: 2, Confidence.LOW: 1, Confidence.NONE: 0}

# Asymmetric trust in low-confidence evidence — decided 29 Aug 2026.
#
# A low-confidence fact may drive a determination toward PROTECTED, never
# toward PUBLIC DOMAIN. The costs are not symmetric: a wrong "protected" costs
# someone a license they did not need; a wrong "public domain" ends in a
# takedown or a lawsuit. So when the rule that fired says public domain and
# the weakest fact it depended on is LOW, the layer stays UNDETERMINED, the
# question stays open, and the evidence is shown as a lead rather than an
# answer (the research stages attach it to the question).
#
# The case this exists for: "Summertime" reading as "not renewed" from a
# licensing-site FAQ. The fact is probably right and the confidence is
# correctly capped at low by the source class — and it should still stay
# open, because the only thing backing a public-domain verdict would be a
# secondary web page. The same asymmetry already sits in the reader: a
# "not renewed" finding needs a primary record.
LOW_CONFIDENCE_PD_RULE = "public_domain_withheld_low_confidence"

# fact name (depends_on_facts) -> the question_ids key the research stage uses for it
_QUESTION_KEY = {"recording_first_published_year": "recording_pub_year"}


def _min_conf(*cs: Optional[Confidence]) -> Confidence:
    present = [c for c in cs if c is not None]
    if not present:
        return Confidence.NONE
    return min(present, key=lambda c: _CONF_RANK[c])


def _from_rule(layer: RightsLayer, j: Jurisdiction, r: RuleResult, confidence: Confidence,
               depends_on: list[str], question_ids: dict[str, str]) -> Determination:
    if r.status == "public_domain" and confidence is Confidence.LOW:
        # See LOW_CONFIDENCE_PD_RULE above: low-confidence evidence is a lead,
        # not grounds for a public-domain verdict.
        return Determination(
            layer_id=layer.layer_id, jurisdiction=j, status=DeterminationStatus.UNDETERMINED,
            expiry_year=None, rule_id=LOW_CONFIDENCE_PD_RULE,
            rule_explanation=(f"{r.explanation} That outcome rests on low-confidence evidence, and "
                              f"low-confidence evidence may support 'protected' but never 'public domain' "
                              f"(rule {r.rule_id} withheld). Treat the evidence as a lead and verify it."),
            confidence=Confidence.NONE, depends_on_facts=depends_on,
            blocked_by=[question_ids[_QUESTION_KEY.get(k, k)] for k in depends_on
                        if _QUESTION_KEY.get(k, k) in question_ids],
        )
    blocked = [question_ids[r.blocked_by]] if r.blocked_by and r.blocked_by in question_ids else []
    return Determination(
        layer_id=layer.layer_id, jurisdiction=j, status=_STATUS[r.status],
        expiry_year=r.expiry_year, rule_id=r.rule_id, rule_explanation=r.explanation,
        confidence=confidence if r.status != "undetermined" else Confidence.NONE,
        depends_on_facts=depends_on, blocked_by=blocked,
    )


def _undetermined(layer: RightsLayer, j: Jurisdiction, rule_id: str, why: str,
                  blocked_by: list[str]) -> Determination:
    return Determination(layer_id=layer.layer_id, jurisdiction=j,
                         status=DeterminationStatus.UNDETERMINED, rule_id=rule_id,
                         rule_explanation=why, confidence=Confidence.NONE, blocked_by=blocked_by)


def determine_composition(layer: RightsLayer, j: Jurisdiction, question_ids: dict[str, str],
                          death_years: list[Optional[int]]) -> Determination:
    tf = layer.term_facts
    if j is Jurisdiction.US:
        if tf.first_publication_year is None:
            return _undetermined(layer, j, "us_publication_year_unknown",
                                 "The composition's US publication year could not be determined.",
                                 [question_ids[k] for k in ("first_publication_year",) if k in question_ids])
        renewal = tf.renewal_filed.value if tf.renewal_filed is not None else None
        r = us_standard_term(tf.first_publication_year.value, renewal_filed=renewal)
        conf = _min_conf(tf.first_publication_year.confidence,
                         tf.renewal_filed.confidence if tf.renewal_filed else None)
        return _from_rule(layer, j, r, conf, ["first_publication_year", "renewal_filed"], question_ids)

    # UK / EU: life + 70 from the LAST surviving author.
    #
    # A derivative signal BLOCKS first: when the credited writers predate the
    # stated publication, the publication is likely a translation or
    # arrangement with its own authors — and computing life+70 from the wrong
    # deaths errs in the dangerous direction (a translator who outlived the
    # original authors lengthens the term). Same failure class as the reissue
    # date: a confident answer resting on an unestablished fact.
    if "derivative" in question_ids:
        return _undetermined(
            layer, j, "life_plus_70_authorship_disputed",
            "The credited writers predate the stated publication, so this is likely a translation "
            "or arrangement whose own authors' deaths the term runs from. Until authorship is "
            "settled, no life-plus-70 term can be computed.",
            [question_ids["derivative"]])

    # An uncorroborated writer list BLOCKS the determination: a missing
    # co-writer can only ever shorten the computed term, so a confident
    # verdict from a partial list is the same failure class as a term
    # computed from a reissue date.
    if not tf.writer_list_corroborated:
        blocked = [question_ids["author_death_year"]] if "author_death_year" in question_ids else []
        return _undetermined(
            layer, j, "life_plus_70_writers_uncorroborated",
            "The term runs from the death of the last surviving author, and the writer list "
            "could not be corroborated against a second source; a missing co-writer would "
            "shorten the computed term.", blocked)
    work_year = tf.first_publication_year.value if tf.first_publication_year else None
    r = life_plus_70(death_years, jurisdiction=j.value, work_year=work_year)
    if tf.author_death_year is not None:
        conf = tf.author_death_year.confidence
    elif r.rule_id.endswith("_life_plus_70_running"):
        # The living floor rests on the work year and the corroborated list,
        # not on a death record — its confidence follows those.
        conf = _min_conf(
            tf.first_publication_year.confidence if tf.first_publication_year else None,
            Confidence.MEDIUM if tf.writer_list_corroborated else Confidence.LOW,
        )
    else:
        conf = Confidence.NONE
    depends = ["author_death_year", "writer_list_corroborated"]
    return _from_rule(layer, j, r, conf, depends, question_ids)


def determine_recording(layer: RightsLayer, j: Jurisdiction, question_ids: dict[str, str]) -> Determination:
    tf = layer.term_facts
    basis = tf.recording_date_basis or RecordingDateBasis.UNKNOWN
    if tf.recording_first_published_year is None or basis not in TRUSTWORTHY_DATE_BASES:
        blocked = [question_ids["recording_pub_year"]] if "recording_pub_year" in question_ids else []
        why = ("The only date on file is an earliest release that may be a reissue; a term "
               "computed from it could be decades wrong." if basis is RecordingDateBasis.FIRST_RELEASE_DATE
               else "The recording's first publication year could not be determined.")
        return _undetermined(layer, j, "recording_pub_year_unconfirmed", why, blocked)
    year = tf.recording_first_published_year.value
    conf = tf.recording_first_published_year.confidence
    if j is Jurisdiction.US:
        r = us_sound_recording(year)
    else:
        r = eu_sound_recording(year, jurisdiction=j.value)
    return _from_rule(layer, j, r, conf, ["recording_first_published_year", "recording_date_basis"],
                      question_ids)


def determine_all(layers: list[RightsLayer], question_ids: dict[str, str],
                  death_years: list[Optional[int]]) -> list[Determination]:
    out = []
    for layer in layers:
        for j in JURISDICTIONS:
            if layer.kind is RightsLayerKind.COMPOSITION:
                out.append(determine_composition(layer, j, question_ids, death_years))
            elif layer.kind is RightsLayerKind.SOUND_RECORDING:
                out.append(determine_recording(layer, j, question_ids))
    return out
