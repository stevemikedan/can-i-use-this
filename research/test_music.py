"""
Tier 3 music research helpers: which record system holds a renewal, and
which registration numbers count as renewal-style.
"""

import research.parallel_client as pc
from pipeline.mockworld import FakeParallel
from research.music import _R_NUMBER, renewal_record_system, renewal_numbers, search_renewal
from research.parallel_client import SearchHit, SearchOutcome
from sources.cache import MemoryCache, set_default


def test_record_system_by_window():
    # window = pub_year + 27 .. pub_year + 28; the online catalog starts at 1978
    assert renewal_record_system(1934) == "scans"     # 1961-1962
    assert renewal_record_system(1949) == "scans"     # 1976-1977
    assert renewal_record_system(1950) == "both"      # 1977-1978
    assert renewal_record_system(1951) == "online"    # 1978-1979
    assert renewal_record_system(1959) == "online"    # 1986-1987
    assert renewal_record_system(1963) == "online"    # 1990-1991


def test_renewal_numbers_pre_and_post_1978():
    def nums(text):
        return _R_NUMBER.findall(text)
    assert nums("BLUE MOON; R290123 12Jan62") == ["R290123"]
    assert nums("Renewal RE0000342857 received 1986") == ["RE0000342857"]
    assert nums("registered as RE 342-857") == ["RE 342-857"]
    assert nums("catalog no. R12 and page 1234567") == []        # too short / no prefix


def test_renewal_numbers_dedupe_across_hits():
    out = SearchOutcome("o", ["q"], hits=[
        SearchHit(url="https://a", title="a", excerpts=["R290123 and R290123"]),
        SearchHit(url="https://b", title="b", excerpts=["RE0000342857"]),
    ])
    assert renewal_numbers(out) == ["R290123", "RE0000342857"]


def test_online_window_search_targets_the_online_catalog():
    fake = FakeParallel()
    set_default(MemoryCache())
    pc.configure(fake)
    try:
        search_renewal("Take Five", ["Paul Desmond"], 1959)
        search_renewal("Blue Moon", ["Richard Rodgers"], 1934)
    finally:
        set_default(None)
        pc.configure(None)
        pc._client_checked = False
    online, scans = fake.calls
    assert "online public catalog" in online["objective"] and "RE" in online["objective"]
    assert any("copyright.gov" in q for q in online["search_queries"])
    assert "online public catalog" not in scans["objective"]
    assert any("Catalog of Copyright Entries" in q for q in scans["search_queries"])
