"""SessionManager (per-session isolation, TTL, LRU cap) and RateLimiter tests."""

import time

from sessions import RateLimiter, SessionManager


def test_distinct_sessions_get_distinct_agents_same_session_reused():
    counter = {"n": 0}

    def factory():
        counter["n"] += 1
        return counter["n"]  # a unique sentinel per creation

    sm = SessionManager(factory, ttl_seconds=1000, max_sessions=10)
    a1, lock_a = sm.get("A")
    b1, _ = sm.get("B")
    a2, _ = sm.get("A")

    assert a1 != b1  # different sessions -> different agents (no shared memory)
    assert a1 == a2  # same session -> same agent reused
    assert sm.count() == 2


def test_idle_sessions_expire():
    sm = SessionManager(object, ttl_seconds=0, max_sessions=10)
    sm.get("A")
    time.sleep(0.01)
    sm.get("B")  # creating B expires the now-idle A
    assert sm.count() == 1


def test_lru_cap_drops_oldest():
    sm = SessionManager(object, ttl_seconds=1000, max_sessions=2)
    a_first, _ = sm.get("A")
    sm.get("B")
    sm.get("C")  # over cap -> LRU ("A") dropped
    assert sm.count() == 2
    a_again, _ = sm.get("A")  # recreated because it was evicted
    assert a_again is not a_first


def test_drop_removes_session():
    sm = SessionManager(object, ttl_seconds=1000, max_sessions=10)
    first, _ = sm.get("A")
    sm.drop("A")
    assert sm.count() == 0
    again, _ = sm.get("A")
    assert again is not first  # fresh agent after a drop (New session control)


def test_rate_limiter_throttles_after_capacity():
    rl = RateLimiter(per_min=3)
    results = [rl.allow("1.2.3.4") for _ in range(5)]
    assert results[:3] == [True, True, True]
    assert results[3] is False  # bucket empty -> throttled
    assert rl.allow("9.9.9.9") is True  # a different key has its own bucket
