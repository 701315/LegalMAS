# src/classifiers/stage8/hybrid_classifier.py
"""
Гибридный классификатор документов по каскаду уровней L1 → L2 → L3 → (L4/LLM-fallback).

ФАСАД / точка входа.
─────────────────────────────────────────────────────────────────────────────
ВАЖНО: этот файл намеренно остаётся центральным — все внешние импорты
вида `from classifiers.stage8.hybrid_classifier import HybridClassifier`
продолжают работать без изменений.

Внутренняя реализация делегирована специализированным модулям:
  _voting.py           — взвешенное голосование L1–L3
  _l4_llm.py           — вызов LLM и парсинг ответа (L4-fallback)
  _content_fetcher.py  — получение header/snippet из DocumentContentService
  _duplicate_handler.py— обработка мастер-копий (Stage 7)
  _result_builder.py   — построение финального DTO и applicable_triggers
"""

from __future__ import annotations

import time
from typing import Any, Optional

from .l1_filename import L1FilenameClassifier
from .l2_header import L2HeaderClassifier
from .l3_semantic import L3SemanticClassifier
from ..yaml_registry import YAMLRegistry
from ops.metrics import get_metrics

from core.config import settings
from core.logging import get_logger
from db.repositories.runner_repo import RunnerRepository
from engine.content.document_content_service import DocumentContentService
from engine.llm.client import LLMClient

# Внутренние модули (скрыты от внешнего кода)
from ._voting import WeightedVoter
from ._l4_llm import L4LLMClassifier
from ._content_fetcher import ContentFetcher
from ._duplicate_handler import DuplicateHandler
from ._result_builder import ResultBuilder

# Реэкспорт контрактов — внешние импорты не ломаются
from classifiers.base import HybridClassificationCandidate, HybridClassificationResultDTO

logger = get_logger(__name__)


