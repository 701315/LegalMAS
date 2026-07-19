# src/db/repositories/run_repo.py

"""
Репозитории для работы с запуском анализа (Run) и единичными задачами (Job).


Зачем нужен этот код:


- RunRepository:
  - создаёт новый запуск анализа сделки (Run);
  - читает Run по id или по сделке;
  - обновляет статус Run и связанные с ним поля (счётчики, error_details, timestamps);
  - считает статистику классификации по результатам Run.


- JobRepository:
  - создаёт записи о фоновых задачах (Job) внутри Run;
  - обновляет статус задач (queued, running, completed, failed, dlq) с таймстемпами.


Как это влияет на работу системы и UX юриста:


- Run — это «один запуск анализа» по сделке. По нему фронт показывает:
  - статус запуска;
  - прогресс по checks (total_checks / completed_checks);
  - агрегированную ошибку уровня Run.


- Job — это отдельная задача внутри Run.
  Эти записи полезны для операционной поддержки и диагностики.
"""


import uuid
from datetime import UTC, datetime


from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession


from core.constants import DocumentClassificationOutcome, RunStatus
from core.logging import get_logger

from ..models.document import Document
from ..models.result import CheckResult
from ..models.run import Job, Run
from .result_repo import ResultRepository


logger = get_logger(__name__)


