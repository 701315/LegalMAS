# src/classifiers/stage8/hybrid_classifier.py
"""
Гибридный классификатор документов по каскаду уровней L1 → L2 → L3 → (L4/LLM-fallback).

ФАСАД / точка входа.
─────────────────────────────────────────────────────────────────────────────
ВАЖНО: этот файл намеренно остаётся центральным — все внешние импорты
вида `from classifiers.stage8.hybrid_classifier import HybridClassifier`
продолжают работать без изменений.

Внутренняя реализация делегирована специализированным модулям:
  _voting.py            — взвешенное голосование L1–L3
  _l4_llm.py            — вызов LLM и парсинг ответа (L4-fallback)
  _l4_executor.py       — L4 execution: document + segment
  _content_fetcher.py   — получение header/snippet из DocumentContentService
  _duplicate_handler.py — обработка мастер-копий (Stage 7)
  _result_builder.py    — построение финального DTO и applicable_triggers
  _decision_support.py  — voting details, pre-L4 signal, helper payloads
  _l4_policy.py         — L4 gating, shortlist и allowed_types policy
  _priority_rules.py    — специальные правила приоритета до голосования
  _finalization.py      — финализация fallback-результата
  _cascade_steps.py     — шаги каскада L1, L2, L3
"""

from __future__ import annotations

import time

from ..yaml_registry import YAMLRegistry
from ops.metrics import get_metrics

from core.config import settings
from core.logging import get_logger
from db.repositories.runner_repo import RunnerRepository
from engine.content.document_content_service import DocumentContentService
from engine.llm.client import LLMClient

from .l1_filename import L1FilenameClassifier
from .l2_header import L2HeaderClassifier
from .l3_semantic import L3SemanticClassifier
from ._voting import WeightedVoter
from ._l4_llm import L4LLMClassifier
from ._content_fetcher import ContentFetcher
from ._duplicate_handler import DuplicateHandler
from ._result_builder import ResultBuilder
from ._decision_support import best_pre_l4_signal, apply_voting
from ._priority_rules import PriorityRulesEvaluator
from ._finalization import FallbackFinalizer
from ._cascade_steps import CascadeSteps
from ._l4_executor import L4Executor
from ._decision_logger import DecisionStrategy, log_classification_decision

# Реэкспорт контрактов — внешние импорты не ломаются
from classifiers.base import HybridClassificationCandidate, HybridClassificationResultDTO  # noqa: F401

__all__ = [
    "HybridClassifier",
    "HybridClassificationCandidate",
    "HybridClassificationResultDTO",
]

logger = get_logger(__name__)


