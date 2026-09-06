from .document_run_language_resolution_repo import DocumentRunLanguageResolutionRepository
# src/db/repositories/__init__.py

"""
Public repository classes for the persistence layer.

Этот модуль даёт единый фасад для всех Repository-классов, чтобы
в остальном коде можно было писать:

    from db.repositories import DealRepository, DocumentRepository, RunRepository

а не импортировать каждый репозиторий из отдельного файла.
"""

from .audit_repo import AuditRepository
from .bundle_repo import BundleRepository
from .calibration_repo import CalibrationRepository
from .check_result_persist_error_repo import CheckResultPersistErrorRepository
from .check_result_presentation_repo import CheckResultPresentationRepository
from .check_result_repo import CheckResultRepository
from .dd_request_repo import DDRequestRepository
from .deal_repo import DealRepository
from .document_repo import DocumentRepository
from .document_segment_repo import DocumentSegmentRepository
from .document_stage_execution_repo import DocumentStageExecutionRepository
from .document_type_instruction_version_repo import DocumentTypeInstructionVersionRepository
from .document_version_repo import DocumentVersionRepository
from .export_repo import ExportRepository
from .idempotency_repo import IdempotencyRepository
from .outbox import OutboxRepository
from .playbook_repo import PlaybookRepository
from .project_role_repo import ProjectRoleRepository
from .relation_repo import RelationRepository
from .result_repo import ResultRepository
from .run_repo import JobRepository, RunRepository
from .runner_repo import RunnerRepository

__all__ = [
    "AuditRepository",
    "BundleRepository",
    "CalibrationRepository",
    "DDRequestRepository",
    "DealRepository",
    "DocumentRepository",
    "DocumentSegmentRepository",
    "DocumentStageExecutionRepository",
    "DocumentTypeInstructionVersionRepository",
    "DocumentVersionRepository",
    "DocumentRunLanguageResolutionRepository",
    "ExportRepository",
    "IdempotencyRepository",
    "OutboxRepository",
    "PlaybookRepository",
    "ProjectRoleRepository",
    "RelationRepository",
    "ResultRepository",
    "RunRepository",
    "JobRepository",
    "RunnerRepository",
    "CheckResultPersistErrorRepository",
    "CheckResultPresentationRepository",
    "CheckResultRepository",
]
