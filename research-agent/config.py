"""Central configuration.

All tunables live here; secrets come from .env (never committed).
Import `settings` everywhere; call `settings.require_keys()` once at startup
(main.py) so unit tests can run without any API keys.
"""

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


@dataclass
class Config:
    # Secrets (required at runtime, not for tests)
    groq_api_key: str = field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
    serpapi_api_key: str = field(default_factory=lambda: os.getenv("SERPAPI_API_KEY", ""))

    # Model & loop
    model: str = field(default_factory=lambda: os.getenv("MODEL", "llama-3.3-70b-versatile"))
    # Hard cost/latency ceiling per turn on a free-tier key; demo tasks need <=5 steps.
    max_steps: int = field(default_factory=lambda: int(os.getenv("MAX_STEPS", "8")))
    # Planner call knobs (kept here so behaviour is tunable, not buried in agent.py).
    planner_temperature: float = field(default_factory=lambda: float(os.getenv("PLANNER_TEMPERATURE", "0.2")))
    planner_max_tokens: int = field(default_factory=lambda: int(os.getenv("PLANNER_MAX_TOKENS", "1024")))
    # Memory-extraction call knobs (temperature 0 = deterministic fact JSON).
    extraction_temperature: float = field(
        default_factory=lambda: float(os.getenv("EXTRACTION_TEMPERATURE", "0.0"))
    )
    extraction_max_tokens: int = field(default_factory=lambda: int(os.getenv("EXTRACTION_MAX_TOKENS", "512")))

    # Memory
    memory_top_k: int = field(default_factory=lambda: int(os.getenv("MEMORY_TOP_K", "5")))
    # Max history messages sent per request - keeps long sessions under the
    # free-tier context/TPM limits; older turns survive as memory facts.
    history_max_messages: int = field(default_factory=lambda: int(os.getenv("HISTORY_MAX_MESSAGES", "30")))
    # Hard ceiling on stored history in a long-lived server process (a never-
    # restarted session would otherwise grow self.history without bound).
    history_hard_cap: int = field(default_factory=lambda: int(os.getenv("HISTORY_HARD_CAP", "200")))

    # Tools / HTTP
    search_count: int = field(default_factory=lambda: int(os.getenv("SEARCH_COUNT", "5")))
    fetch_max_chars: int = field(default_factory=lambda: int(os.getenv("FETCH_MAX_CHARS", "4000")))
    file_max_mb: float = field(default_factory=lambda: float(os.getenv("FILE_MAX_MB", "5")))
    file_max_chars: int = field(default_factory=lambda: int(os.getenv("FILE_MAX_CHARS", "8000")))
    http_timeout: int = field(default_factory=lambda: int(os.getenv("HTTP_TIMEOUT", "20")))
    http_max_redirects: int = field(default_factory=lambda: int(os.getenv("HTTP_MAX_REDIRECTS", "5")))
    retry_attempts: int = field(default_factory=lambda: int(os.getenv("RETRY_ATTEMPTS", "3")))
    retry_base_delay: float = field(default_factory=lambda: float(os.getenv("RETRY_BASE_DELAY", "1.0")))

    # Server (session scoping + abuse controls)
    max_message_chars: int = field(default_factory=lambda: int(os.getenv("MAX_MESSAGE_CHARS", "3000")))
    session_ttl_seconds: int = field(default_factory=lambda: int(os.getenv("SESSION_TTL_SECONDS", "1800")))
    session_max: int = field(default_factory=lambda: int(os.getenv("SESSION_MAX", "500")))
    rate_limit_per_min: int = field(default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_MIN", "30")))

    # Logging
    log_preview_chars: int = field(default_factory=lambda: int(os.getenv("LOG_PREVIEW_CHARS", "200")))

    # Paths
    docs_dir: Path = field(default_factory=lambda: BASE_DIR / "docs")
    log_path: Path = field(default_factory=lambda: BASE_DIR / "tool_calls.jsonl")

    def require_keys(self) -> None:
        missing = [
            name
            for name, value in (
                ("GROQ_API_KEY", self.groq_api_key),
                ("SERPAPI_API_KEY", self.serpapi_api_key),
            )
            if not value
        ]
        if missing:
            sys.exit(f"Missing {', '.join(missing)} - copy .env.example to .env and fill in your keys.")


settings = Config()
