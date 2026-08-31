"""Boundary tests. Run: python -m pytest rules/

Every check from the original print-style script is preserved with the same
label and the same expected value; each one is its own parametrized case so
pytest reports them individually.
"""

import pytest

from rules import (
    us_sound_recording, us_standard_term, life_plus_70, roll_up,
    status_to_verdict, eu_sound_recording,
)

Y = 2026


def _ids(cases):
    return [c[0] for c in cases]


# === US SOUND RECORDINGS (MMA / CLASSICS) ===================================

SR_CASES = [
    ("1922 -> PD (pre-1923)", lambda: us_sound_recording(1922, Y).status, "public_domain"),
    ("1925 -> PD in 2026",    lambda: us_sound_recording(1925, Y).status, "public_domain"),
    ("1925 expiry 2026",      lambda: us_sound_recording(1925, Y).expiry_year, 2026),
    ("1926 -> protected",     lambda: us_sound_recording(1926, Y).status, "protected"),
    ("1926 expiry 2027",      lambda: us_sound_recording(1926, Y).expiry_year, 2027),
    ("1928 -> protected",     lambda: us_sound_recording(1928, Y).status, "protected"),
    ("1928 expiry 2029",      lambda: us_sound_recording(1928, Y).expiry_year, 2029),
    ("1946 expiry 2047",      lambda: us_sound_recording(1946, Y).expiry_year, 2047),
    ("1947 expiry 2058",      lambda: us_sound_recording(1947, Y).expiry_year, 2058),
    ("1956 expiry 2067",      lambda: us_sound_recording(1956, Y).expiry_year, 2067),
    ("1960 expiry 2067",      lambda: us_sound_recording(1960, Y).expiry_year, 2067),
]


@pytest.mark.parametrize("label,got,want", SR_CASES, ids=_ids(SR_CASES))
def test_us_sound_recording(label, got, want):
    assert got() == want, label


# === ROLLING BOUNDARY (advances 1 Jan) =====================================

ROLLING_CASES = [
    ("1926 PD in 2027",        lambda: us_sound_recording(1926, 2027).status, "public_domain"),
    ("1927 protected in 2027", lambda: us_sound_recording(1927, 2027).status, "protected"),
]


@pytest.mark.parametrize("label,got,want", ROLLING_CASES, ids=_ids(ROLLING_CASES))
def test_rolling_boundary(label, got, want):
    assert got() == want, label


# === US PUBLISHED WORKS ====================================================

PUB_CASES = [
    ("1928 -> PD",             lambda: us_standard_term(1928, current_year=Y).status, "public_domain"),
    ("1928 expiry 2024",       lambda: us_standard_term(1928, current_year=Y).expiry_year, 2024),
    ("1930 -> PD",             lambda: us_standard_term(1930, current_year=Y).status, "public_domain"),
    ("1931 renewal unknown",   lambda: us_standard_term(1931, current_year=Y).status, "undetermined"),
    ("1931 blocked_by",        lambda: us_standard_term(1931, current_year=Y).blocked_by, "renewal_filed"),
    ("1955 not renewed -> PD", lambda: us_standard_term(1955, renewal_filed=False, current_year=Y).status, "public_domain"),
    ("1955 renewed -> prot.",  lambda: us_standard_term(1955, renewal_filed=True, current_year=Y).status, "protected"),
    ("1955 renewed exp 2051",  lambda: us_standard_term(1955, renewal_filed=True, current_year=Y).expiry_year, 2051),
    ("1970 -> protected",      lambda: us_standard_term(1970, current_year=Y).status, "protected"),
]


@pytest.mark.parametrize("label,got,want", PUB_CASES, ids=_ids(PUB_CASES))
def test_us_published_works(label, got, want):
    assert got() == want, label


# === LIFE + 70 =============================================================

LIFE_CASES = [
    ("d.1938,1965 -> protected", lambda: life_plus_70([1938, 1965], "EU", Y).status, "protected"),
    ("d.1938,1965 exp 2036",     lambda: life_plus_70([1938, 1965], "EU", Y).expiry_year, 2036),
    ("d.1924 -> PD",             lambda: life_plus_70([1924], "EU", Y).status, "public_domain"),
    ("unknown death -> undet.",  lambda: life_plus_70([1938, None], "EU", Y).status, "undetermined"),
]


@pytest.mark.parametrize("label,got,want", LIFE_CASES, ids=_ids(LIFE_CASES))
def test_life_plus_70(label, got, want):
    assert got() == want, label


# === WEST END BLUES — the spike's gate case ================================

