"""LangGraph nodes for the RCA investigation workflow.

Every node:
  * emits a "started" SSE event (via the queue passed in run config),
  * does its work through `groq_client.structured_call` (the only LLM entry),
  * returns a partial state update which `graph.astream` turns into a
    "completed" SSE event carrying that partial result.

Evidence rules live in code, not in the model:
  * 5-Whys status      -> app/utils/evidence.py (Supported | Hypothesis),
  * fishbone support   -> quote verification -> "Needs investigation",
  * root cause justification/confidence adjusted by verified-step ratio,
  * gaps filtered against code-detected evidence mentions,
  * CAPA target dates computed from the REAL current date,
  * invented record IDs are redacted in final_validation.
"""
from __future__ import annotations

import copy
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.ai import extraction as extraction_mod
from app.ai import domain, groq_client, prompts
from app.ai.state import RCAState
from app.config import settings
from app.schemas import (
    CapaResult,
    FiveWhysResult,
    FishboneResult,
    GapAnalysisResult,
    RootCauseSuggestion,
)
from app.utils.evidence import normalize, quote_in_text

ANALYSIS_TEMP = settings.analysis_temperature


# --- small helpers ---------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex[:10]


def _step(state: RCAState, node: str, details: str, model: str | None) -> list[dict]:
    """Append the step record used by the SSE 'completed' event payload."""
    steps = list(state.get("steps") or [])
    steps.append({"node": node, "model": model, "timestamp": _now(), "details": details})
    return steps


def _emit_started(config: RunnableConfig | None, node: str, model: str | None, details: str) -> None:
    """Push a 'started' event to the SSE queue (set by routers/ai.py)."""
    queue = ((config or {}).get("configurable") or {}).get("node_queue")
    if queue is None:
        return
    queue.put_nowait({
        "kind": "node_started",
        "event": {
            "node": node, "status": "started", "details": details,
            "model": model, "timestamp": _now(), "partial_result": None, "error": None,
        },
    })


# --- 1) intake_extraction ---------------------------------------------------

async def intake_extraction(state: RCAState, config: RunnableConfig) -> dict:
    model = state.get("model") or settings.default_model
    _emit_started(config, "intake_extraction", model, "Extracting structured fields from the document")

    context = state.get("context") or {}
    if any(v for v in context.values()):
        # The user already applied an extraction to the form: reuse it (human-owned).
        fields = extraction_mod.fields_from_context(context)
        source, used_model = "form", None
        details = f"Reused {sum(1 for f in fields.values() if f.value)} applied form fields (no re-extraction)"
        unverifiable: list[str] = []
    else:
        result = await extraction_mod.run_extraction_async(
            state.get("raw_text", ""),
            state.get("email_headers") or {},
            model,
            state.get("extraction_feedback"),
        )
        fields, unverifiable = extraction_mod.verify_extraction(result, state.get("raw_text", ""))
        source, used_model = "llm", model
        stated = sum(1 for f in fields.values() if f.value)
        details = f"Extracted {stated}/{len(fields)} fields stated in the document"

    return {
        "extraction": extraction_mod.fields_to_dicts(fields),
        "extraction_source": source,
        "extraction_unverifiable": unverifiable,
        "extraction_feedback": None,
        "steps": _step(state, "intake_extraction", details, used_model),
    }


# --- 2) validate_extraction -------------------------------------------------

