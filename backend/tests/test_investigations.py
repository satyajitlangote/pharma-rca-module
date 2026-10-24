"""Investigations API: CRUD, QP lock, audited diff, sign-off and reopen."""
import uuid

from conftest import SOURCE, VERBATIM, run_analysis


def _create(client, **overrides):
    payload = {
        "reference": f"DEV-{uuid.uuid4().hex[:8].upper()}",
        "title": "OOS impurity investigation",
        "product_name": "Valsartan API USP",
        "batch_number": "B-2026-118",
        "severity": "Major",
        "description": VERBATIM,
        "actor": "Test Investigator",
        "actor_type": "User",
    }
    payload.update(overrides)
    res = client.post("/api/investigations", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def test_create_ignores_client_qp_fields(client):
    inv = _create(
        client,
        is_qp_verified=True, qp_name="Fake", qp_role="Fake",
        status="Approved & Closed",  # all must be dropped by extra="ignore"
    )
    assert inv["is_qp_verified"] is False
    assert inv["qp_name"] is None
    assert inv["status"] == "Draft"


def test_crud_roundtrip_and_audit_diff(client):
    inv = _create(client)
    iid = inv["id"]

    # audit: create entry with field diffs
    audit = client.get(f"/api/investigations/{iid}/audit").json()
    assert len(audit) == 1 and audit[0]["action"] == "create"
    assert any(d["field"] == "reference" for d in audit[0]["diff"])

    # update with a field-level diff, attributed to the AI actor
    res = client.put(
        f"/api/investigations/{iid}",
        json={"severity": "Critical", "actor": "AI Copilot", "actor_type": "AI"},
    )
    assert res.status_code == 200 and res.json()["severity"] == "Critical"
    audit = client.get(f"/api/investigations/{iid}/audit").json()
    upd = audit[-1]
    assert upd["action"] == "update" and upd["actor_type"] == "AI"
    assert any(d["field"] == "severity" and d["old"] == "Major" and d["new"] == "Critical"
               for d in upd["diff"])

    # list + void (a GMP record is never hard-deleted)
    assert any(r["id"] == iid for r in client.get("/api/investigations").json())
    assert client.delete(f"/api/investigations/{iid}").status_code == 204

    voided = client.get(f"/api/investigations/{iid}").json()
    assert voided["status"] == "Void"
    assert not any(r["id"] == iid for r in client.get("/api/investigations").json())

    # audit survives the void, and the record is frozen
    actions = [a["action"] for a in client.get(f"/api/investigations/{iid}/audit").json()]
    assert actions == ["create", "update", "void"]
    assert client.put(f"/api/investigations/{iid}", json={"title": "x"}).status_code == 409
    assert client.delete(f"/api/investigations/{iid}").status_code == 409


def test_duplicate_reference_conflicts(client):
    inv = _create(client)
    res = client.post("/api/investigations", json={"reference": inv["reference"]})
    assert res.status_code == 409


def test_signoff_locks_and_reopen_unlocks(client):
    inv = _create(client)
    iid = inv["id"]

    # sign-off
    res = client.post(
        f"/api/investigations/{iid}/signoff",
        json={"verifier_name": "Dr. QP", "role": "Qualified Person",
              "comments": "Reviewed", "attestations": ["root cause reviewed"]},
    )
    assert res.status_code == 200
    signed = res.json()
    assert signed["is_qp_verified"] is True
    assert signed["qp_signed_at"] is not None
    assert signed["status"] == "Approved & Closed"

    # locked: PUT and DELETE return 409
    assert client.put(f"/api/investigations/{iid}", json={"title": "x"}).status_code == 409
    assert client.delete(f"/api/investigations/{iid}").status_code == 409
    # double sign-off conflicts (attestations required, so send a valid body)
    assert client.post(
        f"/api/investigations/{iid}/signoff",
        json={"verifier_name": "X", "role": "Y", "attestations": ["reviewed"]},
    ).status_code == 409

    # reopen requires a reason
    assert client.post(f"/api/investigations/{iid}/reopen", json={}).status_code == 422
    res = client.post(
        f"/api/investigations/{iid}/reopen",
        json={"reason": "New evidence received", "actor": "QP", "actor_type": "QP"},
    )
    assert res.status_code == 200
    assert res.json()["is_qp_verified"] is False
    assert res.json()["qp_name"] is None
    assert res.json()["status"] == "Under Investigation"

    # editable again
    assert client.put(f"/api/investigations/{iid}", json={"title": "edited"}).status_code == 200

    # full audited trail: create -> signoff -> reopen -> (edit after reopen)
    actions = [a["action"] for a in client.get(f"/api/investigations/{iid}/audit").json()]
    assert actions == ["create", "signoff", "reopen", "update"]


def test_reopen_unsigned_conflicts(client):
    inv = _create(client)
    res = client.post(f"/api/investigations/{inv['id']}/reopen", json={"reason": "x"})
    assert res.status_code == 409


def _pending_why():
    return {
        "level": 1,
        "question": "Why was the batch OOS?",
        "answer": "An out-of-specification impurity result of 0.42% was found.",
        "evidence_quote": None,
        "evidence_verified": False,
        "status": "Hypothesis",
        "confidence": "Low",
        "origin": "ai",
        "review_state": "pending",
    }


def test_signoff_blocked_while_ai_items_pending(client):
    """The review gate lives on the server, not only in the React dialog."""
    inv = _create(client, five_whys=[_pending_why()])
    iid = inv["id"]
    signoff = {"verifier_name": "Dr. QP", "role": "QP", "attestations": ["reviewed"]}

    res = client.post(f"/api/investigations/{iid}/signoff", json=signoff)
    assert res.status_code == 409
    assert "pending review" in res.json()["detail"]
    assert client.get(f"/api/investigations/{iid}").json()["is_qp_verified"] is False
    actions = [a["action"] for a in client.get(f"/api/investigations/{iid}/audit").json()]
    assert "signoff" not in actions

    # Reviewing the item unlocks sign-off.
    res = client.put(
        f"/api/investigations/{iid}",
        json={"five_whys": [{**_pending_why(), "review_state": "accepted"}]},
    )
    assert res.status_code == 200
    assert client.post(f"/api/investigations/{iid}/signoff", json=signoff).status_code == 200


def test_signoff_requires_attestation(client):
    inv = _create(client)
    res = client.post(
        f"/api/investigations/{inv['id']}/signoff",
        json={"verifier_name": "Dr. QP", "role": "QP", "attestations": []},
    )
    assert res.status_code == 422
    assert client.get(f"/api/investigations/{inv['id']}").json()["is_qp_verified"] is False


def test_full_ai_workflow_then_signoff(client, mock_llm):
    """End-to-end: analysis -> AI save -> review every section -> QP sign-off."""
    mock_llm()
    events = run_analysis(client)
    results = [e for e in events if e["node"] == "END"][0]["partial_result"]["results"]

    # The UI saves exactly what END returned (post-validation, redacted).
    inv = _create(
        client,
        actor="AI Copilot", actor_type="AI",
        five_whys=results["five_whys"],
        fishbone=results["fishbone"],
        root_cause=results["root_cause"],
        contributing_factors=results["contributing_factors"],
        missing_evidence=results["missing_evidence"],
        capas=results["capas"],
    )
    assert inv["root_cause"]["review_state"] == "pending"
    assert all(w["status"] in ("Supported", "Hypothesis") for w in inv["five_whys"])
    assert "CAL-9981" not in inv["capas"][0]["description"]

    # audit attributes the AI save to actor_type AI
    audit = client.get(f"/api/investigations/{inv['id']}/audit").json()
    assert audit[0]["actor_type"] == "AI"

    # Nothing AI-authored is pre-accepted: the server refuses sign-off.
    signoff = {"verifier_name": "Dr. QP", "role": "QP", "attestations": ["reviewed all items"]}
    res = client.post(f"/api/investigations/{inv['id']}/signoff", json=signoff)
    assert res.status_code == 409
    assert "pending review" in res.json()["detail"]

    def accept(items):
        return [{**item, "review_state": "accepted"} for item in items]

    res = client.put(
        f"/api/investigations/{inv['id']}",
        json={
            "five_whys": accept(inv["five_whys"]),
            "fishbone": {"factors": accept(inv["fishbone"]["factors"])},
            "root_cause": {**inv["root_cause"], "review_state": "accepted"},
            "contributing_factors": accept(inv["contributing_factors"]),
            "missing_evidence": accept(inv["missing_evidence"]),
            "capas": accept(inv["capas"]),
            "actor": "Investigator",
            "actor_type": "User",
        },
    )
    assert res.status_code == 200

    res = client.post(f"/api/investigations/{inv['id']}/signoff", json=signoff)
    assert res.status_code == 200 and res.json()["is_qp_verified"] is True
