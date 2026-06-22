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

logger = get_logger(__name__)

MAX_DOCS_PER_RUN = 500
MAX_ERRORS_PER_RUN = 50


# ─── Document snapshot helper ────────────────────────────────────────────────


def _snapshot_check_doc(doc: Any) -> DocumentSnapshot:
    """
    Снять immutable snapshot документа сразу после загрузки ORM-объекта.

    Использует shared контракт DocumentSnapshot из core.pipeline_snapshots.
    Это superset всех полей, нужных checks execution stack:
    - id, doc_type, applicable_triggers, classification_confidence.

    Вызывать сразу после получения ORM-объекта, до первого await.
    """
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
    ) -> None:
        self.llm_client = llm_client
        self.executor = CheckExecutor(llm_client) if llm_client is not None else None
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

        # READ + SNAPSHOT:
        # Документы читаем в одном UoW и сразу превращаем в snapshots
        # через shared контракт core.pipeline_snapshots.
        # Нельзя переносить live ORM Document через границу закрытого UoW.
        async with db_uow() as uow_for_docs:
            runner_repo = RunnerRepository(uow_for_docs.session)
            docs = await runner_repo.get_non_duplicate_docs(deal_id)
            doc_snaps: list[DocumentSnapshot] = [_snapshot_check_doc(doc) for doc in docs]

        if not doc_snaps:
            logger.info(
                "CheckRunner: no non-duplicate documents",
                extra={"deal_id": str(deal_id), "run_id": str(run_id)},
            )
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
                    doc_snap,
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
                        "doc_id": doc_snap.document_id_str,
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
        """
        Legacy-совместимый helper.

        Принимает любой duck-typed объект (ORM Document или DocumentSnapshot).
        Planner читает только id / doc_type / applicable_triggers через getattr,
        поэтому DocumentSnapshot полностью совместим с этим контрактом.
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
    ) -> dict[str, Any]:
        """
        Выполнить одну проверку и сохранить результат.

        Публичную сигнатуру сохраняем: caller всё ещё передаёт `doc`.
        Но сразу внутри приводим его к DocumentSnapshot из core.pipeline_snapshots,
        чтобы дальше deeper layers не зависели от live ORM.
        Это устраняет класс ошибок, когда ORM-объект живёт слишком долго
        через await-цепочки.
        """
        if self.executor is None:
            raise RuntimeError(
                "CheckRunner.execute_single_check вызван без llm_client. "
                "Передайте llm_client= при создании CheckRunner для задач выполнения."
            )

        # Если caller уже передал snapshot — не переснимаем.
        doc_snap: DocumentSnapshot = (
            doc if isinstance(doc, DocumentSnapshot) else _snapshot_check_doc(doc)
        )

        check = self._planner.find_check_for_document(doc_snap, playbook, check_id)

        if check is None:
            logger.warning(
                "CheckRunner.execute_single_check: check not applicable",
                extra={
                    "doc_id": doc_snap.document_id_str,
                    "check_id": check_id,
                },
            )
            await save_not_applicable_result(
                repo=repo,
                run_id=run_id,
                doc=doc_snap,
                check_id=check_id,
                playbook_version_id=self.playbook_version_id,
            )
            return {"exec_result": None, "failed": False}

        if safe_chunks is None:
            _, segments = await self._iter_segments_for_document(
                session=session,
                document_id=doc_snap.document_id,
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
        )

        return {
            "exec_result": exec_result,
            "failed": exec_result.get("result") == "fail",
        }

    async def _is_multi_document(
        self,
        session: AsyncSession,
        document_id: uuid.UUID,
    ) -> bool:
        """
        Определить, участвует ли документ в multi-document пайплайне (есть сегменты).
        """
        version_repo = DocumentVersionRepository(session)
        segment_repo = DocumentSegmentRepository(session)

        version = await version_repo.get_latest(document_id)
        if not version:
            return False

        count = await segment_repo.count_by_version_and_has_segment_id(version.id)
        return count > 0

    async def _iter_segments_for_document(
        self,
        session: AsyncSession,
        document_id: uuid.UUID,
    ):
        """
        Вернуть (version, список сегментов) для документа.
        """
        version_repo = DocumentVersionRepository(session)
        segment_repo = DocumentSegmentRepository(session)

        version = await version_repo.get_latest(document_id)
        if not version:
            return None, []

        segments = await segment_repo.list_by_version(version.id)
        return version, segments

    # ── Внутренние методы ──────────────────────────────────────────

    async def _build_corpus_for_check(
        self,
        *,
        session: AsyncSession,
        doc: DocumentSnapshot,
        check: Any,
        segments: list[Any] | None,
        current_segment: Any | None,
    ) -> list[dict]:
        """
        Build retrieval corpus for a single check based on its corpus_scope policy.

        Routing logic:
        - No segments (single-document) → document-level corpus, no enrichment.
        - corpus_scope=primary_segment → primary segment corpus with enrichment.
        - corpus_scope=current_segment → current segment corpus with enrichment.
          Falls back to primary segment if current_segment is None.
        - corpus_scope=document → full document corpus with per-segment enrichment.
          ScopeResolver handles final scope filtering (default: primary + appendix).

        Failure-isolated at every step:
        - DB error → fallback to document-level without enrichment.
        - Enrichment sidecar load error → proceed without enrichment projection.
        - Segment not found → fallback to document-level without enrichment.
        """
        corpus_scope = getattr(
            getattr(check, "retrieval", None),
            "corpus_scope",
            RetrievalCorpusScope.PRIMARY_SEGMENT,
        )

        # SINGLE-DOCUMENT PATH (no segments)
        if not segments:
            return await self._chunks.build_safe_chunks(
                session=session,
                doc=doc,
                checks=[check],
            )

        artifact_store = ArtifactStore()

        # ── PRIMARY_SEGMENT ────────────────────────────────────────────────────
        if corpus_scope == RetrievalCorpusScope.PRIMARY_SEGMENT:
            primary_segments = [
                s for s in segments if bool(getattr(s, "is_primary", False))
            ]
            if not primary_segments:
                logger.warning(
                    "CheckRunner._build_corpus_for_check: "
                    "no primary segment found, falling back to document-level",
                    extra={"doc_id": doc.document_id_str},
                )
                return await self._chunks.build_safe_chunks(
                    session=session,
                    doc=doc,
                    checks=[check],
                )

            primary = primary_segments[0]
            segment_id = getattr(primary, "segment_id", None)
            if not segment_id:
                return await self._chunks.build_safe_chunks(
                    session=session,
                    doc=doc,
                    checks=[check],
                )

            sidecar: dict | None = None
            try:
                meta = dict(getattr(primary, "segment_meta", None) or {})
                ref = meta.get("legal_units_enrichment_ref")
                if ref and isinstance(ref, str):
                    sidecar = artifact_store.get_json(ref)
            except Exception as exc:
                logger.warning(
                    "CheckRunner._build_corpus_for_check: "
                    "failed to load primary segment enrichment sidecar",
                    extra={
                        "doc_id": doc.document_id_str,
                        "segment_id": segment_id,
                        "error": str(exc),
                    },
                )

            return await self._chunks.build_safe_chunks_for_segment(
                session=session,
                doc=doc,
                checks=[check],
                segment_id=segment_id,
                enrichment_sidecar=sidecar,
            )

        # ── CURRENT_SEGMENT ────────────────────────────────────────────────────
        if corpus_scope == RetrievalCorpusScope.CURRENT_SEGMENT:
            target_segment = current_segment
            if target_segment is None:
                logger.warning(
                    "CheckRunner._build_corpus_for_check: "
                    "corpus_scope=current_segment but no current_segment provided, "
                    "falling back to primary segment",
                    extra={"doc_id": doc.document_id_str},
                )
                primary_segments = [
                    s for s in segments if bool(getattr(s, "is_primary", False))
                ]
                target_segment = primary_segments[0] if primary_segments else None

            if target_segment is None:
                return await self._chunks.build_safe_chunks(
                    session=session,
                    doc=doc,
                    checks=[check],
                )

            segment_id = getattr(target_segment, "segment_id", None)
            if not segment_id:
                return await self._chunks.build_safe_chunks(
                    session=session,
                    doc=doc,
                    checks=[check],
                )

            sidecar = None
            try:
                meta = dict(getattr(target_segment, "segment_meta", None) or {})
                ref = meta.get("legal_units_enrichment_ref")
                if ref and isinstance(ref, str):
                    sidecar = artifact_store.get_json(ref)
            except Exception as exc:
                logger.warning(
                    "CheckRunner._build_corpus_for_check: "
                    "failed to load current segment enrichment sidecar",
                    extra={
                        "doc_id": doc.document_id_str,
                        "segment_id": segment_id,
                        "error": str(exc),
                    },
                )

            return await self._chunks.build_safe_chunks_for_segment(
                session=session,
                doc=doc,
                checks=[check],
                segment_id=segment_id,
                enrichment_sidecar=sidecar,
            )

        # ── DOCUMENT (cross-segment) ───────────────────────────────────────────
        if corpus_scope == RetrievalCorpusScope.DOCUMENT:
            sidecars_by_segment: dict[str, dict] = {}
            for seg in segments:
                seg_id = getattr(seg, "segment_id", None)
                if not seg_id:
                    continue
                try:
                    meta = dict(getattr(seg, "segment_meta", None) or {})
                    ref = meta.get("legal_units_enrichment_ref")
                    if ref and isinstance(ref, str):
                        sidecars_by_segment[seg_id] = artifact_store.get_json(ref)
                except Exception as exc:
                    logger.warning(
                        "CheckRunner._build_corpus_for_check: "
                        "failed to load enrichment sidecar for segment, skipping",
                        extra={
                            "doc_id": doc.document_id_str,
                            "segment_id": seg_id,
                            "error": str(exc),
                        },
                    )

            return await self._chunks.build_safe_chunks(
                session=session,
                doc=doc,
                checks=[check],
                enrichment_sidecars_by_segment=sidecars_by_segment or None,
            )

        # FALLBACK (unknown scope value)
        logger.warning(
            "CheckRunner._build_corpus_for_check: unknown corpus_scope, "
            "falling back to document-level",
            extra={
                "doc_id": doc.document_id_str,
                "corpus_scope": str(corpus_scope),
            },
        )
        return await self._chunks.build_safe_chunks(
            session=session,
            doc=doc,
            checks=[check],
        )

    async def _run_checks_for_document(
        self,
        doc_snap: DocumentSnapshot,
        run_id: uuid.UUID,
        playbook,
    ) -> tuple[int, int]:
        """
        Выполнить все релевантные checks для одного документа.

        Сюда приходит DocumentSnapshot из core.pipeline_snapshots, а не live ORM.
        Deeper layers получают только snapshot.
        В текущем UoW обращаемся к БД только там, где действительно нужно:
        latest version, segments, запись результатов, mark completed.
        """
        total_checks = 0
        failed_checks = 0

        async with db_uow() as uow:
            repo = uow.check_results
            doc_repo = DocumentRepository(uow.session)

            is_multi = await self._is_multi_document(
                uow.session,
                doc_snap.document_id,
            )

            if not is_multi:
                (
                    checks,
                    mode,
                    doc_type,
                    applicable_triggers,
                    global_checks,
                    doc_type_checks,
                ) = self._planner.select_checks_for_document(doc_snap, playbook)

                logger.info(
                    "CheckRunner: checks selected (document-level)",
                    extra={
                        "doc_id": doc_snap.document_id_str,
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
                    doc=doc_snap,
                    document_version_id=None,
                )

                self._log_skipped_conditionals_for_context(
                    ctx=ctx,
                    checks=checks,
                    run_id=run_id,
                )

                safe_chunks = await self._chunks.build_safe_chunks(
                    session=uow.session,
                    doc=doc_snap,
                    checks=checks,
                )

                for check in checks:
                    exec_result = self.executor.execute(doc_snap, check, safe_chunks)
                    await save_check_result(
                        repo=repo,
                        run_id=run_id,
                        doc=doc_snap,
                        check=check,
                        exec_result=exec_result,
                        playbook_version_id=self.playbook_version_id,
                    )
                    total_checks += 1
                    if exec_result.get("result") == "fail":
                        failed_checks += 1

                await doc_repo.set_completed(doc_snap.document_id)
                return total_checks, failed_checks

            version, segments = await self._iter_segments_for_document(
                uow.session,
                doc_snap.document_id,
            )
            if not version or not segments:
                (
                    checks,
                    mode,
                    doc_type,
                    applicable_triggers,
                    global_checks,
                    doc_type_checks,
                ) = self._planner.select_checks_for_document(doc_snap, playbook)

                logger.info(
                    "CheckRunner: checks selected (fallback to document-level, no segments)",
                    extra={
                        "doc_id": doc_snap.document_id_str,
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
                    doc=doc_snap,
                    document_version_id=None,
                )

                self._log_skipped_conditionals_for_context(
                    ctx=ctx,
                    checks=checks,
                    run_id=run_id,
                )

                safe_chunks = await self._chunks.build_safe_chunks(
                    session=uow.session,
                    doc=doc_snap,
                    checks=checks,
                )

                for check in checks:
                    exec_result = self.executor.execute(doc_snap, check, safe_chunks)
                    await save_check_result(
                        repo=repo,
                        run_id=run_id,
                        doc=doc_snap,
                        check=check,
                        exec_result=exec_result,
                        playbook_version_id=self.playbook_version_id,
                    )
                    total_checks += 1
                    if exec_result.get("result") == "fail":
                        failed_checks += 1

                await doc_repo.set_completed(doc_snap.document_id)
                return total_checks, failed_checks

            for segment in segments:
                segment_doc_type = getattr(segment, "segment_doc_type", None)
                segment_triggers = getattr(segment, "segment_applicable_triggers", None) or []

                if not segment_doc_type:
                    logger.info(
                        "CheckRunner: segment skipped (no segment_doc_type)",
                        extra={
                            "doc_id": doc_snap.document_id_str,
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
                    doc=doc_snap,
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
                        "doc_id": doc_snap.document_id_str,
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

                # Load enrichment sidecar once per segment.
                # Used for two purposes:
                # 1. Runtime projection of enriched metadata onto legal_unit chunks
                #    → passed into build_safe_chunks_for_segment → reader.
                # 2. SemanticEnrichmentContext for executor segment-level hints.
                # Loading once avoids duplicate MinIO I/O.
                # Failure-isolated: any error → None → graceful degradation.
                # Enrichment sidecar для semantic_context executor'а.
                # Загружается отдельно от corpus building —
                # corpus builder загружает sidecar'ы сам внутри _build_corpus_for_check.
                _artifact_store = ArtifactStore()
                _enrichment_sidecar: dict | None = None
                try:
                    _segment_meta = dict(getattr(segment, "segment_meta", None) or {})
                    _enrichment_ref = _segment_meta.get("legal_units_enrichment_ref")
                    if _enrichment_ref and isinstance(_enrichment_ref, str):
                        _enrichment_sidecar = _artifact_store.get_json(_enrichment_ref)
                except Exception as _enr_exc:
                    logger.warning(
                        "CheckRunner: failed to load enrichment sidecar for semantic_context",
                        extra={
                            "doc_id": doc_snap.document_id_str,
                            "segment_id": ctx.segment_id,
                            "error": str(_enr_exc),
                        },
                    )
                    _enrichment_sidecar = None

                # Per-check corpus cache keyed by (corpus_scope, segment_id, levels).
                # Checks with the same corpus policy reuse the same built corpus.
                # This avoids redundant I/O while supporting mixed corpus policies.
                corpus_cache: dict[tuple, list[dict]] = {}

                # SemanticEnrichmentContext построим из того же загруженного sidecar.
                # Передаём _artifact_store чтобы load_enrichment_context_for_segment
                # мог перечитать при необходимости (он сам проверит наличие ref).
                _semantic_context = load_enrichment_context_for_segment(
                    document_id=doc_snap.document_id_str,
                    segment=segment,
                    artifact_store=_artifact_store,
                )

                for check in checks:
                    # Build corpus per check, using corpus_scope policy.
                    # Corpus is cached by (scope, segment_id, levels) key
                    # to avoid redundant I/O for checks with identical policy.
                    _corpus_scope = getattr(
                        getattr(check, "retrieval", None),
                        "corpus_scope",
                        RetrievalCorpusScope.PRIMARY_SEGMENT,
                    )
                    _corpus_key = (
                        _corpus_scope,
                        ctx.segment_id,
                        tuple(sorted(
                            getattr(getattr(check, "retrieval", None), "levels", None)
                            or ["legal_unit", "section"]
                        )),
                    )

                    if _corpus_key not in corpus_cache:
                        corpus_cache[_corpus_key] = await self._build_corpus_for_check(
                            session=uow.session,
                            doc=doc_snap,
                            check=check,
                            segments=segments,
                            current_segment=segment,
                        )

                    safe_chunks = corpus_cache[_corpus_key]

                    exec_result = self.executor.execute(
                        doc_snap,
                        check,
                        safe_chunks,
                        semantic_context=_semantic_context,
                    )

                    # Provenance override policy:
                    # For primary_segment / current_segment corpus checks:
                    #   the execution segment IS the retrieval segment → safe to override.
                    # For document corpus checks:
                    #   evidence may come from any segment (e.g. appendix) →
                    #   provenance already set correctly from chunk metadata by executor →
                    #   do NOT override with current execution segment.
                    if _corpus_scope != RetrievalCorpusScope.DOCUMENT:
                        exec_result["segment_id"] = getattr(segment, "segment_id", None)
                        exec_result["segment_type"] = getattr(segment, "segment_type", None)
                        exec_result["segment_title"] = getattr(segment, "segment_title", None)
                        exec_result["segment_order"] = getattr(segment, "segment_order", None)
                        exec_result["is_primary_segment"] = getattr(segment, "is_primary", None)

                    await save_check_result(
                        repo=repo,
                        run_id=run_id,
                        doc=doc_snap,
                        check=check,
                        exec_result=exec_result,
                        playbook_version_id=self.playbook_version_id,
                    )
                    total_checks += 1
                    if exec_result.get("result") == "fail":
                        failed_checks += 1

            await doc_repo.set_completed(doc_snap.document_id)

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
        """
        try:
            effective_doc_type = (
                ctx.segment_doc_type if ctx.scope == "segment" else ctx.document_type
            )
            available_triggers = {str(t).strip() for t in (ctx.triggers or ()) if str(t).strip()}

            for check in checks or []:
                if check is None:
                    continue

                check_doc_types = getattr(check, "doc_types", None) or []
                if check_doc_types and effective_doc_type not in check_doc_types:
                    continue

                conditional = getattr(check, "conditional", None)
                if not conditional:
                    continue

                required_triggers: set[str] = set()

                single_trigger = getattr(conditional, "trigger", None)
                if single_trigger:
                    required_triggers.add(str(single_trigger).strip())

                conditional_triggers = getattr(conditional, "triggers", None) or []
                for item in conditional_triggers:
                    trigger_name = getattr(item, "name", None)
                    trigger_state = getattr(item, "state", None)

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
                            str(ctx.document_version_id) if ctx.document_version_id else None
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
            pass
