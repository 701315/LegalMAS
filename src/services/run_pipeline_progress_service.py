# src/services/run_pipeline_progress_service.py

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.runs import (
    PipelineStepResponse,
    PipelineSubstepResponse,
    RunPipelineProgressResponse,
    StageSubProgressResponse,
)
from core.constants import DocumentStatus
from db.models.document import Document, DocumentStageExecution
from db.models.run import Run
from db.repositories.document_stage_execution_repo import DocumentStageExecutionRepository

TASK_TO_STEP = {
    "workers.build_primary_language_source": "document_preparation",
    "workers.extract_document": "document_preparation",
    "pii.sanitize_document": "document_preparation",
    "workers.build_structure": "document_structure",
    "workers.build_chunks": "document_structure",
    "workers.classify_document": "document_classification",
    "workers.classify_document_segments": "document_classification",
    "workers.build_legal_units_enrichment": "semantic_enrichment",
}

PIPELINE_STEPS_ORDER = [
    "document_preparation",
    "document_structure",
    "document_classification",
    "semantic_enrichment",
    "deal_checks",
    "finalization",
]

STEP_TITLES = {
    "document_preparation": "Подготовка документа",
    "document_structure": "Построение структуры",
    "document_classification": "Классификация",
    "semantic_enrichment": "Семантическое обогащение",
    "deal_checks": "DD-проверки",
    "finalization": "Финализация",
}

STEP_TASKS = {
    "document_preparation": [
        "workers.build_primary_language_source",
        "workers.extract_document",
        "pii.sanitize_document",
    ],
    "document_structure": [
        "workers.build_structure",
        "workers.build_chunks",
    ],
    "document_classification": [
        "workers.classify_document",
        "workers.classify_document_segments",
    ],
    "semantic_enrichment": [
        "workers.build_legal_units_enrichment",
    ],
}

SUBSTEP_TITLES = {
    "workers.build_primary_language_source": "Подготовка основного источника",
    "workers.extract_document": "Извлечение текста",
    "pii.sanitize_document": "Санитизация документа",
    "workers.build_structure": "Построение структуры",
    "workers.build_chunks": "Построение чанков",
    "workers.classify_document": "Классификация документа",
    "workers.classify_document_segments": "Классификация сегментов",
    "workers.build_legal_units_enrichment": "Обогащение semantic-блоков",
}

ACTIVE_EXECUTION_STATUSES = {"planned", "dispatched", "started"}
TERMINAL_EXECUTION_STATUSES = {"succeeded", "failed", "cancelled"}
TERMINAL_RUN_STATUSES = {"completed", "completed_with_errors", "failed"}

DOC_STATUS_RANK = {
    "pending": 0,
    "primary_ready": 1,
    "extracted": 2,
    "sanitized": 3,
    "structured": 4,
    "chunked": 5,
    "classified": 6,
    "enriched": 7,
    "completed": 8,
}

STEP_REQUIRED_STATUS_RANK = {
    "document_preparation": DOC_STATUS_RANK["sanitized"],
    "document_structure": DOC_STATUS_RANK["chunked"],
    "document_classification": DOC_STATUS_RANK["classified"],
    "semantic_enrichment": DOC_STATUS_RANK["enriched"],
}


@dataclass(slots=True)
class _DocumentSnapshot:
    id: uuid.UUID
    name: str | None
    status: str | None


