# src/services/llm_usage_recorder.py

"""
LLMUsageRecorder — сервис записи LLM usage events в immutable ledger.

Принципы:
- Best-effort: сбой записи не роняет pipeline — только warning в лог.
- Idempotent: UniqueConstraint на request_uid защищает от дублей при retry.
- LLMClient не знает о recorder — business context передаётся снаружи.
- Создаётся на каждый вызов с текущей AsyncSession, не singleton.
"""

from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import Integer, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from db.models.llm_usage import LLMUsageEvent
from db.session import transactional_session

logger = get_logger(__name__)

# ── Канонические значения stage ───────────────────────────────────────────────
STAGE_CLASSIFICATION_L4 = "classification_l4"
STAGE_CHECKS_DETECTION_LLM = "checks_detection_llm"
STAGE_CHECKS_EXTRACTION_LLM = "checks_extraction_llm"
STAGE_STRUCTURE_SEMANTIC_ENRICHMENT = "structure_semantic_enrichment"
STAGE_STRUCTURE_CLAUSE_DETECTION = "structure_clause_detection"
STAGE_HEADING_REFINER = "heading_refiner"

REQUEST_UID_MAX_LEN = 128
REQUEST_UID_HASH_HEX_LEN = 40


def normalize_request_uid(uid: str, *, stage: str | None = None) -> str:
    raw = str(uid or "").strip() or "none"

    if len(raw) <= REQUEST_UID_MAX_LEN:
        return raw

    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:REQUEST_UID_HASH_HEX_LEN]
    prefix = (stage or "llm").strip() or "llm"

    max_prefix_len = REQUEST_UID_MAX_LEN - 1 - len(digest)
    if max_prefix_len <= 0:
        return digest[:REQUEST_UID_MAX_LEN]

    return f"{prefix[:max_prefix_len]}:{digest}"

def build_request_uid(
    stage: str,
    deal_id: object,
    document_id: object,
    run_id: object,
    check_id: str | None,
    unique_suffix: str | None = None,
) -> str:
    """
    Построить request_uid для идемпотентной записи.

    По умолчанию UID детерминированный:
    одинаковый logical LLM event при retry даст тот же request_uid.

    Если в одном и том же stage действительно нужно различать несколько
    независимых logical calls, вызывающий код должен передать stable
    unique_suffix (например segment_id/unit_id).
    """
    parts = [
        str(stage),
        str(deal_id) if deal_id else "none",
        str(document_id) if document_id else "none",
        str(run_id) if run_id else "none",
        str(check_id) if check_id else "none",
        str(unique_suffix) if unique_suffix else "none",
    ]
    raw_uid = ":".join(parts)
    return normalize_request_uid(raw_uid, stage=stage)


