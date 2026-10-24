"""aivoa-rca backend package.

Layout:
  main.py      FastAPI app, CORS, lifespan, /api/health
  config.py    environment configuration (secrets only from backend/.env)
  database.py  engine/session/Base (SQLAlchemy 2.x)
  models.py    ORM tables: investigations, audit_logs
  schemas.py   Pydantic v2 models (request/response contracts)
  routers/     HTTP endpoints
  ai/          Groq client, evidence verification, LangGraph workflow
  utils/       document parsing, audit diffs, misc helpers
"""
