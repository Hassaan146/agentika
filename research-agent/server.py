"""FastAPI wrapper for the Agentika web frontend.

Serves the single-page UI (web/index.html) at "/" and exposes a chat endpoint.
Each browser session gets its **own** Agent (own memory + conversation), keyed
by a cookie; idle sessions expire (see sessions.py). Requests within a session
are serialised so concurrency can't corrupt one conversation's history.

Abuse controls: a server-side length cap on the message (the client maxlength is
UX only) and a per-IP rate limit.

Error policy: internals (exception types, stack traces) are logged server-side
only; the client receives {kind, title, reply} with a friendly, actionable
message so limit hits never surface as raw exception names.

Run: uvicorn server:app --port 8010
"""

import logging
import uuid
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse
from groq import APIConnectionError, APIStatusError, RateLimitError
from pydantic import BaseModel, Field

from config import settings
from main import build_agent, build_shared
from sessions import RateLimiter, SessionManager

logger = logging.getLogger("agentika")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Agentika")

# Shared (stateless) pieces built once; real Groq agents are built lazily per
# session so importing this module needs no API keys (unit tests rely on that).
_registry, metrics = build_shared()


def _default_agent_factory():
    settings.require_keys()  # validated on first real session, not at import
    return build_agent(_registry)


session_manager = SessionManager(_default_agent_factory, settings.session_ttl_seconds, settings.session_max)
rate_limiter = RateLimiter(settings.rate_limit_per_min)

WEB_DIR = Path(__file__).resolve().parent / "web"
SESSION_COOKIE = "agentika_sid"


class ChatRequest(BaseModel):
    # Server-side cap: a direct POST can be far larger than the UI allows.
    message: str = Field(..., max_length=settings.max_message_chars)


def _ok(reply: str) -> dict:
    return {"kind": "ok", "reply": reply}


def _err(title: str, reply: str) -> dict:
    return {"kind": "error", "title": title, "reply": reply}


def _session_id(request: Request, response: Response) -> str:
    """Read the session id from an explicit header or the cookie; mint one (and
    set the cookie) on first contact."""
    sid = request.headers.get("X-Session-Id") or request.cookies.get(SESSION_COOKIE)
    if not sid:
        sid = uuid.uuid4().hex
        response.set_cookie(
            SESSION_COOKIE, sid, httponly=True, samesite="lax", max_age=settings.session_ttl_seconds
        )
    return sid


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/icon.svg")
def icon() -> FileResponse:
    return FileResponse(WEB_DIR / "icon.svg", media_type="image/svg+xml")


@app.post("/api/new-session")
def new_session(request: Request, response: Response) -> dict:
    """Drop this browser's server-side session (memory + history) and issue a
    fresh id. Backs the 'New session' control in the UI."""
    old = request.headers.get("X-Session-Id") or request.cookies.get(SESSION_COOKIE)
    if old:
        session_manager.drop(old)
    sid = uuid.uuid4().hex
    response.set_cookie(
        SESSION_COOKIE, sid, httponly=True, samesite="lax", max_age=settings.session_ttl_seconds
    )
    return _ok("New session started.")


@app.post("/api/chat")
def chat(req: ChatRequest, request: Request, response: Response) -> dict:
    if not rate_limiter.allow(_client_ip(request)):
        return _err("Slow down", "Too many requests in a short time. Wait a few seconds and try again.")

    message = req.message.strip()
    if not message:
        return _err("Empty question", "Please type a question first.")

    sid = _session_id(request, response)
    agent, session_lock = session_manager.get(sid)
    try:
        with session_lock:  # serialise overlapping requests on this one session
            return _ok(agent.run_turn(message))
    except RateLimitError:
        logger.exception("Groq rate limit hit")
        return _err(
            "Limit reached",
            "The free-tier rate limit was hit. Wait a few seconds and ask again.",
        )
    except APIStatusError as exc:
        logger.exception("Groq API error (status %s)", exc.status_code)
        detail = str(exc).lower()
        if exc.status_code in (400, 413) and any(
            w in detail for w in ("large", "token", "context", "length")
        ):
            return _err(
                "Session limit reached",
                "This conversation grew past the model's size limit. Start a new session to continue.",
            )
        return _err(
            "Limit reached",
            "The research service refused this request. Try a shorter question, or wait a moment and retry.",
        )
    except APIConnectionError:
        logger.exception("Groq connection error")
        return _err(
            "Connection issue",
            "Could not reach the research service. Check the internet connection and retry.",
        )
    except Exception:
        logger.exception("Unhandled error in /api/chat")
        return _err(
            "Temporary hiccup", "Something unexpected happened. Please try again - the question was not lost."
        )