async def validate_extraction(state: RCAState, config: RunnableConfig) -> dict:
    model = state.get("model")
    _emit_started(config, "validate_extraction", model, "Verifying extracted values against the source text")

    errors: list[str] = []
    if not (state.get("raw_text") or "").strip():
        errors.append("Source document text is empty.")

    # Only LLM output is verified: values the human typed into the form are
    # authoritative (the user may legitimately edit fields beyond the document).
    if state.get("extraction_source") == "llm":
        for name in state.get("extraction_unverifiable") or []:
            errors.append(
                f"Field '{name}' returned a value that does not appear in the source document."
            )

    if errors:
        message = " ".join(errors)
        retries = dict(state.get("retries") or {})
        retries["intake_extraction"] = retries.get("intake_extraction", 0) + 1
        feedback = (
            "Extraction rejected by validation: " + message +
            " Return null for every value that is not literally present in the document."
        )
        return {
            "validation_error": message,
            "extraction_feedback": feedback,
            "retries": retries,
            "steps": _step(state, "validate_extraction", f"FAILED validation: {message}", model),
        }

    return {
        "validation_error": None,
        "extraction_feedback": None,
        "steps": _step(state, "validate_extraction", "All extracted values verified against the source text", model),
    }


# --- 3) five_whys ------------------------------------------------------------

async def five_whys(state: RCAState, config: RunnableConfig) -> dict:
    model = state.get("model") or settings.default_model
    _emit_started(config, "five_whys", model, "Building the 5 Whys causal chain with evidence")

    result: FiveWhysResult = await groq_client.structured_call_async(
        FiveWhysResult,
        prompts.build_five_whys_messages(state),
        model=model,
        temperature=ANALYSIS_TEMP,
        node="five_whys",
    )

    raw_text = state.get("raw_text", "")
    steps: list[dict] = []
    for index, item in enumerate(result.steps, start=1):
        # CODE decides the status — the model cannot claim "Supported".
        supported = quote_in_text(item.evidence_quote, raw_text)
        steps.append({
            "id": _new_id(),
            "level": index,  # renumber 1..n (chain order, not model's labels)
            "question": item.question.strip(),
            "answer": item.answer.strip(),
            "evidence_quote": item.evidence_quote,
            "status": "Supported" if supported else "Hypothesis",
            "origin": "ai",
            "review_state": "pending",
        })

    warnings = list(state.get("warnings") or [])
    details = f"{len(steps)} causal steps ({sum(1 for s in steps if s['status'] == 'Supported')} document-supported)"
    if len(steps) < 3:
        warnings.append(f"Only {len(steps)} causal steps could be proposed before the evidence ran out (expected 3-6).")
    if not any(s["status"] == "Supported" for s in steps):
        warnings.append("No 5-Why step carries verbatim documentary evidence — treat the chain as hypothesis only.")

    return {
        "five_whys": steps,
        "warnings": warnings,
        "steps": _step(state, "five_whys", details, model),
    }


# --- 4) fishbone -------------------------------------------------------------

async def fishbone(state: RCAState, config: RunnableConfig) -> dict:
    model = state.get("model") or settings.default_model
    _emit_started(config, "fishbone", model, "Mapping 6M (Ishikawa) factors")

    result: FishboneResult = await groq_client.structured_call_async(
        FishboneResult,
        prompts.build_fishbone_messages(state),
        model=model,
        temperature=ANALYSIS_TEMP,
        node="fishbone",
    )

    raw_text = state.get("raw_text", "")
    factors: list[dict] = []
    for factor in result.factors:
        supported = quote_in_text(factor.evidence_quote, raw_text)
        factors.append({
            "id": _new_id(),
            "category": factor.category,
            "cause": factor.cause.strip(),
            "subcauses": [s.strip() for s in factor.subcauses if s.strip()],
            "impact": factor.impact.strip(),
            "evidence_quote": factor.evidence_quote,
            "supported_by_document": supported,
            # Non-negotiable labelling rule for unsupported factors:
            "label": "Document-supported" if supported else "Needs investigation",
            "root_cause_candidate": factor.root_cause_candidate and supported,
            "origin": "ai",
            "review_state": "pending",
        })

    unsupported = sum(1 for f in factors if not f["supported_by_document"])
    categories = len({f["category"] for f in factors})
    details = f"{len(factors)} factors across {categories}/6 M's; {unsupported} need investigation"

    return {
        "fishbone": {"factors": factors},
        "steps": _step(state, "fishbone", details, model),
    }


# --- 5) root_cause_synthesis --------------------------------------------------

