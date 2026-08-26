from sources import cache as cache_mod
from sources.cache import MemoryCache, SqliteCache


def test_sqlite_roundtrip(tmp_path):
    c = SqliteCache(str(tmp_path / "t.sqlite"))
    assert c.get("mb:x") is None
    c.set("mb:x", {"a": [1, 2, {"b": "ü"}]})
    e = c.get("mb:x")
    assert e.value == {"a": [1, 2, {"b": "ü"}]}
    assert e.age_s() < 5


def test_sqlite_overwrite_and_stats(tmp_path):
    c = SqliteCache(str(tmp_path / "t.sqlite"))
    c.set("mb:1", 1)
    c.set("mb:1", 2)
    c.set("wd:1", "x")
    assert c.get("mb:1").value == 2
    s = c.stats()
    assert s["entries"] == 2
    assert s["by_prefix"] == {"mb": 1, "wd": 1}


def test_max_age_turns_old_entries_into_misses(tmp_path, monkeypatch):
    c = SqliteCache(str(tmp_path / "t.sqlite"))
    monkeypatch.setattr(cache_mod.time, "time", lambda: 1_000.0)
    c.set("k", "v")
    monkeypatch.setattr(cache_mod.time, "time", lambda: 1_000.0 + 3600)
    assert c.get("k") is not None                 # no max_age: still there
    assert c.get("k", max_age_s=7200) is not None
    assert c.get("k", max_age_s=60) is None


def test_memory_cache():
    c = MemoryCache()
    c.set("a", {"x": 1})
    assert c.get("a").value == {"x": 1}
    assert c.get("b") is None
    assert c.stats()["entries"] == 1


def test_sqlite_survives_reopen(tmp_path):
    path = str(tmp_path / "t.sqlite")
    SqliteCache(path).set("k", [1, 2, 3])
    assert SqliteCache(path).get("k").value == [1, 2, 3]
