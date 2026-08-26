import httpx

from sources import http
from sources.http import as_source, get_json

URL = "https://musicbrainz.org/ws/2/recording/abc"


def ok(body):
    return lambda req: httpx.Response(200, json=body)


def test_success_is_cached_and_second_call_hits_cache(cache, transport):
    calls = transport(ok({"id": "abc"}))
    f1 = get_json(URL, {"inc": "work-rels"}, cache_key="k")
    f2 = get_json(URL, {"inc": "work-rels"}, cache_key="k")
    assert f1.ok and f1.data == {"id": "abc"} and not f1.from_cache and f1.attempts == 1
    assert f2.ok and f2.from_cache and f2.data == {"id": "abc"}
    assert len(calls) == 1
    assert calls[0].headers["User-Agent"].startswith("CanIUseThis/")
    assert "inc=work-rels" in f1.url


def test_503_then_200_retries_with_backoff(cache, transport, sleeps):
    responses = iter([httpx.Response(503, json={"error": "busy"}),
                      httpx.Response(200, json={"ok": 1})])
    calls = transport(lambda req: next(responses))
    f = get_json(URL, cache_key="k")
    assert f.ok and f.attempts == 2 and len(calls) == 2
    assert 1.0 in sleeps                       # first backoff = 1s
    assert cache.get("k").value == {"ok": 1}


def test_retry_after_header_is_honoured(cache, transport, sleeps):
    responses = iter([httpx.Response(503, headers={"Retry-After": "7"}),
                      httpx.Response(200, json={})])
    transport(lambda req: next(responses))
    assert get_json(URL, cache_key="k").ok
    assert 7.0 in sleeps


def test_exhausted_retries_fail_soft(cache, transport, sleeps):
    calls = transport(lambda req: httpx.Response(503))
    f = get_json(URL, cache_key="k", attempts=3)
    assert not f.ok and f.error == "http 503" and f.attempts == 3
    assert len(calls) == 3
    assert cache.get("k") is None
    assert [s for s in sleeps if s in (1.0, 2.0)] == [1.0, 2.0]


def test_404_is_not_retried_and_not_cached(cache, transport):
    calls = transport(lambda req: httpx.Response(404))
    f = get_json(URL, cache_key="k")
    assert not f.ok and f.error == "http 404" and len(calls) == 1
    assert cache.get("k") is None


def test_connection_error_fails_soft(cache, transport):
    def boom(req):
        raise httpx.ConnectError("reset by peer", request=req)
    calls = transport(boom)
    f = get_json(URL, cache_key="k")
    assert not f.ok and f.error.startswith("ConnectError") and len(calls) == 3


def test_invalid_json_fails_soft(cache, transport):
    transport(lambda req: httpx.Response(200, text="<html>busy</html>"))
    f = get_json(URL, cache_key="k")
    assert not f.ok and f.error.startswith("invalid JSON")
    assert cache.get("k") is None


def test_per_host_throttle_sleeps_between_live_calls(cache, transport, sleeps, monkeypatch):
    monkeypatch.setitem(http.MIN_INTERVAL_S, "musicbrainz.org", 0.5)
    transport(ok({}))
    get_json(URL, cache_key="a")
    get_json(URL, cache_key="b")
    get_json(URL, cache_key="b")            # cache hit: no throttle, no sleep
    throttle_sleeps = [s for s in sleeps if 0 < s <= 0.5]
    assert len(throttle_sleeps) == 1


def test_max_age_forces_refetch(cache, transport, monkeypatch):
    from sources import cache as cache_mod
    calls = transport(ok({"v": 1}))
    monkeypatch.setattr(cache_mod.time, "time", lambda: 1000.0)
    get_json(URL, cache_key="k")
    monkeypatch.setattr(cache_mod.time, "time", lambda: 1000.0 + 10 * 86400)
    get_json(URL, cache_key="k", max_age_s=7 * 86400)
    assert len(calls) == 2


def test_as_source_builds_schema_source(cache, transport):
    transport(ok({}))
    f = get_json(URL, cache_key="k")
    s = as_source(f, "MusicBrainz", authoritative=False, excerpt="x")
    assert s.name == "MusicBrainz" and str(s.url) == f.url
    assert s.method.value == "direct_api" and s.retrieved_at == f.retrieved_at
