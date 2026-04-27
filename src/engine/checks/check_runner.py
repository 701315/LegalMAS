# src/engine/checks/check_runner.py

"""
CheckRunner: тонкий оркестратор playbook-based checks.

Делегирует:
- планирование → CheckPlanner
- скоупинг → ScopeResolver
- подготовку чанков → ChunksPreparer
- нормализацию результатов → result_normalizer
- сохранение → result_saver
- выполнение → CheckExecutor
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from db.repositories.document_repo import DocumentRepository
from db.repositories.run_repo import RunRepository
from db.repositories.runner_repo import RunnerRepository
from db.uow import db_uow
from db.repositories.document_version_repo import DocumentVersionRepository
from db.repositories.document_segment_repo import DocumentSegmentRepository
from engine.checks.executor import CheckExecutor
from engine.checks.planning.chunks import ChunksPreparer
from engine.checks.planning.planner import CheckPlanner
from engine.checks.planning.scope import ScopeResolver
from engine.checks.result_saver import save_check_result, save_not_applicable_result
from engine.checks.planning.context import SegmentInfo, CheckContext

logger = get_logger(__name__)

MAX_DOCS_PER_RUN = 500
MAX_ERRORS_PER_RUN = 50


class CheckRunner:
    """
    Playbook-based checks executor.

    Оркеструет: планирование → подготовка чанков → выполнение → сохранение.
    """

    def __init__(
        self,
        llm_client,
        playbook_version_id: uuid.UUID | None = None,
        checks_mode: str = "global_and_doc_type",
        run_repo: Optional[RunRepository] = None,
        checks_scope: dict[str, Any] | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.executor = CheckExecutor(llm_client)
        self.playbook_version_id = playbook_version_id
        self.run_repo = run_repo

        # Делегаты
        self._planner = CheckPlanner(checks_mode=checks_mode)
        self._scope = ScopeResolver(checks_scope=checks_scope)
        self._chunks = ChunksPreparer(scope_resolver=self._scope)

    @property
    def checks_mode(self) -> str:
        return self._planner.checks_mode

    @checks_mode.setter
    def checks_mode(self, value: str) -> None:
        self._planner.checks_mode = value

    # ── Публичный API (сохраняем сигнатуры 1:1) ────────────────────

    async def run_deal_checks(
        self,
        deal_id: uuid.UUID,
        run_id: uuid.UUID,
        playbook,
        checks_mode: str | None = None,
    ) -> dict:
        """Выполнить checks по всем non-duplicate документам сделки."""
        start_time = time.time()

        if checks_mode:
            self.checks_mode = checks_mode

        logger.info(
            "CheckRunner started",
            extra={
                "deal_id": str(deal_id),
                "run_id": str(run_id),
                "checks_mode": self.checks_mode,
            },
        )

        summary: dict = {
            "deal_id": str(deal_id),
            "run_id": str(run_id),
            "processed_docs": 0,
            "total_checks": 0,
            "failed_checks": 0,
            "errors": 0,
        }

        async with db_uow() as uow_for_docs:
            runner_repo = RunnerRepository(uow_for_docs.session)
            docs = await runner_repo.get_non_duplicate_docs(deal_id)

        if not docs:
            logger.info(
                "CheckRunner: no non-duplicate documents",
                extra={"deal_id": str(deal_id), "run_id": str(run_id)},
            )
            return summary

        if len(docs) > MAX_DOCS_PER_RUN:
            logger.warning(
                "CheckRunner: truncating documents",
                extra={"count": len(docs), "max_docs": MAX_DOCS_PER_RUN},
            )
            docs = docs[:MAX_DOCS_PER_RUN]

        for doc in docs:
            try:
                checks_count, failed_count = await self._run_checks_for_document(
                    doc,
                    run_id,
                    playbook,
                )
                summary["processed_docs"] += 1
                summary["total_checks"] += checks_count
                summary["failed_checks"] += failed_count

                if self.run_repo is not None:
                    try:
                        await self.run_repo.increment_completed_checks(run_id)
                    except Exception as e:
                        logger.warning(
                            "CheckRunner: failed to increment completed_checks",
                            extra={"run_id": str(run_id), "error": str(e)},
                        )

            except Exception as e:
                summary["errors"] += 1
                if summary["errors"] > MAX_ERRORS_PER_RUN:
                    logger.error(
                        "CheckRunner: too many errors, aborting",
                        extra={"errors": summary["errors"]},
                    )
                    break

                logger.error(
                    "CheckRunner: checks failed for document",
                    extra={
                        "doc_id": str(getattr(doc, "id", None)),
                        "error": str(e),
                    },
                )

        summary["duration_sec"] = time.time() - start_time
        logger.info("CheckRunner completed", extra=summary)
        return summary

    async def plan_checks_for_run(
        self,
        *,
        session: AsyncSession,
        deal_id: uuid.UUID,
        run_id: uuid.UUID,
        playbook,
    ) -> dict[str, Any]:
        """Делегирует планированию."""
        return await self._planner.plan_checks_for_run(
            session=session,
            deal_id=deal_id,
            run_id=run_id,
            playbook=playbook,
        )

    def find_check_for_document(self, doc, playbook, check_id: str):
        """Делегирует планировщику."""
        return self._planner.find_check_for_document(doc, playbook, check_id)

    async def execute_single_check(
        self,
        *,
        session: AsyncSession,
        repo,
        doc,
        run_id: uuid.UUID,
        playbook,
        check_id: str,
        safe_chunks: list[dict] | None = None,
    ) -> dict[str, Any]:
        """
        Выполнить одну проверку и сохранить результат.

        ВАЖНО:
        - здесь мы не различаем compute vs persist на уровне статусов,
          но не скрываем исключения из save_check_result;
        - Celery-воркер вокруг этого метода уже ловит SoftTimeLimitExceeded
          и generic Exception, выставляя execution_status="TIMEOUT"/"FAILED".
        """
        check = self._planner.find_check_for_document(doc, playbook, check_id)

        if check is None:
            logger.warning(
                "CheckRunner.execute_single_check: check not applicable",
                extra={
                    "doc_id": str(getattr(doc, "id", None)),
                    "check_id": check_id,
                },
            )
            await save_not_applicable_result(
                repo=repo,
                run_id=run_id,
                doc=doc,
                check_id=check_id,
                playbook_version_id=self.playbook_version_id,
            )
            return {"exec_result": None, "failed": False}

        if safe_chunks is None:
            safe_chunks = await self._chunks.build_safe_chunks(
                session=session,
                doc=doc,
                checks=[check],
            )

        exec_result = self.executor.execute(doc, check, safe_chunks)

        await save_check_result(
            repo=repo,
            run_id=run_id,
            doc=doc,
            check=check,
            exec_result=exec_result,
            playbook_version_id=self.playbook_version_id,
        )

        return {
            "exec_result": exec_result,
            "failed": exec_result.get("result") == "fail",
        }

    async def _is_multi_document(self, session: AsyncSession, doc) -> bool:
        """
        Определить, участвует ли документ в multi-document пайплайне (есть сегменты).

        Для непрофессионального программиста:
        - Если по последней версии документа есть хотя бы один сегмент с segment_id,
          значит документ обрабатывается как multi-document.
        - В этом случае проверки будем запускать по сегментам, а не только по целому файлу.
        """
        version_repo = DocumentVersionRepository(session)
        segment_repo = DocumentSegmentRepository(session)

        version = await version_repo.get_latest(doc.id)
        if not version:
            return False

        count = await segment_repo.count_by_version_and_has_segment_id(version.id)
        return count > 0

    async def _iter_segments_for_document(self, session: AsyncSession, doc):
        """
        Вернуть (version, список сегментов) для документа.

        Для непрофессионального программиста:
        - Этот метод нужен, чтобы не дублировать код получения версии и сегментов.
        - Если нет версии или сегментов, возвращает (None, []).
        """
        version_repo = DocumentVersionRepository(session)
        segment_repo = DocumentSegmentRepository(session)

        version = await version_repo.get_latest(doc.id)
        if not version:
            return None, []

        segments = await segment_repo.list_by_version(version.id)
        return version, segments

    # ── Внутренние методы ───────────────────────────────────────────

    async def _run_checks_for_document(
        self,
        doc,
        run_id: uuid.UUID,
        playbook,
    ) -> Tuple[int, int]:
        """
        Выполнить все релевантные checks для одного документа.

        Для непрофессионального программиста:
        - В обычном режиме (single-document) всё работает как раньше.
        - В multi-document режиме checks подбираются отдельно для каждого сегмента
          по его segment_doc_type и segment_applicable_triggers.
        """
        total_checks = 0
        failed_checks = 0

        async with db_uow() as uow:
            repo = uow.check_results

            is_multi = await self._is_multi_document(uow.session, doc)

            if not is_multi:
                (
                    checks,
                    mode,
                    doc_type,
                    applicable_triggers,
                    global_checks,
                    doc_type_checks,
                ) = self._planner.select_checks_for_document(doc, playbook)

                logger.info(
                    "CheckRunner: checks selected (document-level)",
                    extra={
                        "doc_id": str(getattr(doc, "id", None)),
                        "doc_type": doc_type,
                        "checks_mode": mode,
                        "global_checks": len(global_checks),
                        "doc_type_checks": len(doc_type_checks),
                        "total_checks": len(checks),
                        "is_multi_document": is_multi,
                    },
                )

                if not checks:
                    return 0, 0

                ctx = self._planner.build_context_for_document(
                    doc=doc,
                    document_version_id=None,
                )

                self._log_skipped_conditionals_for_context(
                    ctx=ctx,
                    checks=checks,
                    run_id=run_id,
                )

                safe_chunks = await self._chunks.build_safe_chunks(
                    session=uow.session,
                    doc=doc,
                    checks=checks,
                )

                for check in checks:
                    exec_result = self.executor.execute(doc, check, safe_chunks)
                    await save_check_result(
                        repo=repo,
                        run_id=run_id,
                        doc=doc,
                        check=check,
                        exec_result=exec_result,
                        playbook_version_id=self.playbook_version_id,
                    )
                    total_checks += 1
                    if exec_result.get("result") == "fail":
                        failed_checks += 1

                doc_repo = DocumentRepository(uow.session)
                await doc_repo.set_completed(doc.id)
                return total_checks, failed_checks

            version, segments = await self._iter_segments_for_document(uow.session, doc)
            if not version or not segments:
                (
                    checks,
                    mode,
                    doc_type,
                    applicable_triggers,
                    global_checks,
                    doc_type_checks,
                ) = self._planner.select_checks_for_document(doc, playbook)

                logger.info(
                    "CheckRunner: checks selected (fallback to document-level, no segments)",
                    extra={
                        "doc_id": str(getattr(doc, "id", None)),
                        "doc_type": doc_type,
                        "checks_mode": mode,
                        "global_checks": len(global_checks),
                        "doc_type_checks": len(doc_type_checks),
                        "total_checks": len(checks),
                        "is_multi_document": is_multi,
                    },
                )

                if not checks:
                    return 0, 0

                ctx = self._planner.build_context_for_document(
                    doc=doc,
                    document_version_id=None,
                )

                self._log_skipped_conditionals_for_context(
                    ctx=ctx,
                    checks=checks,
                    run_id=run_id,
                )

                safe_chunks = await self._chunks.build_safe_chunks(
                    session=uow.session,
                    doc=doc,
                    checks=checks,
                )

                for check in checks:
                    exec_result = self.executor.execute(doc, check, safe_chunks)
                    await save_check_result(
                        repo=repo,
                        run_id=run_id,
                        doc=doc,
                        check=check,
                        exec_result=exec_result,
                        playbook_version_id=self.playbook_version_id,
                    )
                    total_checks += 1
                    if exec_result.get("result") == "fail":
                        failed_checks += 1

                doc_repo = DocumentRepository(uow.session)
                await doc_repo.set_completed(doc.id)
                return total_checks, failed_checks

            for segment in segments:
                segment_doc_type = getattr(segment, "segment_doc_type", None)
                segment_triggers = getattr(segment, "segment_applicable_triggers", None) or []

                if not segment_doc_type:
                    logger.info(
                        "CheckRunner: segment skipped (no segment_doc_type)",
                        extra={
                            "doc_id": str(getattr(doc, "id", None)),
                            "segment_id": getattr(segment, "segment_id", None),
                        },
                    )
                    continue

                segment_info = SegmentInfo(
                    segment_id=getattr(segment, "segment_id", None),
                    segment_doc_type=segment_doc_type,
                    triggers=tuple(segment_triggers),
                )

                ctx = self._planner.build_context_for_segment(
                    doc=doc,
                    document_version_id=version.id,
                    segment_info=segment_info,
                )

                (
                    checks,
                    mode,
                    effective_doc_type,
                    applicable_triggers,
                    global_checks,
                    doc_type_checks,
                ) = self._planner.select_checks_for_context(ctx, playbook)

                logger.info(
                    "CheckRunner: checks selected (segment-level)",
                    extra={
                        "doc_id": str(getattr(doc, "id", None)),
                        "segment_id": ctx.segment_id,
                        "segment_doc_type": ctx.segment_doc_type,
                        "effective_doc_type": effective_doc_type,
                        "checks_mode": mode,
                        "global_checks": len(global_checks),
                        "doc_type_checks": len(doc_type_checks),
                        "total_checks": len(checks),
                        "is_multi_document": is_multi,
                    },
                )

                if not checks:
                    continue

                self._log_skipped_conditionals_for_context(
                    ctx=ctx,
                    checks=checks,
                    run_id=run_id,
                )

                safe_chunks = await self._chunks.build_safe_chunks_for_segment(
                    session=uow.session,
                    doc=doc,
                    checks=checks,
                    segment_id=ctx.segment_id,
                )

                for check in checks:
                    exec_result = self.executor.execute(doc, check, safe_chunks)

                    # Добавляем segment metadata в exec_result для downstream normalizer/saver
                    exec_result["segment_id"] = getattr(segment, "segment_id", None)
                    exec_result["segment_type"] = getattr(segment, "segment_type", None)
                    exec_result["segment_title"] = getattr(segment, "segment_title", None)
                    exec_result["segment_order"] = getattr(segment, "segment_order", None)
                    exec_result["is_primary_segment"] = getattr(segment, "is_primary", None)

                    await save_check_result(
                        repo=repo,
                        run_id=run_id,
                        doc=doc,
                        check=check,
                        exec_result=exec_result,
                        playbook_version_id=self.playbook_version_id,
                    )
                    total_checks += 1
                    if exec_result.get("result") == "fail":
                        failed_checks += 1

            doc_repo = DocumentRepository(uow.session)
            await doc_repo.set_completed(doc.id)

        return total_checks, failed_checks

    @staticmethod
    def _log_skipped_conditionals_for_context(
        ctx: CheckContext,
        checks: list[Any],
        run_id: uuid.UUID,
    ) -> None:
        """
        Логирует checks из текущего контекста, которые имеют conditional trigger,
        но не срабатывают из-за отсутствия нужного триггера в ctx.triggers.

        Для непрофессионального программиста:
        - Здесь мы смотрим не на весь playbook, а только на уже выбранный
          planner'ом список checks для данного контекста.
        - Это делает логирование точным: логируем только то, что реально
          относится к текущему document/segment flow.
        """
        try:
            effective_doc_type = (
                ctx.segment_doc_type if ctx.scope == "segment" else ctx.document_type
            )
            available_triggers = {
                str(t).strip()
                for t in (ctx.triggers or ())
                if str(t).strip()
            }

            for check in checks or []:
                if check is None:
                    continue

                check_doc_types = getattr(check, "doc_types", None) or []
                if check_doc_types and effective_doc_type not in check_doc_types:
                    continue

                conditional = getattr(check, "conditional", None)
                if not conditional:
                    continue

                # Поддерживаем оба формата:
                # 1) legacy: conditional.trigger
                # 2) multi-trigger: conditional.triggers = [TriggerCondition(...)]
                required_triggers: set[str] = set()

                single_trigger = getattr(conditional, "trigger", None)
                if single_trigger:
                    required_triggers.add(str(single_trigger).strip())

                conditional_triggers = getattr(conditional, "triggers", None) or []
                for item in conditional_triggers:
                    trigger_name = getattr(item, "name", None)
                    trigger_state = getattr(item, "state", None)

                    # Нас интересуют только включённые триггеры ("on"),
                    # потому что именно так сейчас формируются TriggerCondition из YAML.
                    if trigger_name and (trigger_state in (None, "on")):
                        required_triggers.add(str(trigger_name).strip())

                required_triggers = {t for t in required_triggers if t}
                if not required_triggers:
                    continue

                missing_triggers = sorted(required_triggers - available_triggers)
                if not missing_triggers:
                    continue

                logger.info(
                    "CheckRunner: conditional check skipped for context",
                    extra={
                        "document_id": str(ctx.document_id),
                        "document_version_id": (
                            str(ctx.document_version_id)
                            if ctx.document_version_id
                            else None
                        ),
                        "scope": ctx.scope,
                        "segment_id": ctx.segment_id,
                        "segment_doc_type": ctx.segment_doc_type,
                        "doc_type": effective_doc_type,
                        "run_id": str(run_id),
                        "check_id": getattr(check, "id", None),
                        "required_triggers": sorted(required_triggers),
                        "missing_triggers": missing_triggers,
                        "available_triggers": sorted(available_triggers),
                    },
                )
        except Exception:
            # Логирование условных скипов не должно ломать основной пайплайн.
            pass


        