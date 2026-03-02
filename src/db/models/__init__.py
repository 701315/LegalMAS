"""
Import all models so Alembic can discover them for auto-migration.
"""

from src.db.models.bundle import Bundle
from src.db.models.calibration import ClassificationCalibration
from src.db.models.deal import Deal
from src.db.models.document import Document, DocumentVersion
from src.db.models.export import Export
from src.db.models.ops import AuditLog, DLQRecord, IdempotencyKey
from src.db.models.playbook import ModelConfig, PlaybookVersion
from src.db.models.relation import (
    DocumentFamily,
    DocumentFamilyMember,
    DocumentRelation,
)
from src.db.models.result import CheckResult
from src.db.models.run import Job, Run

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
