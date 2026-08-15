# src/services/run_summary_service.py

"""
RunSummaryService — оркестратор генерации executive summary.

Пайплайн (production, anti-hallucination):
1. ensure_record   — создать запись 'pending' + deterministic fallback;
2. claim           — атомарно занять генерацию (один воркер из N);
3. evidence        — собрать canonical evidence package;
4. Pass A          — LLM: claims plan (JSON, response_format=json_object);
5. validation      — детерминированная проверка claims против evidence;
6. Pass B          — LLM: controlled prose по валидированным claims;
7. persist         — status='ready' (text+claims) или 'failed' (fallback).

LLM никогда не читает исходные документы — только структурированный
evidence package. При любом сбое пользователь получает deterministic
fallback, а не пустой экран.
"""

import json
import re
import uuid
from typing import Any, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from db.models.run import Run
from db.repositories.run_summary_repo import (
    RunSummaryRepository,
    TERMINAL_RUN_STATUSES,
)
from engine.llm.client import LLMClient
from engine.prompts.loader import load_prompt
from services.run_summary_evidence import RunSummaryEvidenceBuilder
from services.run_summary_fallback import build_fallback
from services.run_summary_validator import validate_claims
from services.llm_usage_recorder import LLMUsageRecorder  # ← 1. НОВОЕ: импорт рекордера

logger = get_logger(__name__)

SUMMARY_PROMPT_VERSION = "executive_summary_v1"

_PASS_A_TEMPERATURE = 0.1
_PASS_B_TEMPERATURE = 0.2
_PASS_A_MAX_TOKENS = 2500
_PASS_B_MAX_TOKENS = 2500


class SummaryGenerationError(Exception):
    """Ошибка генерации резюме (LLM недоступна, валидация не прошла и т.п.)."""


