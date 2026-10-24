"""ORM models for aivoa-rca.

Tables
  investigations — one RCA record per deviation/incident.
  audit_logs     — field-level diff trail (actor: AI | User | QP).

Notes
  * JSONB is used on PostgreSQL and plain JSON on the SQLite dev fallback
    (`JSON().with_variant(JSONB(), "postgresql")`).
  * All datetimes are timezone-aware UTC, generated in Python so both
    PostgreSQL and SQLite store aware values.
  * QP fields (is_qp_verified, qp_*) are only ever written by the sign-off and
    reopen endpoints — see routers/investigations.py.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# JSONB on PostgreSQL, JSON elsewhere (SQLite dev fallback).
JSON_COL = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    """Timezone-aware UTC now (never naive)."""
    return datetime.now(timezone.utc)


class Investigation(Base):
    __tablename__ = "investigations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Deviation context (values come from the incident document / user edits).
    # `reference` is nullable on purpose: if the document does not state a
    # deviation reference we must NOT invent one.
    reference: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    batch_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    stage: Mapped[str | None] = mapped_column(String(255), nullable=True)
    equipment_area: Mapped[str | None] = mapped_column(String(255), nullable=True)
    incident_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reported_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(16), nullable=True)  # Critical|Major|Minor
    status: Mapped[str] = mapped_column(String(32), default="Draft", server_default="Draft")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    immediate_containment: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Also produced by extraction (kept as columns so "Apply to form" never loses data):
    detected_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quantity_affected: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # RCA content (JSON documents, schema-validated at the API layer).
    five_whys: Mapped[list | None] = mapped_column(JSON_COL, nullable=True)
    fishbone: Mapped[dict | None] = mapped_column(JSON_COL, nullable=True)
    root_cause: Mapped[dict | None] = mapped_column(JSON_COL, nullable=True)
    contributing_factors: Mapped[list | None] = mapped_column(JSON_COL, nullable=True)
    missing_evidence: Mapped[list | None] = mapped_column(JSON_COL, nullable=True)
    capas: Mapped[list | None] = mapped_column(JSON_COL, nullable=True)

    # Source document (verbatim text kept so every quote can be re-verified).
    source_document_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_document_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # QP electronic sign-off — server-managed only (see rule at top of file).
    is_qp_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    qp_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    qp_role: Mapped[str | None] = mapped_column(String(120), nullable=True)
    qp_comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    qp_signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    audit_logs: Mapped[list["AuditLog"]] = relationship(
        back_populates="investigation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AuditLog.timestamp",
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_investigation_id", "investigation_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("investigations.id", ondelete="CASCADE"),
        nullable=False,
    )
    actor: Mapped[str] = mapped_column(String(255), default="system")
    actor_type: Mapped[str] = mapped_column(String(8), default="User")  # AI | User | QP
    action: Mapped[str] = mapped_column(String(64))  # create | update | signoff | reopen | delete
    diff: Mapped[list] = mapped_column(JSON_COL, default=list)  # [{field, old, new}]
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    investigation: Mapped[Investigation] = relationship(back_populates="audit_logs")
