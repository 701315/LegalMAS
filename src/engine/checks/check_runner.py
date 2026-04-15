# src/engine/checks/runner.py

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
from engine.checks.executor import CheckExecutor
from engine.checks.planning.chunks import ChunksPreparer
from engine.checks.planning.planner import CheckPlanner
from engine.checks.planning.scope import ScopeResolver
from engine.checks.result_saver import save_check_result, save_not_applicable_result

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
                    doc, run_id, playbook,
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
        """Выполнить одну проверку и сохранить результат."""
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
                session=session, doc=doc, checks=[check],
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

    # ── Внутренние методы ───────────────────────────────────────────

    async def _run_checks_for_document(
        self,
        doc,
        run_id: uuid.UUID,
        playbook,
    ) -> Tuple[int, int]:
        """Выполнить все релевантные checks для одного документа."""
        total_checks = 0
        failed_checks = 0

        async with db_uow() as uow:
            repo = uow.check_results

            (
                checks, mode, doc_type, applicable_triggers,
                global_checks, doc_type_checks,
            ) = self._planner.select_checks_for_document(doc, playbook)

            logger.info(
                "CheckRunner: checks selected",
                extra={
                    "doc_id": str(getattr(doc, "id", None)),
                    "doc_type": doc_type,
                    "checks_mode": mode,
                    "global_checks": len(global_checks),
                    "doc_type_checks": len(doc_type_checks),
                    "total_checks": len(checks),
                },
            )

            if not checks:
                return 0, 0

            # Log skipped conditional checks
            self._log_skipped_conditionals(doc, run_id, playbook, doc_type, applicable_triggers)

            safe_chunks = await self._chunks.build_safe_chunks(
                session=uow.session, doc=doc, checks=checks,
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

    @staticmethod
    def _log_skipped_conditionals(
        doc, run_id, playbook, doc_type, applicable_triggers,
    ) -> None:
        """Логирует conditional checks, пропущенные из-за отсутствия триггера."""
        try:
            for check in getattr(playbook, "checks", []):
                if getattr(check, "doc_types", None) and doc_type not in check.doc_types:
                    continue
                conditional = getattr(check, "conditional", None)
                if not conditional:
                    continue
                if isinstance(conditional, dict):
                    trigger = conditional.get("trigger")
                else:
                    trigger = getattr(conditional, "trigger", None)
                if trigger and trigger not in applicable_triggers:
                    logger.info(
                        "CheckRunner: conditional check skipped",
                        extra={
                            "doc_id": str(getattr(doc, "id", None)),
                            "run_id": str(run_id),
                            "check_id": getattr(check, "id", None),
                            "required_trigger": trigger,
                        },
                    )
        except Exception:
            pass

        