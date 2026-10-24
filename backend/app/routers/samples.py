"""GET /api/samples — the bundled sample incident documents (Section 9).

IMPORTANT: samples are ONLY used to fill the AI panel input box on an explicit
"user clicked Load sample" request. They are never a fallback for extraction or
analysis output anywhere in the system.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.utils.documents import DocumentError, parse_email_bytes, parse_pdf

router = APIRouter()

# backend/app/routers/samples.py -> repo root / sample_data
SAMPLES_DIR = Path(__file__).resolve().parents[3] / "sample_data"

_SPECS: list[dict] = [
    {
        "id": "oos",
        "filename": "oos_impurity_valsartan.txt",
        "kind": "text",
        "tab": "text",
        "label": "OOS impurity — Valsartan API",
        "description": "Complete OOS deviation with BMR, SCADA, maintenance, calibration and interview evidence.",
    },
    {
        "id": "particulate",
        "filename": "particulate_contamination_metformin.eml",
        "kind": "email",
        "tab": "email",
        "label": "Foreign particulate — Metformin HCl API",
        "description": "Realistic .eml report of glass-like particles found during packing.",
    },
    {
        "id": "yield",
        "filename": "yield_drop_incident.pdf",
        "kind": "pdf",
        "tab": "text",
        "label": "Yield drop — Ibuprofen API (PDF)",
        "description": "Yield deviation served from a real PDF; text is extracted with pypdf.",
    },
    {
        "id": "incomplete",
        "filename": "incomplete_incident_notification.txt",
        "kind": "text",
        "tab": "text",
        "label": "Incomplete notification",
        "description": "Deliberately sparse document — proves 'Not stated in document' and missing-evidence behaviour.",
    },
]


class SampleOut(BaseModel):
    id: str
    filename: str
    kind: str
    tab: str          # AI panel tab this sample should fill: "text" | "email"
    label: str
    description: str
    text: str


def _text_for(spec: dict) -> str:
    path = SAMPLES_DIR / spec["filename"]
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Sample file missing: {spec['filename']}")
    data = path.read_bytes()
    try:
        if spec["kind"] == "pdf":
            return parse_pdf(data, spec["filename"], max_chars=10**9).text
        if spec["kind"] == "email":
            return parse_email_bytes(data, spec["filename"], max_chars=10**9).text
        return data.decode("utf-8", errors="replace")
    except DocumentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/samples", response_model=dict[str, list[SampleOut]])
def list_samples() -> dict[str, list[SampleOut]]:
    return {
        "samples": [
            SampleOut(**spec, text=_text_for(spec))  # pdf => live pypdf extraction
            for spec in _SPECS
        ]
    }
