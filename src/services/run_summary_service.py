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
from core.i18n.result_locales import (
    get_supported_result_locales,
    is_valid_result_locale,
    is_translation_pair_supported,
)
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
from services.llm_usage_recorder import LLMUsageRecorder
from mas_queue.celery_app import celery_app

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
        from datetime import datetime as _dt, timedelta as _td  # noqa: PLC0415

        summary = await self.ensure_record(run_id)
        if summary is None:
            return None

        claimed = await self.repo.claim_for_generation(run_id)
        if not claimed:
            return await self.get_response(run_id)

        # Актуализируем retry_count из БД после claim
        summary = await self.repo.get_by_run_id(run_id)
        current_retry = getattr(summary, "retry_count", 0) if summary else 0

        try:
            await self._generate_inner(run_id)
        except Exception as exc:
            next_retry_count = current_retry + 1
            # Экспоненциальный backoff: 30с → 60с → 120с → 240с → 480с
            backoff_seconds = 30 * (2 ** current_retry)
            next_retry_time = (
                _dt.utcnow() + _td(seconds=backoff_seconds)
                if next_retry_count < 5
                else None
            )

            logger.warning(
                "Run summary generation attempt failed",
                run_id=str(run_id),
                attempt=next_retry_count,
                next_retry_in_sec=backoff_seconds,
                error=str(exc),
            )

            await self.repo.update_status(
                run_id,
                "failed",
                error_message=str(exc)[:2000],
                retry_count=next_retry_count,
                next_retry_at=next_retry_time,
            )
            await self.session.commit()

        return await self.get_response(run_id)


    async def translate(
        self, run_id: uuid.UUID, target_locale: str
    ) -> Optional[dict[str, Any]]:
        """
        Оркестратор асинхронного перевода резюме (симметричный аналог generate()).

        Пайплайн (anti-hallucination / error recovery):
        1. Проверка существования записи резюме.
        2. Быстрый возврат при попадании в кэш (status='ready').
        3. Вызов RunSummaryTranslationService для перевода.
        4. Сохранение результата (status='ready') или запись status='failed' при сбое.

        LLM-сбои не выбрасывают исключение наружу воркера, а записываются в БД
        в поле translation_status[locale] = 'failed', сохраняя консистентность.
        """
        target = target_locale.strip().lower()
        summary = await self.repo.get_by_run_id(run_id)
        if summary is None:
            return None

        # 1. Быстрая проверка кэша (no-op)
        statuses = dict(summary.translation_status or {})
        translations = dict(summary.translations or {})
        if statuses.get(target) == "ready" and target in translations:
            return {
                "status": "ready",
                "locale": target,
            }

        # Импортируем локально, чтобы гарантированно избежать циклических импортов
        from services.run_summary_translation import RunSummaryTranslationService

        translation_service = RunSummaryTranslationService(self.session)

        try:
            # 2. Выполняем перевод структуры
            translated_payload = await translation_service.translate(run_id, target)

            # 3. Успех: сохраняем перевод в кэш и ставим ready
            translations[target] = translated_payload
            statuses[target] = "ready"

            await self.repo.update_status(
                run_id,
                summary.status,  # сохраняем статус основного резюме
                translations=translations,
                translation_status=statuses,
            )
            await self.session.commit()

            return {
                "status": "ready",
                "locale": target,
            }

        except Exception as exc:
            # 4. Сбой: пишем failed в БД, не роняя Celery-инфраструктуру
            logger.error(
                "Run summary translation attempt failed",
                run_id=str(run_id),
                target_locale=target,
                error=str(exc),
                exc_info=True,
            )

            statuses[target] = "failed"
            await self.repo.update_status(
                run_id,
                summary.status,
                translation_status=statuses,
            )
            await self.session.commit()

            return {
                "status": "failed",
                "locale": target,
                "error": str(exc),
            }


    async def get_response(
        self, run_id: uuid.UUID, locale: Optional[str] = None
    ) -> Optional[dict[str, Any]]:
        """
        Вернуть состояние summary для run с поддержкой мультиязычности.
        
        Если запрошена локаль, отличная от языка анализа:
        - Возвращает кэшированный перевод (если готов)
        - Возвращает исходный текст + translation_status (если переводится/упал)
        """
        summary = await self.repo.get_by_run_id(run_id)
        if summary is None:
            return None

        # Определяем язык анализа (дефолт = "ru")
        run = await self.session.get(Run, run_id)
        analysis_lang = (
            (run.analysis_language or "ru").strip().lower()
            if run
            else "ru"
        )

        # Динамический список поддерживаемых в системе result-локалей
        supported = sorted(get_supported_result_locales())
        if analysis_lang not in supported:
            supported = sorted([analysis_lang] + supported)

        # Базовый ответ — всегда на исходном языке анализа
        base = {
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
            "supported_locales": supported,
            "locale": analysis_lang,
            "translation_status": None,
        }

        requested = (locale or analysis_lang).strip().lower()

        # Если запрошена исходная локаль — отдаем оригинал напрямую
        if requested == analysis_lang:
            return base

        # Валидация запрошенной локали через реестр
        if not is_valid_result_locale(requested):
            return base

        # Проверка, поддерживается ли направление перевода
        if not is_translation_pair_supported(analysis_lang, requested):
            logger.warning(
                "Translation direction is not supported by result_locales.json",
                run_id=str(run_id),
                source=analysis_lang,
                target=requested,
            )
            return base

        translations = summary.translations or {}
        statuses = summary.translation_status or {}
        t_status = statuses.get(requested)

        base["translation_status"] = t_status

        # Если перевод готов — отдаем переведенную версию
        if t_status == "ready" and requested in translations:
            translated = translations[requested]
            base["locale"] = requested
            base["text"] = translated.get("text", summary.text)
            base["claims"] = translated.get("claims", summary.claims)
            base["fallback"] = translated.get("fallback", summary.fallback)
            return base

        # В остальных случаях (pending/failed) отдаем оригинал с актуальным статусом
        return base

    async def request_translation(
        self, run_id: uuid.UUID, target_locale: str
    ) -> str:
        """
        Запросить перевод резюме на target_locale.

        Использует реестр result_locales для валидации.
        Idempotent: повторный вызов при "pending"/"ready" — no-op.
        """
        target = target_locale.strip().lower()

        if not is_valid_result_locale(target):
            raise ValueError(f"Unsupported result locale: {target}")

        summary = await self.repo.get_by_run_id(run_id)
        if summary is None:
            raise ValueError(f"Summary not found for run {run_id}")

        # Определяем язык анализа
        run = await self.session.get(Run, run_id)
        analysis_lang = (
            (run.analysis_language or "ru").strip().lower()
            if run
            else "ru"
        )

        # Перевод на самого себя не требуется
        if target == analysis_lang:
            return "ready"

        # Проверяем, поддерживает ли перевод наша матрица в json
        if not is_translation_pair_supported(analysis_lang, target):
            raise ValueError(
                f"Translation pair {analysis_lang} → {target} is not configured/supported"
            )

        statuses = dict(summary.translation_status or {})
        current = statuses.get(target)

        # Предотвращаем избыточные вызовы LLM и гонки условий
        if current == "ready":
            return "ready"
        if current == "pending":
            return "pending"

        # Переводим в pending и сохраняем
        statuses[target] = "pending"
        await self.repo.update_status(
            run_id,
            summary.status,
            translation_status=statuses,
        )
        await self.session.commit()

        # Отправляем задачу в асинхронную очередь Celery
        celery_app.send_task(
            "workers.translate_run_summary",
            args=[str(run_id), target],
            queue="heavy_llm_checks",
        )

        logger.info(
            "Translation requested asynchronously",
            run_id=str(run_id),
            source=analysis_lang,
            target=target,
        )
        return "pending"

    # ── Inner pipeline ────────────────────────────────────────────────

    async def _generate_inner(self, run_id: uuid.UUID) -> None:
        run = await self.session.get(Run, run_id)
        if not run:
            raise SummaryGenerationError("Run not found for summary generation")

        evidence = await self.evidence_builder.build(run_id)
        fallback = build_fallback(evidence)
        
        # При генерации нового мастер-резюме сбрасываем все старые переводы
        await self.repo.update_status(
            run_id,
            "generating",
            fallback=fallback,
            translations=None,
            translation_status=None,
        )
        await self.session.commit()

        # Pass A: claims plan
        claims, model_a = await self._pass_a(run, evidence)

        # Deterministic validation
        passed, errors = validate_claims(claims, evidence)
        if not passed:
            raise SummaryGenerationError(
                "claims validation failed: " + "; ".join(errors[:10])
            )

        # Pass B: controlled prose
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

    async def _record_usage(
        self, 
        run: Run, 
        stage: str, 
        response: Any,
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
        self, run: Run, evidence: dict[str, Any]
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

        await self._record_usage(
            run, "run_summary_pass_a", response, error_details
        )

        if response is None or not (response.text or "").strip():
            raise SummaryGenerationError(
                f"Pass A LLM call failed: "
                f"{error_details.get('error_message', 'empty response')}"
            )

        claims = self._parse_json(response.text)
        if claims is None:
            logger.warning(
                "Pass A: unparseable JSON from LLM",
                run_id=str(run.id),
                text_length=len(response.text),
                preview=response.text[:300],
            )
            raise SummaryGenerationError(
                f"Pass A: invalid JSON (len={len(response.text)})"
            )

        response.parse_success = True

        logger.info(
            "Pass A claims plan parsed",
            run_id=str(run.id),
            risk_claims=len(claims.get("risk_claims", [])),
        )

        return claims, response.model or None

    async def _pass_b(
        self, run: Run, claims: dict[str, Any], evidence: dict[str, Any]
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

        await self._record_usage(
            run, "run_summary_pass_b", response, error_details
        )

        if response is None or not (response.text or "").strip():
            raise SummaryGenerationError(
                f"Pass B LLM call failed: "
                f"{error_details.get('error_message', 'empty response')}"
            )

        return response.text.strip(), response.model or None

    @staticmethod
    def _parse_json(text: str) -> Optional[dict[str, Any]]:
        """Извлечь JSON из LLM-ответа (pure JSON / code block / embedded)."""
        candidate = (text or "").strip()
        
        # Попытка 1: Чистый JSON
        try:
            parsed = json.loads(candidate)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            pass

        # Попытка 2: Markdown code block
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", candidate, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(1))
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                pass

        # Попытка 3: Первый JSON объект в тексте
        brace = re.search(r"\{.*\}", candidate, re.DOTALL)
        if brace:
            try:
                parsed = json.loads(brace.group(0))
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                pass
        
        # Попытка 4: Найти JSON после ключевых фраз
        for prefix in ["вот json", "here is the json", "json:", "ответ:", "result:"]:
            idx = candidate.lower().find(prefix)
            if idx >= 0:
                rest = candidate[idx + len(prefix):].strip()
                brace = re.search(r"\{.*\}", rest, re.DOTALL)
                if brace:
                    try:
                        parsed = json.loads(brace.group(0))
                        return parsed if isinstance(parsed, dict) else None
                    except json.JSONDecodeError:
                        pass

        return None
        

        