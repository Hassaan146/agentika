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

    # Memory
    memory_top_k: int = field(default_factory=lambda: int(os.getenv("MEMORY_TOP_K", "5")))
    # Max history messages sent per request - keeps long sessions under the
    # free-tier context/TPM limits; older turns survive as memory facts.
    history_max_messages: int = field(default_factory=lambda: int(os.getenv("HISTORY_MAX_MESSAGES", "30")))

    # Tools
    search_count: int = field(default_factory=lambda: int(os.getenv("SEARCH_COUNT", "5")))
    fetch_max_chars: int = field(default_factory=lambda: int(os.getenv("FETCH_MAX_CHARS", "4000")))
    file_max_mb: float = field(default_factory=lambda: float(os.getenv("FILE_MAX_MB", "5")))
    file_max_chars: int = field(default_factory=lambda: int(os.getenv("FILE_MAX_CHARS", "8000")))

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