class RunPipelineProgressService:
    STALE_THRESHOLD_MINUTES = 15

    def __init__(self, db: AsyncSession):
        self.db = db

    async def build_progress(self, run: Run) -> RunPipelineProgressResponse:
        now = datetime.now(UTC)

        dse_repo = DocumentStageExecutionRepository(self.db)
        executions = await dse_repo.list_by_run(run.id)
        documents = await self._load_documents_for_deal(run.deal_id)

        for execution in executions:
            if execution.document_id not in documents:
                documents[execution.document_id] = _DocumentSnapshot(
                    id=execution.document_id,
                    name=None,
                    status=None,
                )

        executions_by_step: dict[str, list[DocumentStageExecution]] = defaultdict(list)
        executions_by_task: dict[str, list[DocumentStageExecution]] = defaultdict(list)

        for execution in executions:
            step_code = TASK_TO_STEP.get(execution.task_name)
            if not step_code:
                continue
            executions_by_step[step_code].append(execution)
            executions_by_task[execution.task_name].append(execution)

        steps: list[PipelineStepResponse] = []

        for step_code in (
            "document_preparation",
            "document_structure",
            "document_classification",
            "semantic_enrichment",
        ):
            step = self._build_document_step(
                step_code=step_code,
                documents=documents,
                step_executions=executions_by_step.get(step_code, []),
                executions_by_task=executions_by_task,
                now=now,
            )
            steps.append(step)

        steps.append(self._build_deal_checks_step(run=run, documents=documents, now=now))
        steps.append(self._build_finalization_step(run=run, documents=documents, now=now))

        active_step_codes = [step.code for step in steps if step.status == "running"]
        current_step = self._pick_current_step(steps=steps, run_status=run.status)

        last_activity_at = self._compute_last_activity_at(run=run, executions=executions)
        is_stale = (
            run.status == "running"
            and last_activity_at is not None
            and (now - last_activity_at).total_seconds() > self.STALE_THRESHOLD_MINUTES * 60
        )

        documents_total = len(documents)
        documents_failed = sum(
            1 for doc in documents.values() if doc.status == DocumentStatus.FAILED.value
        )
        documents_quarantine = sum(
            1 for doc in documents.values() if doc.status == DocumentStatus.QUARANTINE.value
        )

        return RunPipelineProgressResponse(
            run_id=run.id,
            deal_id=run.deal_id,
            run_status=run.status,
            started_at=run.started_at,
            completed_at=run.completed_at,
            elapsed_seconds=self._duration_seconds(run.started_at, run.completed_at, now),
            last_activity_at=last_activity_at,
            is_stale=is_stale,
            stale_threshold_minutes=self.STALE_THRESHOLD_MINUTES,
            documents_total=documents_total,
            documents_failed=documents_failed,
            documents_quarantine=documents_quarantine,
            current_step_code=current_step.code if current_step else None,
            current_step_title=current_step.title if current_step else None,
            active_step_codes=active_step_codes,
            steps=steps,
        )

    async def _load_documents_for_deal(self, deal_id: uuid.UUID) -> dict[uuid.UUID, _DocumentSnapshot]:
        result = await self.db.execute(
            select(Document.id, Document.filename, Document.status).where(Document.deal_id == deal_id)
        )
        rows = result.all()

        return {
            row.id: _DocumentSnapshot(
                id=row.id,
                name=row.filename,
                status=row.status,
            )
            for row in rows
        }

    def _build_document_step(
        self,
        *,
        step_code: str,
        documents: dict[uuid.UUID, _DocumentSnapshot],
        step_executions: list[DocumentStageExecution],
        executions_by_task: dict[str, list[DocumentStageExecution]],
        now: datetime,
    ) -> PipelineStepResponse:
        doc_statuses = self._build_document_statuses_for_step(
            step_code=step_code,
            documents=documents,
            step_executions=step_executions,
        )

        documents_total = len(documents)
        documents_completed = sum(1 for status in doc_statuses.values() if status == "completed")
        documents_running = sum(1 for status in doc_statuses.values() if status == "running")
        documents_failed = sum(1 for status in doc_statuses.values() if status == "failed")

        step_status = self._aggregate_step_status(list(doc_statuses.values()))
        started_at = self._min_started_at(step_executions)
        finished_at = self._max_finished_at(step_executions) if self._is_step_terminal(step_status) else None
        duration_seconds = self._duration_seconds(started_at, finished_at, now)

        substeps = self._build_substeps(
            step_code=step_code,
            executions_by_task=executions_by_task,
            inferred_step_status=step_status,
            now=now,
        )

        return PipelineStepResponse(
            code=step_code,
            title=STEP_TITLES[step_code],
            status=step_status,
            documents_total=documents_total,
            documents_completed=documents_completed,
            documents_running=documents_running,
            documents_failed=documents_failed,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=duration_seconds,
            message=self._build_step_message(step_code=step_code, status=step_status),
            error_message=self._extract_latest_error_message(step_executions),
            substeps=substeps,
            sub_progress=self._extract_sub_progress(step_executions, documents),
        )

    def _build_deal_checks_step(
        self,
        *,
        run: Run,
        documents: dict[uuid.UUID, _DocumentSnapshot],
        now: datetime,
    ) -> PipelineStepResponse:
        documents_total = len(documents)
        documents_failed = sum(
            1 for doc in documents.values() if doc.status in (DocumentStatus.FAILED.value, DocumentStatus.QUARANTINE.value)
        )

        if run.total_checks == 0:
            status = "pending"
            documents_completed = 0
            documents_running = 0
        elif run.status == "running":
            status = "running"
            documents_completed = 0
            documents_running = documents_total
        elif run.status == "completed":
            status = "completed"
            documents_completed = documents_total
            documents_running = 0
        elif run.status == "completed_with_errors":
            status = "completed_with_errors"
            documents_completed = max(documents_total - documents_failed, 0)
            documents_running = 0
        elif run.status == "failed":
            status = "failed"
            documents_completed = 0
            documents_running = 0
        else:
            status = "pending"
            documents_completed = 0
            documents_running = 0

        return PipelineStepResponse(
            code="deal_checks",
            title=STEP_TITLES["deal_checks"],
            status=status,
            documents_total=documents_total,
            documents_completed=documents_completed,
            documents_running=documents_running,
            documents_failed=documents_failed,
            started_at=None,
            finished_at=run.completed_at if run.status in TERMINAL_RUN_STATUSES else None,
            duration_seconds=None,
            message=self._build_step_message(step_code="deal_checks", status=status),
            error_message=self._extract_error_message(getattr(run, "error_details", None)),
            substeps=[],
            sub_progress=StageSubProgressResponse(
                kind="checks",
                current=int(getattr(run, "completed_checks", 0) or 0),
                total=int(getattr(run, "total_checks", 0) or 0),
                updated_at=run.completed_at if run.status in TERMINAL_RUN_STATUSES else run.started_at,
            ),
        )

    def _build_finalization_step(
        self,
        *,
        run: Run,
        documents: dict[uuid.UUID, _DocumentSnapshot],
        now: datetime,
    ) -> PipelineStepResponse:
        documents_total = len(documents)
        documents_failed = sum(
            1 for doc in documents.values() if doc.status in (DocumentStatus.FAILED.value, DocumentStatus.QUARANTINE.value)
        )

        if run.status == "completed":
            status = "completed"
        elif run.status == "completed_with_errors":
            status = "completed_with_errors"
        elif run.status == "failed":
            status = "failed"
        else:
            status = "pending"

        return PipelineStepResponse(
            code="finalization",
            title=STEP_TITLES["finalization"],
            status=status,
            documents_total=documents_total,
            documents_completed=documents_total if status in {"completed", "completed_with_errors"} else 0,
            documents_running=0,
            documents_failed=documents_failed if status in {"completed_with_errors", "failed"} else 0,
            started_at=run.completed_at if status in TERMINAL_RUN_STATUSES else None,
            finished_at=run.completed_at if status in TERMINAL_RUN_STATUSES else None,
            duration_seconds=0 if status in TERMINAL_RUN_STATUSES and run.completed_at else None,
            message=self._build_step_message(step_code="finalization", status=status),
            error_message=self._extract_error_message(getattr(run, "error_details", None)),
            substeps=[],
            sub_progress=None,
        )

    def _build_document_statuses_for_step(
        self,
        *,
        step_code: str,
        documents: dict[uuid.UUID, _DocumentSnapshot],
        step_executions: list[DocumentStageExecution],
    ) -> dict[uuid.UUID, str]:
        executions_by_document: dict[uuid.UUID, list[DocumentStageExecution]] = defaultdict(list)
        for execution in step_executions:
            executions_by_document[execution.document_id].append(execution)

        statuses: dict[uuid.UUID, str] = {}

        for document_id, document in documents.items():
            doc_executions = executions_by_document.get(document_id, [])
            if doc_executions:
                statuses[document_id] = self._aggregate_document_execution_status(doc_executions)
            else:
                statuses[document_id] = self._infer_document_status_from_current_state(
                    document_status=document.status,
                    step_code=step_code,
                )

        return statuses

    def _aggregate_document_execution_status(
        self,
        executions: list[DocumentStageExecution],
    ) -> str:
        statuses = {execution.status for execution in executions}

        if statuses & ACTIVE_EXECUTION_STATUSES:
            return "running"

        if statuses and statuses <= {"succeeded"}:
            return "completed"

        if statuses & {"failed", "cancelled"}:
            return "failed"

        return "pending"

    def _infer_document_status_from_current_state(
        self,
        *,
        document_status: str | None,
        step_code: str,
    ) -> str:
        if not document_status:
            return "pending"

        if document_status in {DocumentStatus.FAILED.value, DocumentStatus.QUARANTINE.value}:
            return "failed"

        required_rank = STEP_REQUIRED_STATUS_RANK.get(step_code)
        current_rank = DOC_STATUS_RANK.get(document_status, 0)

        if required_rank is not None and current_rank >= required_rank:
            return "completed"

        return "pending"

    def _aggregate_step_status(self, document_statuses: list[str]) -> str:
        if not document_statuses:
            return "pending"

        if any(status == "running" for status in document_statuses):
            return "running"

        if all(status == "pending" for status in document_statuses):
            return "pending"

        if all(status == "completed" for status in document_statuses):
            return "completed"

        if any(status == "failed" for status in document_statuses):
            if any(status == "completed" for status in document_statuses):
                return "completed_with_errors"
            return "failed"

        if any(status == "completed" for status in document_statuses) and any(
            status == "pending" for status in document_statuses
        ):
            return "running"

        return "pending"

    def _build_substeps(
        self,
        *,
        step_code: str,
        executions_by_task: dict[str, list[DocumentStageExecution]],
        inferred_step_status: str,
        now: datetime,
    ) -> list[PipelineSubstepResponse]:
        substeps: list[PipelineSubstepResponse] = []
        step_tasks = STEP_TASKS.get(step_code, [])

        no_rows_for_step = all(not executions_by_task.get(task_name) for task_name in step_tasks)

        for task_name in step_tasks:
            executions = executions_by_task.get(task_name, [])

            if not executions and no_rows_for_step and inferred_step_status == "completed":
                substeps.append(
                    PipelineSubstepResponse(
                        code=task_name,
                        title=SUBSTEP_TITLES[task_name],
                        status="completed",
                        started_at=None,
                        finished_at=None,
                        duration_seconds=None,
                        error_message=None,
                    )
                )
                continue

            substep_status = self._aggregate_substep_status(executions)
            started_at = self._min_started_at(executions)
            finished_at = self._max_finished_at(executions) if substep_status in {"completed", "failed", "cancelled"} else None

            substeps.append(
                PipelineSubstepResponse(
                    code=task_name,
                    title=SUBSTEP_TITLES[task_name],
                    status=substep_status,
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_seconds=self._duration_seconds(started_at, finished_at, now),
                    error_message=self._extract_latest_error_message(executions),
                )
            )

        return substeps

    def _aggregate_substep_status(self, executions: list[DocumentStageExecution]) -> str:
        if not executions:
            return "planned"

        statuses = {execution.status for execution in executions}

        if statuses & ACTIVE_EXECUTION_STATUSES:
            return "running"

        if statuses and statuses <= {"succeeded"}:
            return "completed"

        if "failed" in statuses:
            return "failed"

        if "cancelled" in statuses:
            return "cancelled"

        return "planned"

    def _extract_sub_progress(
        self,
        executions: list[DocumentStageExecution],
        documents: dict[uuid.UUID, _DocumentSnapshot],
    ) -> StageSubProgressResponse | None:
        candidates: list[tuple[datetime, dict[str, Any]]] = []

        for execution in executions:
            payload = getattr(execution, "progress_details", None)
            if not isinstance(payload, dict):
                continue

            updated_at = self._parse_datetime(payload.get("updated_at"))
            if updated_at is None:
                updated_at = self._latest_execution_activity(execution)

            if updated_at is None:
                continue

            candidates.append((updated_at, payload))

        if not candidates:
            return None

        _, payload = max(candidates, key=lambda item: item[0])

        kind = str(payload.get("kind") or "documents")
        if kind not in {"legal_units", "segments", "checks", "documents"}:
            kind = "documents"

        current_document_id = self._string_or_none(payload.get("current_document_id"))
        current_document_name = self._string_or_none(payload.get("current_document_name"))

        if current_document_id and not current_document_name:
            try:
                doc_uuid = uuid.UUID(current_document_id)
                current_document_name = documents.get(doc_uuid).name if documents.get(doc_uuid) else None
            except (ValueError, TypeError):
                current_document_name = None

        return StageSubProgressResponse(
            kind=kind,
            current=self._int_or_zero(payload.get("current")),
            total=self._int_or_zero(payload.get("total")),
            total_units_in_document=self._optional_int(payload.get("total_units_in_document")),
            current_document_id=current_document_id,
            current_document_name=current_document_name,
            current_segment_id=self._string_or_none(payload.get("current_segment_id")),
            current_segment_title=self._string_or_none(payload.get("current_segment_title")),
            current_unit_label=self._string_or_none(payload.get("current_unit_label")),
            updated_at=self._parse_datetime(payload.get("updated_at")),
        )

    def _pick_current_step(
        self,
        *,
        steps: list[PipelineStepResponse],
        run_status: str,
    ) -> PipelineStepResponse | None:
        for step in steps:
            if step.status == "running":
                return step

        if run_status in TERMINAL_RUN_STATUSES:
            for step in reversed(steps):
                if step.status != "pending":
                    return step
            return None

        for step in steps:
            if step.status == "pending":
                return step

        return None

    def _compute_last_activity_at(
        self,
        *,
        run: Run,
        executions: list[DocumentStageExecution],
    ) -> datetime | None:
        candidates: list[datetime] = []

        if run.completed_at is not None:
            candidates.append(run.completed_at)
        if run.started_at is not None:
            candidates.append(run.started_at)

        for execution in executions:
            latest = self._latest_execution_activity(execution)
            if latest is not None:
                candidates.append(latest)

        return max(candidates) if candidates else None

    def _latest_execution_activity(self, execution: DocumentStageExecution) -> datetime | None:
        candidates: list[datetime] = []

        progress_details = getattr(execution, "progress_details", None)
        if isinstance(progress_details, dict):
            progress_updated = self._parse_datetime(progress_details.get("updated_at"))
            if progress_updated is not None:
                candidates.append(progress_updated)

        for attr_name in ("finished_at", "started_at", "updated_at", "created_at"):
            value = getattr(execution, attr_name, None)
            if isinstance(value, datetime):
                candidates.append(value)

        return max(candidates) if candidates else None

    def _extract_latest_error_message(self, executions: list[DocumentStageExecution]) -> str | None:
        ordered = sorted(
            executions,
            key=lambda execution: self._latest_execution_activity(execution) or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )

        for execution in ordered:
            message = self._extract_error_message(getattr(execution, "error_details", None))
            if message:
                return message

        return None

    def _extract_error_message(self, error_details: Any) -> str | None:
        if not isinstance(error_details, dict):
            return None

        message = error_details.get("message")
        if message:
            return str(message)

        reason = error_details.get("reason")
        if reason:
            return str(reason)

        return None

    def _build_step_message(self, *, step_code: str, status: str) -> str | None:
        if step_code == "semantic_enrichment" and status == "running":
            return "Этот этап может занимать длительное время"

        if step_code == "deal_checks" and status == "pending":
            return "Начнётся после завершения предыдущих этапов"

        if step_code == "finalization" and status == "pending":
            return "Будет выполнена после завершения проверок"

        if status == "completed_with_errors":
            return "Часть документов завершилась с ошибками"

        if status == "failed":
            return "Этап завершился ошибкой"

        if status == "pending":
            return "Ожидает запуска"

        return None

    def _min_started_at(self, executions: list[DocumentStageExecution]) -> datetime | None:
        values = [execution.started_at for execution in executions if execution.started_at is not None]
        return min(values) if values else None

    def _max_finished_at(self, executions: list[DocumentStageExecution]) -> datetime | None:
        values = [execution.finished_at for execution in executions if execution.finished_at is not None]
        return max(values) if values else None

    def _is_step_terminal(self, status: str) -> bool:
        return status in {"completed", "completed_with_errors", "failed"}

    def _duration_seconds(
        self,
        started_at: datetime | None,
        finished_at: datetime | None,
        now: datetime,
    ) -> int | None:
        if started_at is None:
            return None

        end = finished_at or now
        delta = end - started_at
        return max(int(delta.total_seconds()), 0)

    def _parse_datetime(self, value: Any) -> datetime | None:
        if not value:
            return None

        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=UTC)

        if not isinstance(value, str):
            return None

        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)

        return parsed

    def _int_or_zero(self, value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _optional_int(self, value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _string_or_none(self, value: Any) -> str | None:
        if value is None:
            return None
        return str(value)


        