class HybridClassifier:
    """
    Гибридный классификатор документов.

    Публичный API (неизменён):
      classify_document(doc_id: str) -> dict

    Каскад:
      L1 (filename) → L2 (header/keywords) → L3 (semantic) → L4 (LLM-fallback)

    Детали реализации каждого шага — в соответствующих модулях (см. выше).
    """

    def __init__(
        self,
        uow,
        content_service: DocumentContentService | None = None,
    ) -> None:
        self.uow = uow
        self.metrics = get_metrics()

        # Классификаторы уровней
        self.l1 = L1FilenameClassifier()
        self.l2 = L2HeaderClassifier()
        self.l3 = L3SemanticClassifier()

        # Реестр типов документов — источник истины для допустимых type_code
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

        # Веса уровней для взвешенного голосования
        level_weights: dict[str, float] = {
            "L1": float(getattr(settings, "CLASSIFIER_L1_WEIGHT", 0.20)),
            "L2": 0.40,
            "L3": 0.40,
        }

        # Делегаты (вся реализация — в них)
        self._repo = RunnerRepository(uow.session)
        self._voter = WeightedVoter(level_weights)
        self._llm = L4LLMClassifier(LLMClient(), self.registry)
        self._fetcher = ContentFetcher(content_service)
        self._duplicates = DuplicateHandler(self._repo)
        self._builder = ResultBuilder(self.registry, self.hybrid_accept, self.unknown_max)

    # ══════════════════════════════════════════════════════════════════
    # Публичный метод — точка входа
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

        logger.info(
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

        # ── L1: filename / folder ─────────────────────────────────────
        top_l1, candidates, details = self._run_l1(
            doc_id, filename, folder, candidates, details
        )

        # ── Content fetch ─────────────────────────────────────────────
        header_text, snippet_text = await self._fetcher.fetch(doc.id)
        logger.info(
            "Hybrid content fetched",
            extra={
                "doc_id": doc_id,
                "has_header": bool(header_text),
                "has_snippet": bool(snippet_text),
                "header_preview": repr((header_text or "")[:200]),
                "snippet_preview": repr((snippet_text or "")[:200]),
            },
        )

        # ── L2: header / keywords ─────────────────────────────────────
        top_l2, candidates, details = await self._run_l2(
            doc_id,
            header_text,
            snippet_text,
            filename,
            folder,
            candidates,
            details,
        )

        # ── L3: semantic embeddings ───────────────────────────────────
        top_l3, candidates, details, language, jurisdiction, applicable_triggers = (
            await self._run_l3(
                doc_id, snippet_text, filename, folder,
                candidates, details, language, jurisdiction, applicable_triggers,
            )
        )

        # ── Специальные правила приоритета ────────────────────────────
        early = self._check_priority_rules(
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
        details["candidates"] = candidates

        voted = self._voter.vote(candidates)
        final_type, final_conf, language, jurisdiction, details = self._apply_voting(
            doc_id, voted, top_l1, top_l3, language, jurisdiction, details
        )

        # Если голосование дало уверенный результат — возвращаем HYBRID
        if voted is not None and final_conf >= self.hybrid_accept:
            self.metrics.classification_duration.labels(source="hybrid_voting").observe(
                time.time() - started_at
            )
            logger.info(
                "Hybrid final result (HYBRID, after voting)",
                extra={"doc_id": doc_id, "final_type": final_type, "final_confidence": final_conf},
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

        final_type_after_voting = final_type if voted is not None else "UNKNOWN"
        final_conf_after_voting = final_conf if voted is not None else 0.0

        # ── L4: LLM-fallback ─────────────────────────────────────────
        llm_final = await self._run_l4(
            doc_id=doc_id,
            doc=doc,
            filename=filename,
            folder=folder,
            header_text=header_text,
            snippet_text=snippet_text,
            top_l1=top_l1,
            top_l2=top_l2,
            top_l3=top_l3,
            final_conf_after_voting=final_conf_after_voting,
            details=details,
            candidates=candidates,
            language=language,
            jurisdiction=jurisdiction,
            started_at=started_at,
        )
        if llm_final is not None:
            return llm_final

        # ── Fallback: UNKNOWN или слабый HYBRID ───────────────────────
        return self._build_fallback_result(
            doc_id=doc_id,
            final_type=final_type_after_voting,
            final_conf=final_conf_after_voting,
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

        Для непрофессионального программиста:
        - этот метод не ходит в DocumentRepository и не меняет Document;
        - он работает только по тексту сегмента + метаданным файла;
        - каскад упрощён: L1 (filename/folder) опционален, L2 можно пропустить,
          L3 (semantic) обязательный, L4 (LLM-fallback) опциональный;
        - результат по формату такой же, как у classify_document(...) —
          levels_tried, candidates, final_type, final_confidence, level,
          language, jurisdiction, applicable_triggers, details.
        """
        started_at = time.time()

        details: dict = {
            "levels_tried": [],
            "candidates": [],
            "contradiction_detected": False,
            "input_quality": 1.0,
        }
        candidates: list[dict] = []

        # Языковые подсказки (если пришли)
        language = language_hint
        jurisdiction = jurisdiction_hint
        applicable_triggers: list[str] = []

        # ── L1: filename / folder (как слабый hint) ────────────────────
        top_l1: dict | None = None
        if filename or folder_path:
            top_l1, candidates, details = self._run_l1(
                doc_id=f"segment:{segment_id}",
                filename=filename,
                folder=folder_path or "",
                candidates=candidates,
                details=details,
            )

        # ── L3: semantic по самому тексту сегмента ─────────────────────
        top_l3, candidates, details, language, jurisdiction, applicable_triggers = (
            await self._run_l3(
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

        # В сегментах L2 по header обычно не нужен, поэтому пропускаем
        top_l2 = None

        # ── Приоритетные правила и голосование ─────────────────────────
        early = self._check_priority_rules(
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
            # Для сегмента применяем тот же builder, только triggers уже есть
            result = dict(early)
            result["applicable_triggers"] = applicable_triggers
            return result

        candidates.sort(key=lambda c: float(c.get("confidence", 0.0)), reverse=True)
        details["candidates"] = candidates

        voted = self._voter.vote(candidates)
        final_type, final_conf, language, jurisdiction, details = self._apply_voting(
            doc_id=f"segment:{segment_id}",
            voted=voted,
            top_l1=top_l1,
            top_l3=top_l3,
            language=language,
            jurisdiction=jurisdiction,
            details=details,
        )

        # ── Если голосование уверенное — HYBRID без L4 ─────────────────
        if voted is not None and final_conf >= self.hybrid_accept:
            self.metrics.classification_duration.labels(
                source="segment_hybrid_voting"
            ).observe(time.time() - started_at)
            logger.info(
                "Hybrid segment final result (HYBRID, after voting)",
                extra={
                    "segment_id": segment_id,
                    "final_type": final_type,
                    "final_confidence": final_conf,
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

        final_type_after_voting = final_type if voted is not None else "UNKNOWN"
        final_conf_after_voting = final_conf if voted is not None else 0.0

        # ── L4: LLM-fallback по тексту сегмента ────────────────────────
        llm_final = await self._run_l4_for_segment(
            segment_id=segment_id,
            text=text,
            filename=filename,
            folder=folder_path or "",
            top_l1=top_l1,
            top_l3=top_l3,
            final_conf_after_voting=final_conf_after_voting,
            details=details,
            candidates=candidates,
            language=language,
            jurisdiction=jurisdiction,
            started_at=started_at,
        )
        if llm_final is not None:
            # В сегментном кейсе добавляем applicable_triggers из L3
            result = dict(llm_final)
            result["applicable_triggers"] = applicable_triggers
            return result

        # ── Fallback: UNKNOWN или слабый HYBRID ────────────────────────
        fallback = self._build_fallback_result(
            doc_id=f"segment:{segment_id}",
            final_type=final_type_after_voting,
            final_conf=final_conf_after_voting,
            voted=voted,
            candidates=candidates,
            details=details,
            language=language,
            jurisdiction=jurisdiction,
            started_at=started_at,
        )
        # Переопределяем applicable_triggers — для сегмента берём из L3
        fallback["applicable_triggers"] = applicable_triggers
        return fallback


    # ══════════════════════════════════════════════════════════════════
    # Приватные методы-шаги каскада
    # ══════════════════════════════════════════════════════════════════

    def _run_l1(
        self,
        doc_id: str,
        filename: str,
        folder: str,
        candidates: list[dict],
        details: dict,
    ) -> tuple[dict | None, list[dict], dict]:
        """L1: классификация по имени файла / пути к папке."""
        l1_results = self.l1.classify(filename, folder)
        details["levels_tried"].append("L1")

        top_l1: dict | None = None
        if l1_results:
            top_l1 = l1_results[0]
            details["L1"] = {
                "type": top_l1["type_code"],
                "confidence": top_l1["confidence"],
                "method": top_l1["method"],
                "details": top_l1.get("details"),
                "note": "filename_hint",
            }
            candidates.extend(l1_results)
        else:
            details["L1"] = {
                "type": "UNKNOWN",
                "confidence": 0.0,
                "method": "filename",
                "note": "no_patterns_matched",
            }

        logger.info(
            "Hybrid L1 result",
            extra={
                "doc_id": doc_id,
                "filename": filename,
                "folder_path": folder,
                "top_type": top_l1["type_code"] if top_l1 else "UNKNOWN",
                "top_conf": top_l1["confidence"] if top_l1 else 0.0,
                "candidates_count": len(l1_results),
            },
        )
        return top_l1, candidates, details

    async def _run_l2(
        self,
        doc_id: str,
        header_text: str | None,
        snippet_text: str | None,
        filename: str,
        folder: str,
        candidates: list[dict],
        details: dict,
    ) -> tuple[Any | None, list[dict], dict]:
        """L2: классификация по заголовку и YAML-паттернам."""
        top_l2: Any | None = None

        if not header_text and not snippet_text:
            details["L2"] = {
                "type": "UNKNOWN",
                "confidence": 0.0,
                "method": "header_pattern",
                "evidence": None,
                "note": "no_header_or_snippet_text",
            }
            logger.info(
                "Hybrid L2 skipped",
                extra={
                    "doc_id": doc_id,
                    "reason": "no_header_or_snippet_text",
                },
            )
            return top_l2, candidates, details

        l2_result = await self.l2.classify(
            text=header_text or "",
            filename=filename,
            folder_path=folder,
            text_sanitized=None,
            metadata={
                "snippet_text": snippet_text or "",
            },
        )
        details["levels_tried"].append("L2")

        l2_extra = getattr(l2_result, "extra", {}) or {}
        has_exclusion_hit = bool(l2_extra.get("has_exclusion_hit"))
        exclusion_hits = int(l2_extra.get("exclusion_hits", 0))
        excl_hard = int(getattr(settings, "CLASSIFICATION_L2_EXCL_HARD", 2))

        if has_exclusion_hit and exclusion_hits >= excl_hard:
            details["L2"] = {
                "type": "UNKNOWN",
                "confidence": 0.0,
                "method": l2_result.method,
                "evidence": l2_result.evidence,
                "extra": l2_extra,
                "note": "l2_exclusion_hard_hit",
            }
        else:
            details["L2"] = {
                "type": l2_result.doctype,
                "confidence": l2_result.confidence,
                "method": l2_result.method,
                "evidence": l2_result.evidence,
                "extra": l2_extra or None,
            }
            if l2_result.doctype != "UNKNOWN":
                top_l2 = l2_result
                candidates.append(
                    {
                        "type_code": l2_result.doctype,
                        "confidence": l2_result.confidence,
                        "level": "L2",
                        "method": l2_result.method,
                        "signal_quality": l2_extra.get("signal_quality", 1.0),
                        "negative_hits": int(l2_extra.get("soft_exclusion_hits", 0)),  # legacy compatibility
                        "soft_negative_hits": int(l2_extra.get("soft_exclusion_hits", 0)),
                        "hard_negative_hits": int(l2_extra.get("hard_exclusion_hits", 0)),
                        "ambiguity_penalty": float(l2_extra.get("ambiguity_penalty", 0.0)),
                        "input_quality": float(l2_extra.get("input_quality", 1.0)),
                    }
                )

        logger.info(
            "Hybrid L2 result",
            extra={
                "doc_id": doc_id,
                "type": l2_result.doctype,
                "confidence": l2_result.confidence,
                "method": l2_result.method,
                "evidence": l2_result.evidence,
                "has_exclusion_hit": has_exclusion_hit,
                "exclusion_hits": exclusion_hits,
            },
        )
        return top_l2, candidates, details

    async def _run_l3(
        self,
        doc_id: str,
        snippet_text: str | None,
        filename: str,
        folder: str,
        candidates: list[dict],
        details: dict,
        language: str | None,
        jurisdiction: str | None,
        applicable_triggers: list[str],
    ) -> tuple[Any | None, list[dict], dict, str | None, str | None, list[str]]:
        """L3: семантическая классификация через эмбеддинги."""
        top_l3: Any | None = None

        if not snippet_text or not settings.RUNNER_EMBEDDINGS_ENABLED:
            note = "empty_text" if not snippet_text else "embeddings_disabled_or_no_snippet"
            details["L3"] = {
                "type": "UNKNOWN", "confidence": 0.0,
                "method": "embedding_similarity", "evidence": None, "note": note,
            }
            logger.info("Hybrid L3 skipped", extra={"doc_id": doc_id, "reason": note})
            return top_l3, candidates, details, language, jurisdiction, applicable_triggers

        l3_result = await self.l3.classify(
            text=snippet_text,
            filename=filename,
            folder_path=folder,
            text_sanitized=None,
            metadata=None,
        )
        details["levels_tried"].append("L3")

        language = getattr(l3_result, "language", "ru")
        jurisdiction = getattr(l3_result, "jurisdiction", "RU")
        if hasattr(l3_result, "applicable_triggers"):
            applicable_triggers = list(getattr(l3_result, "applicable_triggers") or [])

        l3_extra = getattr(l3_result, "extra", {}) or {}
        raw_sim = float(l3_extra.get("raw_similarity", 0.0))

        details["L3"] = {
            "type": l3_result.doctype,
            "confidence": l3_result.confidence,
            "method": l3_result.method,
            "evidence": l3_result.evidence,
            "language": language,
            "jurisdiction": jurisdiction,
            "alternative_types": getattr(l3_result, "alternative_types", []),
            "extra": l3_extra or None,
        }

        details["input_quality"] = min(
            float(details.get("input_quality", 1.0)),
            float(l3_extra.get("input_quality", 1.0)),
        )

        if l3_result.doctype != "UNKNOWN":
            top_l3 = l3_result
            candidates.append({
                "type_code": l3_result.doctype,
                "confidence": l3_result.confidence,
                "level": "L3",
                "method": l3_result.method,
                "language": language,
                "jurisdiction": jurisdiction,
                "raw_similarity": raw_sim,
                "signal_quality": l3_extra.get("signal_quality", min(1.0, raw_sim + 0.15)),
                "negative_hits": int(l3_extra.get("negative_hits", 0)),
                "ambiguity_penalty": float(l3_extra.get("ambiguity_penalty", 0.0)),
                "input_quality": float(l3_extra.get("input_quality", 1.0)),
                "margin": float(l3_extra.get("margin", 0.0)),
            })

        logger.info(
            "Hybrid L3 result",
            extra={
                "doc_id": doc_id,
                "type": l3_result.doctype,
                "confidence": l3_result.confidence,
                "method": l3_result.method,
                "language": language,
                "jurisdiction": jurisdiction,
                "raw_similarity": raw_sim,
            },
        )
        return top_l3, candidates, details, language, jurisdiction, applicable_triggers


    def _build_llm_shortlist(self, candidates: list[dict], top_k: int = 5) -> list[str]:
        ranked: dict[str, float] = {}

        for c in candidates or []:
            type_code = c.get("type_code")
            if not type_code:
                continue
            conf = float(c.get("confidence", 0.0))
            ranked[type_code] = max(ranked.get(type_code, 0.0), conf)

        if not ranked:
            return []

        return [
            type_code
            for type_code, _ in sorted(ranked.items(), key=lambda x: x[1], reverse=True)[:top_k]
        ]

    def _check_priority_rules(
        self,
        *,
        doc_id: str,
        top_l1: dict | None,
        top_l2: Any | None,
        top_l3: Any | None,
        candidates: list[dict],
        details: dict,
        language: str | None,
        jurisdiction: str | None,
        started_at: float,
    ) -> dict | None:
        """
        Специальные правила приоритета ДО голосования.

        Правило 1: сильный L2 выигрывает, ЕСЛИ нет конфликта с сильным L3.
        Правило 2: L1 и L2 совпали и оба достаточно уверены → HYBRID.

        Возвращает готовый dict-результат или None (продолжаем каскад).
        """
        global_strong_l2 = float(getattr(settings, "CLASSIFICATION_L2_STRONG", 0.85))
        details.setdefault("contradiction_detected", False)

        # ═══════════════════════════════════════════════════════════════════
        # Правило 1: сильный L2 с проверкой на конфликт L2 vs L3
        # ═══════════════════════════════════════════════════════════════════
        if top_l2:
            l2_type = top_l2.doctype
            l2_conf = float(top_l2.confidence)

            winner_cfg = self.registry.get_config(l2_type)
            strong_l2 = global_strong_l2
            if winner_cfg is not None:
                scoring = getattr(winner_cfg, "scoring", {}) or {}
                strong_l2 = float(scoring.get("strong_signal_threshold", global_strong_l2))

            if l2_conf >= strong_l2:
                l2_extra = getattr(top_l2, "extra", {}) or {}
                l2_high_hits = int(l2_extra.get("high_hits", 0))
                l2_medium_hits = int(l2_extra.get("medium_hits", 0))

                distinctive_high = int(l2_extra.get("distinctive_high_hits", l2_high_hits))
                distinctive_medium = int(
                    l2_extra.get("distinctive_medium_hits", l2_medium_hits // 2)
                )
                generic_high = int(l2_extra.get("generic_high_hits", 0))

                weak_l2_signal = (
                    (distinctive_high == 0 and generic_high > 0)
                    or (distinctive_high == 1 and distinctive_medium == 0)
                )

                l3_conflict = False
                l3_semantic_strong = False

                if top_l3 and top_l3.doctype != l2_type:
                    l3_conf = float(top_l3.confidence)
                    l3_extra = getattr(top_l3, "extra", {}) or {}
                    l3_raw_sim = float(l3_extra.get("raw_similarity", 0.0))

                    l3_semantic_strong = l3_raw_sim > 0.80
                    l3_conflict = True

                    details["contradiction_detected"] = True
                    details["contradiction_summary"] = {
                        "l2_type": l2_type,
                        "l3_type": top_l3.doctype,
                        "l2_conf": l2_conf,
                        "l3_conf": l3_conf,
                        "l3_raw_similarity": l3_raw_sim,
                    }

                    logger.warning(
                        "L2_STRONG_WINS: conflict detected with L3",
                        extra={
                            "doc_id": doc_id,
                            "l2_type": l2_type,
                            "l2_conf": l2_conf,
                            "l2_strong_threshold": strong_l2,
                            "l2_distinctive_high_hits": distinctive_high,
                            "l2_generic_high_hits": generic_high,
                            "l2_high_hits_total": l2_high_hits,
                            "l3_type": top_l3.doctype,
                            "l3_conf": l3_conf,
                            "l3_raw_similarity": l3_raw_sim,
                            "l3_semantic_strong": l3_semantic_strong,
                            "weak_l2_signal": weak_l2_signal,
                        },
                    )

                if l3_conflict and l3_semantic_strong and weak_l2_signal:
                    details["l2_strong_suppressed"] = {
                        "reason": "L3_SEMANTIC_CONFLICT",
                        "l2_type": l2_type,
                        "l2_conf": l2_conf,
                        "l2_strong_threshold": strong_l2,
                        "l2_high_hits": l2_high_hits,
                        "l3_type": top_l3.doctype,
                        "l3_raw_similarity": l3_extra.get("raw_similarity"),
                        "decision": "continue_to_voting",
                    }
                    logger.info(
                        "Hybrid decision L2_STRONG_SUPPRESSED by L3",
                        extra={
                            "doc_id": doc_id,
                            "l2_type": l2_type,
                            "l3_type": top_l3.doctype,
                            "l2_strong_threshold": strong_l2,
                        },
                    )
                    return None

                final_type = l2_type
                final_conf = l2_conf
                details["voting"] = {
                    "strategy": "L2_STRONG_WINS",
                    "reason": (
                        f"L2 confidence >= effective strong threshold {strong_l2}, "
                        "no decisive L3 conflict or L2 has strong lexical evidence"
                    ),
                    "l2_high_hits": l2_high_hits,
                    "l2_medium_hits": l2_medium_hits,
                    "l2_distinctive_high_hits": distinctive_high,
                    "l2_distinctive_medium_hits": distinctive_medium,
                    "l2_generic_high_hits": generic_high,
                    "l2_strong_threshold": strong_l2,
                }

                logger.info(
                    "Hybrid decision L2_STRONG_WINS",
                    extra={
                        "doc_id": doc_id,
                        "final_type": final_type,
                        "final_confidence": final_conf,
                        "l2_strong_threshold": strong_l2,
                    },
                )
                self.metrics.classification_duration.labels(source="l2_strong").observe(
                    time.time() - started_at
                )
                return self._builder.build(
                    levels_tried=details["levels_tried"],
                    candidates=candidates,
                    final_type=final_type,
                    final_confidence=final_conf,
                    level="L2",
                    language=language,
                    jurisdiction=jurisdiction,
                    applicable_triggers=self._builder.build_triggers(doc_id, final_type),
                    details=details,
                )

        # ═══════════════════════════════════════════════════════════════════
        # Правило 2: L1 + L2 согласны (без изменений)
        # ═══════════════════════════════════════════════════════════════════
        if (
            top_l1 and top_l2
            and top_l1["type_code"] == top_l2.doctype
            and top_l1["confidence"] >= 0.7
            and top_l2.confidence >= 0.7
        ):
            final_type = top_l2.doctype
            final_conf = float((top_l1["confidence"] + top_l2.confidence) / 2.0)
            details["voting"] = {
                "strategy": "L1_L2_AGREE",
                "reason": "L1 and L2 agree with >= 0.7",
            }
            logger.info(
                "Hybrid decision L1_L2_AGREE",
                extra={
                    "doc_id": doc_id,
                    "final_type": final_type,
                    "final_confidence": final_conf,
                },
            )
            self.metrics.classification_duration.labels(source="l1_l2_agree").observe(
                time.time() - started_at
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

        return None

    def _apply_voting(
        self,
        doc_id: str,
        voted: dict | None,
        top_l1: dict | None,
        top_l3: Any | None,
        language: str | None,
        jurisdiction: str | None,
        details: dict,
    ) -> tuple[str, float, str | None, str | None, dict]:
        """
        Применяет результат голосования и возможный L1-override.
        Возвращает (final_type, final_conf, language, jurisdiction, details).
        """
        if voted is None:
            return "UNKNOWN", 0.0, language, jurisdiction, details

        details["voting"] = voted
        final_type = voted["type"]
        final_conf = voted["confidence"]
        language = voted.get("language", language)
        jurisdiction = voted.get("jurisdiction", jurisdiction)
        # NEW: сохраняем margin и ranking для дебага и возможного L4-routing
        margin = voted.get("margin", 0.0)
        ranking = voted.get("ranking", [])
        details["voting_margin"] = margin
        details["voting_ranking"] = ranking[:3]  # top-3 для компактности

        logger.info(
            "Hybrid voting result with margin",
            extra={
                "doc_id": doc_id,
                "final_type": final_type,
                "final_conf": final_conf,
                "margin": margin,
                "top3": ranking[:3],
            },
        )

        # Защитный кейс: сильный L1 конфликтует с L3, но проиграл голосование
        strong_l1_conf = float(getattr(settings, "CLASSIFICATION_L1_STRONG", 0.9))
        if (
            top_l1 and top_l3
            and top_l1["type_code"] != top_l3.doctype
            and top_l1["confidence"] >= strong_l1_conf
            and top_l3.confidence <= top_l1["confidence"] + 0.1
        ):
            details["voting_override"] = {
                "strategy": "L1_OVERRIDE_L3",
                "reason": "strong L1 (>=L1_STRONG) conflicting with close L3",
                "original_voted": voted,
            }
            final_type = top_l1["type_code"]
            final_conf = float(top_l1["confidence"])
            logger.info(
                "Hybrid voting override by L1",
                extra={
                    "doc_id": doc_id,
                    "final_type": final_type,
                    "final_confidence": final_conf,
                },
            )

        return final_type, final_conf, language, jurisdiction, details

    async def _run_l4(
        self,
        *,
        doc_id: str,
        doc: Any,
        filename: str,
        folder: str,
        header_text: str | None,
        snippet_text: str | None,
        top_l1: dict | None,
        top_l2: Any | None,
        top_l3: Any | None,
        final_conf_after_voting: float,
        details: dict,
        candidates: list[dict],
        language: str | None,
        jurisdiction: str | None,
        started_at: float,
    ) -> dict | None:
        """
        L4: LLM-fallback.

        Возвращает готовый dict-результат или None (продолжаем fallback).
        """
        llm_source_text = _build_llm_source_text(header_text, snippet_text)
        allowed_types = self._build_llm_shortlist(candidates, top_k=5) or self.registry.list_types()

        strong_l1 = float(getattr(settings, "CLASSIFICATION_L1_STRONG", 0.90))
        strong_l2 = float(getattr(settings, "CLASSIFICATION_L2_STRONG", 0.85))
        strong_single = (
            (top_l1 and top_l1.get("confidence", 0.0) >= strong_l1)
            or (top_l2 and top_l2.confidence >= strong_l2)
            or (top_l3 and top_l3.confidence >= strong_l2)
        )

        voted_margin = float(details.get("voting_margin", 1.0))
        need_adjudication = (
            final_conf_after_voting < self.hybrid_accept
            or voted_margin < 0.15
            or details.get("contradiction_detected") is True
            or float(details.get("input_quality", 1.0)) < 0.60
        )

        if not (
            self.l4_enabled
            and self._llm.is_available()
            and llm_source_text
            and allowed_types
            and need_adjudication
            and not strong_single
        ):
            return None

        details["levels_tried"].append("L4")

        logger.info(
            "Hybrid L4 call",
            extra={
                "doc_id": doc_id,
                "final_conf_after_voting": final_conf_after_voting,
                "voting_margin": voted_margin,
                "need_adjudication": need_adjudication,
                "contradiction_detected": details.get("contradiction_detected", False),
                "input_quality": details.get("input_quality", 1.0),
                "allowed_types": allowed_types,
            },
        )

        try:
            llm_response, errordetails = self._llm.call(
                text=llm_source_text,
                filename=filename,
                folder_path=folder,
                allowed_types=allowed_types,
            )
        except Exception as e:
            logger.warning(
                "HybridClassifier: L4 LLM classification failed",
                doc_id=str(doc.id), error=str(e),
            )
            details["L4"] = self._make_l4_error_details(e)
            return None

        if llm_response is None:
            return None

        parsed = self._llm.parse(llm_response, allowed_types=allowed_types)

        # Обогащаем raw диагностикой от retry-механизма
        for key in ("llm_attempts", "error_type", "error_message"):
            if (val := errordetails.get(key)) is not None:
                parsed["raw"][key] = val

        details["L4"] = {
            "type": parsed["type_code"],
            "confidence": parsed["confidence"],
            "method": "llm",
            "reasoning": parsed["reasoning"],
            "parse_success": parsed["parse_success"],
            "raw": parsed["raw"],
        }

        logger.info(
            "Hybrid L4 result",
            extra={"doc_id": doc_id, "doctype": parsed["type_code"], "confidence": parsed["confidence"]},
        )

        if parsed["type_code"] and parsed["type_code"] != "UNKNOWN":
            self.metrics.classification_duration.labels(source="l4").observe(
                time.time() - started_at
            )
            logger.info(
                "Hybrid final result (L4)",
                extra={"doc_id": doc_id, "final_type": parsed["type_code"], "final_confidence": parsed["confidence"]},
            )
            return self._builder.build(
                levels_tried=details["levels_tried"],
                candidates=candidates,
                final_type=parsed["type_code"],
                final_confidence=parsed["confidence"],
                level="L4",
                language=language,
                jurisdiction=jurisdiction,
                applicable_triggers=self._builder.build_triggers(doc_id, parsed["type_code"]),
                details=details,
            )

        return None

    async def _run_l4_for_segment(
        self,
        *,
        segment_id: str,
        text: str,
        filename: str,
        folder: str,
        top_l1: dict | None,
        top_l3: Any | None,
        final_conf_after_voting: float,
        details: dict,
        candidates: list[dict],
        language: str | None,
        jurisdiction: str | None,
        started_at: float,
    ) -> dict | None:
        """
        L4: LLM-fallback для сегмента.

        Отличия от _run_l4:
        - не использует DocumentContentService и header/snippet;
        - работает только по тексту сегмента;
        - не трогает master-copy и не строит triggers (они уже есть из L3).
        """
        llm_source_text = (text or "").strip()
        if not llm_source_text:
            return None

        allowed_types = self._build_llm_shortlist(candidates, top_k=5) or self.registry.list_types()

        strong_l1 = float(getattr(settings, "CLASSIFICATION_L1_STRONG", 0.90))
        strong_l3 = float(getattr(settings, "CLASSIFICATION_L2_STRONG", 0.85))

        strong_single = (
            (top_l1 and top_l1.get("confidence", 0.0) >= strong_l1)
            or (top_l3 and top_l3.confidence >= strong_l3)
        )

        voted_margin = float(details.get("voting_margin", 1.0))
        need_adjudication = (
            final_conf_after_voting < self.hybrid_accept
            or voted_margin < 0.15
            or details.get("contradiction_detected") is True
            or float(details.get("input_quality", 1.0)) < 0.60
        )

        if not (
            self.l4_enabled
            and self._llm.is_available()
            and allowed_types
            and need_adjudication
            and not strong_single
        ):
            return None

        details["levels_tried"].append("L4")
        logger.info(
            "Hybrid segment L4 call",
            extra={
                "segment_id": segment_id,
                "final_conf_after_voting": final_conf_after_voting,
                "voting_margin": voted_margin,
                "need_adjudication": need_adjudication,
                "contradiction_detected": details.get("contradiction_detected", False),
                "input_quality": details.get("input_quality", 1.0),
                "allowed_types": allowed_types,
            },
        )

        try:
            llm_response, errordetails = self._llm.call(
                text=llm_source_text,
                filename=filename,
                folder_path=folder,
                allowed_types=allowed_types,
            )
        except Exception as e:
            logger.warning(
                "HybridClassifier: L4 LLM classification failed for segment",
                segment_id=segment_id,
                error=str(e),
            )
            details["L4"] = self._make_l4_error_details(e)
            return None

        if llm_response is None:
            return None

        parsed = self._llm.parse(llm_response, allowed_types=allowed_types)

        for key in ("llm_attempts", "error_type", "error_message"):
            if (val := errordetails.get(key)) is not None:
                parsed["raw"][key] = val

        details["L4"] = {
            "type": parsed["type_code"],
            "confidence": parsed["confidence"],
            "method": "llm",
            "reasoning": parsed["reasoning"],
            "parse_success": parsed["parse_success"],
            "raw": parsed["raw"],
        }

        logger.info(
            "Hybrid segment L4 result",
            extra={
                "segment_id": segment_id,
                "doctype": parsed["type_code"],
                "confidence": parsed["confidence"],
            },
        )

        if parsed["type_code"] and parsed["type_code"] != "UNKNOWN":
            self.metrics.classification_duration.labels(source="segment_l4").observe(
                time.time() - started_at
            )
            logger.info(
                "Hybrid segment final result (L4)",
                extra={
                    "segment_id": segment_id,
                    "final_type": parsed["type_code"],
                    "final_confidence": parsed["confidence"],
                },
            )
            return self._builder.build(
                levels_tried=details["levels_tried"],
                candidates=candidates,
                final_type=parsed["type_code"],
                final_confidence=parsed["confidence"],
                level="L4",
                language=language,
                jurisdiction=jurisdiction,
                applicable_triggers=[],  # для сегмента мы потом подставим triggers из L3
                details=details,
            )

        return None


    def _build_fallback_result(
        self,
        *,
        doc_id: str,
        final_type: str,
        final_conf: float,
        voted: dict | None,
        candidates: list[dict],
        details: dict,
        language: str | None,
        jurisdiction: str | None,
        started_at: float,
    ) -> dict:
        """Финальный fallback: UNKNOWN или слабый HYBRID."""
        self.metrics.classification_duration.labels(source="fallback").observe(
            time.time() - started_at
        )

        final_type_out = self._builder.apply_unknown_corridor(final_type, final_conf)
        applicable_triggers = self._builder.build_triggers(doc_id, final_type_out)
        zone, requires_review = self._builder.confidence_zone(final_conf)

        logger.info(
            "Hybrid final result",
            extra={
                "doc_id": doc_id,
                "final_type": final_type_out,
                "final_confidence": final_conf,
                "levels_tried": details["levels_tried"],
                "confidence_zone": zone,
                "requires_manual_review": requires_review,
            },
        )

        details["confidence_zone"] = zone
        details["requires_manual_review"] = requires_review

        return {
            "levels_tried": details["levels_tried"],
            "candidates": candidates,
            "final_type": final_type_out,
            "final_confidence": final_conf,
            "level": "HYBRID" if voted is not None and final_type_out != "UNKNOWN" else None,
            "language": language,
            "jurisdiction": jurisdiction,
            "applicable_triggers": applicable_triggers,
            "details": details,
        }

    # ══════════════════════════════════════════════════════════════════
    # Вспомогательные методы
    # ══════════════════════════════════════════════════════════════════

    @staticmethod
    def _empty_result() -> dict:
        return {
            "levels_tried": [],
            "candidates": [],
            "final_type": None,
            "final_confidence": 0.0,
            "level": None,
            "language": None,
            "jurisdiction": None,
            "applicable_triggers": [],
            "details": {"levels_tried": [], "candidates": []},
        }

    @staticmethod
    def _make_l4_error_details(e: Exception) -> dict:
        return {
            "type": "UNKNOWN",
            "confidence": 0.0,
            "method": "llm_error",
            "reasoning": "",
            "parse_success": False,
            "raw": {
                "provider": None,
                "model": None,
                "tokens_used": None,
                "parse_success": False,
                "error_type": "unexpected_exception",
                "error_message": str(e),
                "response_text": None,
                "parsed_json": None,
                "llm_attempts": 0,
            },
        }


# ── Модульная утилита (не метод класса) ──────────────────────────────────────

def _build_llm_source_text(
    header_text: Optional[str],
    snippet_text: Optional[str],
) -> str:
    """Собирает текст для передачи в LLM."""
    parts: list[str] = []
    if header_text:
        parts.append(header_text.strip())
    if snippet_text:
        parts.append(snippet_text.strip())
    return "\n\n".join(p for p in parts if p).strip()



