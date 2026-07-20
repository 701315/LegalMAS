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

Важное правило работы с ORM:
- ORM-объекты не должны переноситься между разными db_uow()/AsyncSession.
- Поэтому документы, прочитанные в одном UoW, сразу снимаются в snapshots,
  а дальше checks execution stack работает только с immutable value objects.
- Shared snapshot-контракты живут в core.pipeline_snapshots.
- DocumentSnapshot из core.pipeline_snapshots является superset всех полей,
  нужных checks execution stack.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from core.pipeline_snapshots import DocumentSnapshot, snapshot_document
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_segment_repo import DocumentSegmentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from db.repositories.run_repo import RunRepository
from db.repositories.runner_repo import RunnerRepository
from db.uow import db_uow
from engine.checks.executor import CheckExecutor
from engine.checks.enrichment_loader import load_enrichment_context_for_segment
from engine.checks.semantic_context import SemanticEnrichmentContext  # noqa: F401
from storage.artifact_store import ArtifactStore
from engine.checks.planning.chunks import ChunksPreparer
from engine.checks.planning.context import CheckContext, SegmentInfo
from engine.checks.planning.planner import CheckPlanner
from engine.checks.planning.scope import ScopeResolver
from engine.checks.result_saver import save_check_result, save_not_applicable_result
from engine.playbook.models import RetrievalCorpusScope
from engine.doc_type_checks.loader import DocTypeCheckLoader

logger = get_logger(__name__)

MAX_DOCS_PER_RUN = 500
MAX_ERRORS_PER_RUN = 50


def _snapshot_check_doc(doc: Any) -> DocumentSnapshot:
    """Снять immutable snapshot документа сразу после загрузки ORM-объекта."""
    return snapshot_document(doc)


