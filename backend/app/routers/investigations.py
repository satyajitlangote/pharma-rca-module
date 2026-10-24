"""Investigations CRUD + QP sign-off / reopen + audit trail.

Rules enforced here (server is the authority, never the client):
  * is_qp_verified / qp_* / status are NOT writable through create/update
    (they do not exist on InvestigationCreate/Update — extra="ignore").
  * A signed record is locked: PUT/DELETE return HTTP 409 until an audited
    POST /reopen clears the verification.
  * Every write appends an AuditLog row with a FIELD-LEVEL diff
    ([{field, old, new}]) and the actor_type (AI | User | QP).
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AuditLog, Investigation, utcnow
from app.schemas import (
    AuditEntryRead,
    InvestigationCreate,
    InvestigationListItem,
    InvestigationRead,
    InvestigationUpdate,
    ReopenRequest,
    SignoffRequest,
)

router = APIRouter(prefix="/api/investigations", tags=["investigations"])

# Columns compared for the audit diff (JSON RCA content compared as whole docs).
_DIFF_FIELDS = [
    "reference", "title", "product_name", "batch_number", "stage", "equipment_area",
    "incident_datetime", "reported_by", "severity", "description", "immediate_containment",
    "detected_by", "quantity_affected", "five_whys", "fishbone", "root_cause",
    "contributing_factors", "missing_evidence", "capas", "source_document_text",
    "source_document_name", "ai_summary", "status", "is_qp_verified", "qp_name",
    "qp_role", "qp_comments", "qp_signed_at",
]

# Columns never compared/diffed for audit noise control.
_SKIP_DIFF = {"updated_at", "created_at"}


# ------------------------------- helpers ----------------------------------

def _get_or_404(db: Session, inv_id: uuid.UUID) -> Investigation:
    inv = db.get(Investigation, inv_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="Investigation not found.")
    return inv


def _assert_unlocked(inv: Investigation) -> None:
    """Signed and voided records are immutable."""
    if inv.is_qp_verified:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Investigation is QP-signed and locked. "
                "Use POST /api/investigations/{id}/reopen to unlock it (audited)."
            ),
        )
    if inv.status == "Void":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Investigation is voided and can no longer be modified.",
        )


def _pending_ai_items(inv: Investigation) -> list[str]:
    """Labels of AI-authored items no reviewer has accepted, edited or rejected.

    Mirrors the client's section gate (rcaSlice listOf); the server is the
    authority, so sign-off must not rely on the UI hiding the button.
    """
    sections = (
        ("five_whys", list(inv.five_whys or [])),
        ("fishbone", list((inv.fishbone or {}).get("factors") or [])),
        ("root_cause", [inv.root_cause] if isinstance(inv.root_cause, dict) and inv.root_cause else []),
        ("contributing_factors", list(inv.contributing_factors or [])),
        ("missing_evidence", list(inv.missing_evidence or [])),
        ("capas", list(inv.capas or [])),
    )
    labels: list[str] = []
    for name, items in sections:
        for idx, item in enumerate(items):
            if (
                isinstance(item, dict)
                and item.get("origin") == "ai"
                and item.get("review_state") == "pending"
            ):
                labels.append(name if name == "root_cause" else f"{name}[{idx}]")
    return labels


def _norm(value: Any) -> Any:
    """Make a value JSON-comparable for the diff."""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _diff(old: dict, new: dict) -> list[dict]:
    """Field-level diff [{field, old, new}] for the audit log."""
    changes: list[dict] = []
    for field in _DIFF_FIELDS:
        if field in _SKIP_DIFF:
            continue
        before, after = _norm(old.get(field)), _norm(new.get(field))
        if before != after:
            changes.append({"field": field, "old": before, "new": after})
    return changes


def _snapshot(inv: Investigation) -> dict:
    return {f: getattr(inv, f) for f in _DIFF_FIELDS}


def _log(db: Session, inv_id: uuid.UUID, action: str, actor: str, actor_type: str, diff: list[dict]) -> None:
    db.add(AuditLog(
        investigation_id=inv_id,
        actor=actor,
        actor_type=actor_type,
        action=action,
        diff=diff,
        timestamp=utcnow(),
    ))


def _check_reference(db: Session, reference: str | None, exclude_id: uuid.UUID | None = None) -> None:
    """Reference is unique when present — fail loudly instead of silently."""
    if not reference:
        return
    q = select(Investigation.id).where(Investigation.reference == reference)
    if exclude_id is not None:
        q = q.where(Investigation.id != exclude_id)
    if db.execute(q).first() is not None:
        raise HTTPException(status_code=409, detail=f"An investigation with reference '{reference}' already exists.")


# ------------------------------- endpoints --------------------------------

@router.post("", response_model=InvestigationRead, status_code=201)
def create_investigation(body: InvestigationCreate, db: Session = Depends(get_db)) -> Investigation:
    _check_reference(db, body.reference)
    data = body.model_dump(exclude={"actor", "actor_type"})
    inv = Investigation(**data, status="Draft", is_qp_verified=False)
    db.add(inv)
    db.flush()  # assign id
    _log(db, inv.id, "create", body.actor, body.actor_type,
         [{"field": f, "old": None, "new": _norm(getattr(inv, f))} for f in _DIFF_FIELDS if getattr(inv, f) not in (None, "", [], {})])
    db.commit()
    db.refresh(inv)
    return inv


@router.get("", response_model=list[InvestigationListItem])
def list_investigations(db: Session = Depends(get_db)) -> list[Investigation]:
    rows = db.execute(
        select(Investigation)
        .where(Investigation.status != "Void")
        .order_by(Investigation.updated_at.desc())
    ).scalars().all()
    return list(rows)


@router.get("/{inv_id}", response_model=InvestigationRead)
def get_investigation(inv_id: uuid.UUID, db: Session = Depends(get_db)) -> Investigation:
    return _get_or_404(db, inv_id)


@router.put("/{inv_id}", response_model=InvestigationRead)
def update_investigation(inv_id: uuid.UUID, body: InvestigationUpdate, db: Session = Depends(get_db)) -> Investigation:
    inv = _get_or_404(db, inv_id)
    _assert_unlocked(inv)
    if body.reference != inv.reference:
        _check_reference(db, body.reference, exclude_id=inv_id)

    before = _snapshot(inv)
    for field, value in body.model_dump(exclude_unset=True, exclude={"actor", "actor_type"}).items():
        setattr(inv, field, value)
    inv.updated_at = utcnow()

    changes = _diff(before, _snapshot(inv))
    if changes:
        _log(db, inv.id, "update", body.actor, body.actor_type, changes)
    db.commit()
    db.refresh(inv)
    return inv


@router.delete("/{inv_id}", status_code=204)
def delete_investigation(inv_id: uuid.UUID, db: Session = Depends(get_db)) -> None:
    """Void, never hard-delete: a GMP record and its audit trail must survive."""
    inv = _get_or_404(db, inv_id)
    _assert_unlocked(inv)

    before = _snapshot(inv)
    inv.status = "Void"
    inv.updated_at = utcnow()
    _log(db, inv.id, "void", "system", "User", _diff(before, _snapshot(inv)))
    db.commit()


@router.post("/{inv_id}/signoff", response_model=InvestigationRead)
def sign_off(inv_id: uuid.UUID, body: SignoffRequest, db: Session = Depends(get_db)) -> Investigation:
    """QP electronic signature: locks the record (subsequent PUT -> 409)."""
    inv = _get_or_404(db, inv_id)
    if inv.is_qp_verified:
        raise HTTPException(status_code=409, detail="Investigation is already QP-signed.")
    if inv.status == "Void":
        raise HTTPException(status_code=409, detail="Investigation is voided and cannot be signed off.")

    pending = _pending_ai_items(inv)
    if pending:
        sections = ", ".join(sorted({label.split("[")[0] for label in pending}))
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{len(pending)} AI item(s) are still pending review ({sections}). "
                "Accept, edit or reject every AI-generated item before QP sign-off."
            ),
        )

    before = _snapshot(inv)
    inv.is_qp_verified = True
    inv.qp_name = body.verifier_name
    inv.qp_role = body.role
    inv.qp_comments = body.comments or None
    inv.qp_signed_at = utcnow()
    inv.status = "Approved & Closed"
    inv.updated_at = utcnow()

    _log(db, inv.id, "signoff", body.verifier_name, "QP",
         _diff(before, _snapshot(inv)) + [
             {"field": "attestations", "old": None, "new": body.attestations},
         ])
    db.commit()
    db.refresh(inv)
    return inv


@router.post("/{inv_id}/reopen", response_model=InvestigationRead)
def reopen(inv_id: uuid.UUID, body: ReopenRequest, db: Session = Depends(get_db)) -> Investigation:
    """Audited unlock: clears QP verification, requires a reason."""
    inv = _get_or_404(db, inv_id)
    if not inv.is_qp_verified:
        raise HTTPException(status_code=409, detail="Investigation is not signed; nothing to reopen.")

    before = _snapshot(inv)
    inv.is_qp_verified = False
    inv.qp_name = None
    inv.qp_role = None
    inv.qp_comments = None
    inv.qp_signed_at = None
    inv.status = "Under Investigation"
    inv.updated_at = utcnow()

    _log(db, inv.id, "reopen", body.actor, body.actor_type,
         _diff(before, _snapshot(inv)) + [
             {"field": "reopen_reason", "old": None, "new": body.reason},
         ])
    db.commit()
    db.refresh(inv)
    return inv


@router.get("/{inv_id}/audit", response_model=list[AuditEntryRead])
def get_audit(inv_id: uuid.UUID, db: Session = Depends(get_db)) -> list[AuditLog]:
    _get_or_404(db, inv_id)
    rows = db.execute(
        select(AuditLog).where(AuditLog.investigation_id == inv_id).order_by(AuditLog.timestamp)
    ).scalars().all()
    return list(rows)
