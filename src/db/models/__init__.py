"""
Import all models so Alembic can discover them for auto-migration.
"""

from db.models.bundle import Bundle
from db.models.calibration import ClassificationCalibration
from db.models.deal import Deal
from db.models.document import Document, DocumentVersion
from db.models.export import Export
from db.models.ops import AuditLog, DLQRecord, IdempotencyKey
from db.models.playbook import ModelConfig, PlaybookVersion
from db.models.relation import (
    DocumentFamily,
    DocumentFamilyMember,
    DocumentRelation,
)
from db.models.result import CheckResult
from db.models.run import Job, Run

__all__ = [
    "Deal",
    "Bundle",
    "Document",
    "DocumentVersion",
    "Family",
    "DocumentFamily",
    "DocumentFamilyMember",
    "DocumentRelation",
    "ModelConfig",
    "PlaybookVersion",
    "Run",
    "Job",
    "CheckResult",
    "Export",
    "IdempotencyKey",
    "AuditLog",
    "DLQRecord",
    "ClassificationCalibration",
]
