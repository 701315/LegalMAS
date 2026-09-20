# src/db/models/__init__.py

"""
Import all ORM models so Alembic can discover them for autogenerate.
"""

from .bundle import Bundle
from .calibration import ClassificationCalibration
from .check_result_persist_error import CheckResultPersistError
from .dd_request import DDRequest
from .deal import Deal
from .deal_member import DealMember
from .tenant import Tenant
from .user import User
from .document import Document, DocumentRunLanguageResolution, DocumentSegment, DocumentStageExecution, DocumentVersion
from .document_type_instruction import DocumentTypeInstructionVersion
from .export import Export
from .ops import AuditLog, DLQRecord, IdempotencyKey
from .outbox import OutboxMessage
from .playbook import ModelConfig, Playbook, PlaybookLineItem, PlaybookVersion
from .relation import DocumentFamily, DocumentFamilyMember, DocumentRelation
from .result import CheckResult, CheckResultPresentation
from .run import Job, Run
from .instruction_override import InstructionOverride
from .run_check_plan_item import RunCheckPlanItem
from .llm_usage import LLMUsageEvent
from .run_summary import RunSummary
from .global_instruction import GlobalInstructionVersion
from .tenant_result_locale_policy import TenantResultLocalePolicy
from .legal_glossary import LegalGlossary  # S3.1
from .instruction_presentation_localization import InstructionPresentationLocalization  # S4.1


__all__ = [
    "AuditLog",
    "Bundle",
    "CheckResult",
    "CheckResultPresentation",
    "CheckResultPersistError",
    "ClassificationCalibration",
    "DDRequest",
    "DLQRecord",
    "Deal",
    "DealMember",
    "Tenant",
    "User",
    "Document",
    "DocumentSegment",
    "DocumentStageExecution",
    "DocumentFamily",
    "DocumentFamilyMember",
    "DocumentRelation",
    "DocumentRunLanguageResolution",
    "DocumentVersion",
    "DocumentTypeInstructionVersion",
    "Export",
    "IdempotencyKey",
    "Job",
    "ModelConfig",
    "OutboxMessage",
    "Playbook",
    "PlaybookLineItem",
    "PlaybookVersion",
    "Run",
    "InstructionOverride",
    "RunCheckPlanItem",
    "LLMUsageEvent",
    "RunSummary",
    "GlobalInstructionVersion",
    "TenantResultLocalePolicy",
    "LegalGlossary",
    "InstructionPresentationLocalization",
]

