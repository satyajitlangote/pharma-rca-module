"""Application configuration.

Rules:
  * Secrets (GROQ_API_KEY) live only here, in backend/.env — never in the
    frontend, localStorage, or any client-supplied request.
  * If DATABASE_URL is not set we use an EXPLICIT SQLite dev fallback and set
    db_fallback_sqlite=True so the UI can show a visible warning.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]  # .../backend

# Load backend/.env if present; real environment variables always win.
load_dotenv(BACKEND_DIR / ".env", override=False)

# The only models the client is allowed to request (allowlist).
# NOTE: the spec's original IDs (llama-3.3-70b-versatile, gemma2-9b-it) are kept
# for keys that have access to them, but this environment's Groq account only
# serves openai/gpt-oss-*, qwen/qwen3.8-27b and allam-2-7b (verified: tool
# calling works on gpt-oss-120b / gpt-oss-20b / qwen3.8-27b, NOT on allam-2-7b).
ALLOWED_AI_MODELS: tuple[str, ...] = (
    "openai/gpt-oss-20b",         # default — verified function calling
    "openai/gpt-oss-120b",        # larger sibling, same tool-calling support
    "qwen/qwen3.8-27b",
    "llama-3.3-70b-versatile",    # spec default (only if the key has access)
    "gemma2-9b-it",               # spec option (JSON-mode path)
)
DEFAULT_AI_MODEL = "openai/gpt-oss-20b"


class Settings:
    """Plain env-backed settings object (one instance: `settings`)."""

    def __init__(self) -> None:
        # --- Database -------------------------------------------------------
        self.database_url: str = os.getenv("DATABASE_URL", "").strip()
        self.db_fallback_sqlite: bool = not self.database_url
        if self.db_fallback_sqlite:
            # Explicit dev fallback only. UI shows a warning when active.
            db_path = (BACKEND_DIR / "aivoa_rca.db").as_posix()
            self.database_url = f"sqlite:///{db_path}"

        # --- AI -------------------------------------------------------------
        self.groq_api_key: str = os.getenv("GROQ_API_KEY", "").strip()
        requested = os.getenv("AI_MODEL", "").strip()
        self.default_model: str = requested if requested in ALLOWED_AI_MODELS else DEFAULT_AI_MODEL
        # Low temperatures for accuracy (principle #7).
        self.extraction_temperature: float = float(os.getenv("EXTRACTION_TEMPERATURE", "0"))
        self.analysis_temperature: float = float(os.getenv("ANALYSIS_TEMPERATURE", "0.1"))

        # --- HTTP -----------------------------------------------------------
        raw_origins = os.getenv(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        )
        self.cors_origins: list[str] = [o.strip() for o in raw_origins.split(",") if o.strip()]

        # --- Document limits ------------------------------------------------
        self.max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))
        self.max_text_chars: int = int(os.getenv("MAX_TEXT_CHARS", "60000"))

    @property
    def groq_configured(self) -> bool:
        return bool(self.groq_api_key)


settings = Settings()
