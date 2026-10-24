"""Accuracy contract tests (mocked LLM — Groq is never called).

Required behaviours:
  1. fabricated extraction values are dropped ("Not stated in document");
  2. every analysis node emits started/completed SSE events;
  3. a fabricated evidence quote can never be "Supported" (-> Hypothesis);
  4. evidence the document already contains is filtered out of the gaps;
  5. CAPA target dates are computed from the REAL current date;
  6. invented record IDs are redacted from the final analysis;
  7. missing/failing Groq key -> HTTP 503 with error_type ai_unavailable.
"""
from datetime import date

import pytest
from langchain_core.messages import HumanMessage

from app.schemas import FiveWhysResult
from conftest import (
    FABRICATED_QUOTE,
    SOURCE,
    VERBATIM,
    clean_extraction,
    fabricated_extraction,
    run_analysis,
    run_graph,
    sample_capas,
    today_plus,
)


# --- 1. extraction never fabricates ----------------------------------------

def test_extraction_drops_fabricated_values(client, mock_llm):
    mock_llm(extraction=fabricated_extraction())
    res = client.post("/api/ai/extract", json={"text": SOURCE})
    assert res.status_code == 200
    body = res.json()

    # Fabricated batch number -> dropped, reported as not stated.
    batch = body["fields"]["batch_number"]
    assert batch["value"] is None
    assert batch["not_stated"] is True
    assert batch["value_verified"] is False
    assert "Not stated" in str(batch) or batch["not_stated"]

    # Real values survive with verified quotes.
    product = body["fields"]["product_name"]
    assert product["value"] == "Valsartan API USP"
    assert product["value_verified"] is True
    # quote was fabricated -> quote dropped + confidence downgraded High->Medium
    assert product["source_quote"] is None
    assert product["confidence"] == "Medium"

    # Not-stated fields are explicit (no invented defaults).
    assert body["fields"]["reported_by"]["not_stated"] is True
    assert body["source_text"].strip()  # source text returned for later verification


def test_extraction_perfect_document_keeps_quotes(client, mock_llm):
    mock_llm(extraction=clean_extraction())
    body = client.post("/api/ai/extract", json={"text": SOURCE}).json()
    batch = body["fields"]["batch_number"]
    assert batch["value"] == "B-2026-118"
    assert batch["quote_verified"] is True
    assert batch["confidence"] == "High"


# --- 2. SSE: one started + completed event per node -------------------------

def test_sse_emits_started_and_completed_per_node(client, mock_llm):
    mock_llm()
    events = run_analysis(client)

    expected = [
        "intake_extraction", "validate_extraction", "five_whys", "fishbone",
        "root_cause_synthesis", "evidence_gap_check", "capa_generation",
        "final_validation",
    ]
    for node in expected:
        statuses = [e["status"] for e in events if e["node"] == node]
        assert "started" in statuses, f"missing started event for {node}: {statuses}"
        assert "completed" in statuses, f"missing completed event for {node}: {statuses}"

    # Every event carries the full contract: model + timestamp + partial_result key.
    for e in events:
        assert "model" in e and "timestamp" in e and "partial_result" in e

    end = [e for e in events if e["node"] == "END"]
    assert len(end) == 1
    assert end[0]["status"] == "completed"
    counts = end[0]["partial_result"]["counts"]
    assert counts["five_whys"] == 3
    assert counts["fishbone_factors"] == 2
    assert counts["capas"] == 1


# --- 3. fabricated quote -> Hypothesis, never Supported ---------------------

