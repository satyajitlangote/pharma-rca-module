"""Pytest configuration: isolated SQLite test DB + LLM mocking helpers.

The suite NEVER calls Groq: every test monkeypatches
`app.ai.groq_client.structured_call` (the single LLM entry point) or clears
the key to exercise the HTTP 503 "AI unavailable" contract.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

# Isolated SQLite test DB — MUST be set before app.config imports (env wins
# over backend/.env because load_dotenv uses override=False).
_TEST_DB = Path(os.environ.get("TEMP", ".")) / f"aivoa_rca_test_{uuid.uuid4().hex[:8]}.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

# --- source document used by the mocked-LLM tests ---------------------------
# Every "verbatim quote" in the mocks below is an exact substring of SOURCE;
# every fabricated quote/value deliberately is NOT.

SOURCE = """Incident Notification DEV-2026-014
Date: 2026-09-14
Product: Valsartan API USP
Batch: B-2026-118
Manufacturing stage: final drying
Equipment: Dryer DR-04

During HPLC release testing an out-of-specification impurity result of 0.42% was
detected against the ICH Q3A limit of 0.10%. The batch was moved to the quarantine
cage in Warehouse 2 on the same day.

Chromatographic review showed raised baseline noise. The dryer calibration was
overdue: the calibration certificate for DR-04 expired on 2026-08-31. The
maintenance log shows the heater element was replaced on 2026-09-01."""

VERBATIM = "During HPLC release testing an out-of-specification impurity result of 0.42% was"
FABRICATED_QUOTE = "The nitrogen purge valve failed at 02:40 on 2026-09-13"


@pytest.fixture(scope="session", autouse=True)
def _tables():
    """Fresh schema per test session (SQLite file in TEMP, never the dev DB)."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    engine.dispose()
    _TEST_DB.unlink(missing_ok=True)


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def ai_key(monkeypatch):
    """Pretend GROQ_API_KEY is configured (actual calls are mocked)."""
    from app.config import settings

    monkeypatch.setattr(settings, "groq_api_key", "test-key-not-real")


@pytest.fixture()
def no_ai_key(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "groq_api_key", "")


# --- LLM mock ---------------------------------------------------------------

def extraction_field(value=None, quote=None, confidence="High"):
    return {"value": value, "source_quote": quote, "confidence": confidence}


def clean_extraction():
    """All values really exist in SOURCE."""
    return {
        "deviation_reference": extraction_field("DEV-2026-014", "Incident Notification DEV-2026-014"),
        "title": extraction_field("out-of-specification impurity result", VERBATIM),
        "product_name": extraction_field("Valsartan API USP", "Product: Valsartan API USP"),
        "batch_number": extraction_field("B-2026-118", "Batch: B-2026-118"),
        "manufacturing_stage": extraction_field("final drying", "Manufacturing stage: final drying"),
        "equipment_or_area": extraction_field("Dryer DR-04", "Equipment: Dryer DR-04"),
        "incident_datetime": extraction_field("2026-09-14", "Date: 2026-09-14"),
        "reported_by": extraction_field(None),
        "severity_suggested": extraction_field(None),
        "description": extraction_field(VERBATIM, VERBATIM),
        "immediate_containment": extraction_field(
            "The batch was moved to the quarantine cage in Warehouse 2",
            "The batch was moved to the quarantine cage in Warehouse 2",
        ),
        "detected_by": extraction_field("During HPLC release testing", VERBATIM),
        "quantity_affected": extraction_field(None),
    }


def fabricated_extraction():
    """batch_number is fabricated (not in the document) + one fake quote."""
    fields = clean_extraction()
    fields["batch_number"] = extraction_field("B-2026-999", "Batch: B-2026-999")
    # value real but quote fabricated -> quote dropped, confidence downgraded
    fields["product_name"] = extraction_field(
        "Valsartan API USP", "NF-grade valsartan manufactured in Building 7", "High"
    )
    return fields


def sample_whys():
    """Step 1 supported (verbatim), steps 2-3 hypothesis (no/fake quote)."""
    return {
        "steps": [
            {"level": 1, "question": "Why was the batch OOS?",
             "answer": "An out-of-specification impurity result of 0.42% was found by HPLC release testing.",
             "evidence_quote": VERBATIM},
            {"level": 2, "question": "Why was the impurity elevated?",
             "answer": "The dryer calibration was overdue at the time of drying.",
             "evidence_quote": "The dryer calibration was overdue"},
            {"level": 3, "question": "Why was calibration overdue?",
             "answer": "The nitrogen purge valve failed at 02:40 and calibration was postponed.",
             "evidence_quote": FABRICATED_QUOTE},
        ]
    }


