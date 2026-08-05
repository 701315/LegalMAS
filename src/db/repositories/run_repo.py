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
from .run_check_plan_item_repo import RunCheckPlanItemRepository


logger = get_logger(__name__)


class RunRepository:
    def __init__(self, session: AsyncSession):
        self.session = session


    async def create(
        self,
        deal_id: uuid.UUID,
        tenant_id: uuid.UUID,
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

        tenant_id обязателен и должен передаваться как Deal.tenant_id.
        Это frozen ownership snapshot: Run принадлежит tenant'у сделки
        в момент создания и никогда не меняет ownership.
        """
        run = Run(
            deal_id=deal_id,
            tenant_id=tenant_id,
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

        ВАЖНО про started_at:
        - started_at устанавливается ТОЛЬКО через try_start_run()
        при первом переходе PENDING → RUNNING.
        - update_status(RUNNING) НЕ трогает started_at, иначе
        каждый повторный вызов (например из finalize_run_if_finished
        после каждого завершённого check) перезаписывал бы started_at
        на "сейчас" и Run.elapsed_seconds давал бы неверное время.
        - Если вызывающий явно передал started_at в kwargs — уважаем это
        (для backfill/восстановления сценариев).

        Про completed_at:
        - completed_at устанавливается один раз при переходе в терминальный
        статус (COMPLETED / COMPLETED_WITH_ERRORS / FAILED), если явно не
        передан. Повторный вызов update_status с тем же терминальным
        статусом всё равно перепишет completed_at на "сейчас" — это
        сохранено как было, потому что терминальный переход обычно
        делается один раз.
        """
        values: dict = {"status": status}

        # started_at: только если явно передан вызывающим (никогда не автозаполняем).
        # Автоматическая установка при PENDING → RUNNING делается в try_start_run().
        if "started_at" in kwargs and kwargs["started_at"] is not None:
            values["started_at"] = kwargs["started_at"]

        # completed_at: если явно передан — уважаем, иначе автозаполнение
        # при переходе в терминальный статус.
        if "completed_at" in kwargs and kwargs["completed_at"] is not None:
            values["completed_at"] = kwargs["completed_at"]

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
        Синхронизировать прогресс Run по RunCheckPlanItem и, если все plan items
        достигли terminal status, перевести Run в финальный статус.

        Инварианты:
        - source of truth для прогресса и финализации Run — run_check_plan_items;
        - Run.total_checks = количество plan items;
        - Run.completed_checks = количество terminal plan items;
        - zero-check run — валидный terminal scenario.
        """
        run = await self.get_by_id(run_id)
        if run is None:
            return None

        plan_item_repo = RunCheckPlanItemRepository(self.session)
        stats = await plan_item_repo.get_run_progress_stats(run_id)

        total_items = int(stats["total_items"] or 0)
        terminal_items = int(stats["terminal_items"] or 0)
        has_errors = bool(stats["has_errors"])

        values: dict = {
            "total_checks": total_items,
            "completed_checks": terminal_items,
            "has_errors": has_errors,
        }

        if run.status in (
            RunStatus.COMPLETED.value,
            RunStatus.COMPLETED_WITH_ERRORS.value,
            RunStatus.FAILED.value,
        ):
            stale_updates = {}
            if (run.total_checks or 0) != total_items:
                stale_updates["total_checks"] = total_items
            if (run.completed_checks or 0) != terminal_items:
                stale_updates["completed_checks"] = terminal_items
            if bool(getattr(run, "has_errors", False)) != has_errors:
                stale_updates["has_errors"] = has_errors
            if stale_updates:
                return await self.update_status(run_id, run.status, **stale_updates)
            return run

        if total_items <= 0:
            final_status = (
                RunStatus.COMPLETED_WITH_ERRORS.value
                if has_errors
                else RunStatus.COMPLETED.value
            )
            return await self.update_status(
                run_id,
                final_status,
                **values,
            )

        if terminal_items < total_items:
            return await self.update_status(
                run_id,
                RunStatus.RUNNING.value,
                **values,
            )

        final_status = (
            RunStatus.COMPLETED_WITH_ERRORS.value
            if has_errors
            else RunStatus.COMPLETED.value
        )
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
        snapshot_schema_version: int | None = None,
    ) -> Run | None:
        """
        Атомарно зафиксировать полный frozen snapshot doc-type инструкций для Run.

        Args:
            run_id:   Идентификатор Run.
            versions: {doc_type: version_id_str} — обратная совместимость
                      с существующим полем instruction_versions.
            manifest: {doc_type: {...}} —
                      provenance frozen snapshot:
                      version_id, content_hash, effective_hash,
                      tenant/deal override ids, resolution_strategy.
            payload:  {doc_type: effective_compiled_payload_dict} —
                      frozen effective payload для DatabaseInstructionProvider.
            snapshot_schema_version: если передан, выставляется атомарно
                      вместе со snapshot. None = не менять.

        Returns:
            Обновлённый Run если запись успешна, иначе None.

        Behaviour:
        - Атомарная запись всех полей одним UPDATE ... RETURNING.
        - snapshot_schema_version пишется в тот же UPDATE — нет
          промежуточного состояния.
        - Пустые словари валидны (zero typed-document run).
        - None для dict-аргументов не валиден.
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

        # --- Build minimal execution manifest V1 ---

        current_run = await self.get_by_id(run_id)
        if not current_run:
            return None

        from db.repositories.playbook_repo import PlaybookRepository

        playbook_repo = PlaybookRepository(self.session)
        pb_version = await playbook_repo.get_by_id(current_run.playbook_version_id)

        doc_type_execution_manifest = {}
        for doc_type, version_id in versions.items():
            doc_manifest = manifest.get(doc_type) or {}
            doc_type_execution_manifest[doc_type] = {
                "version_id": version_id,
                "override_id": doc_manifest.get("override_id"),
                "tenant_override_id": doc_manifest.get("tenant_override_id"),
                "deal_override_id": doc_manifest.get("deal_override_id"),
                "effective_hash": doc_manifest.get("effective_hash"),
                "is_overridden": bool(doc_manifest.get("is_overridden", False)),
                "resolution_strategy": doc_manifest.get("resolution_strategy"),
            }

        playbook_meta = ((getattr(pb_version, "compiled_checks", None) or {}).get("meta") or {})

        execution_manifest = {
            "schema_version": 1,
            "playbook": {
                "version_id": str(current_run.playbook_version_id),
                "immutable_content_hash": getattr(pb_version, "immutable_content_hash", None),
                "model_config_id": (
                    str(current_run.model_config_id)
                    if current_run.model_config_id
                    else None
                ),
            },
            "doc_type_instructions": doc_type_execution_manifest,
            "global_instructions": playbook_meta.get("global_instruction_refs", {}) or {},
        }

        update_values: dict = {
            "instruction_versions": versions,
            "instruction_snapshot_manifest": manifest,
            "instruction_snapshot_payload": payload,
            "execution_manifest": execution_manifest,
        }

        if snapshot_schema_version is not None:
            update_values["snapshot_schema_version"] = snapshot_schema_version

        stmt = (
            update(Run)
            .where(Run.id == run_id)
            .values(**update_values)
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
                snapshot_schema_version=snapshot_schema_version,
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
    

    