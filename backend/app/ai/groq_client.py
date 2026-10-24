"""Single choke point for every Groq call.

Enforced here (NON-NEGOTIABLE accuracy principles):
  * Missing GROQ_API_KEY                -> AIUnavailableError -> HTTP 503.
    There is NO silent fallback, no canned analysis, no substitute model.
  * Structured outputs via ChatGroq.with_structured_output(PydanticModel);
    if the model returns invalid JSON/schema we retry up to 2 times, feeding
    the validation error back, then raise with a clear message (503).
  * temperature 0 for extraction, 0.1 for analysis (configurable).
  * Model allowlist: openai/gpt-oss-20b (default, verified) | gpt-oss-120b |
    qwen/qwen3.8-27b | llama-3.3-70b-versatile | gemma2-9b-it.
    gemma2-9b-it has no tool-calling support on Groq -> JSON mode is used.
    Smaller gpt-oss models occasionally answer with JSON text instead of a
    tool call; that failure is fed back as "call the function" and retried.
  * HTTP 429 (free-tier TPM cap): wait Groq's own suggested time (with
    backoff) before retrying — same max-2-retries budget, no fabricated output.
    A daily (TPD) cap is never retried: no wait can restore the budget before
    the window resets, so it fails immediately with Groq's own reset hint.

Tests monkeypatch `app.ai.groq_client.structured_call` (the only LLM entry point).
"""
from __future__ import annotations

import asyncio
import re
import time
from typing import Optional, Type, TypeVar

from langchain_core.messages import BaseMessage
from langchain_groq import ChatGroq
from pydantic import BaseModel

from app.config import ALLOWED_AI_MODELS, settings

T = TypeVar("T", bound=BaseModel)

RETRIES = 2  # => 3 attempts total ("Groq fails after 2 retries -> 503")


class AIUnavailableError(Exception):
    """Groq key missing or Groq failed after retries. Mapped to HTTP 503."""


def resolve_model(requested: Optional[str]) -> str:
    """Client may ask for an allowlisted model; anything else -> server default."""
    if requested and requested in ALLOWED_AI_MODELS:
        return requested
    return settings.default_model


# --- rate-limit (HTTP 429) handling ----------------------------------------
# Groq free tier caps TPM (e.g. 8000 tokens/min/model). The error message
# carries the server's own suggestion ("...try again in 3.135s..."), which we
# parse and honour — a shorter backoff would just re-hit the same 429.
_WAIT_HINT = re.compile(r"try again in ([\d.]+)s", re.IGNORECASE)
# Per-DAY token cap (TPD) — unlike a per-minute cap, retrying cannot succeed
# until the window resets, so callers must not sit through the retry budget.
_DAILY_CAP = re.compile(r"tokens per day|\bTPD\b", re.IGNORECASE)
_DAILY_HINT = re.compile(r"try again in ([\dm.]+s?)", re.IGNORECASE)
# Per-MINUTE cap: Groq reports the window usage and its own (too-short) hint.
_TPM_LIMIT = re.compile(r"\(TPM\): Limit (\d+)")
_TPM_USAGE = re.compile(r"Used (\d+), Requested (\d+)")


def _is_rate_limit(exc: Exception) -> bool:
    text = str(exc)
    return (
        "429" in text
        or "rate_limit" in text.lower()
        or "tokens per minute" in text.lower()
    )


def _rate_limit_wait(exc: Exception, attempt: int) -> float:
    """Seconds to wait before retrying a 429: server hint, scaled per attempt.

    Groq reports its own suggestion ("try again in 3.135s"). That hint only
    covers the current deficit — but the rejected request's tokens stay in the
    window too, so a short retry is rejected again and the window never drains.
    When the error carries the per-minute usage, wait for the deficit **and**
    the retry's own prompt to fit under the cap (one full window for an 8k TPM
    model with a ~4k prompt), capped at 65 s. No usage numbers -> the hint with
    a per-attempt multiplier, capped at 30 s.
    """
    text = str(exc)
    match = _WAIT_HINT.search(text)
    hint = float(match.group(1)) if match else (5.0 if attempt == 0 else 15.0)

    usage = _TPM_USAGE.search(text)
    limit = _TPM_LIMIT.search(text)
    if usage and limit:
        used, requested, cap = int(usage.group(1)), int(usage.group(2)), int(limit.group(1))
        deficit = used + 2 * requested - cap
        seconds = deficit / (cap / 60.0) + 1.0
        # Groq keeps a rejected request's tokens in the window, so a partial
        # drain can still be rejected. For a prompt-sized request, wait out a
        # whole window (60 s) and start again from an empty one.
        return max(1.0, min(max(hint, seconds, 60.0), 75.0))

    scaled = hint * (3.0 if attempt > 0 else 1.0)
    return max(1.0, min(scaled, 30.0))