class RunSummaryService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = RunSummaryRepository(session)
        self.evidence_builder = RunSummaryEvidenceBuilder(session)
        self.llm = LLMClient()

    # ── Public API ────────────────────────────────────────────────────

    async def ensure_record(self, run_id: uuid.UUID):
        run = await self.session.get(Run, run_id)
        if run is None or run.status not in TERMINAL_RUN_STATUSES:
            return None

        existing = await self.repo.get_by_run_id(run_id)
        if existing is not None:
            return existing

        evidence = await self.evidence_builder.build(run_id)
        fallback = build_fallback(evidence)
        try:
            summary = await self.repo.create(run_id, run.tenant_id, fallback)
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            return await self.repo.get_by_run_id(run_id)

        logger.info("Run summary record created", run_id=str(run_id))
        return summary

    async def generate(self, run_id: uuid.UUID) -> Optional[dict[str, Any]]:
        summary = await self.ensure_record(run_id)
        if summary is None:
            return None

        claimed = await self.repo.claim_for_generation(run_id)
        if not claimed:
            return await self.get_response(run_id)

        try:
            await self._generate_inner(run_id)
        except Exception as exc:
            logger.warning(
                "Run summary generation failed",
                run_id=str(run_id),
                error=str(exc),
            )
            await self.repo.update_status(
                run_id, "failed", error_message=str(exc)[:2000]
            )
            await self.session.commit()

        return await self.get_response(run_id)

    async def get_response(self, run_id: uuid.UUID) -> Optional[dict[str, Any]]:
        summary = await self.repo.get_by_run_id(run_id)
        if summary is None:
            return None
        return {
            "run_id": str(summary.run_id),
            "status": summary.status,
            "text": summary.text,
            "claims": summary.claims,
            "fallback": summary.fallback,
            "model": summary.model,
            "prompt_version": summary.prompt_version,
            "error_message": summary.error_message,
            "generated_at": (
                summary.updated_at.isoformat() if summary.updated_at else None
            ),
        }

    # ── Inner pipeline ────────────────────────────────────────────────

    async def _generate_inner(self, run_id: uuid.UUID) -> None:
        # ← 2. НОВОЕ: Получаем объект Run для передачи в телеметрию
        run = await self.session.get(Run, run_id)
        if not run:
            raise SummaryGenerationError("Run not found for summary generation")

        evidence = await self.evidence_builder.build(run_id)
        fallback = build_fallback(evidence)
        await self.repo.update_status(run_id, "generating", fallback=fallback)
        await self.session.commit()

        # Pass A: claims plan (теперь передаем run)
        claims, model_a = await self._pass_a(run, evidence)

        # Deterministic validation
        passed, errors = validate_claims(claims, evidence)
        if not passed:
            raise SummaryGenerationError(
                "claims validation failed: " + "; ".join(errors[:10])
            )

        # Pass B: controlled prose (теперь передаем run)
        text, model_b = await self._pass_b(run, claims, evidence)

        await self.repo.update_status(
            run_id,
            "ready",
            text=text,
            claims=claims,
            model=model_b or model_a,
            prompt_version=SUMMARY_PROMPT_VERSION,
            error_message=None,
        )
        await self.session.commit()

        logger.info(
            "Run summary generated",
            run_id=str(run_id),
            prompt_version=SUMMARY_PROMPT_VERSION,
        )

    # ← 3. НОВОЕ: Вспомогательный метод для безопасной записи телеметрии
    async def _record_usage(
        self, 
        run: Run, 
        stage: str, 
        response: Any,  # LLMResponse
        error_details: dict
    ) -> None:
        """Best-effort запись использования LLM. Не роняет пайплайн при сбое."""
        if response is None:
            return
            
        try:
            recorder = LLMUsageRecorder(self.session)
            await recorder.record_event(
                tenant_id=run.tenant_id,
                deal_id=run.deal_id,
                stage=stage,
                provider=response.provider or "unknown",
                model=response.model or "unknown",
                run_id=run.id,
                document_id=None,
                check_id=None,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                llm_attempts=error_details.get("llm_attempts"),
                parse_success=response.parse_success,
                error_type=error_details.get("error_type"),
            )
        except Exception as e:
            logger.warning(
                "Failed to record LLM usage for summary", 
                run_id=str(run.id), 
                stage=stage, 
                error=str(e)
            )

    async def _pass_a(
        self, run: Run, evidence: dict[str, Any]  # ← НОВОЕ: добавлен аргумент run
    ) -> tuple[dict[str, Any], Optional[str]]:
        """Pass A: claims plan (structured JSON)."""
        prompt = load_prompt(
            "summary/claims_plan_v1",
            {"evidence_json": json.dumps(evidence, ensure_ascii=False)},
        )

        response, error_details = await self.llm.call_with_retries_async(
            prompt,
            temperature=_PASS_A_TEMPERATURE,
            max_tokens=_PASS_A_MAX_TOKENS,
            response_format="json_object",
        )

        # ← НОВОЕ: Записываем телеметрию Pass A
        await self._record_usage(run, "run_summary_pass_a", response, error_details)

        if response is None:
            raise SummaryGenerationError(
                f"Pass A LLM call failed: {error_details.get('error_message')}"
            )

        claims = self._parse_json(response.text)
        if claims is None:
            raise SummaryGenerationError("Pass A returned non-JSON output")

        return claims, response.model or None

    async def _pass_b(
        self, run: Run, claims: dict[str, Any], evidence: dict[str, Any]  # ← НОВОЕ: добавлен run
    ) -> tuple[str, Optional[str]]:
        """Pass B: controlled prose по валидированным claims."""
        context = {
            "scope": evidence.get("scope"),
            "coverage": evidence.get("coverage"),
            "risk_distribution": evidence.get("risk_distribution"),
            "open_items": evidence.get("open_items"),
        }

        prompt = load_prompt(
            "summary/controlled_prose_v1",
            {
                "claims_json": json.dumps(claims, ensure_ascii=False),
                "context_json": json.dumps(context, ensure_ascii=False),
            },
        )

        response, error_details = await self.llm.call_with_retries_async(
            prompt,
            temperature=_PASS_B_TEMPERATURE,
            max_tokens=_PASS_B_MAX_TOKENS,
        )

        # ← НОВОЕ: Записываем телеметрию Pass B
        await self._record_usage(run, "run_summary_pass_b", response, error_details)

        if response is None or not (response.text or "").strip():
            raise SummaryGenerationError(
                f"Pass B LLM call failed: {error_details.get('error_message')}"
            )

        return response.text.strip(), response.model or None

    @staticmethod
    def _parse_json(text: str) -> Optional[dict[str, Any]]:
        """Извлечь JSON из LLM-ответа (pure JSON / code block / embedded)."""
        candidate = (text or "").strip()
        try:
            parsed = json.loads(candidate)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            pass

        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", candidate, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(1))
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                pass

        brace = re.search(r"\{.*\}", candidate, re.DOTALL)
        if brace:
            try:
                parsed = json.loads(brace.group(0))
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                pass

        return None
        

        