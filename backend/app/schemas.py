"""Pydantic v2 request/response schemas.

Split by concern:
  * investigation CRUD / sign-off / audit   (this file section)
  * AI extraction & analysis schemas        (app/schemas.py, AI section)
  * LangGraph structured-output contracts   (app/schemas.py, LangGraph section)

Server-side safety rules implemented here:
  * `extra="ignore"` on update => client-supplied is_qp_verified / qp_* /
    status can never be written through the normal CRUD path.
  * Severity and Status are closed Literals.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["Critical", "Major", "Minor"]
InvestigationStatus = Literal[
    "Draft", "Under Investigation", "Pending QP Review", "Approved & Closed", "Void"
]
ActorType = Literal["AI", "User", "QP"]


class InvestigationCreate(BaseModel):
    """POST /api/investigations — context fields only.

    Deliberately has NO is_qp_verified / qp_* / status fields: the server
    creates records as Draft with verification cleared.
    """

    model_config = ConfigDict(extra="ignore")

    reference: Optional[str] = None
    title: Optional[str] = Field(default=None, max_length=500)
    product_name: Optional[str] = None
    batch_number: Optional[str] = None
    stage: Optional[str] = None
    equipment_area: Optional[str] = None
    incident_datetime: Optional[datetime] = None
    reported_by: Optional[str] = None
    severity: Optional[Severity] = None
    description: Optional[str] = None
    immediate_containment: Optional[str] = None
    detected_by: Optional[str] = None
    quantity_affected: Optional[str] = None

    five_whys: Optional[list] = None
    fishbone: Optional[dict] = None
    root_cause: Optional[dict] = None
    contributing_factors: Optional[list] = None
    missing_evidence: Optional[list] = None
    capas: Optional[list] = None

    source_document_text: Optional[str] = None
    source_document_name: Optional[str] = None
    ai_summary: Optional[str] = None

    # Who is saving (used for the audit trail). Never used for QP fields.
    actor: str = "system"
    actor_type: ActorType = "User"


class InvestigationUpdate(BaseModel):
    """PUT /api/investigations/{id} — partial update.

    extra="ignore" is the enforcement of rule 7: even if a client sends
    {"is_qp_verified": true, "qp_name": "...", "status": "Approved & Closed"}
    those keys are dropped and never reach the ORM.
    """

    model_config = ConfigDict(extra="ignore")

    reference: Optional[str] = None
    title: Optional[str] = Field(default=None, max_length=500)
    product_name: Optional[str] = None
    batch_number: Optional[str] = None
    stage: Optional[str] = None
    equipment_area: Optional[str] = None
    incident_datetime: Optional[datetime] = None
    reported_by: Optional[str] = None
    severity: Optional[Severity] = None
    description: Optional[str] = None
    immediate_containment: Optional[str] = None
    detected_by: Optional[str] = None
    quantity_affected: Optional[str] = None

    five_whys: Optional[list] = None
    fishbone: Optional[dict] = None
    root_cause: Optional[dict] = None
    contributing_factors: Optional[list] = None
    missing_evidence: Optional[list] = None
    capas: Optional[list] = None

    source_document_text: Optional[str] = None
    source_document_name: Optional[str] = None
    ai_summary: Optional[str] = None

    actor: str = "system"
    actor_type: ActorType = "User"


class SignoffRequest(BaseModel):
    """POST /api/investigations/{id}/signoff — QP electronic signature."""

    model_config = ConfigDict(extra="ignore")

    verifier_name: str = Field(min_length=1, max_length=255)
    role: str = Field(min_length=1, max_length=120)
    comments: str = ""
    attestations: list[str] = Field(min_length=1)


class ReopenRequest(BaseModel):
    """POST /api/investigations/{id}/reopen — audited unlock."""

    model_config = ConfigDict(extra="ignore")

    reason: str = Field(min_length=1, max_length=1000)
    actor: str = "system"
    actor_type: ActorType = "User"


class InvestigationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reference: Optional[str] = None
    title: Optional[str] = None
    product_name: Optional[str] = None
    batch_number: Optional[str] = None
    stage: Optional[str] = None
    equipment_area: Optional[str] = None
    incident_datetime: Optional[datetime] = None
    reported_by: Optional[str] = None
    severity: Optional[Severity] = None
    status: InvestigationStatus
    description: Optional[str] = None
    immediate_containment: Optional[str] = None
    detected_by: Optional[str] = None
    quantity_affected: Optional[str] = None

    five_whys: Optional[list] = None
    fishbone: Optional[dict] = None
    root_cause: Optional[dict] = None
    contributing_factors: Optional[list] = None
    missing_evidence: Optional[list] = None
    capas: Optional[list] = None

    source_document_text: Optional[str] = None
    source_document_name: Optional[str] = None
    ai_summary: Optional[str] = None

    is_qp_verified: bool
    qp_name: Optional[str] = None
    qp_role: Optional[str] = None
    qp_comments: Optional[str] = None
    qp_signed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class InvestigationListItem(BaseModel):
    """Compact row for the saved-investigations list."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reference: Optional[str] = None
    title: Optional[str] = None
    product_name: Optional[str] = None
    batch_number: Optional[str] = None
    severity: Optional[Severity] = None
    status: InvestigationStatus
    is_qp_verified: bool
    updated_at: datetime


class AuditEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    investigation_id: uuid.UUID
    actor: str
    actor_type: ActorType
    action: str
    diff: list
    timestamp: datetime


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    dialect: str                 # from engine.dialect.name — the real dialect
    db_fallback: bool            # True only for the SQLite dev fallback
    db_ok: bool
    groq_configured: bool
    model: str
    server_time: datetime


# ============================================================================
# AI schemas
# ============================================================================

Confidence = Literal["Low", "Medium", "High"]


class ExtractedField(BaseModel):
    """One extracted value with its verbatim source quote (LLM output shape)."""

    value: Optional[str] = Field(default=None, description="Verbatim value from the document, or null if not stated.")
    source_quote: Optional[str] = Field(default=None, description="Short verbatim snippet supporting the value, or null.")
    confidence: Confidence = Field(default="Low", description="High = explicit verbatim, Medium = explicit but ambiguous, Low = unclear.")


class ExtractionResult(BaseModel):
    """Structured output of the extraction node.

    Invariant enforced by app/ai/extraction.py after generation: every value
    and quote must be locatable in the source text, otherwise it is dropped
    and reported as "Not stated in document".
    """

    deviation_reference: ExtractedField = Field(description="Deviation/incident record number exactly as written (e.g. DEV-2026-014). Null if not stated.")
    title: ExtractedField = Field(description="Short factual title/subject of the incident. Null if not stated.")
    product_name: ExtractedField = Field(description="API / product name exactly as written (include grade/USP suffix if present).")
    batch_number: ExtractedField = Field(description="Batch/lot number exactly as written.")
    manufacturing_stage: ExtractedField = Field(description="Processing stage where the event occurred (e.g. 'final drying', 'blending').")
    equipment_or_area: ExtractedField = Field(description="Equipment ID or area referenced for the event.")
    incident_datetime: ExtractedField = Field(description="Date/time of the incident as ISO-8601 (YYYY-MM-DD or YYYY-MM-DDTHH:MM) ONLY if the document states it.")
    reported_by: ExtractedField = Field(description="Person who reported the incident (for emails: typically the sender).")
    severity_suggested: ExtractedField = Field(description="Severity only if the document suggests one (Critical/Major/Minor or equivalent wording).")
    description: ExtractedField = Field(description="Factual description of the event, copied verbatim/condensed from the document.")
    immediate_containment: ExtractedField = Field(description="Immediate containment/quarantine action stated in the document.")
    detected_by: ExtractedField = Field(description="Who/what detected the problem (e.g. 'QC analyst during release testing').")
    quantity_affected: ExtractedField = Field(description="Quantity/batch amount affected, exactly as stated (e.g. '4 drums', '200 kg').")


EXTRACTION_FIELDS: tuple[str, ...] = tuple(ExtractionResult.model_fields.keys())

# extraction field -> investigation column / frontend draft key
EXTRACT_TO_FORM: dict[str, str] = {
    "deviation_reference": "reference",
    "title": "title",
    "product_name": "product_name",
    "batch_number": "batch_number",
    "manufacturing_stage": "stage",
    "equipment_or_area": "equipment_area",
    "incident_datetime": "incident_datetime",
    "reported_by": "reported_by",
    "severity_suggested": "severity",
    "description": "description",
    "immediate_containment": "immediate_containment",
    "detected_by": "detected_by",
    "quantity_affected": "quantity_affected",
}


