"""Document -> structured extraction, then IN-CODE verification.

Accuracy principles enforced here:
  #1 every extracted value must exist in the input document;
  #4 only records present in the source may be cited;
  #6 structured output with validation, retried by groq_client (max 2 retries).

`verify_extraction` is deliberately independent of the model: it re-checks every
value/quote against raw_text and drops what cannot be located.
"""
from __future__ import annotations

from typing import Optional

from app.ai import groq_client
from app.ai import prompts
from app.config import settings
from app.schemas import (
    EXTRACTION_FIELDS,
    EXTRACT_TO_FORM,
    ExtractionFieldOut,
    ExtractionResult,
)
from app.utils.evidence import quote_in_text, value_in_text

# Confidence downgrade ladder when the supporting quote cannot be located.
_DOWNGRADE = {"High": "Medium", "Medium": "Low", "Low": "Low"}


def run_extraction(
    raw_text: str,
    email_headers: Optional[dict],
    model: str,
    feedback: Optional[str] = None,
) -> ExtractionResult:
    """One structured LLM extraction call (temperature 0, 3 attempts max)."""
    messages = prompts.build_extraction_messages(raw_text, email_headers, feedback)
    return groq_client.structured_call(
        ExtractionResult,
        messages,
        model=model,
        temperature=settings.extraction_temperature,
        node="intake_extraction",
    )


async def run_extraction_async(
    raw_text: str,
    email_headers: Optional[dict],
    model: str,
    feedback: Optional[str] = None,
) -> ExtractionResult:
    """Non-blocking `run_extraction` for async callers (nodes, HTTP handlers)."""
    messages = prompts.build_extraction_messages(raw_text, email_headers, feedback)
    return await groq_client.structured_call_async(
        ExtractionResult,
        messages,
        model=model,
        temperature=settings.extraction_temperature,
        node="intake_extraction",
    )


def verify_extraction(
    result: "ExtractionResult | dict",
    raw_text: str,
) -> tuple[dict[str, ExtractionFieldOut], list[str]]:
    """Verify every field against the source text.

    Returns (fields, unverifiable):
      * fields      — safe output; value/quote dropped when they cannot be traced;
      * unverifiable — names of fields whose *value* the model produced but the
        code could NOT find in the document (they were dropped to null).
        The graph uses this list to fail validation and retry the extraction;
        the preview endpoint simply reports them as "Not stated in document".
    """
    data = result.model_dump() if isinstance(result, ExtractionResult) else dict(result)
    fields: dict[str, ExtractionFieldOut] = {}
    unverifiable: list[str] = []

    for name in EXTRACTION_FIELDS:
        raw = data.get(name) or {}
        value = raw.get("value")
        quote = raw.get("source_quote")
        confidence = raw.get("confidence") or "Low"

        # (a) the value itself must exist in the document — else drop it.
        if value is not None and not value_in_text(value, raw_text):
            unverifiable.append(name)
            value, quote, confidence = None, None, "Low"
        elif value is None:
            quote, confidence = None, "Low"
        else:
            # (b) the supporting quote must exist — else drop the quote and
            # downgrade confidence one step (value stays: it was verified).
            if quote is not None and not quote_in_text(quote, raw_text):
                quote = None
            if quote is None:
                confidence = _DOWNGRADE.get(confidence, "Low")

        fields[name] = ExtractionFieldOut(
            value=value,
            source_quote=quote,
            confidence=confidence,
            value_verified=value is not None,
            quote_verified=quote is not None,
            not_stated=value is None,
        )
    return fields, unverifiable


def fields_from_context(context: dict) -> dict[str, ExtractionFieldOut]:
    """Build the extraction dict for the 'form' path (values already applied
    to the RCA form by the user). Values are human-owned from then on, so they
    are not re-verified against the document on every analysis run."""
    fields: dict[str, ExtractionFieldOut] = {}
    for name in EXTRACTION_FIELDS:
        value = context.get(EXTRACT_TO_FORM[name])
        value = value if isinstance(value, str) and value.strip() else None
        fields[name] = ExtractionFieldOut(
            value=value,
            source_quote=None,
            confidence="Medium",
            value_verified=True,   # authoritative form context (user may edit it)
            quote_verified=False,
            not_stated=value is None,
        )
    return fields


def fields_to_dicts(fields: dict[str, ExtractionFieldOut]) -> dict[str, dict]:
    return {k: v.model_dump() for k, v in fields.items()}