class HybridClassifier:
    """
    Гибридный классификатор документов.

    Публичный API (неизменён):
      classify_document(doc_id: str) -> dict
      classify_segment(...) -> dict

    Каскад:
      L1 (filename) → L2 (header/keywords) → L3 (semantic) → L4 (LLM-fallback)
    """

    def __init__(
        self,
        uow,
        content_service: DocumentContentService | None = None,
    ) -> None:
        self.uow = uow
        self.metrics = get_metrics()
        self.registry = YAMLRegistry.get_instance()

        # Пороги
        base_accept = float(getattr(settings, "CLASSIFICATION_HYBRID_ACCEPT", 0.65))
        base_unknown = float(getattr(settings, "CLASSIFICATION_UNKNOWN_MAX", 0.40))
        self.hybrid_accept: float = float(
            getattr(settings, "CLASSIFIER_ACCEPT_THRESHOLD", base_accept)
        )
        self.unknown_max: float = float(
            getattr(settings, "CLASSIFIER_UNKNOWN_THRESHOLD", base_unknown)
        )
        self.l4_enabled: bool = bool(getattr(settings, "CLASSIFIER_L4_ENABLED", True))

        level_weights: dict[str, float] = {
            "L1": float(getattr(settings, "CLASSIFIER_L1_WEIGHT", 0.20)),
            "L2": 0.40,
            "L3": 0.40,
        }

        # Делегаты
        self._repo = RunnerRepository(uow.session)
        self._voter = WeightedVoter(level_weights)
        self._llm = L4LLMClassifier(LLMClient(), self.registry)
        self._fetcher = ContentFetcher(content_service)
        self._duplicates = DuplicateHandler(self._repo)
        self._builder = ResultBuilder(self.registry, self.hybrid_accept, self.unknown_max)
        self._priority_rules = PriorityRulesEvaluator(
            registry=self.registry,
            builder=self._builder,
            metrics=self.metrics,
        )
        self._finalizer = FallbackFinalizer(
            builder=self._builder,
            metrics=self.metrics,
        )
        self._l4_executor = L4Executor(
            llm=self._llm,
            builder=self._builder,
            metrics=self.metrics,
            registry=self.registry,
            l4_enabled=self.l4_enabled,
            hybrid_accept=self.hybrid_accept,
        )

        # Классификаторы уровней + каскад
        self.l1 = L1FilenameClassifier()
        self.l2 = L2HeaderClassifier()
        self.l3 = L3SemanticClassifier()
        self._cascade = CascadeSteps(l1=self.l1, l2=self.l2, l3=self.l3)

    # ══════════════════════════════════════════════════════════════════
    # Публичный API
    # ══════════════════════════════════════════════════════════════════

    async def classify_document(self, doc_id: str) -> dict:
        """
        Основной метод классификации одного документа.
        Каскад: L1 → L2 → L3 → (L4-fallback при необходимости).
        """
        started_at = time.time()

        doc = await self.uow.documents.get_by_id(doc_id)
        if doc is None:
            logger.warning("HybridClassifier: document not found", doc_id=doc_id)
            return self._empty_result()

        filename = getattr(doc, "filename", "") or ""
        folder = getattr(doc, "folder_path", None) or getattr(doc, "folder", "") or ""

        logger.debug(
            "Hybrid classify_document start",
            extra={
                "doc_id": doc_id,
                "filename": filename,
                "folder_path": folder,
                "is_duplicate": bool(getattr(doc, "is_duplicate", False)),
            },
        )

        details: dict = {
            "levels_tried": [],
            "candidates": [],
            "contradiction_detected": False,
            "input_quality": 1.0,
        }
        candidates: list[dict] = []
        language: str | None = None
        jurisdiction: str | None = None
        applicable_triggers: list[str] = []

        # ── Stage 7: дубликаты ────────────────────────────────────────
        master_result = self._duplicates.get_master_result(doc)
        if master_result is not None:
            details["levels_tried"].append("MASTERCOPY")
            details["MASTERCOPY"] = {
                "type": master_result["doc_type"],
                "confidence": master_result["classification_confidence"],
                "copied_from_master": master_result["master_id"],
            }
            self.metrics.classification_duration.labels(source="copied").observe(
                time.time() - started_at
            )
            log_classification_decision(
                doc_id=doc_id,
                decided_by=DecisionStrategy.COPIED,
                final_type=master_result["doc_type"],
                final_confidence=master_result["classification_confidence"],
                levels_tried=details["levels_tried"],
                started_at=started_at,
                extra={"copied_from_master": str(master_result["master_id"])},
            )
            return self._builder.build(
                levels_tried=details["levels_tried"],
                candidates=[],
                final_type=master_result["doc_type"],
                final_confidence=master_result["classification_confidence"],
                level="COPIED",
                language=master_result["language"],
                jurisdiction=master_result["jurisdiction"],
                applicable_triggers=master_result["applicable_triggers"],
                details=details,
                copied_from_master=master_result["master_id"],
            )

        # ── L1 ───────────────────────────────────────────────────────
        top_l1, candidates, details = self._cascade.run_l1(
            doc_id=doc_id,
            filename=filename,
            folder=folder,
            candidates=candidates,
            details=details,
        )

        # ── Content fetch ─────────────────────────────────────────────
        header_text, snippet_text = await self._fetcher.fetch(doc.id)
        logger.debug(
            "Hybrid content fetched",
            extra={
                "doc_id": doc_id,
                "has_header": bool(header_text),
                "has_snippet": bool(snippet_text),
                "header_preview": repr((header_text or "")[:200]),
                "snippet_preview": repr((snippet_text or "")[:200]),
            },
        )

        # ── L2 ───────────────────────────────────────────────────────
        top_l2, candidates, details = await self._cascade.run_l2(
            doc_id=doc_id,
            header_text=header_text,
            snippet_text=snippet_text,
            filename=filename,
            folder=folder,
            candidates=candidates,
            details=details,
        )

        # ── L3 ───────────────────────────────────────────────────────
        top_l3, candidates, details, language, jurisdiction, applicable_triggers = (
            await self._cascade.run_l3(
                doc_id=doc_id,
                snippet_text=snippet_text,
                filename=filename,
                folder=folder,
                candidates=candidates,
                details=details,
                language=language,
                jurisdiction=jurisdiction,
                applicable_triggers=applicable_triggers,
            )
        )

        # ── Приоритетные правила ──────────────────────────────────────
        early = self._priority_rules.evaluate(
            doc_id=doc_id,
            top_l1=top_l1,
            top_l2=top_l2,
            top_l3=top_l3,
            candidates=candidates,
            details=details,
            language=language,
            jurisdiction=jurisdiction,
            started_at=started_at,
        )
        if early is not None:
            return early

        # ── Взвешенное голосование ────────────────────────────────────
        candidates.sort(key=lambda c: float(c.get("confidence", 0.0)), reverse=True)
        details["candidates"] = (
            candidates
            if settings.CLASSIFICATION_TRACE_INCLUDE_CANDIDATES
            else candidates[:3]
        )

        voted = self._voter.vote(candidates)
        final_type, final_conf, language, jurisdiction, details = apply_voting(
            doc_id=doc_id,
            voted=voted,
            top_l1=top_l1,
            top_l3=top_l3,
            language=language,
            jurisdiction=jurisdiction,
            details=details,
        )

        # ── Если голосование уверенное — HYBRID ──────────────────────
        if voted is not None and final_conf >= self.hybrid_accept:
            self.metrics.classification_duration.labels(
                source="hybrid_voting"
            ).observe(time.time() - started_at)
            voting_details = details.get("voting") or {}
            log_classification_decision(
                doc_id=doc_id,
                decided_by=DecisionStrategy.HYBRID_VOTING,
                final_type=final_type,
                final_confidence=final_conf,
                levels_tried=details["levels_tried"],
                started_at=started_at,
                contradiction=details.get("contradiction_detected", False),
                voting_score=voting_details.get("score"),
                single_source_cap_applied=voting_details.get("single_source_cap_applied"),
                extra={
                    "voting_margin": details.get("voting_margin"),
                    "voting_override": bool(details.get("voting_override")),
                    "support_count": voting_details.get("support_count"),
                    "support_levels": voting_details.get("support_levels"),
                },
            )
            return self._builder.build(
                levels_tried=details["levels_tried"],
                candidates=candidates,
                final_type=final_type,
                final_confidence=final_conf,
                level="HYBRID",
                language=language,
                jurisdiction=jurisdiction,
                applicable_triggers=self._builder.build_triggers(doc_id, final_type),
                details=details,
            )

        # ── Pre-L4 signal ─────────────────────────────────────────────
        final_type_av, final_conf_av, language, jurisdiction, pre_l4_src = (
            best_pre_l4_signal(
                voted=voted,
                top_l1=top_l1,
                top_l2=top_l2,
                top_l3=top_l3,
                language=language,
                jurisdiction=jurisdiction,
            )
        )
        details["pre_l4_best_signal"] = {
            "source": pre_l4_src,
            "type": final_type_av,
            "confidence": final_conf_av,
        }

        # ── L4 ───────────────────────────────────────────────────────
        llm_final = await self._l4_executor.run_for_document(
            doc_id=doc_id,
            filename=filename,
            folder=folder,
            header_text=header_text,
            snippet_text=snippet_text,
            final_conf_after_voting=final_conf_av,
            details=details,
            candidates=candidates,
            language=language,
            jurisdiction=jurisdiction,
            started_at=started_at,
        )
        if llm_final is not None:
            return llm_final

        # ── Fallback ─────────────────────────────────────────────────
        return self._finalizer.build_fallback_result(
            doc_id=doc_id,
            final_type=final_type_av,
            final_conf=final_conf_av,
            voted=voted,
            candidates=candidates,
            details=details,
            language=language,
            jurisdiction=jurisdiction,
            started_at=started_at,
        )

    async def classify_segment(
        self,
        *,
        segment_id: str,
        text: str,
        filename: str = "",
        folder_path: str = "",
        language_hint: str | None = None,
        jurisdiction_hint: str | None = None,
    ) -> dict:
        """
        Классификация одного сегмента текста (segment-aware режим).
        Не ходит в DocumentRepository и не меняет Document.
        """
        started_at = time.time()

        details: dict = {
            "levels_tried": [],
            "candidates": [],
            "contradiction_detected": False,
            "input_quality": 1.0,
        }
        candidates: list[dict] = []
        language = language_hint
        jurisdiction = jurisdiction_hint
        applicable_triggers: list[str] = []

        # ── L1 (опциональный hint) ────────────────────────────────────
        top_l1: dict | None = None
        if filename or folder_path:
            top_l1, candidates, details = self._cascade.run_l1(
                doc_id=f"segment:{segment_id}",
                filename=filename,
                folder=folder_path or "",
                candidates=candidates,
                details=details,
            )

        # ── L3 ───────────────────────────────────────────────────────
        top_l3, candidates, details, language, jurisdiction, applicable_triggers = (
            await self._cascade.run_l3(
                doc_id=f"segment:{segment_id}",
                snippet_text=text,
                filename=filename,
                folder=folder_path or "",
                candidates=candidates,
                details=details,
                language=language,
                jurisdiction=jurisdiction,
                applicable_triggers=applicable_triggers,
            )
        )
        top_l2 = None

        # ── Приоритетные правила ──────────────────────────────────────
        early = self._priority_rules.evaluate(
            doc_id=f"segment:{segment_id}",
            top_l1=top_l1,
            top_l2=top_l2,
            top_l3=top_l3,
            candidates=candidates,
            details=details,
            language=language,
            jurisdiction=jurisdiction,
            started_at=started_at,
        )
        if early is not None:
            return early

        # ── Взвешенное голосование ────────────────────────────────────
        candidates.sort(key=lambda c: float(c.get("confidence", 0.0)), reverse=True)
        details["candidates"] = (
            candidates
            if settings.CLASSIFICATION_TRACE_INCLUDE_CANDIDATES
            else candidates[:3]
        )

        voted = self._voter.vote(candidates)
        final_type, final_conf, language, jurisdiction, details = apply_voting(
            doc_id=f"segment:{segment_id}",
            voted=voted,
            top_l1=top_l1,
            top_l3=top_l3,
            language=language,
            jurisdiction=jurisdiction,
            details=details,
        )

        # ── Если голосование уверенное — HYBRID ──────────────────────
        if voted is not None and final_conf >= self.hybrid_accept:
            self.metrics.classification_duration.labels(
                source="segment_hybrid_voting"
            ).observe(time.time() - started_at)
            voting_details = details.get("voting") or {}
            log_classification_decision(
                doc_id=f"segment:{segment_id}",
                decided_by=DecisionStrategy.HYBRID_VOTING,
                final_type=final_type,
                final_confidence=final_conf,
                levels_tried=details["levels_tried"],
                started_at=started_at,
                contradiction=details.get("contradiction_detected", False),
                voting_score=voting_details.get("score"),
                single_source_cap_applied=voting_details.get("single_source_cap_applied"),
                extra={
                    "voting_margin": details.get("voting_margin"),
                    "segment_id": segment_id,
                    "support_count": voting_details.get("support_count"),
                    "support_levels": voting_details.get("support_levels"),
                },
            )
            return self._builder.build(
                levels_tried=details["levels_tried"],
                candidates=candidates,
                final_type=final_type,
                final_confidence=final_conf,
                level="HYBRID",
                language=language,
                jurisdiction=jurisdiction,
                applicable_triggers=applicable_triggers,
                details=details,
            )

        # ── Pre-L4 signal ─────────────────────────────────────────────
        final_type_av, final_conf_av, language, jurisdiction, pre_l4_src = (
            best_pre_l4_signal(
                voted=voted,
                top_l1=top_l1,
                top_l2=None,
                top_l3=top_l3,
                language=language,
                jurisdiction=jurisdiction,
            )
        )
        details["pre_l4_best_signal"] = {
            "source": pre_l4_src,
            "type": final_type_av,
            "confidence": final_conf_av,
            "segment_id": segment_id,
        }

        # ── L4 ───────────────────────────────────────────────────────
        llm_final = await self._l4_executor.run_for_segment(
            segment_id=segment_id,
            text=text,
            filename=filename,
            folder=folder_path or "",
            final_conf_after_voting=final_conf_av,
            details=details,
            candidates=candidates,
            language=language,
            jurisdiction=jurisdiction,
            applicable_triggers=applicable_triggers,
            started_at=started_at,
        )
        if llm_final is not None:
            return llm_final

        # ── Fallback ─────────────────────────────────────────────────
        return self._finalizer.build_fallback_result(
            doc_id=f"segment:{segment_id}",
            final_type=final_type_av,
            final_conf=final_conf_av,
            voted=voted,
            candidates=candidates,
            details=details,
            language=language,
            jurisdiction=jurisdiction,
            started_at=started_at,
            applicable_triggers=applicable_triggers,
        )

    # ══════════════════════════════════════════════════════════════════
    # Статические helpers
    # ══════════════════════════════════════════════════════════════════

    @staticmethod
    def _empty_result() -> dict:
        return {
            "levels_tried": [],
            "candidates": [],
            "final_type": "UNKNOWN",
            "final_confidence": 0.0,
            "level": None,
            "language": None,
            "jurisdiction": None,
            "applicable_triggers": [],
            "details": {
                "levels_tried": [],
                "candidates": [],
                "confidence_zone": "unknown",
                "requires_manual_review": True,
                "voting": {
                    "strategy": "NO_RESULT",
                    "reason": "no levels executed, no candidates produced",
                    "type": "UNKNOWN",
                    "score": None,
                    "confidence": 0.0,
                    "margin": None,
                    "support_count": None,
                    "support_levels": [],
                    "single_source_cap_applied": False,
                    "ranking": [],
                    "extra": {},
                },
                "voting_margin": None,
                "unknown_corridor": {
                    "applied": True,
                    "original_type": "UNKNOWN",
                    "original_confidence": 0.0,
                    "final_type_after_corridor": "UNKNOWN",
                },
            },
        }
    
    
