"""
Application use case for processing pending localized result presentations.

The use case owns D4 business orchestration:
- atomic pending -> processing claim;
- canonical source/hash validation;
- configured LLM invocation;
- ready / failed / stale persistence;
- translation usage metadata.

The Celery worker remains a thin transport adapter.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any
from core.exceptions import TransientError, PermanentError
from core.logging import get_logger

logger = get_logger(__name__)
from sqlalchemy.ext.asyncio import AsyncSession

from core.result_presentation_content import (
    PRESENTATION_CONTENT_VERSION_V1,
    PRESENTATION_CONTENT_VERSION_V2,
    build_presentation_source_hash,
)
from db.models.result import CheckResult
from db.repositories.check_result_presentation_repo import (
    CheckResultPresentationRepository,
)
from engine.llm.client import LLMClient
from services.llm_usage_recorder import (
    LLMUsageRecorder,
    STAGE_RESULT_PRESENTATION_TRANSLATION,
)
from services.result_presentation_translation_service import (
    RESULT_PRESENTATION_TRANSLATION_PROMPT_VERSION,
    translate_result_presentation,
)
from engine.localization.glossary_resolver import GlossaryResolver
from engine.localization.validator import (
    validate_translation_response,
    GlossaryComplianceError,
)
from db.repositories.legal_glossary_repo import LegalGlossaryRepository
from ops.metrics import get_metrics
from services.translation_audit import (
    ACTION_CLAIMED,
    ACTION_FAILED,
    ACTION_TRANSLATED,
    ACTOR_WORKER,
    log_translation_event,
)


@dataclass(frozen=True)
class ClaimedPresentation:
    """Detached primitive data captured before the claim transaction is closed."""

    presentation_id: uuid.UUID
    check_result_id: uuid.UUID
    locale: str
    content_version: str
    source_content_hash: str
    source_locale: str | None


class ResultPresentationTranslationUseCase:
    """Process one pending result-presentation batch sequentially."""

    def __init__(
        self,
        *,
        db: AsyncSession,
        llm_client: LLMClient | None = None,
        glossary_resolver: GlossaryResolver | None = None,
    ) -> None:
        self.db = db
        self.llm_client = llm_client or LLMClient()
        self.presentation_repo = CheckResultPresentationRepository(db)
        self.glossary_resolver = glossary_resolver

    async def execute(
        self,
        *,
        run_id: str,
        deal_id: str,
        tenant_id: str,
        locale: str,
        content_version: str = PRESENTATION_CONTENT_VERSION_V2,
        batch_limit: int = 25,
    ) -> dict[str, Any]:
        """
        Claim and process up to batch_limit pending presentation records.

        A task processes records sequentially to avoid excessive local GPU/VRAM
        contention. The worker may be safely redelivered: only pending rows are
        claimed and terminal rows are never reopened.
        """
        run_uuid = uuid.UUID(run_id)
        normalized_locale = locale.strip().lower()
        normalized_version = content_version.strip()

        if not normalized_locale:
            raise ValueError("locale must be a non-empty string")

        if not normalized_version:
            raise ValueError("content_version must be a non-empty string")

        claimed_orm = await self.presentation_repo.claim_pending_for_run(
            run_id=run_uuid,
            locale=normalized_locale,
            content_version=normalized_version,
            limit=batch_limit,
        )

        claimed = [
            ClaimedPresentation(
                presentation_id=item.id,
                check_result_id=item.check_result_id,
                locale=item.locale,
                content_version=item.content_version,
                source_content_hash=item.source_content_hash,
                source_locale=item.source_locale,
            )
            for item in claimed_orm
        ]

        # Commit the pending -> processing claim before any LLM call.
        # No PostgreSQL row lock remains active during local model inference.
        await self.db.commit()

        # Sprint 6.5: Emit Prometheus metric for claimed items
        if claimed:
            try:
                get_metrics().translation_claimed_total.labels(locale=normalized_locale).inc(len(claimed))
            except Exception:
                pass

        # Sprint 6.4: Audit — log claim of presentations by background worker
        if claimed:
            try:
                await log_translation_event(
                    self.db,
                    tenant_id=uuid.UUID(tenant_id),
                    deal_id=uuid.UUID(deal_id),
                    action=ACTION_CLAIMED,
                    actor=ACTOR_WORKER,
                    details={
                        "run_id": run_id,
                        "locale": normalized_locale,
                        "content_version": normalized_version,
                        "claimed_count": len(claimed),
                    },
                )
                await self.db.commit()
            except Exception:
                await self.db.rollback()

        summary: dict[str, Any] = {
            "status": "completed",
            "run_id": run_id,
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "locale": normalized_locale,
            "content_version": normalized_version,
            "claimed": len(claimed),
            "ready": 0,
            "failed": 0,
            "stale": 0,
            "missing_result": 0,
        }

        for item in claimed:
            try:
                await self._process_one(item=item, summary=summary)
            except TransientError:
                logger.warning(
                    "Transient error on presentation %s, will retry next batch",
                    item.presentation_id,
                )
            except Exception:
                logger.exception(
                    "Unexpected error on presentation %s",
                    item.presentation_id,
                )

        return summary

    async def _process_one(
        self,
        *,
        item: ClaimedPresentation,
        summary: dict[str, Any],
    ) -> None:
        """Process one already-claimed presentation row."""
        check_result = await self.db.get(CheckResult, item.check_result_id)

        if check_result is None:
            await self.presentation_repo.mark_failed(
                presentation_id=item.presentation_id,
                error_message="Canonical CheckResult was not found",
                translation_metadata={
                    "prompt_version": RESULT_PRESENTATION_TRANSLATION_PROMPT_VERSION,
                    "failure_reason": "check_result_not_found",
                },
            )
            await self.db.commit()
            summary["failed"] += 1
            summary["missing_result"] += 1

            # Sprint 6.5: Emit Prometheus failure metric
            try:
                get_metrics().translation_failed_total.labels(
                    locale=item.locale, reason="check_result_not_found"
                ).inc()
            except Exception:
                pass

            return

        # Snapshot canonical values while the ORM row is loaded and before the
        # transaction is committed. LLM execution must use primitives only.
        check_name = check_result.check_name
        display_text = check_result.display_text
        review_message = check_result.review_message
        document_id = check_result.document_id
        check_id = check_result.check_id

        # Extract free-text fields from structured_data for Matrix translation
        raw_structured_data = check_result.structured_data or {}
        structured_data_fields: dict[str, str] = {}
        if isinstance(raw_structured_data, dict):
            for field_name, field_payload in raw_structured_data.items():
                if isinstance(field_payload, dict):
                    raw_val = field_payload.get("value")
                    if isinstance(raw_val, str) and raw_val.strip():
                        structured_data_fields[field_name] = raw_val.strip()

        current_hash = build_presentation_source_hash(
            check_name=check_name,
            display_text=display_text,
            review_message=review_message,
            structured_data=raw_structured_data if item.content_version == PRESENTATION_CONTENT_VERSION_V2 else None,
            content_version=item.content_version,
        )

        if current_hash != item.source_content_hash:
            await self.presentation_repo.mark_stale(
                presentation_id=item.presentation_id,
                translation_metadata={
                    "prompt_version": RESULT_PRESENTATION_TRANSLATION_PROMPT_VERSION,
                    "failure_reason": "source_content_hash_mismatch",
                    "stored_source_content_hash": item.source_content_hash,
                    "current_source_content_hash": current_hash,
                },
            )
            await self.db.commit()
            summary["stale"] += 1
            return

        # End the read transaction before the potentially long LLM request.
        await self.db.commit()

        started = time.perf_counter()

        try:
            # Build source text for glossary compliance validation (S3.6)
            source_text_parts = [check_name]
            if display_text:
                source_text_parts.append(display_text)
            if review_message:
                source_text_parts.append(review_message)
            source_text = " ".join(source_text_parts) if source_text_parts else None

            # Load glossary terms if resolver is provided (S3.6)
            glossary_terms: dict[str, str] | None = None
            if self.glossary_resolver:
                glossary_terms = await self.glossary_resolver.resolve_terms(
                    tenant_id=uuid.UUID(summary["tenant_id"]),
                    source_locale=item.source_locale or "ru",
                    target_locale=item.locale,
                )

            translated = await translate_result_presentation(
                llm_client=self.llm_client,
                source_locale=item.source_locale,
                target_locale=item.locale,
                check_name=check_name,
                display_text=display_text,
                review_message=review_message,
                structured_data_fields=structured_data_fields or None,
                glossary_terms=glossary_terms if glossary_terms else None,
            )

            # Post-translation validation if glossary was used (S3.5/S3.6)
            if glossary_terms:
                expected_keys = {"localized_check_name", "display_text", "review_message"}
                validation_result = validate_translation_response(
                    response_text=translated.raw_response.get("text", ""),
                    expected_keys=expected_keys,
                    glossary_terms=glossary_terms,
                    source_text=source_text,
                )

                # If glossary violations found, raise retryable error
                if validation_result.glossary_violations:
                    violation = validation_result.glossary_violations[0]
                    raise GlossaryComplianceError(
                        f"Glossary compliance failed: {violation.source_term} -> {violation.expected_target}",
                        source_term=violation.source_term,
                        expected_target=violation.expected_target,
                        actual_target=violation.actual_target,
                    )

        except GlossaryComplianceError as exc:
            # Glossary violations are retryable — reset to pending
            duration_ms = int((time.perf_counter() - started) * 1000)
            await self.presentation_repo.mark_failed(
                presentation_id=item.presentation_id,
                error_message=str(exc),
                translation_metadata={
                    "prompt_version": RESULT_PRESENTATION_TRANSLATION_PROMPT_VERSION,
                    "failure_reason": "glossary_compliance_violation",
                    "duration_ms": duration_ms,
                },
            )
            await self.presentation_repo.reset_processing_to_pending(
                presentation_id=item.presentation_id
            )
            await self.db.commit()

            # Sprint 6.5: Emit Prometheus failure metric
            try:
                get_metrics().translation_failed_total.labels(
                    locale=item.locale, reason="glossary_compliance_violation"
                ).inc()
            except Exception:
                pass

            raise TransientError(f"Glossary compliance violation (will retry): {exc}") from exc

        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            exc_str = str(exc)

            # Проверяем, является ли ошибка транзитной (сетевой/LLM таймаут)
            is_transient = any(
                marker in exc_str.lower()
                for marker in ["transient_error", "timeout", "connect_error", "httpx.timeoutexception", "httpx.connecterror"]
            )

            if is_transient:
                await self.presentation_repo.mark_failed(
                    presentation_id=item.presentation_id,
                    error_message=f"Transient failure (will retry): {exc_str}",
                    translation_metadata={
                        "prompt_version": RESULT_PRESENTATION_TRANSLATION_PROMPT_VERSION,
                        "failure_reason": "transient_translation_error",
                        "duration_ms": duration_ms,
                    },
                )
                await self.presentation_repo.reset_processing_to_pending(
                    presentation_id=item.presentation_id
                )
                await self.db.commit()

                # Sprint 6.5: Emit Prometheus failure metric
                try:
                    get_metrics().translation_failed_total.labels(
                        locale=item.locale, reason="transient_translation_error"
                    ).inc()
                except Exception:
                    pass

                raise TransientError(f"LLM translation transient failure: {exc_str}") from exc

            # Перманентная ошибка (неверный prompt, JSON parse error, etc.)
            await self.presentation_repo.mark_failed(
                presentation_id=item.presentation_id,
                error_message=exc_str,
                translation_metadata={
                    "prompt_version": RESULT_PRESENTATION_TRANSLATION_PROMPT_VERSION,
                    "failure_reason": "translation_error",
                    "duration_ms": duration_ms,
                },
            )
            await self.db.commit()
            summary["failed"] += 1

            # Sprint 6.5: Emit Prometheus failure metric
            try:
                get_metrics().translation_failed_total.labels(
                    locale=item.locale, reason="translation_error"
                ).inc()
            except Exception:
                pass

            # Sprint 6.4: Audit — log permanent translation failure
            try:
                await log_translation_event(
                    self.db,
                    tenant_id=uuid.UUID(summary["tenant_id"]),
                    deal_id=uuid.UUID(summary["deal_id"]),
                    action=ACTION_FAILED,
                    actor=ACTOR_WORKER,
                    details={
                        "presentation_id": str(item.presentation_id),
                        "locale": item.locale,
                        "failure_reason": "translation_error",
                        "duration_ms": duration_ms,
                        "error": exc_str[:500],
                    },
                )
                await self.db.commit()
            except Exception:
                await self.db.rollback()

            return

        duration_ms = int((time.perf_counter() - started) * 1000)

        translation_metadata = {
            "prompt_version": RESULT_PRESENTATION_TRANSLATION_PROMPT_VERSION,
            "execution_mode": "active_application_provider",
            "source_locale": item.source_locale,
            "target_locale": item.locale,
            "content_version": item.content_version,
            "source_content_hash": item.source_content_hash,
            "duration_ms": duration_ms,
            "llm_attempts": translated.attempts,
            "prompt_tokens": translated.prompt_tokens,
            "completion_tokens": translated.completion_tokens,
        }

        await self.presentation_repo.mark_ready(
            presentation_id=item.presentation_id,
            localized_check_name=translated.localized_check_name,
            display_text=translated.display_text,
            review_message=translated.review_message,
            localized_structured_data=translated.localized_structured_data,
            translation_provider=translated.provider,
            translation_model=translated.model,
            translation_metadata=translation_metadata,
        )
        await self.db.commit()

        # Sprint 6.5: Emit success and duration metrics to Prometheus
        try:
            get_metrics().translation_success_total.labels(
                locale=item.locale,
                provider=translated.provider,
                model=translated.model,
            ).inc()
            get_metrics().translation_duration_seconds.labels(
                locale=item.locale,
                provider=translated.provider,
            ).observe(duration_ms / 1000.0)
        except Exception:
            pass

        # Sprint 6.4: Audit — log successful translation
        try:
            await log_translation_event(
                self.db,
                tenant_id=uuid.UUID(summary["tenant_id"]),
                deal_id=uuid.UUID(summary["deal_id"]),
                action=ACTION_TRANSLATED,
                actor=ACTOR_WORKER,
                details={
                    "presentation_id": str(item.presentation_id),
                    "locale": item.locale,
                    "duration_ms": duration_ms,
                    "provider": translated.provider,
                    "model": translated.model,
                },
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()

        try:
            usage_recorder = LLMUsageRecorder(self.db)
            await usage_recorder.record_event(
                tenant_id=uuid.UUID(summary["tenant_id"]),
                deal_id=uuid.UUID(summary["deal_id"]),
                run_id=uuid.UUID(summary["run_id"]),
                document_id=document_id,
                check_id=check_id,
                stage=STAGE_RESULT_PRESENTATION_TRANSLATION,
                provider=translated.provider,
                model=translated.model,
                prompt_tokens=translated.prompt_tokens,
                completion_tokens=translated.completion_tokens,
                duration_ms=duration_ms,
                llm_attempts=translated.attempts,
                parse_success=True,
                error_type=None,
                request_uid=(
                    "result-presentation-translation:"
                    f"{item.presentation_id}:{item.content_version}"
                ),
            )
            await self.db.commit()
        except Exception:
            # Usage logging is intentionally best-effort. Translation state has
            # already been committed and must not be changed by telemetry errors.
            await self.db.rollback()

        summary["ready"] += 1
