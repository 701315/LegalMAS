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
  - статус запуска (ожидает, выполняется, завершён, завершён с ошибками, упал);
  - прогресс по документам (total_checks / completed_checks);
  - агрегированную ошибку уровня Run (если пайплайн упал целиком).

- Job — это отдельная задача внутри Run (например, import, extract, run_deal_checks).
  Эти записи удобны для операционной поддержки и диагностики, но обычно не показываются напрямую юристу.
"""

import uuid
from datetime import UTC, datetime, timezone

from sqlalchemy import select, update, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.result import CheckResult
from ..models.run import Job, Run
from ..models.document import Document
from core.constants import RunStatus


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
    ) -> Run:
        """
        Создать новый запуск анализа (Run) для сделки.

        Для юриста это означает:
        - «я запустил новый анализ по сделке»;
        - в дальнейшем именно по этому Run будут считаться прогресс и статусы.

        Важно:
        - pipeline_strategy описывает, как этот запуск будет использовать уже
          существующие артефакты (layout, clause_tree, classification);
        - checks_mode определяет, по какому набору проверок будет идти анализ
          (например, полный прогон или укороченный).
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
        - это единая точка смены статуса Run (pending, running, completed,
          completed_with_errors, failed и т.п.);
        - здесь же аккуратно заполняются started_at / completed_at, если вызывающий
          их не передал явно.

        Примеры использования:
        - оркестратор ставит Run в "running" и заполняет total_checks;
        - Runner, когда все документы обработаны, ставит "completed" или
          "completed_with_errors";
        - при критическом сбое (MinIO, БД, конфигурация) Run помечается "failed"
          и может получить error_details с агрегированным описанием проблемы.
        """

        def _to_naive_utc(dt: datetime | None) -> datetime | None:
            """
            Вспомогательная функция:
            - принимает datetime с таймзоной или без;
            - приводит к naive UTC (без tzinfo), чтобы единообразно хранить в БД.
            """
            if dt is None:
                return None
            if dt.tzinfo is None:
                return dt
            return dt.astimezone(timezone.utc).replace(tzinfo=None)

        values: dict = {"status": status}

        # если вызывающий явно передал started_at/completed_at — нормализуем
        if "started_at" in kwargs and kwargs["started_at"] is not None:
            values["started_at"] = _to_naive_utc(kwargs["started_at"])
        if "completed_at" in kwargs and kwargs["completed_at"] is not None:
            values["completed_at"] = _to_naive_utc(kwargs["completed_at"])

        # автозаполнение, если не передали
        if status == RunStatus.RUNNING.value and "started_at" not in values:
            # now(UTC) → naive UTC
            values["started_at"] = datetime.now(UTC).replace(tzinfo=None)
        # Важно: completed_with_errors — такой же "завершённый" Run, как completed/failed.
        if status in (
            RunStatus.COMPLETED.value,
            RunStatus.COMPLETED_WITH_ERRORS.value,
            RunStatus.FAILED.value,
        ) and "completed_at" not in values:
            values["completed_at"] = datetime.now(UTC).replace(tzinfo=None)

        # остальные kwargs (total_checks, completed_checks, error_details и т.п.)
        for k, v in kwargs.items():
            if k in ("started_at", "completed_at"):
                continue
            values[k] = v

        stmt = (
            update(Run)
            .where(Run.id == run_id)
            .values(**values)
            .returning(Run)
        )
        result = await self.session.execute(stmt)
        run = result.scalar_one_or_none()
        if run:
            await self.session.flush()
        return run

    async def increment_completed_checks(self, run_id: uuid.UUID) -> int:
        """
        Увеличить счётчик completed_checks на 1 и вернуть новое значение.

        Зачем это нужно:
        - каждый раз, когда документ успешно доходит до стадии checks,
          Runner вызывает этот метод;
        - фронт по полям total_checks / completed_checks показывает юристу прогресс
          выполнения Run (например, «15 из 20 документов проверено»).
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

        Используется для:
        - понимания, все ли документы, запланированные в Run, дошли до стадии checks;
        - принятия решения, можно ли финализировать Run (completed / completed_with_errors / failed).
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

        Зачем это нужно:
        - при построении отчётов (DD grid, summary) мы хотим выбирать только те документы,
          которые реально участвовали в данном Run;
        - это фильтр «по факту наличия результатов checks» для конкретного запуска.
        """
        subq = (
            select(CheckResult.document_id)
            .where(CheckResult.run_id == run_id)
            .distinct()
        )
        result = await self.session.execute(subq)
        return [row[0] for row in result.all()]

    async def get_latest_for_deal(self, deal_id: uuid.UUID) -> Run | None:
        """
        Вернуть последний Run для сделки по дате создания/ID.

        Используется, например, при ручной переклассификации:
        - чтобы понять, какой Run по сделке был последним;
        - при необходимости переиспользовать его конфигурацию (playbook, model_config).
        """
        stmt = (
            select(Run)
            .where(Run.deal_id == deal_id)
            .order_by(desc(Run.created_at))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_deal(self, deal_id: uuid.UUID) -> list[Run]:
        """
        Вернуть все Run'ы для указанной сделки, отсортированные по дате создания (новые сначала).

        Для фронта это основа для страницы «История запусков анализа по сделке».
        """
        stmt = (
            select(Run)
            .where(Run.deal_id == deal_id)
            .order_by(desc(Run.created_at))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_classification_stats_for_run(self, run_id: uuid.UUID) -> dict:
        """
        Посчитать статистику классификации по всем документам,
        которые проверялись в этом Run.

        Это нужно для:
        - быстрой оценки качества классификации по Run;
        - построения «шапки» отчёта: сколько документов попало в L0/L1/L2/L3/L4,
          сколько низкоуверенных, сколько с неизвестным типом.
        """
        # все document_id, участвовавшие в Run
        subq = (
            select(CheckResult.document_id)
            .where(CheckResult.run_id == run_id)
            .distinct()
            .subquery()
        )

        stmt = (
            select(
                Document.classification_level,
                Document.classification_confidence,
                Document.doc_type,
            )
            .where(Document.id.in_(select(subq)))
        )
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
            "LMANUAL": "l4_llm",  # ручная разметка считаем как максимальный уровень
        }

        for level, confidence, doc_type in rows:
            raw_level = level or "L0"
            level_norm = raw_level.replace("_", "").upper()
            key = level_map.get(level_norm, "l0_no_match")
            stats[key] += 1

            if confidence and 0 < confidence < 0.6:
                stats["low_confidence_count"] += 1
            if not doc_type or doc_type in ("Generic", "Unknown"):
                stats["unknown_doc_type_count"] += 1

        return stats


    async def try_start_run(self, run_id: uuid.UUID) -> bool:
        """
        Атомарно перевести Run из PENDING в RUNNING.

        Для непрофессионального программиста:
        - Этот метод делает один запрос к базе:
          "если Run ещё в статусе 'pending', поставь ему статус 'running'".
        - Если Run уже кто‑то запустил (он не в pending),
          метод вернёт False, и мы поймём, что повторно запускать пайплайн не нужно.
        """
        stmt = (
            update(Run)
            .where(Run.id == run_id, Run.status == RunStatus.PENDING.value)
            .values(status=RunStatus.RUNNING.value)
            .returning(Run.id)
        )
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        if not row:
            # Ничего не поменяли — Run уже не в PENDING.
            return False

        # Дополнительно, по аналогии с update_status, можем проставить started_at.
        await self.session.execute(
            update(Run)
            .where(Run.id == run_id)
            .values(started_at=datetime.now(UTC).replace(tzinfo=None))
        )
        await self.session.flush()
        return True


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

        Пример:
        - одна задача import для конкретного файла;
        - одна задача extract для документа;
        - одна задача проверки (checks) в рамках Run (например, run_deal_checks).

        Эти записи полезны для операторов и для отладки пайплайна.
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

        Логика:
        - при переводе в "running" проставляем started_at (если вызывающий не передал его сам);
        - при переводе в один из финальных статусов ("completed", "failed", "dlq")
          проставляем finished_at.

        Это помогает в эксплуатации:
        - видеть, когда задача стартовала и когда завершилась;
        - считать длительность выполнения отдельных стадий пайплайна.
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
