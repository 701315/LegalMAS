# src/classifiers/stage8/hybrid_classifier.py

"""
    Гибридный классификатор документов по каскаду уровней L1 → L2 → L3 → (L4/LLM-fallback).

    Для непрофессионального программиста:
    - L1 (filename) и L2 (header/keywords) используют правила из YAML через YAMLRegistry.
    - L3 (semantic) смотрит на смысл текста через эмбеддинги.
    - L4 (LLM) вызывается только как резервный вариант, если L1–L3 не дали
      уверенного результата.

    Источник правил:
    - YAMLRegistry.get_instance() даёт DocumentTypeConfig для каждого типа.
    - Из DocumentTypeConfig берутся:
        * filename_patterns / folder_patterns (L1),
        * header_patterns / keywords_* / exclusions (L2),
        * semantic-прототипы (L3, через rules_keywords / rules_phrases и др.),
        * trigger_definitions / trigger_ids (для applicable_triggers).

    applicable_triggers:
    - Это список строковых идентификаторов триггеров для финального типа документа.
    - Строится на основе блока trigger_definitions в YAML-конфиге этого типа
      через YAMLRegistry / DocumentTypeConfig.
    - В паре с doc_type образует «профиль документа», который затем использует
      движок проверки (CheckRunner/DocTypeCheckLoader) для выбора рисков/check'ов.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from .l1_filename import L1FilenameClassifier
from .l2_header import L2HeaderClassifier
from .l3_semantic import L3SemanticClassifier
from ..yaml_registry import YAMLRegistry
from ops.metrics import get_metrics

from core.config import settings
from core.logging import get_logger
from db.repositories.runner_repo import RunnerRepository
from engine.content.document_content_service import DocumentContentService
from engine.llm.client import LLMClient, LLMResponse

from classifiers.base import HybridClassificationCandidate, HybridClassificationResultDTO

logger = get_logger(__name__)


class HybridClassifier:
    """
    Гибридный классификатор документов по каскаду уровней L1 → L2 → L3 → (L4/LLM-fallback).

    Назначение:
    - Единая точка классификации документов в пайплайне (Stage 6/7).
    - Учитывает дубликаты (master/family) и четыре уровня сигналов:
      L1: имя файла / путь,
      L2: заголовок и YAML‑паттерны,
      L3: семантика (эмбеддинги),
      L4: LLM‑fallback.

    Важно:
    - L4/LLM используется только как резервный вариант, когда L1–L3 и голосование
      не дали уверенный результат.
    - Если LLM выключен или произошла ошибка, поведение остаётся как раньше.

    Результат classify_document(doc_id):
      Возвращает словарь с полями:
        - levels_tried: список уровней, которые реально отрабатывали
            например: ["L1", "L2", "L3", "L4"] или ["MASTERCOPY"]
        - candidates: список всех кандидатов от L1–L3:
            [
              {
                "type_code": "...",
                "confidence": 0.9,
                "level": "L2",
                "method": "header_pattern",
                ...
              },
              ...
            ]
        - final_type: строка с финальным type_code или "UNKNOWN"
        - final_confidence: число 0.0–1.0 — уверенность финального решения
        - level: строка с уровнем, который дал финальное решение
                 ("L1", "L2", "L3", "L4", "HYBRID", "COPIED") или None
        - language: язык документа (обычно "ru")
        - jurisdiction: юрисдикция (обычно "RU")
        - applicable_triggers: список строк‑триггеров, найденных на L3
        - details: словарь с подробностями по уровням и голосованию:
            details["L1"], ["L2"], ["L3"], ["L4"], ["MASTERCOPY"]
            details["voting"], details["voting_override"]
            details["candidates"] — дубликат поля candidates для удобства.
    """


    def __init__(self, uow, content_service: DocumentContentService | None = None) -> None:
        """
        uow — unit of work, через который мы получаем:
          - session для RunnerRepository,
          - доступ к репозиторию документов (uow.documents).

        content_service — сервис, который даёт header/snippet из clause tree.
        """
        self.uow = uow
        self.repo = RunnerRepository(uow.session)
        self.content_service = content_service
        self.metrics = get_metrics()

        self.l1 = L1FilenameClassifier()
        self.l2 = L2HeaderClassifier()
        self.l3 = L3SemanticClassifier()

        # Реестр типов документов — источник истины для допустимых type_code
        self.registry = YAMLRegistry.get_instance()

        # Клиент для работы с LLM (L4-fallback)
        self.llm_client = LLMClient()

        # Веса уровней для взвешенного голосования (L4 в голосовании не участвует)
        self.level_weights: dict[str, float] = {
            "L1": float(getattr(settings, "CLASSIFIER_L1_WEIGHT", 0.20)),
            "L2": 0.40,
            "L3": 0.40,
        }

        # Порог для уверенного HYBRID‑решения и UNKNOWN‑коридор.
        # Для непрофессионального программиста:
        # - если уверенность >= hybrid_accept → считаем результат уверенным;
        # - если уверенность <= unknown_max → считаем тип не определён (UNKNOWN);
        # - зона между ними = "низкая уверенность", документ можно пометить как
        #   требующий ручной проверки.
        # Базовые пороги из "низкоуровневых" настроек Stage 8
        base_accept = float(getattr(settings, "CLASSIFICATION_HYBRID_ACCEPT", 0.65))
        base_unknown = float(getattr(settings, "CLASSIFICATION_UNKNOWN_MAX", 0.40))

        # Доменные алиасы — могут переопределяться через переменные окружения,
        # при этом сохраняется обратная совместимость со старыми именами.
        self.hybrid_accept: float = float(
            getattr(settings, "CLASSIFIER_ACCEPT_THRESHOLD", base_accept)
        )
        self.unknown_max: float = float(
            getattr(settings, "CLASSIFIER_UNKNOWN_THRESHOLD", base_unknown)
        )

        # Флаг: включён ли вообще L4-fallback как этап.
        # Для непрофессионального программиста:
        # - если False, L4 не вызывается даже при наличии LLM.
        self.l4_enabled: bool = bool(getattr(settings, "CLASSIFIER_L4_ENABLED", True))


    def _build_applicable_triggers(self, doc_id: str, final_type: str) -> list[str]:
        """
        Построить applicable_triggers для финального типа документа.

        Для непрофессионального программиста:
        - Берём YAML-конфиг типа через YAMLRegistry / DocumentTypeConfig.
        - Возвращаем список trigger_ids (ключи trigger_definitions).
        - Если тип UNKNOWN или конфиг не найден, возвращаем пустой список.
        """
        if not isinstance(final_type, str) or not final_type or final_type == "UNKNOWN":
            return []

        cfg = self.registry.get_config(final_type)
        if cfg is None:
            logger.info(
                "HybridClassifier: no YAML config found for final_type",
                extra={"doc_id": doc_id, "final_type": final_type},
            )
            return []

        try:
            return list(getattr(cfg, "trigger_ids", []) or [])
        except Exception as e:
            logger.warning(
                "HybridClassifier: failed to build applicable_triggers",
                extra={
                    "doc_id": doc_id,
                    "final_type": final_type,
                    "error": str(e),
                },
            )
            return []


    def _build_result_dto(
        self,
        *,
        final_type: Optional[str],
        final_confidence: float,
        level: Optional[str],
        language: Optional[str],
        jurisdiction: Optional[str],
        applicable_triggers: list[str],
        levels_tried: list[str],
        candidates: list[dict],
        details: dict,
    ) -> dict:
        """
        Построить результат в виде HybridClassificationResultDTO и вернуть .__dict__.

        ВНИМАНИЕ:
        - Внешний контракт HybridClassifier.classify_document остаётся dict.
        - Этот helper просто гарантирует соответствие модели HybridClassificationResultDTO.
        """
        dto_candidates: list[HybridClassificationCandidate] = []
        for c in candidates or []:
            dto_candidates.append(
                HybridClassificationCandidate(
                    doctype=c.get("type_code") or c.get("doctype", "UNKNOWN"),
                    confidence=float(c.get("confidence") or 0.0),
                    level=str(c.get("level") or ""),
                    method=c.get("method"),
                    evidence=c.get("evidence"),
                    language=c.get("language"),
                    jurisdiction=c.get("jurisdiction"),
                    extra={
                        k: v
                        for k, v in c.items()
                        if k
                        not in {
                            "type_code",
                            "doctype",
                            "confidence",
                            "level",
                            "method",
                            "evidence",
                            "language",
                            "jurisdiction",
                        }
                    },
                )
            )

        dto = HybridClassificationResultDTO(
            final_type=final_type,
            final_confidence=float(final_confidence or 0.0),
            level=level,
            language=language,
            jurisdiction=jurisdiction,
            applicable_triggers=list(applicable_triggers or []),
            levels_tried=list(levels_tried or []),
            candidates=dto_candidates,
            details=details or {},
        )
        # Возвращаем обычный dict, чтобы не ломать вызывающий код
        return dto.__dict__



    async def classify_document(self, doc_id: str) -> dict:
        """
        Основной метод классификации одного документа с учётом Stage 7 и каскада L1→L2→L3→(L4).
        """
        started_at = time.time()

        doc = await self.uow.documents.get_by_id(doc_id)
        if doc is None:
            logger.warning("HybridClassifier: document not found", doc_id=doc_id)
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

        details: dict = {"levels_tried": [], "candidates": []}
        candidates: list[dict] = []

        # Аккумуляторы для языка / юрисдикции / триггеров
        language: str | None = None
        jurisdiction: str | None = None
        applicable_triggers: list[str] = []

        # --- Stage 7: обработка дубликатов ---
        if getattr(doc, "is_duplicate", False):
            master = self.repo.get_master_document(doc_id)
            if master and getattr(master, "classification_confidence", None):
                logger.info(
                    "Hybrid master copy used",
                    extra={
                        "doc_id": doc_id,
                        "master_id": str(master.id),
                        "master_type": master.doc_type,
                        "master_confidence": float(
                            master.classification_confidence or 0.0
                        ),
                    },
                )
                details["levels_tried"].append("MASTERCOPY")
                details["MASTERCOPY"] = {
                    "type": master.doc_type,
                    "confidence": float(master.classification_confidence or 0.0),
                    "copied_from_master": str(master.id),
                }

                self.metrics.classification_duration.labels(source="copied").observe(
                    time.time() - started_at
                )

                return self._build_result_dto(
                    levels_tried=details["levels_tried"],
                    candidates=[],
                    final_type=master.doc_type,
                    final_confidence=float(master.classification_confidence or 0.0),
                    level="COPIED",
                    copied_from_master=str(master.id),
                    language=getattr(master, "language", None),
                    jurisdiction=getattr(master, "jurisdiction", None),
                    applicable_triggers=list(getattr(master, "applicable_triggers", []) or []),
                    details=details,
                )

        # --- L1: filename/folder ---
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

        # --- Получаем header и snippet из контент‑сервиса ---
        header_text: str | None = None
        snippet_text: str | None = None

        if self.content_service is not None:
            # 1) Берём нормализованную шапку (title + преамбула) из layout.
            # Это основной источник для L2.
            try:
                header_text = await self.content_service.get_title_and_preamble(doc.id)
            except AttributeError:
                # На случай, если метод ещё не внедрён в рантайме — просто пропускаем.
                header_text = None

            # 2) Сниппет берём напрямую из layout (v2-артефакт).
            # get_snippet_from_layout() читает layout_primary_sanitized_ref или layout_primary_ref
            # — тот же source of truth, что и весь v2-пайплайн.
            # get_header_and_snippet() больше не используем: он требует clause tree (legacy),
            # которого у новых документов может не быть.
            try:
                snippet_text = await self.content_service.get_snippet_from_layout(doc.id)
            except AttributeError:
                # Защитный fallback: если метод ещё не задеплоен в рантайме —
                # просто пропускаем, L3/L4 отработают без сниппета.
                snippet_text = None

        else:
            logger.warning(
                "HybridClassifier: content_service is not configured, L2/L3/L4 will be limited",
                doc_id=str(doc.id),
            )

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

        # --- L2: header / keywords ---
        l2_result = None
        top_l2: Any | None = None

        if header_text:
            l2_result = await self.l2.classify(
                text=header_text,
                filename=filename,
                folder_path=folder,
                text_sanitized=None,
                metadata=None,
            )
            details["levels_tried"].append("L2")

            l2_extra = getattr(l2_result, "extra", {}) or {}
            has_exclusion_hit = bool(l2_extra.get("has_exclusion_hit"))
            exclusion_hits = int(l2_extra.get("exclusion_hits", 0))

            if has_exclusion_hit and exclusion_hits >= int(
                getattr(settings, "CLASSIFICATION_L2_EXCL_HARD", 2)
            ):
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
        else:
            details["L2"] = {
                "type": "UNKNOWN",
                "confidence": 0.0,
                "method": "header_pattern",
                "evidence": None,
                "note": "no_header_text",
            }
            logger.info(
                "Hybrid L2 skipped",
                extra={"doc_id": doc_id, "reason": "no_header_text"},
            )

        # --- L3: semantic embeddings ---
        l3_result = None
        top_l3: Any | None = None

        if snippet_text and settings.RUNNER_EMBEDDINGS_ENABLED:
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
                applicable_triggers = list(
                    getattr(l3_result, "applicable_triggers") or []
                )

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

            if l3_result.doctype != "UNKNOWN":
                top_l3 = l3_result
                candidates.append(
                    {
                        "type_code": l3_result.doctype,
                        "confidence": l3_result.confidence,
                        "level": "L3",
                        "method": l3_result.method,
                        "language": language,
                        "jurisdiction": jurisdiction,
                        "raw_similarity": raw_sim,
                    }
                )

            logger.info(
                "Hybrid L3 result",
                extra={
                    "doc_id": doc_id,
                    "type": l3_result.doctype,
                    "confidence": l3_result.confidence,
                    "method": l3_result.method,
                    "evidence": l3_result.evidence,
                    "language": language,
                    "jurisdiction": jurisdiction,
                    "raw_similarity": raw_sim,
                    "alt_types": getattr(l3_result, "alternative_types", []),
                },
            )
        else:
            note = (
                "empty_text"
                if not snippet_text
                else "embeddings_disabled_or_no_snippet"
            )
            details["L3"] = {
                "type": "UNKNOWN",
                "confidence": 0.0,
                "method": "embedding_similarity",
                "evidence": None,
                "note": note,
            }
            logger.info(
                "Hybrid L3 skipped",
                extra={"doc_id": doc_id, "reason": note},
            )

        # --- Специальные правила приоритета до голосования ---

        # 1) Если L2 очень сильный — доверяем ему (даже если L3 говорит чуть другое).
        strong_l2_threshold = float(
            getattr(settings, "CLASSIFICATION_L2_STRONG", 0.85)
        )
        if top_l2 and top_l2.confidence >= strong_l2_threshold:
            final_type = top_l2.doctype
            final_conf = float(top_l2.confidence)
            details["voting"] = {
                "strategy": "L2_STRONG_WINS",
                "reason": f"L2 confidence >= {strong_l2_threshold}",
            }

            logger.info(
                "Hybrid decision L2_STRONG_WINS",
                extra={
                    "doc_id": doc_id,
                    "final_type": final_type,
                    "final_confidence": final_conf,
                },
            )

            self.metrics.classification_duration.labels(source="l2_strong").observe(
                time.time() - started_at
            )

            applicable_triggers = self._build_applicable_triggers(doc_id, final_type)

            return self._build_result_dto(
                levels_tried=details["levels_tried"],
                candidates=candidates,
                final_type=final_type,
                final_confidence=final_conf,
                level="L2",
                language=language,
                jurisdiction=jurisdiction,
                applicable_triggers=applicable_triggers,
                details=details,
            )

        # 2) Если L1 и L2 совпали по типу и оба достаточно уверены — фиксируем это как HYBRID.
        if top_l1 and top_l2:
            if (
                top_l1["type_code"] == top_l2.doctype
                and top_l1["confidence"] >= 0.7
                and top_l2.confidence >= 0.7
            ):
                final_type = top_l2.doctype
                final_conf = float(
                    (top_l1["confidence"] + top_l2.confidence) / 2.0
                )
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

                applicable_triggers = self._build_applicable_triggers(doc_id, final_type)

                return self._build_result_dto(
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

        # Для непрофессионального программиста:
        # - сортируем кандидатов по уверенности от большего к меньшему.
        #   Это не меняет результат голосования, но делает список удобным
        #   для отображения в интерфейсе и аудита.
        candidates.sort(key=lambda c: float(c.get("confidence", 0.0)), reverse=True)
        details["candidates"] = candidates
        voted = self._weighted_voting(candidates)

        if voted is not None:
            details["voting"] = voted
            final_type = voted["type"]
            final_conf = voted["confidence"]
            language = voted.get("language", language)
            jurisdiction = voted.get("jurisdiction", jurisdiction)

            logger.info(
                "Hybrid voting result",
                extra={
                    "doc_id": doc_id,
                    "voted": voted,
                    "candidates": candidates,
                },
            )

            # Защитный кейс: если сильный L1 конфликтует с L3, но проиграл голосование — даём L1 право перебить.
            strong_l1_conf = float(
                getattr(settings, "CLASSIFICATION_L1_STRONG", 0.9)
            )
            if top_l1 and top_l3:
                if (
                    top_l1["type_code"] != top_l3.doctype
                    and top_l1["confidence"] >= strong_l1_conf
                    and top_l3.confidence <= top_l1["confidence"] + 0.1
                ):
                    final_type = top_l1["type_code"]
                    final_conf = float(top_l1["confidence"])
                    details["voting_override"] = {
                        "strategy": "L1_OVERRIDE_L3",
                        "reason": "strong L1 (>=L1_STRONG) conflicting with close L3",
                        "original_voted": voted,
                    }

                    logger.info(
                        "Hybrid voting override by L1",
                        extra={
                            "doc_id": doc_id,
                            "final_type": final_type,
                            "final_confidence": final_conf,
                            "original_voted": voted,
                        },
                    )

            # Если голосование дало уверенный результат — сразу возвращаем HYBRID
            if final_conf >= self.hybrid_accept:
                self.metrics.classification_duration.labels(source="hybrid_voting").observe(
                    time.time() - started_at
                )
                logger.info(
                    "Hybrid final result (HYBRID, after voting)",
                    extra={
                        "doc_id": doc_id,
                        "final_type": final_type,
                        "final_confidence": final_conf,
                    },
                )

                applicable_triggers = self._build_applicable_triggers(doc_id, final_type)

                return self._build_result_dto(
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

            final_type_after_voting = final_type
            final_conf_after_voting = final_conf
        else:
            final_type_after_voting = "UNKNOWN"
            final_conf_after_voting = 0.0

        # --- L4: LLM-fallback, если включён и есть текст ---
        llm_enabled = self.llm_client.is_available()
        llm_source_text = self._build_llm_source_text(header_text, snippet_text)

        llm_used = False
        llm_result_doctype: Optional[str] = None
        llm_result_confidence: float = 0.0
        llm_reasoning: str = ""
        llm_parse_success: bool = False
        llm_raw: dict[str, Any] = {}

        # Список допустимых типов из YAMLRegistry
        allowed_types = self.registry.list_types()

        # Не вызываем L4, если есть сильный сигнал любого уровня.
        # Для непрофессионального программиста:
        # - "сильный" сигнал значит, что один уровень и так очень уверен,
        #   и звать LLM только добавит шума и затрат.
        strong_single_level = False
        l1_strong = float(getattr(settings, "CLASSIFICATION_L1_STRONG", 0.90))
        l2_strong = float(getattr(settings, "CLASSIFICATION_L2_STRONG", 0.85))

        if top_l1 and top_l1.get("confidence", 0.0) >= l1_strong:
            strong_single_level = True
        if top_l2 and top_l2.confidence >= l2_strong:
            strong_single_level = True
        if top_l3 and top_l3.confidence >= l2_strong:
            strong_single_level = True

        if (
            self.l4_enabled
            and llm_enabled
            and llm_source_text
            and final_conf_after_voting < self.hybrid_accept
            and allowed_types
            and not strong_single_level
        ):
            details["levels_tried"].append("L4")

            logger.info(
                "Hybrid L4 call",
                extra={
                    "doc_id": doc_id,
                    "final_conf_after_voting": final_conf_after_voting,
                },
            )

            llm_errordetails: dict[str, Any] = {}

            try:
                llm_response, llm_errordetails = self._call_llm_for_classification(
                    text=llm_source_text,
                    filename=filename,
                    folder_path=folder,
                    allowed_types=allowed_types,
                )
            except Exception as e:
                # Для непрофессионального программиста:
                # - если сломалось уже вокруг самого вызова helper-метода,
                #   мы не роняем классификацию;
                # - записываем информацию об ошибке в details["L4"]["raw"].
                logger.warning(
                    "HybridClassifier: L4 LLM classification failed",
                    doc_id=str(doc.id),
                    error=str(e),
                )
                details["L4"] = {
                    "type": "UNKNOWN",
                    "confidence": 0.0,
                    "method": "llm_error",
                    "reasoning": "",
                    "parse_success": False,
                    "raw": {
                        "provider": getattr(self.llm_client, "provider", None),
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
                llm_response = None
                llm_errordetails = {
                    "llm_attempts": 0,
                    "error_type": "unexpected_exception",
                    "error_message": str(e),
                }

            if llm_response is not None:
                llm_used = True
                parsed = self._parse_llm_classification(
                    llm_response,
                    allowed_types=allowed_types,
                )

                llm_result_doctype = parsed.get("type_code") or "UNKNOWN"
                llm_result_confidence = float(parsed.get("confidence", 0.0) or 0.0)
                llm_reasoning = parsed.get("reasoning") or ""
                llm_parse_success = bool(parsed.get("parse_success", False))
                llm_raw = parsed.get("raw") or {}

                # Для непрофессионального программиста:
                # - сюда добавляем служебную информацию от общего retry-механизма;
                # - так details["L4"]["raw"] будет таким же информативным,
                #   как у LLM-детекторов checks.
                for key in ("llm_attempts", "error_type", "error_message"):
                    value = llm_errordetails.get(key)
                    if value is not None:
                        llm_raw[key] = value

                # Для непрофессионального программиста:
                # - здесь мы формируем единый контракт L4 для details["L4"],
                #   похожий на то, как устроены LLM‑детекторы checks.
                details["L4"] = {
                    "type": llm_result_doctype,
                    "confidence": llm_result_confidence,
                    "method": "llm",
                    "reasoning": llm_reasoning,
                    "parse_success": llm_parse_success,
                    "raw": llm_raw,
                }

                logger.info(
                    "Hybrid L4 result",
                    extra={
                        "doc_id": doc_id,
                        "doctype": llm_result_doctype,
                        "confidence": llm_result_confidence,
                    },
                )

        # --- Если L4 дал допустимый тип — используем его как финальный fallback ---
        if llm_used and llm_result_doctype and llm_result_doctype != "UNKNOWN":
            self.metrics.classification_duration.labels(source="l4").observe(
                time.time() - started_at
            )
            logger.info(
                "Hybrid final result (L4)",
                extra={
                    "doc_id": doc_id,
                    "final_type": llm_result_doctype,
                    "final_confidence": llm_result_confidence,
                },
            )

            applicable_triggers = self._build_applicable_triggers(doc_id, llm_result_doctype)

            return self._build_result_dto(
                levels_tried=details["levels_tried"],
                candidates=candidates,
                final_type=llm_result_doctype,
                final_confidence=llm_result_confidence,
                level="L4",
                language=language,
                jurisdiction=jurisdiction,
                applicable_triggers=applicable_triggers,
                details=details,
            )

        # --- Fallback: если L4 не помог или выключен — UNKNOWN или слабый HYBRID ---
        self.metrics.classification_duration.labels(source="fallback").observe(
            time.time() - started_at
        )

        final_type_out = final_type_after_voting
        final_conf_out = final_conf_after_voting

        # UNKNOWN‑коридор.
        # - если уверенность меньше или равна порогу unknown_max,
        #   мы считаем, что тип надёжно не определён и записываем "UNKNOWN".
        #   Это помогает фронтенду и аналитике отличать "реальные" типы
        #   от случаев, когда модель по сути не уверена.
        if final_conf_out <= self.unknown_max:
            final_type_out = "UNKNOWN"

        # --- Определяем applicable_triggers для финального типа документа ---

        # Для непрофессионального программиста:
        # - На этом этапе у нас есть финальный тип документа (final_type_out).
        # - Нам нужно понять, какие триггеры «актуальны» для этого типа:
        #   ипотека, маткапитал, сельхозземли и т.п.
        # - Список этих триггеров берётся из блока trigger_definitions
        #   в YAML-конфиге типа через YAMLRegistry / DocumentTypeConfig.

        applicable_triggers = self._build_applicable_triggers(doc_id, final_type_out)

        # Зоны уверенности классификации.
        # - confident: модель уверена, можно использовать тип без ручной проверки;
        # - low: тип определён, но с низкой уверенностью — желательно проверить руками;
        # - unknown: тип надёжно не определён, документ требует внимания.
        if final_conf_out >= self.hybrid_accept:
            confidence_zone = "confident"
            requires_manual_review = False
        elif final_conf_out <= self.unknown_max:
            confidence_zone = "unknown"
            requires_manual_review = True
        else:
            confidence_zone = "low"
            requires_manual_review = True

        logger.info(
            "Hybrid final result",
            extra={
                "doc_id": doc_id,
                "final_type": final_type_out,
                "final_confidence": final_conf_out,
                "levels_tried": details["levels_tried"],
                "confidence_zone": confidence_zone,
                "requires_manual_review": requires_manual_review,
                "applicable_triggers": applicable_triggers,
            },
        )

        details["confidence_zone"] = confidence_zone
        details["requires_manual_review"] = requires_manual_review

        return {
            "levels_tried": details["levels_tried"],
            "candidates": candidates,
            "final_type": final_type_out,
            "final_confidence": final_conf_out,
            "level": "HYBRID" if voted is not None and final_type_out != "UNKNOWN" else None,
            "language": language,
            "jurisdiction": jurisdiction,
            "applicable_triggers": applicable_triggers,
            "details": details,
        }
    

    def _weighted_voting(self, candidates: list[dict]) -> dict | None:
        """
        Взвешенное голосование по кандидатам L1–L3.

        Для каждого кандидата:
          score(type) += confidence * weight(level)
        """
        if not candidates:
            return None

        type_scores: dict[str, float] = {}
        type_meta: dict[str, dict] = {}
        total_weight = 0.0

        for c in candidates:
            level = c.get("level", "L1")
            w = self.level_weights.get(level, 0.20)
            type_code = c["type_code"]
            score = float(c["confidence"]) * w

            type_scores[type_code] = type_scores.get(type_code, 0.0) + score
            total_weight += w

            prev = type_meta.get(type_code)
            if prev is None or score > prev.get("score", 0.0):
                type_meta[type_code] = {
                    "language": c.get("language", "ru"),
                    "jurisdiction": c.get("jurisdiction", "RU"),
                    "score": score,
                }

        if not type_scores or total_weight <= 0.0:
            return None

        best_type = max(type_scores, key=type_scores.get)
        confidence = type_scores[best_type] / total_weight

        meta = type_meta.get(best_type, {})
        return {
            "type": best_type,
            "confidence": round(confidence, 4),
            "language": meta.get("language", "ru"),
            "jurisdiction": meta.get("jurisdiction", "RU"),
        }

    @staticmethod
    def _build_llm_source_text(
        header_text: Optional[str],
        snippet_text: Optional[str],
    ) -> str:
        """
        Собирает текст, который мы передаём в LLM для классификации.
        """
        parts: list[str] = []
        if header_text:
            parts.append(header_text.strip())
        if snippet_text:
            parts.append(snippet_text.strip())
        return "\n\n".join(p for p in parts if p).strip()

    def _call_llm_for_classification(
        self,
        text: str,
        filename: str,
        folder_path: str,
        allowed_types: list[str],
    ) -> tuple[LLMResponse | None, dict]:
        """
        Вызывает LLM для задачи классификации документа.

        Важно:
        - мы явно передаём список допустимых type_code (из YAMLRegistry);
        - просим модель выбрать ровно один код из этого списка;
        - формат ответа синхронизирован с промптом
          /prompts/classification/classify_document.txt и LocalLLMClassifier:
          ожидаем JSON с полями type_code, confidence, reasoning.
        """
        # Таблица type_code → name (для подсказки модели)
        rows: list[str] = []
        for tc in allowed_types:
            cfg = self.registry.get_config(tc)
            human_name = cfg.name if cfg else ""
            rows.append(f"- {tc}: {human_name}")
        types_block = "\n".join(rows)

        # Инструкция для LLM. Здесь мы не жёстко дублируем весь внешний промпт,
        # но выдерживаем тот же JSON-контракт: type_code / confidence / reasoning.
        instruction = (
            "Ты — классификатор юридических документов.\n"
            "Твоя задача — выбрать наиболее подходящий код типа документа из разрешённого списка.\n\n"
            "Разрешённые типы документов (type_code: человекочитаемое название):\n"
            f"{types_block}\n\n"
            "Инструкция:\n"
            "1) Внимательно прочитай имя файла, путь к папке и начало текста документа.\n"
            "2) Выбери РОВНО ОДИН type_code из списка выше, который лучше всего описывает документ.\n"
            "3) Если ни один тип не подходит, верни значение null или строку \"UNKNOWN\" в поле type_code.\n"
            "4) Ответ ДОЛЖЕН быть строго в формате JSON вида:\n"
            "{"
            "\"type_code\": \"<один type_code из списка или \\\"UNKNOWN\\\" или null>\", "
            "\"confidence\": <число от 0 до 1>, "
            "\"reasoning\": \"краткое объяснение в 1–2 предложениях\""
            "}\n\n"
            "Не добавляй никакого текста до или после JSON.\n"
        )

        prompt = (
            f"{instruction}"
            f"Имя файла: {filename}\n"
            f"Путь к папке: {folder_path}\n\n"
            f"Начало текста документа:\n{text}\n"
        )

        # Для непрофессионального программиста:
        # - здесь мы используем общий метод LLM-клиента с повторами;
        # - он возвращает два значения:
        #   1) сам ответ LLM (или None),
        #   2) диагностическую информацию по вызову.
        # Мы честно возвращаем оба значения наверх, без скрытых атрибутов.
        response, errordetails = self.llm_client.call_with_retries(
            prompt=prompt,
            temperature=0.0,
            max_tokens=settings.LLM_MAX_TOKENS,
        )
        return response, errordetails
    

    @staticmethod
    def _parse_llm_classification(
        response: LLMResponse,
        *,
        allowed_types: List[str],
    ) -> Dict[str, Any]:
        """
        Аккуратно разобрать JSON из ответа LLM для L4‑классификации и привести к безопасным значениям.

        Для непрофессионального программиста:
        - Модель должна вернуть JSON с полями type_code, confidence, reasoning.
        - Мы НЕ доверяем ответу «как есть», а:
          * проверяем, что type_code входит в список допустимых типов из YAMLRegistry;
          * приводим confidence к числу от 0 до 1;
          * reasoning делаем строкой.
        - В поле raw складываем всю диагностическую информацию, чтобы
          потом можно было понять, что именно вернул провайдер и как это парсилось.
        """

        text = (response.text or "").strip()
        allowed_set = set(allowed_types or [])

        # Базовый каркас raw-диагностики
        raw: Dict[str, Any] = {
            "provider": getattr(response, "provider", None),
            "model": getattr(response, "model", None),
            "tokens_used": getattr(response, "tokens_used", None),
            "parse_success": False,
            "error_type": None,
            "error_message": None,
            "response_text": text,
            "parsed_json": None,
        }

        type_code = "UNKNOWN"
        confidence = 0.0
        reasoning = ""
        parse_success = False

        try:
            # Пытаемся вытащить JSON-объект из текста (на случай мусора вокруг)
            start_idx = text.find("{")
            end_idx = text.rfind("}") + 1
            if start_idx == -1 or end_idx <= start_idx:
                raise ValueError("No JSON object found in LLM response")

            obj = json.loads(text[start_idx:end_idx])
            if not isinstance(obj, dict):
                raise ValueError("LLM response JSON is not an object")

            raw["parsed_json"] = obj

            # --- type_code ---
            raw_type = obj.get("type_code")
            # На всякий случай поддерживаем старое имя поля "doctype"
            if raw_type is None:
                raw_type = obj.get("doctype")

            if isinstance(raw_type, str):
                raw_type = raw_type.strip()
            else:
                raw_type = ""

            # Всё, что похоже на "UNKNOWN" (в любом регистре), трактуем как отсутствие типа.
            if raw_type.upper() == "UNKNOWN":
                raw_type = ""

            if raw_type and raw_type in allowed_set:
                type_code = raw_type
            else:
                type_code = "UNKNOWN"

            # --- confidence ---
            raw_conf = obj.get("confidence", 0.0)
            try:
                confidence = float(raw_conf)
            except (TypeError, ValueError):
                confidence = 0.0
            if confidence < 0.0:
                confidence = 0.0
            if confidence > 1.0:
                confidence = 1.0

            # --- reasoning ---
            reasoning_val = obj.get("reasoning", "")
            if isinstance(reasoning_val, str):
                reasoning = reasoning_val
            else:
                reasoning = str(reasoning_val)

            parse_success = True
            raw["parse_success"] = True

        except Exception as e:
            # Любая ошибка парсинга — это не крах пайплайна, а сигнал в raw.
            raw["error_type"] = "parse_error"
            raw["error_message"] = str(e)
            raw["parse_success"] = False
            type_code = "UNKNOWN"
            confidence = 0.0
            reasoning = ""

        return {
            "type_code": type_code,
            "confidence": confidence,
            "reasoning": reasoning,
            "parse_success": parse_success,
            "raw": raw,
        }