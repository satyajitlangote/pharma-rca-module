"""FastAPI entrypoint for aivoa-rca.

Startup = FastAPI lifespan (not the removed on_event hooks): create tables and
verify connectivity. CORS only allows the configured frontend origins.
"""
from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone

# Windows only: run uvicorn on the selector event loop.
# The default ProactorEventLoop has a fatal race on this platform — when a
# client disconnects while accept() is pending (common right after a long SSE
# stream closes), the accept task dies with OSError WinError 64 unretrieved
# and uvicorn silently stops accepting connections while the process stays
# alive (zombie holding no socket). The selector loop catches
# ConnectionResetError during accept, so this failure class cannot happen.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

import app.models  # noqa: F401  (registers tables on Base.metadata)
from app.config import settings
from app.database import Base, engine
from app.schemas import HealthResponse


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Small deterministic schema created from models.py (no Alembic in this
    # module). Safe to run repeatedly.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="aivoa-rca",
    description="AI-powered Root Cause Analysis module for API manufacturing (ICH Q7 / GMP).",
    version="1.0.0",
    lifespan=lifespan,
)

# Explicit origins + regex for local dev servers on dynamic Vite ports.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness + truthful environment report.

    `dialect` is read from engine.dialect.name (the DB we are really using),
    `db_fallback` is derived from it, so the UI can never lie about the DB.
    """
    dialect = engine.dialect.name
    db_ok = True
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:  # pragma: no cover - reported, not raised
        db_ok = False

    return HealthResponse(
        status="ok" if db_ok else "degraded",
        dialect=dialect,
        db_fallback=dialect != "postgresql",  # sqlite dev fallback => visible warning
        db_ok=db_ok,
        groq_configured=settings.groq_configured,
        model=settings.default_model,
        server_time=datetime.now(timezone.utc),
    )


# --- Routers ---------------------------------------------------------------
from app.routers import ai, investigations, samples  # noqa: E402  (import after app creation)

app.include_router(ai.router)                 # /api/ai/* (step 2)
app.include_router(samples.router)            # /api/samples (step 3)
app.include_router(investigations.router)     # /api/investigations (step 4)
