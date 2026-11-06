"""wiki_ingest waits for the per-space lock (Aldeia-IT/aldeia-box#1483 C2, D2, AC2).

The lock is the real ``space_ingest_lock`` (fcntl.flock on a file in a temp
``WIKI_LOCK_DIR``): two opens of the lock file contend even inside one process,
so threads stand in for concurrent callers. Anytype and the ingest body are
fakes; nothing here reaches a live service.
"""

import threading
import time

import pytest

SPACE = "space-lock-wait-001"


class _FakeClient:
    def close(self):
        pass


@pytest.fixture
def fake_ingest(monkeypatch, tmp_path):
    """Run wiki_ingest with a fake client and a fake ``_run_ingest`` body.

    Returns a dict the body records into: ``inside`` (callers in the body now),
    ``max_inside`` and ``runs``. ``hold`` sets how long the body takes.
    """
    import anytype_llm_wiki.wiki.ingest as _ingest
    import anytype_llm_wiki.wiki.remember as _remember
    from anytype_llm_wiki.wiki import types_schema

    monkeypatch.setenv("WIKI_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.delenv("WIKI_EXTRACT_ENDPOINT", raising=False)
    monkeypatch.delenv("WIKI_INGEST_LOCK_WAIT_S", raising=False)
    monkeypatch.setattr(_ingest, "WikiClient", _FakeClient)
    monkeypatch.setattr(
        _ingest._bootstrap,
        "_read_schema_version",
        lambda client, space_id: types_schema.WIKI_SCHEMA_VERSION,
    )
    monkeypatch.setattr(_remember, "_drain_pending", lambda *a, **k: None)
    monkeypatch.setattr(_ingest, "INGEST_LOCK_POLL_S", 0.02, raising=False)

    state = {"inside": 0, "max_inside": 0, "runs": [], "hold": 0.0}
    guard = threading.Lock()

    def fake_run(client, source, space_id, domain_hint, schema_warnings, subject_hint=None):
        with guard:
            state["inside"] += 1
            state["max_inside"] = max(state["max_inside"], state["inside"])
        time.sleep(state["hold"])
        with guard:
            state["inside"] -= 1
            state["runs"].append(source)
        return {"status": "ok", "source": source, "warnings": []}

    monkeypatch.setattr(_ingest, "_run_ingest", fake_run)
    return state


def _hold_lock(seconds: float, acquired: threading.Event):
    from anytype_llm_wiki.wiki.util import space_ingest_lock

    with space_ingest_lock(SPACE, "holder"):
        acquired.set()
        time.sleep(seconds)


def _ingest(source: str) -> dict:
    from anytype_llm_wiki.wiki.ingest import wiki_ingest

    return wiki_ingest(source=source, space_id=SPACE)


class TestLockWait:
    def test_waits_past_the_old_budget_then_runs(self, fake_ingest, monkeypatch):
        """The holder keeps the lock 3 s, past the old ~2.4 s retry budget; the
        waiting ingest then runs and returns its own result."""
        monkeypatch.setenv("WIKI_INGEST_LOCK_WAIT_S", "30")
        acquired = threading.Event()
        holder = threading.Thread(target=_hold_lock, args=(3.0, acquired))
        holder.start()
        assert acquired.wait(5)
        started = time.monotonic()
        result = _ingest("https://example.org/waiter")
        waited = time.monotonic() - started
        holder.join()
        assert result == {"status": "ok", "source": "https://example.org/waiter", "warnings": []}
        assert waited >= 2.5, waited

    def test_timeout_returns_ingest_in_progress(self, fake_ingest, monkeypatch):
        monkeypatch.setenv("WIKI_INGEST_LOCK_WAIT_S", "0.5")
        acquired = threading.Event()
        holder = threading.Thread(target=_hold_lock, args=(1.2, acquired))
        holder.start()
        assert acquired.wait(5)
        started = time.monotonic()
        result = _ingest("https://example.org/late")
        waited = time.monotonic() - started
        holder.join()
        assert result["status"] == "error"
        assert result["error"].startswith("[DATA ERROR] ingest_in_progress"), result
        assert "0.5 s wait (WIKI_INGEST_LOCK_WAIT_S)" in result["error"]
        assert 0.4 <= waited < 2.0, waited
        assert fake_ingest["runs"] == [], "the ingest body never ran"


class TestConcurrentIngestsAllComplete:
    def test_n_concurrent_ingests_all_complete_serialized(self, fake_ingest):
        """AC2: five ingests of one space at once, each 0.8 s long (4 s in all,
        past the old 2.4 s budget): every caller gets its own ok result, no
        ingest_in_progress, and the lock lets only one body run at a time."""
        fake_ingest["hold"] = 0.8
        sources = [f"https://example.org/page-{i}" for i in range(5)]
        results: dict[str, dict] = {}

        def call(src):
            results[src] = _ingest(src)

        threads = [threading.Thread(target=call, args=(s,)) for s in sources]
        for t in threads:
            t.start()
        for t in threads:
            t.join(60)
        assert sorted(results) == sorted(sources)
        for src, result in results.items():
            assert "ingest_in_progress" not in str(result), result
            assert result["status"] == "ok" and result["source"] == src
        assert sorted(fake_ingest["runs"]) == sorted(sources)
        assert fake_ingest["max_inside"] == 1


class TestWaitConfig:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [(None, 1800.0), ("60", 60.0), ("0", 0.0), ("-5", 1800.0), ("abc", 1800.0),
         ("nan", 1800.0), ("inf", 1800.0)],
    )
    def test_ingest_lock_wait_s(self, monkeypatch, raw, expected):
        from anytype_llm_wiki.wiki import config

        if raw is None:
            monkeypatch.delenv("WIKI_INGEST_LOCK_WAIT_S", raising=False)
        else:
            monkeypatch.setenv("WIKI_INGEST_LOCK_WAIT_S", raw)
        assert config.ingest_lock_wait_s() == expected

    def test_attempts_span_the_wait(self):
        from anytype_llm_wiki.wiki.ingest import INGEST_LOCK_POLL_S, _lock_wait_attempts

        assert _lock_wait_attempts(0) == 1
        assert (_lock_wait_attempts(1800) - 1) * INGEST_LOCK_POLL_S == pytest.approx(1800)