def get_chat(model: str, temperature: float) -> ChatGroq:
    if not settings.groq_configured:
        raise AIUnavailableError(
            "AI unavailable: GROQ_API_KEY is not configured on the server. "
            "Set it in backend/.env — no AI data was generated."
        )
    return ChatGroq(
        api_key=settings.groq_api_key,
        model=model,
        temperature=temperature,
        max_retries=0,  # retries are handled here so failures are visible
        # Bounded per-attempt timeout (langchain-groq -> groq SDK -> httpx).
        # Without it a stalled HTTPS connection hangs the node forever; with it
        # a stall becomes a normal exception -> retry -> clear HTTP 503.
        timeout=120.0,
    )


def structured_call(
    schema: Type[T],
    messages: list[BaseMessage],
    *,
    model: str,
    temperature: float,
    node: str,
) -> T:
    """Invoke Groq with a Pydantic structured output, up to 3 attempts."""
    chat = get_chat(model, temperature)
    # gemma2-9b-it cannot do tool/function calling on Groq -> JSON mode.
    method = "json_mode" if model.startswith("gemma") else "function_calling"

    feedback: Optional[str] = None
    last_error = "unknown error"
    for attempt in range(RETRIES + 1):
        try:
            attempt_messages = list(messages)
            if feedback:
                from langchain_core.messages import HumanMessage
                attempt_messages.append(HumanMessage(content=feedback))
            runnable = chat.with_structured_output(schema, method=method)
            result = runnable.invoke(attempt_messages)
            # Some code paths return a dict; validate either way (raises on bad shape).
            return result if isinstance(result, schema) else schema.model_validate(result)
        except AIUnavailableError:
            raise
        except Exception as exc:  # transport error OR schema/JSON validation failure
            if _DAILY_CAP.search(str(exc)):
                # Retrying cannot succeed before the daily window resets. Fail
                # now with Groq's own hint instead of burning the retry budget.
                hint = _DAILY_HINT.search(str(exc))
                reset = f"try again in {hint.group(1)}" if hint else "retry after it resets"
                raise AIUnavailableError(
                    f"AI daily token quota reached for model '{model}' in node "
                    f"'{node}' — {reset}. No data was generated."
                ) from exc
            last_error = f"{type(exc).__name__}: {str(exc)[:400]}"
            rate_limited = _is_rate_limit(exc)
            if not rate_limited:
                # Schema/JSON failure -> feed the validation error back.
                # A 429 produced no model output, so there is nothing to correct.
                if "tool_use_failed" in str(exc) or "did not call a tool" in str(exc):
                    feedback = (
                        "Your previous reply did not produce a valid function call "
                        f"({last_error[:200]}). Call the provided function with ONE "
                        "complete JSON object of arguments that matches its schema. "
                        "Never answer with plain text and never truncate the arguments. "
                        "Only values present in the document may appear; otherwise null."
                    )
                else:
                    feedback = (
                        "Your previous response could not be validated against the required "
                        f"JSON schema ({last_error}). Reply again with ONE JSON object that "
                        "matches the schema exactly. Remember: only values present in the "
                        "document may appear; otherwise use null."
                    )
            if attempt < RETRIES:
                # Honour Groq's suggested 429 wait (a fixed 0.5s just re-hits it).
                time.sleep(_rate_limit_wait(exc, attempt) if rate_limited else 0.5 * (attempt + 1))

    raise AIUnavailableError(
        f"AI failed after {RETRIES} retries in node '{node}': {last_error}"
    )


async def structured_call_async(
    schema: Type[T],
    messages: list[BaseMessage],
    *,
    model: str,
    temperature: float,
    node: str,
) -> T:
    """`structured_call` on a worker thread.

    The Groq SDK is synchronous and retries sleep; calling it directly inside
    an async node blocks the event loop, so `/api/health` stops answering and
    SSE events only flush when the whole node finishes. Offloading keeps the
    loop free while the worker thread blocks. Resolving `structured_call` by
    name at call time keeps tests' monkeypatch of the sync entry point valid.
    """
    return await asyncio.to_thread(
        structured_call,
        schema,
        messages,
        model=model,
        temperature=temperature,
        node=node,
    )