async def root_cause_synthesis(state: RCAState, config: RunnableConfig) -> dict:
    model = state.get("model") or settings.default_model
    _emit_started(config, "root_cause_synthesis", model, "Synthesizing the proposed root cause")

    suggestion: RootCauseSuggestion = await groq_client.structured_call_async(
        RootCauseSuggestion,
        prompts.build_root_cause_messages(state),
        model=model,
        temperature=ANALYSIS_TEMP,
        node="root_cause_synthesis",
    )

    raw_text = state.get("raw_text", "")
    whys = state.get("five_whys") or []
    total = len(whys)
    supported = sum(1 for w in whys if w.get("status") == "Supported")
    ratio = (supported / total) if total else 0.0

    # Confidence is capped by how much of the chain the document actually supports.
    confidence = suggestion.confidence
    if ratio < 0.5 and confidence != "Low":
        confidence = "Medium" if confidence == "High" and ratio >= 0.25 else "Low"

    justification = f"{supported} of {total} causal steps are supported by verbatim document evidence."
    if ratio < 0.5:
        justification += " Evidence coverage is low: treat as hypothesis pending QP review."
    elif ratio < 1:
        justification += " Remaining steps are unverified hypotheses."

    root_cause = {
        "id": _new_id(),
        "primary_root_cause": suggestion.primary_root_cause.strip(),
        "category": suggestion.category,
        "confidence": confidence,
        "justification": justification,
        # The label can NEVER claim verification before a QP signs off:
        "label": "AI-suggested, pending QP confirmation",
        "supporting_evidence": [w["evidence_quote"] for w in whys if w.get("status") == "Supported"],
        "origin": "ai",
        "review_state": "pending",
    }

    contributing = [
        {
            "id": _new_id(),
            "text": cf.text.strip(),
            "category": cf.category,
            "evidence_quote": cf.evidence_quote,
            "supported": quote_in_text(cf.evidence_quote, raw_text),
            "origin": "ai",
            "review_state": "pending",
        }
        for cf in suggestion.contributing_factors
    ]

    details = f"category={root_cause['category']}, confidence={confidence}, {supported}/{total} steps supported"
    return {
        "root_cause": root_cause,
        "contributing_factors": contributing,
        "steps": _step(state, "root_cause_synthesis", details, model),
    }


# --- 6) evidence_gap_check ----------------------------------------------------

def _same_evidence_item(a: str, b: str) -> bool:
    """Token-overlap check: is 'batch record for BMR-1' the same item as
    'Batch manufacturing record'? Used to avoid duplicate/contradictory gaps."""
    ta, tb = set(normalize(a).split()), set(normalize(b).split())
    if not ta or not tb:
        return False
    return len(ta & tb) / min(len(ta), len(tb)) >= 0.6


async def evidence_gap_check(state: RCAState, config: RunnableConfig) -> dict:
    model = state.get("model") or settings.default_model
    _emit_started(config, "evidence_gap_check", model, "Comparing required evidence against the document")

    raw_text = state.get("raw_text", "")
    # Code-side detection of evidence the document really mentions (not the LLM).
    mentioned_code = domain.mentioned_evidence_types(raw_text)

    result: GapAnalysisResult = await groq_client.structured_call_async(
        GapAnalysisResult,
        prompts.build_gap_messages(state, mentioned_code),
        model=model,
        temperature=ANALYSIS_TEMP,
        node="evidence_gap_check",
    )

    # Merge code-detected + model-reported mentions, normalized.
    mentioned_norm = {normalize(m) for m in mentioned_code}
    mentioned_norm |= {normalize(m) for m in result.mentioned if m.strip()}

    gaps: list[dict] = []
    seen: set[str] = set()
    dropped_present = 0
    for gap in result.gaps:
        key = normalize(gap.item)
        if not key or key in seen:
            continue
        seen.add(key)
        # (a) exact phrase already in the document -> not missing.
        if key in normalize(raw_text):
            dropped_present += 1
            continue
        # (b) same as an evidence type the document mentions -> not missing.
        if any(_same_evidence_item(key, m) for m in mentioned_norm):
            dropped_present += 1
            continue
        gaps.append({
            "id": _new_id(),
            "item": gap.item.strip(),
            "why_needed": gap.why_needed.strip(),
            "suggested_action": gap.suggested_action.strip(),
            "priority": gap.priority,
            "status": "Missing",
            "origin": "ai",
            "review_state": "pending",
        })

    details = f"{len(gaps)} genuinely missing evidence items (code mentioned: {', '.join(mentioned_code) or 'none'})"
    if dropped_present:
        details += f"; {dropped_present} rejected as already present"

    return {
        "missing_evidence": gaps,
        "steps": _step(state, "evidence_gap_check", details, model),
    }


