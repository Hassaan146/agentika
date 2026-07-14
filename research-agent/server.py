"""FastAPI wrapper for the Agentika web frontend.

Serves the single-page UI (web/index.html) at "/" and exposes one chat
endpoint. One Agent instance = one session memory, same as the CLI.

Error policy: internals (exception types, stack traces) are logged server-side
only; the client receives {kind, title, reply} with a friendly, actionable
message so limit hits never surface as raw exception names.

Run: uvicorn server:app --port 8010
"""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from groq import APIConnectionError, APIStatusError, RateLimitError
from pydantic import BaseModel

from config import settings
from main import build

settings.require_keys()

logger = logging.getLogger("agentika")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Agentika")
agent, metrics = build()

WEB_DIR = Path(__file__).resolve().parent / "web"


class ChatRequest(BaseModel):
    message: str


def _ok(reply: str) -> dict:
    return {"kind": "ok", "reply": reply}


def _err(title: str, reply: str) -> dict:
    return {"kind": "error", "title": title, "reply": reply}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/icon.svg")
def icon() -> FileResponse:
    return FileResponse(WEB_DIR / "icon.svg", media_type="image/svg+xml")


@app.post("/api/chat")
def chat(req: ChatRequest) -> dict:
    message = req.message.strip()
    if not message:
        return _err("Empty question", "Please type a question first.")
    try:
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
                "This conversation grew past the model's size limit. "
                "Refresh the page to start a fresh session.",
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
