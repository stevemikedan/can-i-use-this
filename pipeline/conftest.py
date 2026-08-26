"""Reuse the sources/ fixtures (isolated cache, mock transport, no sleeping)."""

import pytest

from research import parallel_client as pc
from sources.conftest import cache, sleeps, transport  # noqa: F401  (pytest picks these up)


@pytest.fixture
def no_parallel():
    """Tier 3 unavailable — the degrade path."""
    pc.configure(None)
    yield
    pc._client_checked = False


@pytest.fixture
def fake_parallel():
    """Tier 3 available with canned hits."""
    class Result:
        def __init__(self, hits):
            self._d = {"search_id": "s1", "session_id": "x", "results": hits}

        def model_dump(self):
            return self._d

    class Client:
        def __init__(self):
            self.calls = []

        def search(self, **kw):
            self.calls.append(kw)
            return Result([
                {"url": "https://archive.org/details/cce-1962", "title": "CCE 1962 renewals",
                 "excerpts": ["BLUE MOON; w Lorenz Hart, m Richard Rodgers. R290123 12Jan62"]},
                {"url": "https://adp.library.ucsb.edu/x", "title": "DAHR", "excerpts": ["Victor 1961"]},
            ])

    c = Client()
    pc.configure(c)
    yield c
    pc.configure(None)
    pc._client_checked = False