# --- 7) capa_generation ---------------------------------------------------------

async def capa_generation(state: RCAState, config: RunnableConfig) -> dict:
    model = state.get("model") or settings.default_model
    _emit_started(config, "capa_generation", model, "Proposing corrective and preventive actions")

    result: CapaResult = await groq_client.structured_call_async(
        CapaResult,
        prompts.build_capa_messages(state),
        model=model,
        temperature=ANALYSIS_TEMP,
        node="capa_generation",
    )

    # Real current date + relative days from the model -> real calendar dates.
    today = date.today()
    capas: list[dict] = []
    for capa in result.capas:
        days = min(max(capa.target_days_from_now, 1), 365)
        capas.append({
            "id": _new_id(),
            "type": capa.type,
            "description": capa.description.strip(),
            "linked_cause": capa.linked_cause.strip(),
            "rationale": capa.rationale.strip(),
            "owner_role": capa.owner_role.strip(),
            "department": capa.department.strip(),
            "target_date": (today + timedelta(days=days)).isoformat(),
            "voe_plan": capa.voe_plan.strip(),
            "status": "Proposed",
            "origin": "ai",
            "review_state": "pending",
        })

    # Soft traceability check: linked_cause should reference a generated cause.
    warnings = list(state.get("warnings") or [])
    pool = [ (state.get("root_cause") or {}).get("primary_root_cause", "") ]
    pool += [c.get("text", "") for c in state.get("contributing_factors") or []]
    pool += [w.get("answer", "") for w in state.get("five_whys") or []]
    pool += [f.get("cause", "") for f in (state.get("fishbone") or {}).get("factors") or []]
    unlinked = [
        c["id"] for c in capas
        if c["linked_cause"] and not any(_same_evidence_item(c["linked_cause"], p) for p in pool if p)
    ]
    if unlinked:
        warnings.append(
            f"{len(unlinked)} CAPA(s) reference a cause that could not be matched to the generated analysis; please check the rationale."
        )

    details = f"{len(capas)} CAPA(s) proposed, dates computed from {today.isoformat()}"
    return {
        "capas": capas,
        "warnings": warnings,
        "steps": _step(state, "capa_generation", details, model),
    }


# --- 8) final_validation --------------------------------------------------------

# Record-like identifiers that must exist in the source document (principle #4).
_ID_PATTERN = re.compile(
    r"\b(?:DEV|OOS|CC|CAPA|BMR|SOP|CAL|CERT|COA|NCR|LR|PO|CR|EC|CC)[-\s#:]?\d{2,}[A-Za-z0-9\-/]*\b"
    r"|\b[A-Z]{2,6}-\d{2,}[A-Za-z0-9\-/]*\b"
)
_ID_REDACTION = "[not in source document]"

# Analysis sections the client persists; final_validation returns them redacted.
SECTION_KEYS = (
    "five_whys",
    "fishbone",
    "root_cause",
    "contributing_factors",
    "missing_evidence",
    "capas",
)


