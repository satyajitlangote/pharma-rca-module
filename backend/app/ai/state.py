"""RCAState: the shared state of the LangGraph investigation workflow.

Graph (see app/ai/graph.py):

  START -> intake_extraction -> validate_extraction --(ok)--------------> five_whys
                                     |                 \--(fail, <=2 retries)--> intake_extraction
                                     \__(fail, retries exhausted)--> error_end -> END
                                     
  five_whys -> fishbone -> root_cause_synthesis -> evidence_gap_check
            -> capa_generation -> final_validation --(ok)-------------> END
                                            |          \--(fail, <=2 retries)--> capa_generation
                                            \__(retries exhausted)--> error_end -> END
"""
from __future__ import annotations

from typing import NotRequired, TypedDict

from app.schemas import AnalyzeRequest


class RCAState(TypedDict, total=False):
    # input
    raw_text: str
    source_document_name: NotRequired[str | None]
    context: NotRequired[dict]                # current RCA form values (may be {})
    email_headers: NotRequired[dict]
    model: str                                # model actually used for this run

    # extraction
    extraction: NotRequired[dict]             # field -> {value, source_quote, confidence, ...}
    extraction_source: NotRequired[str]       # "llm" | "form"
    extraction_feedback: NotRequired[str | None]
    extraction_unverifiable: NotRequired[list[str]]

    # analysis outputs
    five_whys: NotRequired[list[dict]]
    fishbone: NotRequired[dict]               # {"factors": [...]}
    root_cause: NotRequired[dict]
    contributing_factors: NotRequired[list[dict]]
    missing_evidence: NotRequired[list[dict]]
    capas: NotRequired[list[dict]]

    # control flow
    validation_error: NotRequired[str | None]
    final_validation_error: NotRequired[str | None]
    retries: NotRequired[dict[str, int]]
    errors: NotRequired[list[str]]
    warnings: NotRequired[list[str]]
    steps: NotRequired[list[dict]]            # {node, model, timestamp, details}


def build_initial_state(req: AnalyzeRequest, model: str) -> RCAState:
    """Initial state for one analysis run (all empty containers pre-set)."""
    return RCAState(
        raw_text=req.source_text,
        source_document_name=req.source_document_name,
        context=dict(req.context or {}),
        model=model,
        extraction={},
        extraction_source="llm",  # intake node switches to "form" when context is present
        extraction_feedback=None,
        extraction_unverifiable=[],
        five_whys=[],
        fishbone={"factors": []},
        root_cause={},
        contributing_factors=[],
        missing_evidence=[],
        capas=[],
        validation_error=None,
        final_validation_error=None,
        retries={},
        errors=[],
        warnings=[],
        steps=[],
    )
