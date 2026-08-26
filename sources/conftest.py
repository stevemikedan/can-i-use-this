"""Shared fixtures: isolated in-memory cache, mock HTTP transport, no sleeping."""

import httpx
import pytest

from sources import http
from sources.cache import MemoryCache, set_default


@pytest.fixture
def cache():
    c = MemoryCache()
    set_default(c)
    yield c
    set_default(None)


@pytest.fixture
def sleeps():
    """Records requested sleep durations instead of sleeping."""
    calls: list[float] = []
    return calls


@pytest.fixture
def transport(sleeps):
    """
    Returns install(handler) -> calls list. handler(request) -> httpx.Response.
    Every request is appended to calls for assertions.
    """
    calls: list[httpx.Request] = []

    def install(handler):
        def wrapped(request):
            calls.append(request)
            return handler(request)
        http.configure(client=httpx.Client(transport=httpx.MockTransport(wrapped)),
                       sleep=sleeps.append)
        return calls

    yield install
    http.configure(client=httpx.Client(), sleep=lambda s: None)
    http._last_call.clear()
