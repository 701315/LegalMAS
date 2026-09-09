"""
RunSummaryTranslationService — асинхронный перевод структуры резюме (text, claims, fallback).
"""

import json
import uuid
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from db.models.run import Run
from db.repositories.run_summary_repo import RunSummaryRepository
from engine.llm.client import LLMClient
from engine.prompts.loader import load_prompt
from services.llm_usage_recorder import LLMUsageRecorder

logger = get_logger(__name__)

_TRANSLATE_TEMPERATURE = 0.1
_TRANSLATE_MAX_TOKENS = 3500


class RunSummaryTranslationService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = RunSummaryRepository(session)
        self.llm = LLMClient()

    async def translate(self, run_id: uuid.UUID, target_locale: str) -> dict[str, Any]:
        """
        Перевести резюме (text + claims + fallback) на target_locale.
        Выполняет один LLM-вызов для всего пакета для экономии токенов и времени.
        """
        target = target_locale.strip().lower()
        summary = await self.repo.get_by_run_id(run_id)
        if not summary or not summary.text:
            raise ValueError(f"No ready summary found for run {run_id}")

        run = await self.session.get(Run, run_id)
        if not run:
            raise ValueError(f"Run not found: {run_id}")

        source_locale = (run.analysis_language or "ru").strip().lower()

        # Собираем исходный пакет
        package_to_translate = {
            "text": summary.text,
            "claims": summary.claims or {},
            "fallback": summary.fallback or {},
        }

        prompt = load_prompt(
            "summary/translate_v1",
            {
                "source_locale": source_locale,
                "target_locale": target,
                "source_json": json.dumps(package_to_translate, ensure_ascii=False),
            },
        )

        response, error_details = await self.llm.call_with_retries_async(
            prompt,
            temperature=_TRANSLATE_TEMPERATURE,
            max_tokens=_TRANSLATE_MAX_TOKENS,
            response_format="json_object",
        )

        await self._record_usage(run, f"summary_translate_{target}", response, error_details)

        if response is None or not (response.text or "").strip():
            raise RuntimeError(
                f"LLM translation call failed: {error_details.get('error_message', 'empty response')}"
            )

        # Парсим ответ
        translated_data = self._parse_json(response.text)
        if not translated_data:
            logger.warning(
                "Translation output is not valid JSON",
                run_id=str(run_id),
                preview=response.text[:300],
            )
            raise RuntimeError("Translation output failed JSON parsing validation")

        response.parse_success = True

        # Детерминированно выравниваем структуру
        aligned = self.validate_and_align_translation(translated_data, package_to_translate)
        
        logger.info(
            "Summary translated and aligned successfully",
            run_id=str(run_id),
            target_locale=target,
            model=response.model,
        )
        return aligned

    def validate_and_align_translation(self, translated: dict, original: dict) -> dict:
        """
        Гарантирует 100% структурную целостность перевода.
        Заменяет изменённые или поломанные LLM-машинные идентификаторы
        (check_ids, severities, numbers, filters) обратно на оригинальные.
        """
        aligned = {
            "text": translated.get("text") or original.get("text"),
            "claims": {},
            "fallback": {},
        }

        # 1. Выравнивание CLAIMS
        orig_claims = original.get("claims") or {}
        trans_claims = translated.get("claims") or {}

        aligned_claims = {
            "overall_assessment": trans_claims.get("overall_assessment")
            or orig_claims.get("overall_assessment", "")
        }

        orig_risks = orig_claims.get("risk_claims") or []
        trans_risks = trans_claims.get("risk_claims") or []
        aligned_risks = []

        for idx, orig_risk in enumerate(orig_risks):
            trans_risk = trans_risks[idx] if idx < len(trans_risks) else {}
            aligned_risk = {
                "text": trans_risk.get("text") or orig_risk.get("text", ""),
                "severity": orig_risk.get("severity"),  # Жестко берём оригинал
                "check_ids": orig_risk.get("check_ids"),  # Жестко берём оригинал
            }
            aligned_risks.append(aligned_risk)

        aligned_claims["risk_claims"] = aligned_risks

        # Ограничения покрытия
        if "limitations" in orig_claims:
            orig_limits = orig_claims.get("limitations") or []
            trans_limits = trans_claims.get("limitations") or []
            aligned_limits = []
            for idx, orig_lim in enumerate(orig_limits):
                trans_lim = trans_limits[idx] if idx < len(trans_limits) else orig_lim
                aligned_limits.append(trans_lim)
            aligned_claims["limitations"] = aligned_limits

        aligned["claims"] = aligned_claims

        # 2. Выравнивание FALLBACK
        orig_fb = original.get("fallback") or {}
        trans_fb = translated.get("fallback") or {}

        aligned_fb = {
            "title": trans_fb.get("title") or orig_fb.get("title", "Key Metrics"),
            "coverage": orig_fb.get("coverage"),  # Жестко берём оригинал
            "risk_distribution": orig_fb.get("risk_distribution"),  # Жестко берём оригинал
            "top_findings": [],
            "open_items": [],
            "actions": [],
            "source": orig_fb.get("source", "deterministic_evidence_package"),
        }

        # Выравнивание top_findings
        orig_findings = orig_fb.get("top_findings") or []
        trans_findings = trans_fb.get("top_findings") or []
        aligned_findings = []
        for idx, orig_f in enumerate(orig_findings):
            trans_f = trans_findings[idx] if idx < len(trans_findings) else {}
            aligned_f = {
                "check_id": orig_f.get("check_id"),
                "check_name": trans_f.get("check_name") or orig_f.get("check_name"),
                "severity": orig_f.get("severity"),
                "doc_types": orig_f.get("doc_types"),
                "count": orig_f.get("count"),
            }
            aligned_findings.append(aligned_f)
        aligned_fb["top_findings"] = aligned_findings

        # Выравнивание open_items
        orig_items = orig_fb.get("open_items") or []
        trans_items = trans_fb.get("open_items") or []
        aligned_items = []
        for idx, orig_item in enumerate(orig_items):
            trans_item = trans_items[idx] if idx < len(trans_items) else orig_item
            aligned_items.append(trans_item)
        aligned_fb["open_items"] = aligned_items

        # Выравнивание actions
        orig_actions = orig_fb.get("actions") or []
        trans_actions = trans_fb.get("actions") or []
        aligned_actions = []
        for idx, orig_act in enumerate(orig_actions):
            trans_act = trans_actions[idx] if idx < len(trans_actions) else {}
            aligned_act = {
                "label": trans_act.get("label") or orig_act.get("label"),
                "filter": orig_act.get("filter"),  # Жестко берём оригинал
            }
            aligned_actions.append(aligned_act)
        aligned_fb["actions"] = aligned_actions

        aligned["fallback"] = aligned_fb
        return aligned

    async def _record_usage(
        self, run: Run, stage: str, response: Any, error_details: dict
    ) -> None:
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
                "Failed to record LLM usage for summary translation",
                run_id=str(run.id),
                stage=stage,
                error=str(e),
            )

    @staticmethod
    def _parse_json(text: str) -> Optional[dict[str, Any]]:
        candidate = (text or "").strip()
        try:
            parsed = json.loads(candidate)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            pass

        # Markdown code block helper
        import re
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", candidate, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(1))
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                pass
        return None

        