class ExtractionFieldOut(BaseModel):
    """Verified extraction field returned to the UI."""

    value: Optional[str] = None
    source_quote: Optional[str] = None
    confidence: Confidence = "Low"
    value_verified: bool = False   # value located in the source text by code
    quote_verified: bool = False   # quote located in the source text by code
    not_stated: bool = True        # convenience: value is None => "Not stated in document"


class ExtractionResponse(BaseModel):
    fields: dict[str, ExtractionFieldOut]
    email_context: Optional[dict] = None   # From/Subject/Date when input was an email
    source_kind: str = "text"              # pdf | email | text
    source_text: str = ""                  # parsed text; needed to run/verify the analysis
    truncated: bool = False
    warning: Optional[str] = None
    model: str
    text_length: int = 0


class ExtractRequest(BaseModel):
    """JSON body of POST /api/ai/extract (the multipart variant sends a file)."""

    model_config = ConfigDict(extra="ignore")

    text: Optional[str] = None                 # pasted text or pasted email
    source_document_name: Optional[str] = None
    model: Optional[str] = None                # allowlisted client model choice


class AnalyzeRequest(BaseModel):
    """Body of POST /api/ai/analyze/stream."""

    model_config = ConfigDict(extra="ignore")

    source_text: str = Field(min_length=1, description="Verbatim source document text (already extracted from PDF/email if any).")
    source_document_name: Optional[str] = None
    context: dict[str, Optional[str]] = Field(
        default_factory=dict,
        description="Current RCA form values; when non-empty the graph reuses them instead of re-extracting.",
    )
    model: Optional[str] = None  # allowlisted client model choice


class ValidateKeyResponse(BaseModel):
    ok: bool
    model: str
    detail: str


# ============================================================================
# LangGraph structured-output contracts (one per analysis node)
# ============================================================================

SixMCategory = Literal["Man", "Machine", "Material", "Method", "Measurement", "Environment"]
RootCauseCategory = Literal[
    "Equipment/Metrology", "Material", "Method/Procedure", "Human factors", "Environment", "Quality system"
]


class WhyStepIn(BaseModel):
    """One 5-Whys link. `status` is deliberately NOT part of the LLM output:
    it is computed in code from evidence verification."""

    level: int = Field(ge=1, le=8)
    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    evidence_quote: Optional[str] = Field(default=None, description="Verbatim quote from the document supporting the answer, or null when there is no direct documentary evidence.")


class FiveWhysResult(BaseModel):
    steps: list[WhyStepIn] = Field(min_length=2, max_length=6, description="3-6 levels in most cases; fewer only when evidence runs out. Never pad.")


class FishboneFactorIn(BaseModel):
    category: SixMCategory
    cause: str = Field(min_length=1)
    subcauses: list[str] = Field(default_factory=list)
    impact: str = ""
    evidence_quote: Optional[str] = Field(default=None, description="Verbatim quote when the document supports this factor, else null (it will be labelled 'Needs investigation').")
    root_cause_candidate: bool = False


class FishboneResult(BaseModel):
    factors: list[FishboneFactorIn] = Field(max_length=24)


class ContributingFactorIn(BaseModel):
    text: str = Field(min_length=1)
    category: RootCauseCategory
    evidence_quote: Optional[str] = None


class RootCauseSuggestion(BaseModel):
    primary_root_cause: str = Field(min_length=1)
    category: RootCauseCategory
    confidence: Confidence
    contributing_factors: list[ContributingFactorIn] = Field(max_length=8)


class EvidenceGapIn(BaseModel):
    item: str = Field(min_length=1, description="Evidence type needed to confirm/refute the root cause.")
    why_needed: str
    suggested_action: str
    priority: Literal["High", "Medium", "Low"]


class GapAnalysisResult(BaseModel):
    mentioned: list[str] = Field(default_factory=list, description="Evidence types the document actually mentions.")
    gaps: list[EvidenceGapIn] = Field(max_length=15, description="Only evidence that is genuinely NOT in the document.")


class CapaIn(BaseModel):
    type: Literal["Corrective", "Preventive"]
    description: str = Field(min_length=1)
    linked_cause: str = Field(description="The specific cause (verbatim fragment) this action addresses.")
    rationale: str = Field(description="Short explanation linked to that cause.")
    owner_role: str
    department: str
    target_days_from_now: int = Field(ge=1, le=365, description="Relative due date; the server converts it to a real calendar date.")
    voe_plan: str = Field(description="Measurable Verification of Effectiveness plan.")


class CapaResult(BaseModel):
    capas: list[CapaIn] = Field(min_length=1, max_length=10)
