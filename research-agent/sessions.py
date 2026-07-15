"""Per-session agent storage and a small rate limiter for the web server.

Why this exists: the CLI is one process = one user, but the FastAPI server can
be opened by anyone and serves requests concurrently (FastAPI runs the sync
endpoint in a threadpool). A single shared Agent would mean (a) every visitor
shares one memory/conversation, and (b) two overlapping requests corrupting the
same `history`/`turn`. This module gives each session its own Agent, expires
idle ones (bounding memory growth), and serialises requests within a session.

No external dependencies - a lock-guarded dict with monotonic-clock TTL and a
token-bucket limiter are enough at this scale.
"""

import threading
import time
from collections.abc import Callable

from agent import Agent


class SessionManager:
    """Maps a session id -> its own Agent, with idle-TTL eviction and a cap.

    Each entry also carries a per-session lock so two overlapping requests on
    the *same* session serialise (no interleaved turns / corrupted history),
    while different sessions still run in parallel.
    """

    def __init__(self, agent_factory: Callable[[], Agent], ttl_seconds: int, max_sessions: int) -> None:
        self._factory = agent_factory
        self._ttl = ttl_seconds
        self._max = max_sessions
        self._lock = threading.Lock()  # guards the _sessions map only (never held during a turn)
        self._sessions: dict[str, list] = {}  # sid -> [agent, last_used_monotonic, session_lock]

    def get(self, sid: str) -> tuple[Agent, threading.Lock]:
        now = time.monotonic()
        with self._lock:
            entry = self._sessions.get(sid)
            if entry is None:
                self._expire_locked(now)  # reclaim idle slots before creating
                entry = [self._factory(), now, threading.Lock()]
                self._sessions[sid] = entry
                self._enforce_cap_locked()  # cap includes the entry just added
            else:
                entry[1] = now
            return entry[0], entry[2]

    def drop(self, sid: str) -> None:
        with self._lock:
            self._sessions.pop(sid, None)

    def count(self) -> int:
        with self._lock:
            return len(self._sessions)

    def _expire_locked(self, now: float) -> None:
        """Drop sessions idle longer than the TTL (frees memory in a long-lived
        process; also bounds the per-session history leak)."""
        expired = [sid for sid, e in self._sessions.items() if now - e[1] > self._ttl]
        for sid in expired:
            del self._sessions[sid]

    def _enforce_cap_locked(self) -> None:
        """Keep at most `max_sessions`, dropping the least-recently-used first."""
        if len(self._sessions) <= self._max:
            return
        ordered = sorted(self._sessions.items(), key=lambda kv: kv[1][1])
        for sid, _ in ordered[: len(self._sessions) - self._max]:
            del self._sessions[sid]


class RateLimiter:
    """Per-key (per-IP) token bucket: `capacity` requests, refilled steadily.

    The client-side 3,000-char cap and UI throttle are UX only - a direct curl
    bypasses them - so cost/DoS control has to live server-side.
    """

    def __init__(self, per_min: int) -> None:
        self._capacity = float(per_min)
        self._refill_per_sec = per_min / 60.0
        self._lock = threading.Lock()
        self._buckets: dict[str, tuple[float, float]] = {}  # key -> (tokens, last_monotonic)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            tokens, last = self._buckets.get(key, (self._capacity, now))
            tokens = min(self._capacity, tokens + (now - last) * self._refill_per_sec)
            if tokens < 1.0:
                self._buckets[key] = (tokens, now)
                return False
            self._buckets[key] = (tokens - 1.0, now)
            return True