def _generated_strings(state: dict):
    """Yield (container_dict, key) for every LLM-produced free-text field."""
    for why in state.get("five_whys") or []:
        for key in ("question", "answer"):
            yield why, key
    for factor in (state.get("fishbone") or {}).get("factors") or []:
        yield factor, "cause"
        yield factor, "impact"
    root = state.get("root_cause") or {}
    yield root, "primary_root_cause"
    for cf in state.get("contributing_factors") or []:
        yield cf, "text"
    for capa in state.get("capas") or []:
        for key in ("description", "linked_cause", "rationale", "voe_plan"):
            yield capa, key


def _find_invented_ids(state: RCAState, raw_text: str) -> list[str]:
    """IDs referenced by the analysis that do NOT exist in the source document."""
    invented: list[str] = []
    seen: set[str] = set()
    lowered = raw_text.lower()
    for container, key in _generated_strings(state):
        value = container.get(key)
        if not isinstance(value, str):
            continue
        for match in _ID_PATTERN.findall(value):
            token = match.strip()
            if token.lower() in lowered or token in seen:
                continue
            seen.add(token)
            invented.append(token)
    return invented


def _redacted_sections(state: RCAState, invented: list[str]) -> dict:
    """Copy the analysis sections with fabricated record IDs replaced.

    Returns new containers: the graph state is not mutated, so the redacted
    versions travel back to the client inside this node's state update.
    """
    sections = {key: copy.deepcopy(state.get(key)) for key in SECTION_KEYS}
    for container, key in _generated_strings(sections):
        value = container.get(key)
        if not isinstance(value, str):
            continue
        for token in invented:
            if token in value:
                value = value.replace(token, _ID_REDACTION)
        container[key] = value
    return sections


async def final_validation(state: RCAState, config: RunnableConfig) -> dict:
    model = state.get("model")
    _emit_started(config, "final_validation", model, "Validating the analysis output")

    errors: list[str] = []
    if not ((state.get("root_cause") or {}).get("primary_root_cause") or "").strip():
        errors.append("Root cause is empty.")
    if len(state.get("five_whys") or []) < 2:
        errors.append("The 5 Whys chain has fewer than 2 steps.")
    if not (state.get("fishbone") or {}).get("factors"):
        errors.append("The fishbone analysis has no factors.")
    if not state.get("capas"):
        errors.append("No CAPA was generated.")

    warnings = list(state.get("warnings") or [])
    invented = _find_invented_ids(state, state.get("raw_text", ""))
    redacted: dict = {}
    if invented:
        redacted = _redacted_sections(state, invented)
        warnings.append(
            "Removed identifiers not present in the source document: " + ", ".join(invented)
        )

    if errors:
        message = " ".join(errors)
        retries = dict(state.get("retries") or {})
        retries["capa_generation"] = retries.get("capa_generation", 0) + 1
        return {
            "final_validation_error": message,
            "retries": retries,
            "warnings": warnings,
            "steps": _step(state, "final_validation", f"FAILED validation: {message}", model),
        }

    details = "analysis passed schema/required-field/invented-ID checks"
    if invented:
        details += f" ({len(invented)} invented identifier(s) redacted)"
    return {
        # Redacted sections are part of the update so the client receives what
        # the server actually validated (the raw node outputs are not persisted).
        **redacted,
        "final_validation_error": None,
        "warnings": warnings,
        "steps": _step(state, "final_validation", details, model),
    }


# --- 9) error_end ----------------------------------------------------------------

async def error_end(state: RCAState, config: RunnableConfig) -> dict:
    """Terminal node for exhausted retries: surfaces a clear, fabrication-free error."""
    model = state.get("model")
    _emit_started(config, "error_end", model, "Workflow stopped on validation failure")

    messages = [m for m in (state.get("validation_error"), state.get("final_validation_error")) if m]
    if not messages:
        messages = ["The investigation workflow failed validation."]
    errors = list(state.get("errors") or [])
    for message in messages:
        if message not in errors:
            errors.append(message)
    errors.append(
        "AI output was rejected after 2 retries — no analysis was accepted. "
        "Fix the input document or retry the investigation."
    )

    return {
        "errors": errors,
        "steps": _step(state, "error_end", "FAILED: " + " ".join(messages), model),
    }
