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

from sqlalchemy.ext.asyncio import AsyncSession

from core.result_presentation_content import (
    PRESENTATION_CONTENT_VERSION_V1,
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
    ) -> None:
        self.db = db
        self.llm_client = llm_client or LLMClient()
        self.presentation_repo = CheckResultPresentationRepository(db)

    async def execute(
        self,
        *,
        run_id: str,
        deal_id: str,
        tenant_id: str,
        locale: str,
        content_version: str = PRESENTATION_CONTENT_VERSION_V1,
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
            await self._process_one(item=item, summary=summary)

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
            return

        # Snapshot canonical values while the ORM row is loaded and before the
        # transaction is committed. LLM execution must use primitives only.
        check_name = check_result.check_name
        display_text = check_result.display_text
        review_message = check_result.review_message
        document_id = check_result.document_id
        check_id = check_result.check_id

        current_hash = build_presentation_source_hash(
            check_name=check_name,
            display_text=display_text,
            review_message=review_message,
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
            translated = await translate_result_presentation(
                llm_client=self.llm_client,
                source_locale=item.source_locale,
                target_locale=item.locale,
                check_name=check_name,
                display_text=display_text,
                review_message=review_message,
            )
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)

            await self.presentation_repo.mark_failed(
                presentation_id=item.presentation_id,
                error_message=str(exc),
                translation_metadata={
                    "prompt_version": RESULT_PRESENTATION_TRANSLATION_PROMPT_VERSION,
                    "failure_reason": "translation_error",
                    "duration_ms": duration_ms,
                },
            )
            await self.db.commit()
            summary["failed"] += 1
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
            translation_provider=translated.provider,
            translation_model=translated.model,
            translation_metadata=translation_metadata,
        )
        await self.db.commit()

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