class RunRepository:
    def __init__(self, session: AsyncSession):
        self.session = session


    async def create(
        self,
        deal_id: uuid.UUID,
        playbook_version_id: uuid.UUID,
        model_config_id: uuid.UUID | None = None,
        bundle_id: uuid.UUID | None = None,
        environment_hash: str | None = None,
        profile: str = "full",
        pipeline_strategy: str = "REUSE_STRUCTURE",
        checks_mode: str = "global_and_doc_type",
        checks_scope: dict | None = None,
    ) -> Run:
        """
        Создать новый запуск анализа (Run) для сделки.


        Для юриста это означает:
        - «я запустил новый анализ по сделке»;
        - в дальнейшем именно по этому Run будут считаться прогресс и статусы.


        Важно:
        - pipeline_strategy описывает, как запуск использует существующие артефакты;
        - checks_mode определяет общий режим проверок;
        - checks_scope определяет область документа, по которой запускать checks
          (например, только primary, только appendices, или оба типа сегментов).
        """
        run = Run(
            deal_id=deal_id,
            bundle_id=bundle_id,
            playbook_version_id=playbook_version_id,
            model_config_id=model_config_id,
            environment_hash=environment_hash,
            profile=profile,
            pipeline_strategy=pipeline_strategy,
            checks_mode=checks_mode,
            checks_scope=checks_scope,
        )
        self.session.add(run)
        await self.session.flush()
        return run


    async def get_by_id(self, run_id: uuid.UUID) -> Run | None:
        """Вернуть Run по ID (или None, если не найден)."""
        result = await self.session.execute(select(Run).where(Run.id == run_id))
        return result.scalar_one_or_none()


    async def get(self, run_id: uuid.UUID) -> Run | None:
        """
        Удобный псевдоним для get_by_id.


        Нужен, чтобы код, который ожидает метод .get(...),
        мог работать с RunRepository без лишних изменений.
        """
        return await self.get_by_id(run_id)


    async def update_status(self, run_id: uuid.UUID, status: str, **kwargs) -> Run | None:
        """
        Обновить статус Run и дополнительные поля.


        Основная идея:
        - это единая точка смены статуса Run;
        - здесь же аккуратно заполняются started_at / completed_at,
          если вызывающий их не передал явно.
        """
        values: dict = {"status": status}

        if "started_at" in kwargs and kwargs["started_at"] is not None:
            values["started_at"] = kwargs["started_at"]
        if "completed_at" in kwargs and kwargs["completed_at"] is not None:
            values["completed_at"] = kwargs["completed_at"]

        if status == RunStatus.RUNNING.value and "started_at" not in values:
            values["started_at"] = datetime.now(UTC)

        if (
            status
            in (
                RunStatus.COMPLETED.value,
                RunStatus.COMPLETED_WITH_ERRORS.value,
                RunStatus.FAILED.value,
            )
            and "completed_at" not in values
        ):
            values["completed_at"] = datetime.now(UTC)

        for k, v in kwargs.items():
            if k in ("started_at", "completed_at"):
                continue
            values[k] = v

        stmt = update(Run).where(Run.id == run_id).values(**values).returning(Run)
        result = await self.session.execute(stmt)
        run = result.scalar_one_or_none()
        if run:
            await self.session.flush()
        return run


    async def increment_completed_checks(self, run_id: uuid.UUID) -> int:
        """
        Увеличить счётчик completed_checks на 1 и вернуть новое значение.
        """
        stmt = (
            update(Run)
            .where(Run.id == run_id)
            .values(completed_checks=Run.completed_checks + 1)
            .returning(Run.completed_checks)
        )
        result = await self.session.execute(stmt)
        new_count = result.scalar_one()
        await self.session.flush()
        return new_count


    async def get_counts(self, run_id: uuid.UUID) -> tuple[int, int]:
        """
        Вернуть (total_checks, completed_checks) для Run.
        """
        result = await self.session.execute(
            select(Run.total_checks, Run.completed_checks).where(Run.id == run_id)
        )
        row = result.first()
        if not row:
            return 0, 0
        total = row[0] or 0
        completed = row[1] or 0
        return total, completed


    async def get_document_ids_for_run(self, run_id: uuid.UUID) -> list[uuid.UUID]:
        """
        Вернуть уникальные document_id, для которых есть CheckResult с данным run_id.
        """
        subq = select(CheckResult.document_id).where(CheckResult.run_id == run_id).distinct()
        result = await self.session.execute(subq)
        return [row[0] for row in result.all()]


    async def get_latest_for_deal(self, deal_id: uuid.UUID) -> Run | None:
        """
        Вернуть последний Run для сделки по дате создания.
        """
        stmt = select(Run).where(Run.deal_id == deal_id).order_by(desc(Run.created_at)).limit(1)
        result = await self.session.execute(stmt)
        return result.scalars().first()


    async def get_by_deal(self, deal_id: uuid.UUID) -> list[Run]:
        """
        Вернуть все Run'ы для сделки, новые сначала.
        """
        stmt = select(Run).where(Run.deal_id == deal_id).order_by(desc(Run.created_at))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


    async def get_classification_stats_for_run(self, run_id: uuid.UUID) -> dict:
        """
        Посчитать статистику классификации по документам, участвовавшим в Run.
        """
        subq = (
            select(CheckResult.document_id)
            .where(CheckResult.run_id == run_id)
            .distinct()
            .subquery()
        )


        stmt = select(
            Document.classification_level,
            Document.classification_confidence,
            Document.doc_type,
            Document.classification_outcome,
        ).where(Document.id.in_(select(subq)))
        result = await self.session.execute(stmt)
        rows = result.all()


        stats = {
            "total_documents": len(rows),
            "l0_no_match": 0,
            "l1_filename": 0,
            "l2_keyword": 0,
            "l3_semantic": 0,
            "l4_llm": 0,
            "low_confidence_count": 0,
            "unknown_doc_type_count": 0,
        }


        level_map = {
            "L0": "l0_no_match",
            "L1": "l1_filename",
            "L2": "l2_keyword",
            "L3": "l3_semantic",
            "L4": "l4_llm",
            "LMANUAL": "l4_llm",
        }


        for level, confidence, doc_type, classification_outcome in rows:
            raw_level = level or "L0"
            level_norm = raw_level.replace("_", "").upper()
            key = level_map.get(level_norm, "l0_no_match")
            stats[key] += 1

            if confidence and 0 < confidence < 0.6:
                stats["low_confidence_count"] += 1

            outcome = str(classification_outcome or "")

            # Канонический источник истины — classification_outcome.
            is_unknown = outcome == DocumentClassificationOutcome.UNKNOWN.value

            # Defensive fallback для исторических строк, где UNKNOWN/Generic
            # могли храниться напрямую в doc_type.
            if not is_unknown and outcome in (
                "",
                DocumentClassificationOutcome.TYPED.value,
            ):
                normalized_doc_type = (doc_type or "").strip()
                is_unknown = normalized_doc_type in {"Generic", "Unknown"}

            if is_unknown:
                stats["unknown_doc_type_count"] += 1


        return stats


    async def try_start_run(self, run_id: uuid.UUID) -> bool:
        """
        Атомарно перевести Run из PENDING в RUNNING.
        """
        stmt = (
            update(Run)
            .where(Run.id == run_id, Run.status == RunStatus.PENDING.value)
            .values(
                status=RunStatus.RUNNING.value,
                started_at=datetime.now(UTC),
            )
            .returning(Run.id)
        )
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        if not row:
            return False

        await self.session.flush()
        return True


    async def finalize_run_if_finished(self, run_id: uuid.UUID) -> Run | None:
        """
        Синхронизировать прогресс Run по CheckResult и, если все checks завершены,
        перевести Run в финальный статус.


        Инварианты:
        - source of truth для ожидаемого объёма checks — Run.total_checks,
          который выставляет scheduler;
        - materialized_checks — это факт появления CheckResult, а не план;
        - zero-check run не должен бесконечно оставаться RUNNING.
        """
        run = await self.get_by_id(run_id)
        if run is None:
            return None


        result_repo = ResultRepository(self.session)


        planned_total_checks = int(getattr(run, "total_checks", 0) or 0)
        materialized_checks = await result_repo.count_distinct_checks_for_run(run_id)
        completed_checks = await result_repo.count_finished_checks_for_run(run_id)
        has_failed_checks = await result_repo.has_failed_or_timed_out_checks(run_id)


        values: dict = {
            "completed_checks": completed_checks,
            "has_errors": has_failed_checks,
        }


        # total_checks уже определён scheduler'ом как execution plan.
        # Перетираем его только если в Run он ещё не был выставлен.
        if planned_total_checks <= 0 and materialized_checks > 0:
            planned_total_checks = materialized_checks
            values["total_checks"] = planned_total_checks


        if run.status in (
            RunStatus.COMPLETED.value,
            RunStatus.COMPLETED_WITH_ERRORS.value,
            RunStatus.FAILED.value,
        ):
            stale_updates = {}
            if (run.completed_checks or 0) != completed_checks:
                stale_updates["completed_checks"] = completed_checks
            if bool(getattr(run, "has_errors", False)) != has_failed_checks:
                stale_updates["has_errors"] = has_failed_checks
            if stale_updates:
                return await self.update_status(run_id, run.status, **stale_updates)
            return run


        # zero-check run — валидный terminal scenario
        if planned_total_checks <= 0:
            final_status = (
                RunStatus.COMPLETED_WITH_ERRORS.value
                if has_failed_checks
                else RunStatus.COMPLETED.value
            )
            values["total_checks"] = 0
            return await self.update_status(
                run_id,
                final_status,
                **values,
            )


        # checks есть, но ещё не все в terminal execution_status
        if completed_checks < planned_total_checks:
            values["total_checks"] = planned_total_checks
            return await self.update_status(
                run_id,
                RunStatus.RUNNING.value,
                **values,
            )


        final_status = (
            RunStatus.COMPLETED_WITH_ERRORS.value
            if has_failed_checks
            else RunStatus.COMPLETED.value
        )


        values["total_checks"] = planned_total_checks
        return await self.update_status(
            run_id,
            final_status,
            **values,
        )


    async def mark_run_failed(
        self,
        run_id: uuid.UUID,
        message: str,
        *,
        error_details: dict | None = None,
    ) -> Run | None:
        """
        Пометить Run как FAILED только в случае run-level/orchestrator-level ошибки.
        """
        payload = dict(error_details or {})
        payload.setdefault("message", message)
        payload.setdefault("level", "run")
        payload.setdefault("status", "failed")


        current = await self.get_by_id(run_id)
        if current is None:
            return None


        return await self.update_status(
            run_id,
            RunStatus.FAILED.value,
            total_checks=current.total_checks or 0,
            completed_checks=current.completed_checks or 0,
            has_errors=True,
            error_details=payload,
        )

    async def update_instruction_versions(
        self,
        run_id: uuid.UUID,
        versions: dict[str, str],
    ) -> Run | None:
        """
        Атомарно записать зафиксированные версии инструкций для Run.

        Args:
            run_id: Идентификатор Run.
            versions: Карта {doc_type: version_id_str}.
                      Ключи — строковые doc_type codes.
                      Значения — строковые UUID версий инструкций.

        Returns:
            Обновлённый Run если запись успешна, иначе None.

        Behaviour:
        - Атомарная запись через UPDATE ... RETURNING.
        - Пустой словарь {} валиден и будет записан (zero-check run).
        - None не валиден — для отсутствия данных используется NULL в БД,
          но этот метод не должен вызываться для такого случая.
        - Метод идемпотентен: повторная запись того же словаря безопасна.

        Используется:
        - check_worker.py при старте Run для фиксации версий инструкций.
        """
        if versions is None:
            logger.warning(
                "run_repo.update_instruction_versions: versions is None, "
                "refusing to overwrite with NULL — use empty dict {} for zero-check runs",
                run_id=str(run_id),
            )
            return None

        if not isinstance(versions, dict):
            logger.error(
                "run_repo.update_instruction_versions: versions is not a dict, refusing to write",
                run_id=str(run_id),
                versions_type=type(versions).__name__,
            )
            return None

        # Защита: логируем если словарь пустой (валидно для zero-check runs),
        # но информируем для диагностики.
        if not versions:
            logger.info(
                "run_repo.update_instruction_versions: empty versions dict (zero-check run?)",
                run_id=str(run_id),
            )

        stmt = (
            update(Run)
            .where(Run.id == run_id)
            .values(instruction_versions=versions)
            .returning(Run)
        )
        result = await self.session.execute(stmt)
        run = result.scalar_one_or_none()

        if run:
            await self.session.flush()
            logger.info(
                "run_repo.update_instruction_versions: successfully updated",
                run_id=str(run_id),
                doc_types_count=len(versions),
                doc_types=sorted(versions.keys())[:10],  # первые 10 для логов
            )
        else:
            logger.warning(
                "run_repo.update_instruction_versions: Run not found",
                run_id=str(run_id),
            )

        return run

    async def update_instruction_snapshot(
        self,
        run_id: uuid.UUID,
        versions: dict[str, str],
        manifest: dict[str, dict],
        payload: dict[str, dict],
    ) -> Run | None:
        """
        Атомарно зафиксировать полный frozen snapshot doc-type инструкций для Run.

        Args:
            run_id:   Идентификатор Run.
            versions: {doc_type: version_id_str} — обратная совместимость
                      с существующим полем instruction_versions.
            manifest: {doc_type: {version_id, content_hash, override_id}} —
                      метаданные снапшота для аудита/UI.
            payload:  {doc_type: full_yaml_dict} — передаётся в
                      DatabaseInstructionProvider для исполнения checks.

        Returns:
            Обновлённый Run если запись успешна, иначе None.

        Behaviour:
        - Атомарная запись всех трёх полей одним UPDATE ... RETURNING.
        - Пустые словари валидны (zero typed-document run).
        - None для любого аргумента не валиден — caller должен передавать {}.
        - Идемпотентен.
        """
        for name, value in (
            ("versions", versions),
            ("manifest", manifest),
            ("payload", payload),
        ):
            if value is None:
                logger.warning(
                    "run_repo.update_instruction_snapshot: %s is None, "
                    "refusing to overwrite with NULL — use empty dict {} instead",
                    name,
                    run_id=str(run_id),
                )
                return None
            if not isinstance(value, dict):
                logger.error(
                    "run_repo.update_instruction_snapshot: %s is not a dict, refusing to write",
                    name,
                    run_id=str(run_id),
                    value_type=type(value).__name__,
                )
                return None

        stmt = (
            update(Run)
            .where(Run.id == run_id)
            .values(
                instruction_versions=versions,
                instruction_snapshot_manifest=manifest,
                instruction_snapshot_payload=payload,
            )
            .returning(Run)
        )
        result = await self.session.execute(stmt)
        run = result.scalar_one_or_none()

        if run:
            await self.session.flush()
            logger.info(
                "run_repo.update_instruction_snapshot: successfully updated",
                run_id=str(run_id),
                doc_types_count=len(versions),
                doc_types=sorted(versions.keys())[:10],
            )
        else:
            logger.warning(
                "run_repo.update_instruction_snapshot: Run not found",
                run_id=str(run_id),
            )

        return run


class JobRepository:
    def __init__(self, session: AsyncSession):
        self.session = session


    async def create(
        self,
        run_id: uuid.UUID,
        task_type: str,
        document_id: uuid.UUID | None = None,
    ) -> Job:
        """
        Создать новую запись о задаче (Job) внутри Run.
        """
        job = Job(
            run_id=run_id,
            task_type=task_type,
            document_id=document_id,
        )
        self.session.add(job)
        await self.session.flush()
        return job


    async def update_status(self, job_id: uuid.UUID, status: str, **kwargs) -> Job | None:
        """
        Обновить статус Job.
        """
        values = {"status": status, **kwargs}
        if status == "running" and "started_at" not in kwargs:
            values["started_at"] = datetime.now(UTC)
        if status in ("completed", "failed", "dlq") and "finished_at" not in kwargs:
            values["finished_at"] = datetime.now(UTC)


        stmt = update(Job).where(Job.id == job_id).values(**values).returning(Job)
        result = await self.session.execute(stmt)
        job = result.scalar_one_or_none()
        if job:
            await self.session.flush()
        return job
    

    