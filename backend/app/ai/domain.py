"""ICH Q7 / GMP domain knowledge.

This module only GUIDES prompts and grounds verification (what categories
exist, which evidence types are typical). It is NEVER used as canned analysis:
every causal claim must still come from the source document.
"""
from __future__ import annotations

from app.utils.evidence import normalize

# Fishbone / Ishikawa 6M categories (exact labels used by the UI).
SIX_M: tuple[str, ...] = ("Man", "Machine", "Material", "Method", "Measurement", "Environment")

# Root cause categories used in the synthesis step.
ROOT_CAUSE_CATEGORIES: tuple[str, ...] = (
    "Equipment/Metrology",
    "Material",
    "Method/Procedure",
    "Human factors",
    "Environment",
    "Quality system",
)

SEVERITIES: tuple[str, ...] = ("Critical", "Major", "Minor")

INVESTIGATION_STATUSES: tuple[str, ...] = (
    "Draft", "Under Investigation", "Pending QP Review", "Approved & Closed",
)

# Typical evidence in API manufacturing investigations. Keys = display names,
# values = aliases used to detect whether the document actually mentions it.
EVIDENCE_TYPES: dict[str, tuple[str, ...]] = {
    "Batch manufacturing record": ("batch manufacturing record", "bmr", "batch record"),
    "Equipment logs": ("equipment log", "equipment logs", "equipment history", "logbook", "log book"),
    "Calibration records": ("calibration record", "calibration", "calibrat"),
    "SCADA/DCS trend data": ("scada", "dcs", "trend data", "trend chart", "trending"),
    "Maintenance records": ("maintenance record", "maintenance log", "maintenance", "repair record"),
    "Change controls": ("change control", "change request"),
    "Training records": ("training record", "training", "qualification record"),
    "Supplier CoA": ("certificate of analysis", "supplier coa", "coa"),
    "Lab/OOS investigation": ("oos", "out of specification", "lab investigation", "laboratory investigation"),
    "Environmental monitoring": ("environmental monitoring", "em data", "particulate"),
    "Operator interviews": ("operator interview", "interview", "operator statement"),
    "SOP / procedure": ("sop", "standard operating procedure", "procedure"),
}


def mentioned_evidence_types(text: str) -> list[str]:
    """Code-side detection (not the LLM) of which typical evidence types the
    document actually mentions. Used to guarantee that the missing-evidence
    list never claims something is missing when it is present."""
    lowered = normalize(text)
    mentioned: list[str] = []
    for name, aliases in EVIDENCE_TYPES.items():
        if any(normalize(alias) in lowered for alias in aliases):
            mentioned.append(name)
    return mentioned