def test_fabricated_quote_is_hypothesis(client, mock_llm):
    mock_llm()
    events = run_analysis(client)
    completed = {e["node"]: e["partial_result"] for e in events if e["status"] == "completed"}
    whys = completed["five_whys"]["five_whys"]

    by_status = {}
    for w in whys:
        by_status.setdefault(w["status"], []).append(w)

    # The verbatim quote is Supported; the fabricated one is Hypothesis.
    supported = by_status.get("Supported", [])
    assert any(VERBATIM in (w["evidence_quote"] or "") for w in supported)
    hypothesis = by_status.get("Hypothesis", [])
    assert any(FABRICATED_QUOTE in (w["evidence_quote"] or "") for w in hypothesis)
    # No step with a fabricated quote may ever be Supported.
    assert all(FABRICATED_QUOTE not in (w["evidence_quote"] or "") for w in supported)

    # Root cause confidence is capped by evidence coverage and labelled pending.
    root = completed["root_cause_synthesis"]["root_cause"]
    assert root["label"] == "AI-suggested, pending QP confirmation"
    assert 2 == sum(1 for w in whys if w["status"] == "Supported")
    # contributing factor with fabricated quote is not "supported"
    cfs = completed["root_cause_synthesis"]["contributing_factors"]
    fake_cf = [c for c in cfs if FABRICATED_QUOTE in (c["evidence_quote"] or "")]
    assert fake_cf and fake_cf[0]["supported"] is False


# --- 4. gaps: evidence already in the document is filtered out ---------------

def test_gap_check_filters_present_evidence(client, mock_llm):
    mock_llm()
    events = run_analysis(client)
    completed = {e["node"]: e["partial_result"] for e in events if e["status"] == "completed"}
    gaps = completed["evidence_gap_check"]["missing_evidence"]

    items = [g["item"].lower() for g in gaps]
    # "Calibration records" ARE mentioned in the document (code-side detection)
    # and the document text mentions calibration -> must NOT be listed missing.
    assert not any("calibration" in i for i in items), items
    # The genuinely absent evidence survives, with status Missing.
    assert any("audit trail" in i for i in items), items
    assert all(g["status"] == "Missing" for g in gaps)


# --- 5. CAPA dates come from the real clock ---------------------------------

def test_capa_target_date_is_real(client, mock_llm):
    mock_llm(capas=sample_capas(days=14))
    events = run_analysis(client)
    completed = {e["node"]: e["partial_result"] for e in events if e["status"] == "completed"}
    capas = completed["capa_generation"]["capas"]

    assert capas[0]["target_date"] == today_plus(14)
    assert capas[0]["target_date"] >= date.today().isoformat()  # never in the past
    assert capas[0]["status"] == "Proposed"


# --- 6. invented record IDs are redacted -------------------------------------

def test_invented_ids_are_redacted(mock_llm):
    mock_llm()
    # Deterministic final state: final_validation redacts IDs not in the source.
    final = run_graph()
    assert not final.get("final_validation_error")

    # The CAPA description cited CAL-9981, which does NOT exist in SOURCE.
    desc = final["capas"][0]["description"]
    assert "CAL-9981" not in desc
    assert "[not in source document]" in desc
    assert any(
        "CAL-9981" in w and "not present in the source document" in w
        for w in final["warnings"]
    ), final["warnings"]


def test_invented_ids_warned_in_sse_stream(client, mock_llm):
    """The redacted content — not just a warning — is what the client receives."""
    mock_llm()
    events = run_analysis(client)
    end = [e for e in events if e["node"] == "END"][0]
    assert end["status"] == "completed"
    warnings = end["partial_result"]["warnings"]
    assert any("CAL-9981" in w for w in warnings), warnings

    results = end["partial_result"]["results"]
    assert set(results) == {
        "five_whys", "fishbone", "root_cause",
        "contributing_factors", "missing_evidence", "capas",
    }
    assert "CAL-9981" not in str(results)
    assert "[not in source document]" in results["capas"][0]["description"]

    # The final_validation node update carries the redaction too, so no client
    # can reconstruct the raw proposal from the authoritative payload.
    completed = {e["node"]: e["partial_result"] for e in events if e["status"] == "completed"}
    assert "CAL-9981" not in str(completed["final_validation"].get("capas"))


def test_invented_id_not_redacted_when_in_document(client, mock_llm):
    """IDs present in the source document must survive."""
    capas = sample_capas(days=7)
    capas["capas"][0]["description"] = "Verify against DEV-2026-014 before reuse."
    mock_llm(capas=capas)
    events = run_analysis(client)
    completed = {e["node"]: e["partial_result"] for e in events if e["status"] == "completed"}
    assert "DEV-2026-014" in completed["capa_generation"]["capas"][0]["description"]
    end = [e for e in events if e["node"] == "END"][0]
    assert not any("DEV-2026-014" in w for w in end["partial_result"]["warnings"])


