"""
The consistency layer: cross-checks between facts that constrain each other.
Runs as its own stage after research and before rules.

Five instances of one shape motivated it:

  1. A reissue date used as a publication date, contradicted by the session
     date (MusicBrainz first-release-date, 1975 for a 1928 session).
  2. An incomplete writer list, contradicted by a sibling work crediting
     more writers (King Oliver alone; Clarence Williams d. 1965).
  3. A Wikidata name match returning a person whose dates contradict the
     work (the actor Clarence Williams, d. 2021).
  4. A writer dying before the stated publication (Weill d. 1950, a 1954
     publication) - the derivative check.
  5. A recording dated before its own composition (Garland's October 1938
     session; the film's August 1939 release recorded as publication).

Each is two facts that contradict each other, where each fact was checked
only against its own source and one was silently trusted. A check here
compares the pair, degrades confidence on both, and opens a question that
names the honest readings, instead of picking a winner.

Conflicts DEGRADE rather than block: a capped fact falls to LOW, which the
asymmetry in determine.py already prevents from supporting "public domain",
while "protected" still stands - erring toward protected is safe. A check
blocks outright only when the conflict makes the determination meaningless;
the derivative check (the founding member of this family, still emitted in
stage_research_composition because it gates life+70 research) does exactly
that, since disputed authorship is life+70's entire input.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from schemas import Confidence, PipelineStage as S, ResearchedFact, UnresolvedQuestion

if TYPE_CHECKING:  # pragma: no cover
    from pipeline.music import MusicRun

# Layer ids, matching schemas' layer vocabulary. Not imported from
# pipeline.music: music imports this module.
COMPOSITION = "composition"
RECORDING = "sound_recording"

# A death year more than this many years after the stated work year would
# make the writer implausibly old at writing (a 15-year-old prodigy living
# to 120). Beyond it the match is probably the wrong person - instance 3.
MAX_YEARS_DEATH_AFTER_WORK = 105


def _cap_low(fact: ResearchedFact | None, note: str) -> None:
    if fact is not None and fact.confidence is not Confidence.LOW:
        fact.confidence = Confidence.LOW
        fact.reasoning = ((fact.reasoning or "") + " " + note).strip()


def _predates_question(title: str, comp_year: int, rec_year: int) -> UnresolvedQuestion:
    return UnresolvedQuestion(
        question_id="consistency:recording_predates_composition",
        question=f'Is {comp_year} the publication of "{title}", or a release date after its {rec_year} recording?',
        why_it_matters=(
            f"The recording is dated {rec_year} and the composition's stated publication is {comp_year}: a "
            f"recording cannot predate the song it embodies. Each date can be defensible on its own (a session "
            f"recorded months before release; a publication year taken from a film's release) and the pair "
            f"still cannot both be first-publication facts. The honest readings: the composition date is a "
            f"release date rather than the song's publication, or the recording date is its session rather "
            f"than its first publication. Until one is settled, both dates are held at low confidence."),
        if_yes=f"If the composition was published in {comp_year}, the recording's {rec_year} date is its "
               f"session and the recording term runs from first release instead.",
        if_no=f"If the recording was first published in {rec_year}, the composition had been published by "
              f"then too, and both terms start earlier than the record states.",
        affects_layer_ids=[COMPOSITION, RECORDING],
        search_terms=[f'"{title}" copyright {comp_year}', f'"{title}" first published'],
        estimated_effort="minutes",
    )


def check_recording_before_composition(run: "MusicRun") -> None:
    """Instance 5: a recording dated before the composition it embodies."""
    comp_tf, rec_tf = run.composition.term_facts, run.recording.term_facts
    cy, ry = comp_tf.first_publication_year, rec_tf.recording_first_published_year
    if cy is None or ry is None or ry.value >= cy.value:
        return
    title = (run.cf.title if run.cf else None) or run.title
    q = _predates_question(title, cy.value, ry.value)
    note = (f"CONSISTENCY: the recording is dated {ry.value}, before this composition's stated "
            f"{cy.value} publication; see the open question ({q.question_id}).")
    _cap_low(cy, note)
    _cap_low(ry, note)
    run.comp_questions.append(q)
    # Bind the capped facts to the question so a withheld public-domain
    # outcome (LOW_CONFIDENCE_PD_RULE) points here - unless research already
    # opened its own question for the fact, which keeps precedence.
    run.comp_question_ids.setdefault("first_publication_year", q.question_id)
    run.rec_question_ids.setdefault("recording_pub_year", q.question_id)
    run.em.emit(S.RESEARCH, "progress",
                f"Consistency: recording dated {ry.value} predates the stated {cy.value} publication; "
                f"both dates held at low confidence, question opened")


def check_death_year_plausible(run: "MusicRun") -> None:
    """Instance 3 generalized: a death year that makes a writer impossibly
    long-lived relative to the work is probably the wrong person."""
    if run.cf is None or not run.cf.year:
        return
    year = run.cf.year
    odd = [w for w in run.cf.writers
           if w.death_year and w.death_year - year > MAX_YEARS_DEATH_AFTER_WORK]
    if not odd:
        return
    names = ", ".join(f"{w.name} (d. {w.death_year})" for w in odd)
    q = UnresolvedQuestion(
        question_id="consistency:death_year_implausible",
        question=f"Is the person on record for {names.split(' (')[0]} the writer of the {year} work?",
        why_it_matters=(
            f"{names}: a death more than {MAX_YEARS_DEATH_AFTER_WORK} years after the {year} work would make "
            f"the writer implausibly long-lived. A name search can land on the wrong person with the same "
            f"name, and life-plus-70 would then run from the wrong death. The death year is held at low "
            f"confidence until the identification is confirmed."),
        if_yes="If the identification is right, the life-plus-70 term stands as computed.",
        if_no="If it is the wrong person, the true writer's death year is earlier and the term ends sooner.",
        affects_layer_ids=[COMPOSITION],
        search_terms=[f'"{w.name}" songwriter' for w in odd[:2]],
        estimated_effort="minutes",
    )
    _cap_low(run.composition.term_facts.author_death_year,
             f"CONSISTENCY: an implausible death year is on record ({names}); see {q.question_id}.")
    run.comp_questions.append(q)
    run.comp_question_ids.setdefault("author_death_year", q.question_id)
    run.em.emit(S.RESEARCH, "progress",
                f"Consistency: implausible death year on record ({names}); held at low confidence")


def check_publication_country(run: "MusicRun") -> None:
    """A researched non-US publication country contradicts the US-publication
    assumption the US term rules run on."""
    tf = run.composition.term_facts
    c = tf.first_publication_country
    if c is None or str(c.value).strip().upper() in ("US", "USA", "UNITED STATES"):
        return
    q = UnresolvedQuestion(
        question_id="consistency:publication_country",
        question=f"Was the composition first published in the US, or in {c.value}?",
        why_it_matters=(
            f"The record states first publication in {c.value}, but the US determination applies US "
            f"publication rules (renewal, notice, the 95-year term). A foreign first publication can "
            f"carry a different US term via restoration (URAA) and a different country of origin."),
        if_yes="If first publication was in the US, the US term as computed stands.",
        if_no=f"If first publication was in {c.value}, the US term may differ; check URAA restoration.",
        affects_layer_ids=[COMPOSITION],
        search_terms=[f'"{(run.cf.title if run.cf else None) or run.title}" first published {c.value}'],
        estimated_effort="hours",
    )
    run.comp_questions.append(q)
    run.em.emit(S.RESEARCH, "progress",
                f"Consistency: first publication recorded in {c.value}, not the US; question opened")


def check_conflicting_values_cap(run: "MusicRun") -> None:
    """Instance 2's residue: where sources disagreed and one value was
    picked, the disagreement is on the record (conflicting_values) - and a
    fact carrying a recorded disagreement cannot be high confidence."""
    for layer in (run.composition, run.recording):
        if layer is None:
            continue
        for name in type(layer.term_facts).model_fields:
            fact = getattr(layer.term_facts, name)
            if isinstance(fact, ResearchedFact) and fact.conflicting_values \
                    and fact.confidence is Confidence.HIGH:
                fact.confidence = Confidence.MEDIUM
                fact.reasoning = ((fact.reasoning or "")
                                  + " CONSISTENCY: sources disagreed on this value "
                                    "(see conflicting values); confidence capped at medium.").strip()
                run.em.emit(S.RESEARCH, "progress",
                            f"Consistency: sources disagreed on {name}; confidence capped at medium")


CHECKS = [
    check_recording_before_composition,
    check_death_year_plausible,
    check_publication_country,
    check_conflicting_values_cap,
]


def run_checks(run: "MusicRun") -> None:
    for check in CHECKS:
        check(run)


# --- holder facts (Parallel Task enrichment) ----------------------------------
#
# Task adds more new facts than anything else in the product - publishers,
# administrators, shares - and every new fact is a new opportunity for a
# contradiction nobody notices. These run over each HoldersFinding before it
# is returned to the caller; they are pure functions, not stage checks,
# because enrichment runs after the verdict.

def check_holders(holders, raw_parties, work_year) -> list[UnresolvedQuestion]:
    """Cross-checks over rights-holder research. Mutates confidence caps in
    place (degrade, never block) and returns the questions to attach."""
    questions: list[UnresolvedQuestion] = []

    # Shares that sum past 100% cannot all be right.
    total = sum(h.share_percent for h in holders if h.share_percent is not None)
    if total > 100.001:
        for h in holders:
            if h.share_percent is not None:
                _cap_low(h.name, "CONSISTENCY: reported shares sum past 100%; see the open question.")
        questions.append(UnresolvedQuestion(
            question_id="consistency:holder_shares_exceed_100",
            question=f"Reported ownership shares sum to {total:g}%. Which are current?",
            why_it_matters=(f"The shares found sum to {total:g}%, which cannot all be right at once. "
                           f"Catalog sales and administration changes leave stale shares in web "
                           f"sources; the MLC record is the way to settle which are current. "
                           f"Every share here is held at low confidence."),
            if_yes="If the larger shares are current, the smaller parties may have sold their interest.",
            if_no="If the smaller shares are current, a catalog sale may not have been reported yet.",
            affects_layer_ids=[COMPOSITION],
            search_terms=[], estimated_effort="minutes"))

    # The same name with different shares: surface the disagreement, cap it.
    seen: dict[str, object] = {}
    for h in holders:
        key = "".join(ch for ch in h.name.value.casefold() if ch.isalnum())
        if key in seen and seen[key].share_percent != h.share_percent:
            first = seen[key]
            first.name.conflicting_values.append(
                f"{h.share_percent}% (also reported for {h.name.value})")
            _cap_low(first.name, "CONSISTENCY: sources disagree on this party's share.")
            _cap_low(h.name, "CONSISTENCY: sources disagree on this party's share.")
        else:
            seen[key] = h

    # A publisher founded after the work: the same shape as an author who
    # died before publication. (Administrators legitimately postdate old
    # works - catalogs get bought - so only the publisher role is checked.)
    if work_year:
        odd = [p for p in raw_parties
               if p.get("role") == "publisher" and not p.get("is_administrator")
               and isinstance(p.get("founded_year"), int) and p["founded_year"] > work_year]
        if odd:
            names = ", ".join(f"{p['name']} (founded {p['founded_year']})" for p in odd[:3])
            for h in holders:
                if any(p["name"] == h.name.value for p in odd):
                    _cap_low(h.name, "CONSISTENCY: founded after the work; see the open question.")
            questions.append(UnresolvedQuestion(
                question_id="consistency:publisher_postdates_work",
                question=f"Is {odd[0]['name']} the original publisher, or a later owner of the catalog?",
                why_it_matters=(f"{names}: a publisher founded after the {work_year} work cannot be its "
                               f"original publisher. It may be the current owner after a catalog sale, "
                               f"or the research may have matched the wrong company. Held at low "
                               f"confidence until settled."),
                if_yes="If it acquired the catalog, it is still who you license from.",
                if_no="If it is the wrong company, the actual publisher is unidentified.",
                affects_layer_ids=[COMPOSITION],
                search_terms=[f'"{odd[0]["name"]}" catalog acquisition'], estimated_effort="minutes"))
    return questions