class CheckRunner:
    """
    Playbook-based checks executor.
    Оркеструет: планирование → подготовка чанков → выполнение → сохранение.
    """

    def __init__(
        self,
        llm_client=None,
        playbook_version_id: uuid.UUID | None = None,
        checks_mode: str = "global_and_doc_type",
        run_repo: RunRepository | None = None,
        checks_scope: dict[str, Any] | None = None,
        doc_type_loader: DocTypeCheckLoader | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.executor = CheckExecutor(llm_client) if llm_client is not None else None
        self.playbook_version_id = playbook_version_id
        self.run_repo = run_repo

        self._planner = CheckPlanner(
            checks_mode=checks_mode,
            doc_type_loader=doc_type_loader,
        )
        self._scope = ScopeResolver(checks_scope=checks_scope)
        self._chunks = ChunksPreparer(scope_resolver=self._scope)

    @property
    def checks_mode(self) -> str:
        return self._planner.checks_mode

    @checks_mode.setter
    def checks_mode(self, value: str) -> None:
        self._planner.checks_mode = value

    # ── Публичный API ──────────────────────────────────────────────

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
            doc_snaps: list[DocumentSnapshot] = [_snapshot_check_doc(doc) for doc in docs]

        if not doc_snaps:
            return summary

        if len(doc_snaps) > MAX_DOCS_PER_RUN:
            logger.warning(
                "CheckRunner: truncating documents",
                extra={"count": len(doc_snaps), "max_docs": MAX_DOCS_PER_RUN},
            )
            doc_snaps = doc_snaps[:MAX_DOCS_PER_RUN]

        for doc_snap in doc_snaps:
            try:
                checks_count, failed_count = await self._run_checks_for_document(
                    doc_snap, run_id, playbook
                )
                summary["processed_docs"] += 1
                summary["total_checks"] += checks_count
                summary["failed_checks"] += failed_count

                # Progress for Run is derived from RunCheckPlanItem terminal states.
                # Manual increment of Run.completed_checks is intentionally removed.

            except Exception as e:
                summary["errors"] += 1
                logger.error(
                    "CheckRunner: doc failed",
                    extra={"doc_id": doc_snap.document_id_str, "error": str(e)},
                )
                if summary["errors"] > MAX_ERRORS_PER_RUN:
                    break

        summary["duration_sec"] = time.time() - start_time
        return summary

    async def plan_checks_for_run(
        self,
        *,
        session: AsyncSession,
        deal_id: uuid.UUID,
        run_id: uuid.UUID,
        playbook,
    ) -> dict[str, Any]:
        """
        Делегирует планированию.
        ИСПРАВЛЕНО: восстановлен метод, удалённый при рефакторинге.
        Используется check_worker.py при построении плана выполнения Run.
        """
        return await self._planner.plan_checks_for_run(
            session=session,
            deal_id=deal_id,
            run_id=run_id,
            playbook=playbook,
        )

    def find_check_for_document(self, doc, playbook, check_id: str):
        """
        Legacy-совместимый helper.
        ИСПРАВЛЕНО: восстановлен метод, удалённый при рефакторинге.
        Принимает любой duck-typed объект (ORM Document или DocumentSnapshot).
        """
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
        plan_item_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """Выполнить одну проверку и сохранить результат."""
        if self.executor is None:
            raise RuntimeError(
                "CheckRunner.execute_single_check вызван без llm_client. "
                "Передайте llm_client= при создании CheckRunner для задач выполнения."
            )

        doc_snap: DocumentSnapshot = (
            doc if isinstance(doc, DocumentSnapshot) else _snapshot_check_doc(doc)
        )

        check = self._planner.find_check_for_document(doc_snap, playbook, check_id)

        if check is None:
            logger.warning(
                "CheckRunner.execute_single_check: check not applicable",
                extra={"doc_id": doc_snap.document_id_str, "check_id": check_id},
            )
            await save_not_applicable_result(
                repo=repo,
                run_id=run_id,
                doc=doc_snap,
                check_id=check_id,
                playbook_version_id=self.playbook_version_id,
                plan_item_id=plan_item_id,
            )
            return {"exec_result": None, "failed": False}

        if safe_chunks is None:
            _, segments = await self._iter_segments_for_document(
                session, doc_snap.document_id
            )
            safe_chunks = await self._build_corpus_for_check(
                session=session,
                doc=doc_snap,
                check=check,
                segments=segments,
                current_segment=None,
            )

        exec_result = self.executor.execute(doc_snap, check, safe_chunks)
        await save_check_result(
            repo=repo,
            run_id=run_id,
            doc=doc_snap,
            check=check,
            exec_result=exec_result,
            playbook_version_id=self.playbook_version_id,
            plan_item_id=plan_item_id,
        )
        return {
            "exec_result": exec_result,
            "failed": exec_result.get("result") == "fail",
        }

    # ── Оркестрация выполнения ──────────────────────────────────────

    async def _run_checks_for_document(
        self,
        doc_snap: DocumentSnapshot,
        run_id: uuid.UUID,
        playbook,
    ) -> tuple[int, int]:
        """Роутинг: Single-doc или Multi-doc."""
        async with db_uow() as uow:
            repo = uow.check_results
            doc_repo = DocumentRepository(uow.session)
            is_multi = await self._is_multi_document(uow.session, doc_snap.document_id)

            if not is_multi:
                ctx = self._planner.build_context_for_document(doc_snap, None)
                checks, *_ = self._planner.select_checks_for_context(ctx, playbook)

                async def doc_builder(chk: Any) -> list[dict]:
                    return await self._build_corpus_for_check(
                        session=uow.session,
                        doc=doc_snap,
                        check=chk,
                        segments=None,
                        current_segment=None,
                    )

                t, f = await self._execute_checks_batch(
                    repo=repo,
                    run_id=run_id,
                    doc_snap=doc_snap,
                    checks=checks,
                    ctx=ctx,
                    corpus_builder_fn=doc_builder,
                )

            else:
                t, f = 0, 0
                version, segments = await self._iter_segments_for_document(
                    uow.session, doc_snap.document_id
                )

                for segment in (segments or []):
                    seg_id = getattr(segment, "segment_id", None)
                    seg_type = getattr(segment, "segment_doc_type", None)
                    if not seg_type:
                        continue

                    ctx = self._planner.build_context_for_segment(
                        doc=doc_snap,
                        document_version_id=version.id,
                        segment_info=SegmentInfo(
                            seg_id,
                            seg_type,
                            tuple(getattr(segment, "segment_applicable_triggers", None) or []),
                        ),
                    )
                    checks, *_ = self._planner.select_checks_for_context(ctx, playbook)

                    # ИСПРАВЛЕНО: closure bug — фиксируем значения segment/segments
                    # через аргументы по умолчанию, чтобы замыкание не захватывало
                    # переменную цикла по ссылке (иначе все builders увидят
                    # последний сегмент после завершения цикла).
                    async def seg_builder(
                        chk: Any,
                        _seg: Any = segment,
                        _segs: list = segments,
                    ) -> list[dict]:
                        return await self._build_corpus_for_check(
                            session=uow.session,
                            doc=doc_snap,
                            check=chk,
                            segments=_segs,
                            current_segment=_seg,
                        )

                    prov = {
                        "segment_id": seg_id,
                        "segment_type": seg_type,
                        "segment_title": getattr(segment, "segment_title", None),
                        "segment_order": getattr(segment, "segment_order", None),
                        "is_primary_segment": getattr(segment, "is_primary", None),
                    }

                    res_t, res_f = await self._execute_checks_batch(
                        repo=repo,
                        run_id=run_id,
                        doc_snap=doc_snap,
                        checks=checks,
                        ctx=ctx,
                        corpus_builder_fn=seg_builder,
                        semantic_context=load_enrichment_context_for_segment(
                            doc_snap.document_id_str, segment, ArtifactStore()
                        ),
                        segment_provenance=prov,
                    )
                    t += res_t
                    f += res_f

            # ИСПРАВЛЕНО: set_completed теперь вызывается для ОБОИХ путей (single и multi).
            # В предыдущей версии single-doc делал early return и не достигал этой строки.
            await doc_repo.set_completed(doc_snap.document_id)
            return t, f

    async def _execute_checks_batch(
        self,
        *,
        repo: Any,
        run_id: uuid.UUID,
        doc_snap: DocumentSnapshot,
        checks: list[Any],
        ctx: CheckContext,
        corpus_builder_fn: Any,
        semantic_context: Any | None = None,
        segment_provenance: dict | None = None,
    ) -> tuple[int, int]:
        """Универсальный batch-исполнитель проверок."""
        total, failed = 0, 0
        if not checks:
            return 0, 0

        self._log_skipped_conditionals_for_context(ctx, checks, run_id)

        corpus_cache: dict[tuple, list[dict]] = {}

        for check in checks:
            retr_cfg = getattr(check, "retrieval", None)
            corpus_scope = getattr(retr_cfg, "corpus_scope", RetrievalCorpusScope.PRIMARY_SEGMENT)
            levels = tuple(sorted(getattr(retr_cfg, "levels", None) or ["legal_unit", "section"]))
            cache_key = (corpus_scope, ctx.segment_id, levels)

            if cache_key not in corpus_cache:
                corpus_cache[cache_key] = await corpus_builder_fn(check)

            exec_result = self.executor.execute(
                doc_snap,
                check,
                corpus_cache[cache_key],
                semantic_context=semantic_context,
            )

            if segment_provenance and corpus_scope != RetrievalCorpusScope.DOCUMENT:
                exec_result.update(segment_provenance)

            await save_check_result(
                repo=repo,
                run_id=run_id,
                doc=doc_snap,
                check=check,
                exec_result=exec_result,
                playbook_version_id=self.playbook_version_id,
            )
            total += 1
            if exec_result.get("result") == "fail":
                failed += 1

        return total, failed

    # ── Инфраструктура ─────────────────────────────────────────────

    async def _is_multi_document(
        self,
        session: AsyncSession,
        document_id: uuid.UUID,
    ) -> bool:
        version = await DocumentVersionRepository(session).get_latest(document_id)
        if not version:
            return False
        return (
            await DocumentSegmentRepository(session).count_by_version_and_has_segment_id(
                version.id
            )
            > 0
        )

    async def _iter_segments_for_document(
        self,
        session: AsyncSession,
        document_id: uuid.UUID,
    ):
        version = await DocumentVersionRepository(session).get_latest(document_id)
        if not version:
            return None, []
        segments = await DocumentSegmentRepository(session).list_by_version(version.id)
        return version, segments

    async def _build_corpus_for_check(
        self,
        *,
        session: AsyncSession,
        doc: DocumentSnapshot,
        check: Any,
        segments: list[Any] | None,
        current_segment: Any | None,
    ) -> list[dict]:
        """Логика выбора политики retrieval corpus."""
        scope = getattr(
            getattr(check, "retrieval", None),
            "corpus_scope",
            RetrievalCorpusScope.PRIMARY_SEGMENT,
        )

        if not segments:
            return await self._chunks.build_safe_chunks(
                session=session, doc=doc, checks=[check]
            )

        artifact_store = ArtifactStore()

        if scope in (RetrievalCorpusScope.PRIMARY_SEGMENT, RetrievalCorpusScope.CURRENT_SEGMENT):
            target = current_segment
            if scope == RetrievalCorpusScope.PRIMARY_SEGMENT or target is None:
                primaries = [s for s in segments if getattr(s, "is_primary", False)]
                target = primaries[0] if primaries else segments[0]

            seg_id = getattr(target, "segment_id", None)
            sidecar: dict | None = None
            try:
                ref = (getattr(target, "segment_meta", None) or {}).get(
                    "legal_units_enrichment_ref"
                )
                if ref:
                    sidecar = artifact_store.get_json(ref)
            except Exception:
                pass

            return await self._chunks.build_safe_chunks_for_segment(
                session=session,
                doc=doc,
                checks=[check],
                segment_id=seg_id,
                enrichment_sidecar=sidecar,
            )

        if scope == RetrievalCorpusScope.DOCUMENT:
            sidecars: dict[str, dict] = {}
            for s in segments:
                try:
                    ref = (getattr(s, "segment_meta", None) or {}).get(
                        "legal_units_enrichment_ref"
                    )
                    if ref:
                        sidecars[getattr(s, "segment_id", None)] = artifact_store.get_json(ref)
                except Exception:
                    pass
            return await self._chunks.build_safe_chunks(
                session=session,
                doc=doc,
                checks=[check],
                enrichment_sidecars_by_segment=sidecars,
            )

        return await self._chunks.build_safe_chunks(session=session, doc=doc, checks=[check])

    @staticmethod
    def _log_skipped_conditionals_for_context(
        ctx: CheckContext,
        checks: list[Any],
        run_id: uuid.UUID,
    ) -> None:
        """Логирует checks, пропущенные из-за несработавших триггеров."""
        try:
            available = {str(t).strip() for t in (ctx.triggers or ())}
            for check in (checks or []):
                cond = getattr(check, "conditional", None)
                if not cond:
                    continue
                req: set[str] = set()
                single = getattr(cond, "trigger", None)
                if single:
                    req.add(str(single).strip())
                for t in getattr(cond, "triggers", []):
                    if getattr(t, "state", None) in (None, "on") and getattr(t, "name", None):
                        req.add(str(t.name).strip())
                missing = sorted({t for t in req if t} - available)
                if missing:
                    logger.info(
                        "CheckRunner: conditional skipped",
                        extra={
                            "doc_id": str(ctx.document_id),
                            "check_id": getattr(check, "id", None),
                            "missing_triggers": missing,
                            "run_id": str(run_id),
                        },
                    )
        except Exception:
            pass


        

