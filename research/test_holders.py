"""The holders validator in isolation: the three constraints, enforced."""

from datetime import datetime, timezone

from research.holders import (
    MLC_NOTE, TASK_CONFIDENCE_CEILING, HoldersFinding, holders_from_task,
)
from research.parallel_client import TaskOutcome
from schemas import Confidence


def outcome(content, basis=None, error=None, from_cache=False):
    return TaskOutcome("input", content, basis or [], "run1", "base-fast",
                       datetime.now(timezone.utc), from_cache=from_cache, error=error)


def party(name, role="publisher", share=None, admin=False, founded=None):
    return {"name": name, "role": role, "is_administrator": admin, "share_percent": share,
            "territory": None, "founded_year": founded, "evidence": f"{name} per source"}


BASIS = [{"field": "parties", "citations": [
    {"url": "https://example.com/a", "title": "Music trade page", "excerpts": ["Warner Chappell administers the song"]}],
    "reasoning": "Warner Chappell named"}]


def test_cited_party_caps_at_medium_uncited_at_low():
    f = holders_from_task(outcome(
        {"parties": [party("Warner Chappell", admin=True, share=50),
                     party("Unknown Sub Publisher")], "one_stop": None, "notes": ""},
        basis=BASIS), "composition")
    assert f.ok and len(f.holders) == 2
    cited = next(h for h in f.holders if h.name.value == "Warner Chappell")
    uncited = next(h for h in f.holders if h.name.value == "Unknown Sub Publisher")
    assert cited.name.confidence is TASK_CONFIDENCE_CEILING     # MEDIUM, never higher
    assert uncited.name.confidence is Confidence.LOW
    src = cited.name.sources[0]
    assert src.method.value == "parallel_task" and not src.authoritative


def test_shortfall_never_becomes_unclaimed_share():
    # Constraint 2: 50% found does NOT mean 50% unclaimed.
    f = holders_from_task(outcome(
        {"parties": [party("Warner Chappell", share=50)], "one_stop": None, "notes": ""},
        basis=BASIS), "composition")
    assert f.clearance.unclaimed_share_percent is None
    assert f.found_share_total == 50
    assert "not necessarily unclaimed" in f.completeness_note
    assert "cannot be verified without the MLC" in f.completeness_note
    assert MLC_NOTE in (f.clearance.difficulty_reasoning or "")


def test_uncited_one_stop_is_dropped():
    # An unsourced fact is not a fact — even a convenient boolean.
    f = holders_from_task(outcome(
        {"parties": [party("Big Corp")], "one_stop": True, "notes": ""}), "composition")
    assert f.clearance.is_one_stop is None


def test_error_outcome_degrades_not_raises():
    f = holders_from_task(outcome(None, error="PARALLEL_API_KEY not set"), "composition")
    assert not f.ok and f.holders == [] and f.clearance is None


def test_ledger_names_the_task_operation():
    f = holders_from_task(outcome(
        {"parties": [party("Warner Chappell")], "one_stop": None, "notes": ""},
        basis=BASIS, from_cache=True), "composition")
    assert f.ledger[0] == "Parallel Task — rights holders (composition)"
    assert "cached" in f.ledger[1]


# --- the consistency layer over holder facts (pipeline/consistency.py) ------------

def holder(name, share=None, role="publisher", conf=Confidence.MEDIUM):
    from schemas import ResearchedFact, RightsHolder
    return RightsHolder(name=ResearchedFact(value=name, confidence=conf, sources=[]),
                        role=role, share_percent=share)


def test_shares_past_100_open_a_question_and_cap():
    from pipeline.consistency import check_holders
    hs = [holder("A Corp", 60), holder("B Corp", 60)]
    qs = check_holders(hs, [], 1950)
    assert any(q.question_id == "consistency:holder_shares_exceed_100" for q in qs)
    assert all(h.name.confidence is Confidence.LOW for h in hs)


def test_conflicting_shares_for_one_party_surface_and_cap():
    from pipeline.consistency import check_holders
    hs = [holder("A Corp", 50), holder("a corp", 25)]
    check_holders(hs, [], 1950)
    assert hs[0].name.conflicting_values
    assert hs[0].name.confidence is Confidence.LOW


def test_publisher_founded_after_the_work_opens_a_question():
    from pipeline.consistency import check_holders
    hs = [holder("New Notes LLC")]
    raw = [{"name": "New Notes LLC", "role": "publisher", "is_administrator": False,
            "founded_year": 1998}]
    qs = check_holders(hs, raw, 1934)
    assert any(q.question_id == "consistency:publisher_postdates_work" for q in qs)
    assert hs[0].name.confidence is Confidence.LOW
    # an administrator postdating the work is normal (catalogs get bought)
    hs2 = [holder("Admin Co", role="administrator")]
    raw2 = [{"name": "Admin Co", "role": "administrator", "is_administrator": True,
             "founded_year": 1998}]
    assert not check_holders(hs2, raw2, 1934)