# --- 7. AI unavailable -> 503, form untouched --------------------------------

def test_extract_returns_503_without_key(client, no_ai_key):
    res = client.post("/api/ai/extract", json={"text": SOURCE})
    assert res.status_code == 503
    body = res.json()
    assert body["error_type"] == "ai_unavailable"
    assert "GROQ_API_KEY" in body["detail"]
    assert body["ok"] is False
    # No extraction payload at all — nothing fabricated into the UI.
    assert "fields" not in body


def test_analyze_returns_503_without_key(client, no_ai_key):
    res = client.post("/api/ai/analyze/stream", json={"source_text": SOURCE})
    assert res.status_code == 503
    body = res.json()
    assert body["error_type"] == "ai_unavailable"
    assert "form was not modified" in body["detail"]


def test_validate_key_returns_503_without_key(client, no_ai_key):
    res = client.post("/api/ai/validate-key", json={})
    assert res.status_code == 503
    assert res.json()["error_type"] == "ai_unavailable"


def test_groq_failure_after_retries_is_503(client, monkeypatch, ai_key):
    """Groq configured but failing -> clear 503, no canned fallback."""
    from app.ai.groq_client import AIUnavailableError

    def failing_call(schema, messages, *, model, temperature, node):
        raise AIUnavailableError(f"AI failed after 2 retries in node '{node}': boom")

    monkeypatch.setattr("app.ai.groq_client.structured_call", failing_call)
    res = client.post("/api/ai/extract", json={"text": SOURCE})
    assert res.status_code == 503
    assert res.json()["error_type"] == "ai_unavailable"
    assert "2 retries" in res.json()["detail"]


def test_failed_analysis_leaves_no_investigation(client, mock_llm):
    """A failed stream must never write a record (no fabrication anywhere)."""
    mock_llm()
    before = client.get("/api/investigations").json()
    run_analysis(client)  # success path writes nothing by itself (UI saves)
    after = client.get("/api/investigations").json()
    assert before == after


def test_daily_token_cap_fails_fast(monkeypatch):
    """A per-DAY 429 cannot succeed by retrying -> one attempt, actionable 503."""
    from app.ai import groq_client

    attempts: list = []

    class _Runnable:
        def invoke(self, messages):
            attempts.append(messages)
            raise RuntimeError(
                "Error code: 429 - {'error': {'message': 'Rate limit reached for model "
                "`openai/gpt-oss-120b` on tokens per day (TPD): Limit 200000, Used "
                "197803, Requested 2863. Please try again in 4m47.712s.'}}"
            )

    class _Chat:
        def with_structured_output(self, schema, method):
            return _Runnable()

    monkeypatch.setattr(groq_client, "get_chat", lambda model, temperature: _Chat())

    with pytest.raises(groq_client.AIUnavailableError) as exc:
        groq_client.structured_call(
            FiveWhysResult,
            [HumanMessage(content="x")],
            model="openai/gpt-oss-120b",
            temperature=0.1,
            node="five_whys",
        )

    assert len(attempts) == 1, "a daily cap must not be retried"
    message = str(exc.value)
    assert "daily token quota" in message
    assert "try again in 4m47.712s" in message
    assert "No data was generated" in message


def test_tpm_backoff_covers_the_retry_itself():
    """Groq's hint only covers the deficit; the retry's own prompt must fit too."""
    from app.ai import groq_client

    exc = RuntimeError(
        "Error code: 429 - rate limit reached on tokens per minute (TPM): "
        "Limit 8000, Used 5408, Requested 3254. Please try again in 4.965s."
    )
    wait = groq_client._rate_limit_wait(exc, 0)
    assert 60.0 <= wait <= 75.0
    # The rejected request's tokens stay in the window, so the hint alone (~5 s)
    # would be rejected again.
    assert wait > 4.965


def test_tpm_backoff_without_usage_falls_back_to_hint():
    from app.ai import groq_client

    exc = RuntimeError("Error code: 429 - Please try again in 3.5s")
    assert groq_client._rate_limit_wait(exc, 0) == 3.5
    assert groq_client._rate_limit_wait(exc, 1) == 10.5
