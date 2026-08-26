from types import SimpleNamespace

import pytest

from research import parallel_client as pc
from sources.cache import MemoryCache, set_default


@pytest.fixture
def cache():
    c = MemoryCache()
    set_default(c)
    yield c
    set_default(None)


class FakeSearchResult:
    def __init__(self, results):
        self._d = {"search_id": "search_1", "session_id": "s", "results": results}

    def model_dump(self):
        return self._d


class FakeClient:
    def __init__(self, results=None, raise_exc=None):
        self.calls = []
        self.results = results or []
        self.raise_exc = raise_exc
        self.task_run = SimpleNamespace(create=self._create, result=self._result)

    def search(self, **kw):
        self.calls.append(("search", kw))
        if self.raise_exc:
            raise self.raise_exc
        return FakeSearchResult(self.results)

    def _create(self, **kw):
        self.calls.append(("task.create", kw))
        return SimpleNamespace(run_id="trun_1")

    def _result(self, run_id, **kw):
        self.calls.append(("task.result", run_id))
        return SimpleNamespace(model_dump=lambda: {
            "run": {"run_id": run_id},
            "output": {"content": {"renewed": True},
                       "basis": [{"field": "renewed", "citations": [{"url": "https://x"}]}]},
        })


@pytest.fixture
def fake():
    client = FakeClient(results=[
        {"url": "https://archive.org/details/catalogofcopyrig3161libr", "title": "CCE 1962",
         "excerpts": ["BLUE MOON; w Lorenz Hart, m Richard Rodgers. R290000 ..."],
         "publish_date": None},
        {"url": "https://example.org/other", "title": None, "excerpts": []},
    ])
    pc.configure(client)
    yield client
    pc.configure(None)
    pc._client_checked = False


def test_search_calls_sdk_and_caches(cache, fake):
    out = pc.search("renewal?", ['"Blue Moon" renewal 1962'])
    assert out.ok and out.search_id == "search_1" and len(out.hits) == 2
    assert out.hits[0].title == "CCE 1962" and "R290000" in out.hits[0].excerpts[0]
    assert fake.calls[0][0] == "search"
    assert fake.calls[0][1]["search_queries"] == ['"Blue Moon" renewal 1962']
    assert fake.calls[0][1]["mode"] == "fast"
    out2 = pc.search("renewal?", ['"Blue Moon" renewal 1962'])
    assert out2.from_cache and len(out2.hits) == 2 and len(fake.calls) == 1


def test_search_without_key_fails_soft(cache):
    pc.configure(None)
    out = pc.search("q", ["a"])
    assert not out.ok and "PARALLEL_API_KEY" in out.error and out.hits == []
    pc._client_checked = False


def test_search_sdk_error_fails_soft(cache):
    pc.configure(FakeClient(raise_exc=RuntimeError("429 rate limited")))
    out = pc.search("q", ["a"])
    assert not out.ok and "429" in out.error
    pc.configure(None)
    pc._client_checked = False


def test_hit_source_builds_schema_source(cache, fake):
    out = pc.search("q", ["a"])
    s = pc.hit_source(out.hits[0], out)
    assert s.method.value == "parallel_search" and str(s.url).startswith("https://archive.org")
    assert s.excerpt and len(s.excerpt) <= 200


def test_run_task_returns_content_and_basis(cache, fake):
    out = pc.run_task({"title": "Blue Moon"}, {"type": "object"})
    assert out.ok and out.content == {"renewed": True} and out.basis[0]["field"] == "renewed"
    assert out.run_id == "trun_1"
    assert [c[0] for c in fake.calls] == ["task.create", "task.result"]
    assert fake.calls[0][1]["processor"] == "base-fast"
    again = pc.run_task({"title": "Blue Moon"}, {"type": "object"})
    assert again.from_cache and len(fake.calls) == 2


def test_run_task_refuses_pro_and_ultra(cache, fake):
    assert not pc.run_task("x", {}, processor="pro").ok
    assert not pc.run_task("x", {}, processor="ultra").ok
    assert fake.calls == []