class LLMUsageRecorder:
    """Записывает LLM usage events в ledger."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @classmethod
    async def record_event_isolated(cls, **kwargs) -> LLMUsageEvent | None:
        """
        Безопасная best-effort запись в отдельной транзакции.

        Использовать в worker-коде, чтобы telemetry никогда не могла
        rollback-нуть основную бизнес-транзакцию.
        """
        async with transactional_session() as session:
            recorder = cls(session)
            return await recorder.record_event(**kwargs)

    async def _safe_rollback(self) -> None:
        try:
            await self._session.rollback()
        except Exception:
            pass

    async def record_event(
        self,
        *,
        tenant_id: uuid.UUID,
        deal_id: uuid.UUID,
        stage: str,
        provider: str,
        model: str,
        run_id: uuid.UUID | None = None,
        document_id: uuid.UUID | None = None,
        check_id: str | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        duration_ms: int | None = None,
        llm_attempts: int | None = None,
        parse_success: bool | None = None,
        error_type: str | None = None,
        request_uid: str | None = None,
    ) -> LLMUsageEvent | None:
        """
        Записать один LLM usage event.

        Возвращает объект или None при ошибке.
        Никогда не бросает исключение — best-effort.
        """
        total_tokens: int | None = None
        if prompt_tokens is not None or completion_tokens is not None:
            total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)

        uid = normalize_request_uid(
            request_uid
            or build_request_uid(
                stage=stage,
                deal_id=deal_id,
                document_id=document_id,
                run_id=run_id,
                check_id=check_id,
            ),
            stage=stage,
        )

        event = LLMUsageEvent(
            tenant_id=tenant_id,
            deal_id=deal_id,
            run_id=run_id,
            document_id=document_id,
            stage=stage,
            check_id=check_id,
            provider=provider or "",
            model=model or "",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            duration_ms=duration_ms,
            llm_attempts=llm_attempts,
            parse_success=parse_success,
            error_type=error_type,
            request_uid=uid,
        )

        use_savepoint = self._session.in_transaction()

        try:
            if use_savepoint:
                async with self._session.begin_nested():
                    self._session.add(event)
                    await self._session.flush()
            else:
                self._session.add(event)
                await self._session.flush()

            return event

        except IntegrityError:
            if not use_savepoint:
                await self._safe_rollback()

            logger.info(
                "LLMUsageRecorder: duplicate request_uid, skipping",
                request_uid=uid,
                stage=stage,
                deal_id=str(deal_id),
            )
            return None

        except Exception as exc:
            if not use_savepoint:
                await self._safe_rollback()

            logger.warning(
                "LLMUsageRecorder: failed to record event",
                stage=stage,
                deal_id=str(deal_id),
                document_id=str(document_id) if document_id else None,
                request_uid=uid,
                error=str(exc),
            )
            return None

    async def get_deal_summary(self, deal_id: uuid.UUID) -> dict:
        """
        Агрегат потребления токенов по сделке.
        Группирует по stage, provider, model.
        """
        stmt = (
            select(
                LLMUsageEvent.stage,
                LLMUsageEvent.provider,
                LLMUsageEvent.model,
                func.count().label("calls"),
                func.coalesce(
                    func.sum(LLMUsageEvent.prompt_tokens), 0
                ).label("prompt_tokens"),
                func.coalesce(
                    func.sum(LLMUsageEvent.completion_tokens), 0
                ).label("completion_tokens"),
                func.coalesce(
                    func.sum(LLMUsageEvent.total_tokens), 0
                ).label("total_tokens"),
                func.avg(LLMUsageEvent.duration_ms).label("avg_duration_ms"),
                func.count(1)
                .filter(LLMUsageEvent.parse_success.is_(False))
                .label("parse_failures"),
            )
            .where(LLMUsageEvent.deal_id == deal_id)
            .group_by(
                LLMUsageEvent.stage,
                LLMUsageEvent.provider,
                LLMUsageEvent.model,
            )
            .order_by(LLMUsageEvent.stage)
        )

        rows = (await self._session.execute(stmt)).all()

        stages: list[dict] = []
        grand_total_tokens = 0
        grand_total_calls = 0

        for row in rows:
            stage_total = int(row.total_tokens or 0)
            stage_calls = int(row.calls or 0)
            grand_total_tokens += stage_total
            grand_total_calls += stage_calls

            stages.append(
                {
                    "stage": row.stage,
                    "provider": row.provider,
                    "model": row.model,
                    "calls": stage_calls,
                    "prompt_tokens": int(row.prompt_tokens or 0),
                    "completion_tokens": int(row.completion_tokens or 0),
                    "total_tokens": stage_total,
                    "avg_duration_ms": (
                        int(row.avg_duration_ms)
                        if row.avg_duration_ms is not None
                        else None
                    ),
                    "parse_failures": int(row.parse_failures or 0),
                }
            )

        return {
            "deal_id": str(deal_id),
            "total_tokens": grand_total_tokens,
            "total_calls": grand_total_calls,
            "by_stage": stages,
        }

    async def get_deal_summary_by_document(self, deal_id: uuid.UUID) -> list[dict]:
        """
        Агрегат потребления токенов по сделке, сгруппированный по документу.

        Возвращает список документов, отсортированных по убыванию
        total_tokens. Документы без document_id пропускаются.
        """
        stmt = (
            select(
                LLMUsageEvent.document_id,
                func.count().label("calls"),
                func.coalesce(
                    func.sum(LLMUsageEvent.prompt_tokens), 0
                ).label("prompt_tokens"),
                func.coalesce(
                    func.sum(LLMUsageEvent.completion_tokens), 0
                ).label("completion_tokens"),
                func.coalesce(
                    func.sum(LLMUsageEvent.total_tokens), 0
                ).label("total_tokens"),
                func.count(1)
                .filter(LLMUsageEvent.parse_success.is_(False))
                .label("parse_failures"),
            )
            .where(
                LLMUsageEvent.deal_id == deal_id,
                LLMUsageEvent.document_id.is_not(None),
            )
            .group_by(LLMUsageEvent.document_id)
            .order_by(func.sum(LLMUsageEvent.total_tokens).cast(Integer).desc())
        )

        rows = (await self._session.execute(stmt)).all()

        return [
            {
                "document_id": str(row.document_id),
                "calls": int(row.calls or 0),
                "prompt_tokens": int(row.prompt_tokens or 0),
                "completion_tokens": int(row.completion_tokens or 0),
                "total_tokens": int(row.total_tokens or 0),
                "parse_failures": int(row.parse_failures or 0),
            }
            for row in rows
        ]


        