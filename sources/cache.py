"""
Persistent cache for Tier 2 responses.

PROJECT.md §4.6: recording selection costs 7-19 MusicBrainz calls at 1 req/s,
so the cache is the latency fix, not an optimization. Every Tier 2 response
is stored indefinitely, keyed by a stable string ("mb:recording:{mbid}:...").
Callers may pass max_age_s to treat old entries as misses (search results).

Backends share one tiny interface so the local SQLite file used during the
build can be swapped for Firestore on Cloud Run without touching callers:

    CACHE_BACKEND=sqlite     (default)  CACHE_PATH=.cache/tier2.sqlite
    CACHE_BACKEND=firestore             CACHE_COLLECTION=tier2_cache
    CACHE_BACKEND=memory                (tests)
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional, Protocol

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SQLITE_PATH = os.path.join(REPO_ROOT, ".cache", "tier2.sqlite")


@dataclass
class Entry:
    value: Any
    fetched_at: float  # unix epoch seconds

    def age_s(self, now: Optional[float] = None) -> float:
        return (now if now is not None else time.time()) - self.fetched_at


class Cache(Protocol):
    def get(self, key: str, max_age_s: Optional[float] = None) -> Optional[Entry]: ...
    def set(self, key: str, value: Any) -> None: ...
    def stats(self) -> dict: ...


def _fresh(entry: Optional[Entry], max_age_s: Optional[float]) -> Optional[Entry]:
    if entry is None:
        return None
    if max_age_s is not None and entry.age_s() > max_age_s:
        return None
    return entry


class MemoryCache:
    """In-process dict. For tests and one-off scripts."""

    def __init__(self) -> None:
        self._d: dict[str, Entry] = {}

    def get(self, key: str, max_age_s: Optional[float] = None) -> Optional[Entry]:
        return _fresh(self._d.get(key), max_age_s)

    def set(self, key: str, value: Any) -> None:
        self._d[key] = Entry(value, time.time())

    def stats(self) -> dict:
        return {"backend": "memory", "entries": len(self._d)}


class SqliteCache:
    """One file, one table, WAL mode. Thread-safe via a lock."""

    def __init__(self, path: str = DEFAULT_SQLITE_PATH) -> None:
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS cache ("
            " key TEXT PRIMARY KEY, value TEXT NOT NULL, fetched_at REAL NOT NULL)"
        )
        self._conn.commit()

    def get(self, key: str, max_age_s: Optional[float] = None) -> Optional[Entry]:
        with self._lock:
            row = self._conn.execute(
                "SELECT value, fetched_at FROM cache WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        return _fresh(Entry(json.loads(row[0]), row[1]), max_age_s)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO cache (key, value, fetched_at) VALUES (?, ?, ?)",
                (key, json.dumps(value, ensure_ascii=False), time.time()),
            )
            self._conn.commit()

    def stats(self) -> dict:
        with self._lock:
            n, size = self._conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(LENGTH(value)), 0) FROM cache"
            ).fetchone()
            by_prefix = self._conn.execute(
                "SELECT substr(key, 1, instr(key || ':', ':') - 1), COUNT(*) "
                "FROM cache GROUP BY 1 ORDER BY 2 DESC"
            ).fetchall()
        return {"backend": "sqlite", "path": self.path, "entries": n,
                "bytes": size, "by_prefix": dict(by_prefix)}


class FirestoreCache:
    """
    Firestore backend for Cloud Run. Same interface. Document id is a hash of
    the key (Firestore ids can't contain '/'); the key is stored in the doc.

    Requires google-cloud-firestore and credentials: ADC locally, the runtime
    service account (roles/datastore.user) on Cloud Run. /api/health probes it
    with a real write and read; deploy/deploy.sh checks that on every deploy.
    """

    def __init__(self, collection: str = "tier2_cache", project: Optional[str] = None) -> None:
        from google.cloud import firestore  # lazy: optional dependency

        self._db = firestore.Client(project=project)
        self._col = self._db.collection(collection)
        self.collection = collection

    @staticmethod
    def _doc_id(key: str) -> str:
        return hashlib.sha1(key.encode("utf-8")).hexdigest()

    def get(self, key: str, max_age_s: Optional[float] = None) -> Optional[Entry]:
        snap = self._col.document(self._doc_id(key)).get()
        if not snap.exists:
            return None
        d = snap.to_dict()
        return _fresh(Entry(json.loads(d["value"]), d["fetched_at"]), max_age_s)

    def set(self, key: str, value: Any) -> None:
        self._col.document(self._doc_id(key)).set({
            "key": key,
            "value": json.dumps(value, ensure_ascii=False),
            "fetched_at": time.time(),
        })

    def stats(self) -> dict:
        out = {"backend": "firestore", "collection": self.collection}
        try:                                   # aggregation count: one read, proves the collection is live
            out["entries"] = int(self._col.count().get()[0][0].value)
        except Exception as e:                 # older client library or missing permission
            out["entries_error"] = f"{type(e).__name__}: {e}"
        return out


_default: Optional[Cache] = None
_default_lock = threading.Lock()


def get_cache() -> Cache:
    """Process-wide default, chosen by CACHE_BACKEND."""
    global _default
    with _default_lock:
        if _default is None:
            backend = os.environ.get("CACHE_BACKEND", "sqlite").lower()
            if backend == "memory":
                _default = MemoryCache()
            elif backend == "firestore":
                _default = FirestoreCache(
                    collection=os.environ.get("CACHE_COLLECTION", "tier2_cache"),
                    project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
                )
            else:
                _default = SqliteCache(os.environ.get("CACHE_PATH", DEFAULT_SQLITE_PATH))
        return _default


def set_default(cache: Optional[Cache]) -> None:
    """Override the process default (tests)."""
    global _default
    with _default_lock:
        _default = cache


if __name__ == "__main__":
    print(json.dumps(get_cache().stats(), indent=2))
