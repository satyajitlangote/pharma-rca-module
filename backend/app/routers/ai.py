"""AI endpoints: extraction preview, SSE analysis stream, Groq key check.

Failure contract (accuracy principle #3 — NEVER silently fall back):
  * missing GROQ_API_KEY or Groq failing after 2 retries => HTTP 503 with a
    clear message (analysis stream: a "failed" SSE event + END failed);
  * no canned/keyword-matched analysis is ever substituted for real output;
  * the UI shows its "AI unavailable" banner and leaves the form untouched.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from app.ai import extraction as extraction_mod
from app.ai import groq_client
from app.ai.graph import graph
from app.ai.groq_client import AIUnavailableError
from app.ai.nodes import SECTION_KEYS
from app.ai.state import build_initial_state
from app.config import settings
from app.schemas import (
    AnalyzeRequest,
    ExtractRequest,
    ExtractionResponse,
    ValidateKeyResponse,
)
from app.utils.documents import DocumentError, parse_text, parse_upload

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ai_unavailable(detail: str) -> JSONResponse:
    """503 with a clear message; UI turns this into the 'AI unavailable' banner."""
    return JSONResponse(
        status_code=503,
        content={"detail": detail, "error_type": "ai_unavailable", "ok": False},
    )


def _sse(event: dict) -> bytes:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8")


# ---------------------------------------------------------------------------
# POST /api/ai/extract — preview only (never writes to the form/DB)
# ---------------------------------------------------------------------------

class _ExtractJson(BaseModel):
    """(Local alias used when parsing a raw JSON body.)"""
    model_config = {"extra": "ignore"}
    text: Optional[str] = None
    source_document_name: Optional[str] = None
    model: Optional[str] = None


async def _read_extract_input(request: Request):
    """Manual body parsing: multipart file OR JSON text/email in ONE endpoint."""
    content_type = (request.headers.get("content-type") or "").lower()

    data: bytes | None = None
    filename: str | None = None
    file_ct: str | None = None
    text: str | None = None
    source_name: str | None = None
    model_req: str | None = None

    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        upload = form.get("file")
        if upload is not None and hasattr(upload, "read"):
            data = await upload.read()
            filename = getattr(upload, "filename", None) or None
            file_ct = getattr(upload, "content_type", None) or None
        raw_text = form.get("text")
        text = raw_text if isinstance(raw_text, str) and raw_text.strip() else None
        raw_name = form.get("source_document_name")
        source_name = raw_name if isinstance(raw_name, str) else None
        raw_model = form.get("model")
        model_req = raw_model if isinstance(raw_model, str) and raw_model else None
    else:
        try:
            body = await request.json()
        except Exception:
            body = None
        if not isinstance(body, dict):
            return None, None, None, None, None, None
        parsed = _ExtractJson.model_validate(body)
        text = parsed.text if parsed.text and parsed.text.strip() else None
        source_name = parsed.source_document_name
        model_req = parsed.model

    if data is not None and len(data) > settings.max_upload_bytes:
        raise DocumentError(
            f"File is too large ({len(data):,} bytes). "
            f"Limit is {settings.max_upload_bytes:,} bytes — paste the text instead.",
            status_code=413,
        )
    if data is None and text is None and source_name is None and model_req is None:
        # Not a usable body at all (e.g. malformed JSON)
        return None, None, None, None, None, None
    return data, filename, file_ct, text, source_name, model_req


@router.post("/api/ai/extract", response_model=ExtractionResponse)
async def extract(request: Request) -> ExtractionResponse | JSONResponse:
    # Fail fast, before touching the document: never partially process then 503.
    if not settings.groq_configured:
        return _ai_unavailable(
            "AI unavailable: GROQ_API_KEY is not configured on the server. "
            "Add it to backend/.env. No data was extracted."
        )

    try:
        data, filename, file_ct, text, source_name, model_req = await _read_extract_input(request)
    except DocumentError as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})

    if data is None and text is None:
        return JSONResponse(
            status_code=422,
            content={"detail": "No document provided. Upload a file or paste text (or an email)."},
        )

    # Parse the document (PDF / .eml / text). Explicit errors, no fallbacks.
    try:
        if data is not None:
            doc = parse_upload(data, filename, file_ct, settings.max_text_chars)
        else:
            doc = parse_text(text or "", source_name, settings.max_text_chars)
    except DocumentError as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})

    model = groq_client.resolve_model(model_req)
    try:
        result = await extraction_mod.run_extraction_async(doc.text, doc.email_headers, model, None)
    except AIUnavailableError as exc:
        return _ai_unavailable(str(exc))

    # Drop any value/quote that cannot be traced to the document (never fabricate).
    fields, _unverifiable = extraction_mod.verify_extraction(result, doc.text)

    return ExtractionResponse(
        fields=fields,
        email_context=doc.email_headers or None,
        source_kind=doc.kind,
        source_text=doc.text,
        truncated=doc.truncated,
        warning=doc.warning,
        model=model,
        text_length=len(doc.text),
    )


# ---------------------------------------------------------------------------
# POST /api/ai/analyze/stream — SSE, one event per LangGraph node
# ---------------------------------------------------------------------------

@router.post("/api/ai/analyze/stream")
async def analyze_stream(req: AnalyzeRequest):
    if not settings.groq_configured:
        return _ai_unavailable(
            "AI unavailable: GROQ_API_KEY is not configured on the server. "
            "Add it to backend/.env. The form was not modified."
        )
    if not req.source_text.strip():
        return JSONResponse(status_code=422, content={"detail": "source_text is empty — provide the incident document text."})

    model = groq_client.resolve_model(req.model)
    state = build_initial_state(req, model)
    # Long documents: truncate with a *visible* warning carried in the stream.
    if len(state["raw_text"]) > settings.max_text_chars:
        state["warnings"] = [
            f"Document truncated to {settings.max_text_chars:,} characters before analysis."
        ]
        state["raw_text"] = state["raw_text"][: settings.max_text_chars]

    queue: asyncio.Queue = asyncio.Queue()

    async def generate():
        """Merge three producers into one SSE stream:
        (a) node 'started' events pushed by the nodes themselves,
        (b) per-node updates yielded by graph.astream,
        (c) a terminal END event."""
        last_node = "graph"
        failed = False
        failure_error: str | None = None
        final_state: dict = {}

        async def drive_graph():
            nonlocal failure_error
            try:
                # Real streaming: one updates-chunk per completed node.
                async for chunk in graph.astream(
                    state, config={"configurable": {"node_queue": queue}}
                ):
                    await queue.put({"kind": "update", "chunk": chunk})
            except AIUnavailableError as exc:
                failure_error = str(exc)
                await queue.put({"kind": "failed", "error": failure_error})
            except Exception as exc:  # unexpected -> clear error, no fabrication
                failure_error = f"AI investigation failed: {type(exc).__name__}: {exc}"
                await queue.put({"kind": "failed", "error": failure_error})
            finally:
                await queue.put({"kind": "done"})

        task = asyncio.create_task(drive_graph())
        try:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    # Keep-alive: a node may legitimately wait ~60 s on a TPM
                    # retry. An SSE comment keeps proxies from dropping the
                    # stream; the client ignores lines without "data: ".
                    yield ": keep-alive\n\n"
                    continue
                kind = item["kind"]
                if kind == "done":
                    break
                if kind == "node_started":
                    event = item["event"]
                    last_node = event["node"]
                    yield _sse(event)
                elif kind == "failed":
                    failed = True
                    yield _sse({
                        "node": last_node, "status": "failed",
                        "details": item["error"], "model": model,
                        "timestamp": _now(), "partial_result": None,
                        "error": item["error"],
                    })
                elif kind == "update":
                    chunk = item["chunk"] or {}
                    for node_name, patch in chunk.items():
                        if node_name.startswith("__") or not isinstance(patch, dict):
                            continue
                        last_node = node_name
                        final_state.update(patch)
                        step_rec = (patch.get("steps") or [{}])[-1]
                        partial = {k: v for k, v in patch.items() if k != "steps"}
                        if node_name == "error_end":
                            failed = True
                            failure_error = failure_error or "; ".join(patch.get("errors") or [])
                        yield _sse({
                            "node": node_name,
                            "status": "failed" if node_name == "error_end" else "completed",
                            "details": step_rec.get("details"),
                            "model": step_rec.get("model"),
                            "timestamp": step_rec.get("timestamp") or _now(),
                            "partial_result": partial,
                            "error": "; ".join(patch.get("errors") or []) or None
                                     if node_name == "error_end" else None,
                        })
        finally:
            if not task.done():
                task.cancel()

        # Terminal event: full-picture summary for the UI stepper.
        errors = final_state.get("errors") or []
        root_cause = final_state.get("root_cause") or {}
        summary = {
            "counts": {
                "five_whys": len(final_state.get("five_whys") or []),
                "fishbone_factors": len((final_state.get("fishbone") or {}).get("factors") or []),
                "contributing_factors": len(final_state.get("contributing_factors") or []),
                "missing_evidence": len(final_state.get("missing_evidence") or []),
                "capas": len(final_state.get("capas") or []),
            },
            "root_cause_label": root_cause.get("label"),
            "errors": errors,
            "warnings": final_state.get("warnings") or [],
            # Post-validation content (invented IDs already redacted). The
            # client persists these, not the raw per-node proposals.
            "results": {key: final_state.get(key) for key in SECTION_KEYS},
        }
        yield _sse({
            "node": "END",
            "status": "failed" if failed or errors else "completed",
            "details": "investigation failed — see errors" if (failed or errors)
                       else "investigation complete (AI-suggested, pending QP confirmation)",
            "model": model,
            "timestamp": _now(),
            "partial_result": summary,
            "error": failure_error or ("; ".join(errors) or None),
        })

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# POST /api/ai/validate-key — connectivity test for the UI
# ---------------------------------------------------------------------------

class _ValidateJson(BaseModel):
    model_config = {"extra": "ignore"}
    model: Optional[str] = Field(default=None)


@router.post("/api/ai/validate-key", response_model=ValidateKeyResponse)
def validate_key(payload: _ValidateJson | None = None) -> ValidateKeyResponse | JSONResponse:
    if not settings.groq_configured:
        return _ai_unavailable(
            "AI unavailable: GROQ_API_KEY is not configured on the server. "
            "Add it to backend/.env to enable AI features."
        )
    model = groq_client.resolve_model(payload.model if payload else None)
    try:
        chat = groq_client.get_chat(model, 0.0)
        chat.invoke([HumanMessage(content="Reply with the single word OK.")])
    except AIUnavailableError as exc:
        return _ai_unavailable(str(exc))
    except Exception as exc:
        return _ai_unavailable(
            f"AI unavailable: Groq connectivity check failed for model '{model}': "
            f"{type(exc).__name__}: {exc}"
        )
    return ValidateKeyResponse(ok=True, model=model, detail="Groq is reachable with the configured key.")