def sample_fishbone():
    return {
        "factors": [
            {"category": "Machine", "cause": "Dryer DR-04 calibration overdue",
             "subcauses": ["calibration certificate expired"], "impact": "Impure API",
             "evidence_quote": "the calibration certificate for DR-04 expired on 2026-08-31",
             "root_cause_candidate": True},
            {"category": "Measurement", "cause": "Baseline noise in HPLC",
             "subcauses": [], "impact": "Unclear integration",
             "evidence_quote": None, "root_cause_candidate": False},
        ]
    }


def sample_root_cause():
    return {
        "primary_root_cause": "Overdue calibration of Dryer DR-04 allowed drying outside qualified conditions.",
        "category": "Equipment/Metrology",
        "confidence": "High",
        "contributing_factors": [
            {"text": "Heater element was replaced shortly before the batch.",
             "category": "Equipment/Metrology",
             "evidence_quote": "The maintenance log shows the heater element was replaced on 2026-09-01"},
            {"text": "Nitrogen purge valve failure delayed calibration.",
             "category": "Equipment/Metrology",
             "evidence_quote": FABRICATED_QUOTE},
        ],
    }


def sample_gaps():
    """'Calibration records' are IN the document -> must be filtered out."""
    return {
        "mentioned": ["Calibration records"],
        "gaps": [
            {"item": "Calibration records", "why_needed": "to confirm due date",
             "suggested_action": "retrieve certificate", "priority": "High"},
            {"item": "HPLC audit trail", "why_needed": "to confirm injection sequence",
             "suggested_action": "export sequence data", "priority": "Medium"},
        ],
    }


def sample_capas(days=14):
    return {
        "capas": [
            {"type": "Corrective",
             "description": "Recalibrate Dryer DR-04 per SOP and verify against CAL-9981 before reuse.",
             "linked_cause": "Overdue calibration of Dryer DR-04",
             "rationale": "Calibration was overdue at the time of drying.",
             "owner_role": "Maintenance Lead", "department": "Engineering",
             "target_days_from_now": days,
             "voe_plan": "Review next 3 batches for impurity within limits."},
        ]
    }


@pytest.fixture()
def mock_llm(monkeypatch, ai_key):
    """Install a fake structured_call returning canned node outputs.

    Returns the list of node names called (so tests can assert call counts /
    retry behaviour).
    """
    def _install(extraction=None, whys=None, fishbone=None, root_cause=None,
                 gaps=None, capas=None):
        from app.schemas import (
            CapaResult, ExtractionResult, FiveWhysResult, FishboneResult,
            GapAnalysisResult, RootCauseSuggestion,
        )

        outputs = {
            ExtractionResult: extraction or clean_extraction(),
            FiveWhysResult: whys or sample_whys(),
            FishboneResult: fishbone or sample_fishbone(),
            RootCauseSuggestion: root_cause or sample_root_cause(),
            GapAnalysisResult: gaps or sample_gaps(),
            CapaResult: capas or sample_capas(),
        }
        calls: list[str] = []

        def fake_structured_call(schema, messages, *, model, temperature, node):
            calls.append(node)
            return schema.model_validate(outputs[schema])

        monkeypatch.setattr("app.ai.groq_client.structured_call", fake_structured_call)
        return calls

    return _install


def iter_sse(response):
    """Parse an httpx streaming response into SSE event dicts."""
    import json

    events = []
    for line in response.iter_lines():
        if line.startswith("data: "):
            payload = line[6:].strip()
            if payload:
                events.append(json.loads(payload))
    return events


def run_analysis(client, text=SOURCE, context=None):
    """POST /api/ai/analyze/stream and return the parsed SSE events."""
    with client.stream(
        "POST",
        "/api/ai/analyze/stream",
        json={"source_text": text, "context": context or {}},
    ) as response:
        assert response.status_code == 200, response.read()
        return iter_sse(response)


def run_graph(text=SOURCE, context=None):
    """Run the LangGraph pipeline directly -> deterministic final state.

    Used for assertions about post-processing (e.g. invented-ID redaction)
    where the SSE event ordering is intentionally concurrent.
    """
    import asyncio

    from app.ai.graph import graph
    from app.ai.groq_client import resolve_model
    from app.ai.state import build_initial_state
    from app.schemas import AnalyzeRequest

    req = AnalyzeRequest(source_text=text, context=context or {})
    state = build_initial_state(req, resolve_model(None))
    return asyncio.run(graph.ainvoke(state))


def today_plus(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()