def _west_end_blues():
    comp = us_standard_term(1928, current_year=Y)
    rec = us_sound_recording(1928, Y)
    verdict, blocking = roll_up([
        ("composition", status_to_verdict(comp.status), True),
        ("recording",   status_to_verdict(rec.status), True),
    ])
    return comp, rec, verdict, blocking


WEB_CASES = [
    ("composition PD",             lambda: _west_end_blues()[0].status, "public_domain"),
    ("composition exp 2024",       lambda: _west_end_blues()[0].expiry_year, 2024),
    ("recording protected",        lambda: _west_end_blues()[1].status, "protected"),
    ("recording exp 2029",         lambda: _west_end_blues()[1].expiry_year, 2029),
    ("roll-up = license_required", lambda: _west_end_blues()[2], "license_required"),
    ("blocking layer = recording", lambda: _west_end_blues()[3], "recording"),
]


@pytest.mark.parametrize("label,got,want", WEB_CASES, ids=_ids(WEB_CASES))
def test_west_end_blues(label, got, want):
    assert got() == want, label


# === EU / UK SOUND RECORDINGS (added Aug 26 for the jurisdiction matrix) ===

EU_SR_CASES = [
    ("1928 -> PD (50y, not revived)", lambda: eu_sound_recording(1928, "EU", Y).status, "public_domain"),
    ("1928 expiry 1979",              lambda: eu_sound_recording(1928, "EU", Y).expiry_year, 1979),
    ("1962 -> PD",                    lambda: eu_sound_recording(1962, "EU", Y).status, "public_domain"),
    ("1963 -> protected (extended)",  lambda: eu_sound_recording(1963, "EU", Y).status, "protected"),
    ("1963 expiry 2034",              lambda: eu_sound_recording(1963, "EU", Y).expiry_year, 2034),
    ("1955 UK rule id",               lambda: eu_sound_recording(1955, "UK", Y).rule_id, "uk_sr_pre_1963"),
    ("1970 UK rule id",               lambda: eu_sound_recording(1970, "UK", Y).rule_id, "uk_sr_70_from_publication"),
    ("1963 PD in 2034",               lambda: eu_sound_recording(1963, "EU", 2034).status, "public_domain"),
]


@pytest.mark.parametrize("label,got,want", EU_SR_CASES, ids=_ids(EU_SR_CASES))
def test_eu_sound_recording(label, got, want):
    assert got() == want, label


# === ROLL-UP EDGE CASES ====================================================

ROLLUP_CASES = [
    ("undetermined beats license",
     lambda: roll_up([("a", "undetermined", True), ("b", "license_required", True)])[0],
     "undetermined"),
    ("non-required excluded",
     lambda: roll_up([("a", "clear", True), ("b", "restricted", False)])[0],
     "clear"),
    ("re-record: comp only",
     lambda: roll_up([("composition", "clear", True), ("recording", "license_required", False)])[0],
     "clear"),
]


@pytest.mark.parametrize("label,got,want", ROLLUP_CASES, ids=_ids(ROLLUP_CASES))
def test_roll_up_edge_cases(label, got, want):
    assert got() == want, label


# --- the living floor (31 Aug): an author cannot die before the work existed ---

def test_life_plus_70_living_floor_protects_recent_works():
    from rules.terms import life_plus_70
    # 1999 work, no recorded death: death >= 1999, so protected until at least 2070
    r = life_plus_70([None], jurisdiction="UK", current_year=2026, work_year=1999)
    assert r.status == "protected" and r.expiry_year == 2070
    assert r.rule_id == "uk_life_plus_70_running"
    assert "at least" in r.explanation
    # one known death, one unknown: the unknown still floors the term forward
    r2 = life_plus_70([1990, None], jurisdiction="EU", current_year=2026, work_year=1999)
    assert r2.status == "protected" and r2.rule_id == "eu_life_plus_70_running"


def test_life_plus_70_old_work_with_unknown_death_still_blocks():
    from rules.terms import life_plus_70
    # 1940 work, unknown death: the floor (2011) has passed — genuinely unknown
    r = life_plus_70([None], jurisdiction="UK", current_year=2026, work_year=1940)
    assert r.status == "undetermined" and r.rule_id == "uk_death_year_unknown"
    # and with no work year at all, unchanged behaviour
    r2 = life_plus_70([None], jurisdiction="UK", current_year=2026)
    assert r2.status == "undetermined"


def test_life_plus_70_known_deaths_unchanged():
    from rules.terms import life_plus_70
    r = life_plus_70([1965], jurisdiction="UK", current_year=2026, work_year=1928)
    assert r.status == "protected" and r.expiry_year == 2036
