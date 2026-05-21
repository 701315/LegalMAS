# src/db/repositories/document_stage_execution_repo.py

"""
Repository for DocumentStageExecution lifecycle operations.

Для непрофессионального программиста:

- Этот репозиторий — единственная официальная точка, через которую
  оркестратор и stage-workers должны создавать и обновлять execution-записи
  в таблице document_stage_executions.

- Одна execution-запись = одна попытка выполнить одну pipeline-стадию
  для одной версии документа.

- Зачем это нужно:
  - чтобы не ставить одну и ту же стадию в очередь несколько раз;
  - чтобы видеть жизненный цикл выполнения стадии:
    planned -> dispatched -> started -> succeeded / failed / cancelled;
  - чтобы хранить понятную историю ошибок и повторных попыток.

- Важно:
  - этот репозиторий НЕ меняет Document.status;
  - он НЕ обновляет refs в DocumentVersion;
  - он работает только с execution-ledger таблицей.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.constants import DocumentStageExecutionStatus
from ..models.document import DocumentStageExecution


class DocumentStageExecutionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_planned(
        self,
        run_id: uuid.UUID,
        document_id: uuid.UUID,
        document_version_id: uuid.UUID,
        from_status: str,
        to_status: str,
        orchestration_strategy: str,
        task_name: str,
    ) -> DocumentStageExecution:
        """
        Create a new PLANNED execution record.

        Обычно вызывается оркестратором ПЕРЕД постановкой Celery task.
        Если в БД уже есть активная execution-запись для этого же:
        (document_version_id, to_status, orchestration_strategy),
        PostgreSQL partial unique index выбросит IntegrityError.

        Почему мы это не скрываем:
        - это и есть основной механизм защиты от дублей;
        - оркестратор должен уметь поймать конфликт и не ставить
          повторную задачу в очередь.
        """
        execution = DocumentStageExecution(
            run_id=run_id,
            document_id=document_id,
            document_version_id=document_version_id,
            from_status=from_status,
            to_status=to_status,
            orchestration_strategy=orchestration_strategy,
            task_name=task_name,
            status=DocumentStageExecutionStatus.PLANNED.value,
        )
        self.session.add(execution)
        await self.session.flush()
        return execution

    async def get_by_id(
        self,
        execution_id: uuid.UUID,
    ) -> DocumentStageExecution | None:
        """Get execution record by ID."""
        result = await self.session.execute(
            select(DocumentStageExecution).where(
                DocumentStageExecution.id == execution_id
            )
        )
        return result.scalar_one_or_none()

    async def get_active_for_stage(
        self,
        document_version_id: uuid.UUID,
        to_status: str,
        orchestration_strategy: str,
    ) -> DocumentStageExecution | None:
        """
        Return active execution for a given target stage, if any exists.

        Активными считаются статусы:
        planned / dispatched / started.
        """
        result = await self.session.execute(
            select(DocumentStageExecution).where(
                DocumentStageExecution.document_version_id == document_version_id,
                DocumentStageExecution.to_status == to_status,
                DocumentStageExecution.orchestration_strategy == orchestration_strategy,
                DocumentStageExecution.status.in_(
                    [
                        DocumentStageExecutionStatus.PLANNED.value,
                        DocumentStageExecutionStatus.DISPATCHED.value,
                        DocumentStageExecutionStatus.STARTED.value,
                    ]
                ),
            )
        )
        return result.scalar_one_or_none()

    async def mark_dispatched(
        self,
        execution_id: uuid.UUID,
        celery_task_id: str | None = None,
    ) -> DocumentStageExecution | None:
        """
        Mark execution as DISPATCHED after task was successfully enqueued.
        """
        stmt = (
            update(DocumentStageExecution)
            .where(DocumentStageExecution.id == execution_id)
            .values(
                status=DocumentStageExecutionStatus.DISPATCHED.value,
                celery_task_id=celery_task_id,
            )
            .returning(DocumentStageExecution)
        )
        result = await self.session.execute(stmt)
        execution = result.scalar_one_or_none()

        if execution:
            await self.session.flush()

        return execution

    async def mark_started(
        self,
        execution_id: uuid.UUID,
    ) -> DocumentStageExecution | None:
        """
        Mark execution as STARTED when worker begins actual processing.
        """
        stmt = (
            update(DocumentStageExecution)
            .where(DocumentStageExecution.id == execution_id)
            .values(
                status=DocumentStageExecutionStatus.STARTED.value,
                started_at=datetime.now(timezone.utc),
            )
            .returning(DocumentStageExecution)
        )
        result = await self.session.execute(stmt)
        execution = result.scalar_one_or_none()

        if execution:
            await self.session.flush()

        return execution

    async def mark_succeeded(
        self,
        execution_id: uuid.UUID,
    ) -> DocumentStageExecution | None:
        """
        Mark execution as SUCCEEDED when stage fully completed
        and all postconditions passed.
        """
        stmt = (
            update(DocumentStageExecution)
            .where(DocumentStageExecution.id == execution_id)
            .values(
                status=DocumentStageExecutionStatus.SUCCEEDED.value,
                finished_at=datetime.now(timezone.utc),
            )
            .returning(DocumentStageExecution)
        )
        result = await self.session.execute(stmt)
        execution = result.scalar_one_or_none()

        if execution:
            await self.session.flush()

        return execution

    async def mark_failed(
        self,
        execution_id: uuid.UUID,
        error_details: dict,
    ) -> DocumentStageExecution | None:
        """
        Mark execution as FAILED and store structured error details.

        error_details ожидается в едином JSON-формате, например:
        {
            "stage": "chunks",
            "type": "chunking_v2_contract_violation",
            "reason": "missing_chunks_manifest_v2_ref",
            "message": "...",
            "run_id": "...",
            "timestamp": "...",
        }
        """
        stmt = (
            update(DocumentStageExecution)
            .where(DocumentStageExecution.id == execution_id)
            .values(
                status=DocumentStageExecutionStatus.FAILED.value,
                error_details=error_details,
                finished_at=datetime.now(timezone.utc),
            )
            .returning(DocumentStageExecution)
        )
        result = await self.session.execute(stmt)
        execution = result.scalar_one_or_none()

        if execution:
            await self.session.flush()

        return execution

    async def mark_cancelled(
        self,
        execution_id: uuid.UUID,
        error_details: dict | None = None,
    ) -> DocumentStageExecution | None:
        """
        Mark execution as CANCELLED.

        Используется, когда execution нужно явно закрыть без успешного выполнения,
        например при отмене orchestration branch или ручной остановке.
        """
        values: dict[str, object] = {
            "status": DocumentStageExecutionStatus.CANCELLED.value,
            "finished_at": datetime.now(timezone.utc),
        }

        if error_details is not None:
            values["error_details"] = error_details

        stmt = (
            update(DocumentStageExecution)
            .where(DocumentStageExecution.id == execution_id)
            .values(**values)
            .returning(DocumentStageExecution)
        )
        result = await self.session.execute(stmt)
        execution = result.scalar_one_or_none()

        if execution:
            await self.session.flush()

        return execution


    async def create_planned_or_none_on_conflict(
        self,
        run_id: uuid.UUID,
        document_id: uuid.UUID,
        document_version_id: uuid.UUID,
        from_status: str,
        to_status: str,
        orchestration_strategy: str,
        task_name: str,
    ) -> DocumentStageExecution | None:
        """
        Safe helper for orchestrator.

        Пытается создать PLANNED execution.
        Если partial unique index в БД обнаруживает уже существующую активную
        execution-запись для этого stage transition, возвращаем None вместо ошибки.

        Это удобно именно для orchestration-кода, чтобы он мог спокойно сказать:
        "задача уже активна, повторно не ставим".

        Важно про savepoint:
        - Мы используем session.begin_nested() вместо прямого rollback().
        - begin_nested() создаёт PostgreSQL SAVEPOINT внутри текущей транзакции.
        - При IntegrityError откатывается только этот savepoint.
        - Основная транзакция сессии остаётся живой.
        - Все ORM-объекты, загруженные до этого вызова, остаются валидными.
        - Это предотвращает MissingGreenlet при последующем обращении к атрибутам
        ранее загруженных объектов (run_obj, docs, version и т.д.).
        """
        try:
            async with self.session.begin_nested():
                return await self.create_planned(
                    run_id=run_id,
                    document_id=document_id,
                    document_version_id=document_version_id,
                    from_status=from_status,
                    to_status=to_status,
                    orchestration_strategy=orchestration_strategy,
                    task_name=task_name,
                )
        except IntegrityError:
            return None
        
        