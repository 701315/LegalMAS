# src/classifiers/stage8/hybrid_classifier.py

"""
HybridClassifier (L1 → L2 → L3 → L4) с интеграцией контент‑сервиса и LLM‑fallback.

Назначение:
- Единая точка классификации документов в Runner.
- Учитывает dedup/families и четыре уровня сигналов:
  L1: имя файла / путь (быстрый, дешёвый)
  L2: заголовок (header) + keywords/regex по YAML-паттернам
  L3: семантика (эмбеддинги) по обогащённым прототипам типов
  L4: LLM-fallback, если предыдущие уровни не дали уверенный результат.

Ключевые принципы:
- L2 и сильный L1 имеют приоритет над L3 при конфликте.
- Exclusions из L2 могут полностью подавлять тип.
- L4 никогда не переезжает сильно уверенный L1/L2/L3.
- Есть явный UNKNOWN‑коридор по confidence.
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

logger = get_logger(__name__)


class HybridClassifier:
    """
    Гибридный классификатор документов по каскаду уровней L1 → L2 → L3 → (L4/LLM-fallback).

    Важно:
    - L4/LLM используется только как резервный вариант, когда L1–L3 и голосование
      не дали уверенный результат.
    - Если LLM выключен или произошла ошибка, поведение остаётся как раньше.
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

        # Порог для уверенного HYBRID‑решения и UNKNOWN‑коридор
        self.hybrid_accept: float = float(
            getattr(settings, "CLASSIFICATION_HYBRID_ACCEPT", 0.65)
        )
        self.unknown_max: float = float(
            getattr(settings, "CLASSIFICATION_UNKNOWN_MAX", 0.40)
        )

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

                self.metrics.classification_duration.labels(...).observe(
                    time.time() - started_at
                )

                return {
                    "levels_tried": details["levels_tried"],
                    "candidates": [],
                    "final_type": master.doc_type,
                    "final_confidence": float(
                        master.classification_confidence or 0.0
                    ),
                    "level": "COPIED",
                    "copied_from_master": str(master.id),
                    "language": getattr(master, "language", None),
                    "jurisdiction": getattr(master, "jurisdiction", None),
                    "applicable_triggers": list(
                        getattr(master, "applicable_triggers", []) or []
                    ),
                    "details": details,
                }

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

            # 2) Сниппет оставляем как раньше — первые несколько листовых клауз.
            _, snippet_text = await self.content_service.get_header_and_snippet(doc.id)
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

            self.metrics.classification_duration.labels(...).observe(
                time.time() - started_at
            )
            return {
                "levels_tried": details["levels_tried"],
                "candidates": candidates,
                "final_type": final_type,
                "final_confidence": final_conf,
                "level": "L2",
                "language": language,
                "jurisdiction": jurisdiction,
                "applicable_triggers": applicable_triggers,
                "details": details,
            }

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

                self.metrics.classification_duration.labels(...).observe(
                    time.time() - started_at
                )
                return {
                    "levels_tried": details["levels_tried"],
                    "candidates": candidates,
                    "final_type": final_type,
                    "final_confidence": final_conf,
                    "level": "HYBRID",
                    "language": language,
                    "jurisdiction": jurisdiction,
                    "applicable_triggers": applicable_triggers,
                    "details": details,
                }

        # --- Взвешенное голосование L1–L3 ---
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
                self.metrics.classification_duration.labels(...).observe(
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
                return {
                    "levels_tried": details["levels_tried"],
                    "candidates": candidates,
                    "final_type": final_type,
                    "final_confidence": final_conf,
                    "level": "HYBRID",
                    "language": language,
                    "jurisdiction": jurisdiction,
                    "applicable_triggers": applicable_triggers,
                    "details": details,
                }

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

        # Список допустимых типов из YAMLRegistry
        allowed_types = self.registry.list_types()

        # Не вызываем L4, если есть сильный сигнал любого уровня
        strong_single_level = False
        if top_l1 and top_l1.get("confidence", 0.0) >= 0.9:
            strong_single_level = True
        if top_l2 and top_l2.confidence >= 0.9:
            strong_single_level = True
        if top_l3 and top_l3.confidence >= 0.9:
            strong_single_level = True

        if (
            llm_enabled
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

            try:
                llm_response = self._call_llm_for_classification(
                    text=llm_source_text,
                    filename=filename,
                    folder_path=folder,
                    allowed_types=allowed_types,
                )
            except Exception as e:
                logger.warning(
                    "HybridClassifier: L4 LLM classification failed",
                    doc_id=str(doc.id),
                    error=str(e),
                )
                llm_response = None

            if llm_response is not None:
                llm_used = True
                parsed = self._parse_llm_classification(
                    llm_response, allowed_types=allowed_types
                )
                llm_result_doctype = parsed.get("doctype")
                llm_result_confidence = parsed.get("confidence", 0.0)

                details["L4"] = {
                    "raw_text": llm_response.text,
                    "provider": llm_response.provider,
                    "model": llm_response.model,
                    "parsed": parsed,
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
            self.metrics.classification_duration.labels(...).observe(
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
            return {
                "levels_tried": details["levels_tried"],
                "candidates": candidates,
                "final_type": llm_result_doctype,
                "final_confidence": llm_result_confidence,
                "level": "L4",
                "language": language,
                "jurisdiction": jurisdiction,
                "applicable_triggers": applicable_triggers,
                "details": details,
            }

        # --- Fallback: если L4 не помог или выключен — UNKNOWN или слабый HYBRID ---
        self.metrics.classification_duration.labels(...).observe(
            time.time() - started_at
        )

        final_type_out = final_type_after_voting
        final_conf_out = final_conf_after_voting

        # UNKNOWN‑коридор
        if final_conf_out <= self.unknown_max:
            final_type_out = "UNKNOWN"

        logger.info(
            "Hybrid final result",
            extra={
                "doc_id": doc_id,
                "final_type": final_type_out,
                "final_confidence": final_conf_out,
                "levels_tried": details["levels_tried"],
            },
        )

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
    ) -> LLMResponse | None:
        """
        Вызывает LLM для задачи классификации документа.

        Важно:
        - мы явно передаём список допустимых type_code (из YAMLRegistry);
        - просим модель выбрать ровно один код из этого списка.
        """
        # Таблица type_code → name (для подсказки модели)
        rows: list[str] = []
        for tc in allowed_types:
            cfg = self.registry.get_config(tc)
            human_name = cfg.name if cfg else ""
            rows.append(f"- {tc}: {human_name}")
        types_block = "\n".join(rows)

        # Инструкция полностью на русском, без экранирования кавычек
        instruction = (
            "Ты — классификатор юридических документов.\n"
            "Твоя задача — выбрать наиболее подходящий код типа документа из разрешённого списка.\n\n"
            "Разрешённые типы документов (type_code: человекочитаемое название):\n"
            f"{types_block}\n\n"
            "Инструкция:\n"
            "1) Внимательно прочитай имя файла, путь к папке и начало текста документа.\n"
            "2) Выбери РОВНО ОДИН type_code из списка выше, который лучше всего описывает документ.\n"
            "3) Если ни один тип не подходит, верни значение \"UNKNOWN\" в поле doctype.\n"
            "4) Ответ ДОЛЖЕН быть строго в формате JSON следующего вида:\n"
            '{ \"doctype\": \"<один type_code из списка или UNKNOWN>\", '
            '\"confidence\": <число от 0 до 1> }\n\n'
            "Не добавляй никакого текста до или после JSON.\n"
        )

        prompt = (
            f"{instruction}"
            f"Имя файла: {filename}\n"
            f"Путь к папке: {folder_path}\n\n"
            f"Начало текста документа:\n{text}\n"
        )

        return self.llm_client.call(
            prompt=prompt,
            temperature=0.0,
            max_tokens=settings.LLM_MAX_TOKENS,
        )

    @staticmethod
    def _parse_llm_classification(
        response: LLMResponse,
        *,
        allowed_types: List[str],
    ) -> Dict[str, Any]:
        """
        Парсит ответ LLM для задачи классификации документа.

        Ожидаемый формат текста:
        - JSON: {"doctype": "...", "confidence": 0.85}
        - или JSON внутри текста.

        Дополнительное правило:
        - если doctype не входит в allowed_types, он заменяется на "UNKNOWN".
        """
        text = response.text.strip()

        data: dict[str, Any] = {}
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                candidate = text[start : end + 1]
                try:
                    data = json.loads(candidate)
                except json.JSONDecodeError:
                    data = {}
            else:
                data = {}

        raw_doctype = data.get("doctype") if isinstance(data, dict) else None
        raw_confidence = data.get("confidence") if isinstance(data, dict) else None

        if isinstance(raw_doctype, str):
            doctype = raw_doctype.strip()
        else:
            doctype = ""

        if not doctype or doctype not in allowed_types:
            doctype = "UNKNOWN"

        try:
            conf_val = float(raw_confidence)
        except (TypeError, ValueError):
            conf_val = 0.7

        conf_val = max(0.0, min(1.0, conf_val))

        return {
            "doctype": doctype,
            "confidence": conf_val,
        }
