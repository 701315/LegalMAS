"""
Import all models so Alembic can discover them for auto-migration.
"""

from src.db.models.deal import Deal
from src.db.models.bundle import Bundle
from src.db.models.document import Document, DocumentVersion
from src.db.models.relation import Family, DocumentRelation
from src.db.models.playbook import ModelConfig, PlaybookVersion
from src.db.models.run import Run, Job
from src.db.models.result import CheckResult
from src.db.models.export import Export
from src.db.models.ops import IdempotencyKey, AuditLog, DLQRecord

__all__ = [
    "Deal",
    "Bundle",
    "Document",
    "DocumentVersion",
    "Family",
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
]
