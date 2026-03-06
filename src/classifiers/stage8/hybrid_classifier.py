"""
Stage 8 HybridClassifier (L1 → L2 → L3) с интеграцией Stage 7 и контент‑сервиса.

Назначение:
- Единая точка классификации документов в Runner.
- Учитывает dedup/families (Stage 7) и три уровня сигналов:
  L1: имя файла / путь (быстрый, дешёвый)
  L2: заголовок (header) по YAML-паттернам
  L3: семантика (эмбеддинги) по обогащённым прототипам типов.

Формат результата:
{
    "levels_tried": ["L1", "L2", "L3"],
    "candidates": [
        {"type_code": "...", "confidence": 0.9, "level": "L1", "method": "filename"},
        ...
    ],
    "final_type": "contract_1.6_real_estate" | "UNKNOWN" | None,
    "final_confidence": 0.0–1.0,
    "level": "L1" | "L2" | "L3" | "HYBRID" | "COPIED" | None,
    "copied_from_master": "<uuid>" (опционально),
    "language": "ru" | "en" | None,
    "jurisdiction": "RU" | "US" | None,
    "applicable_triggers": [...],
    "details": {
        "levels_tried": ["L1", "L2", "L3"],
        "L1": {...},
        "L2": {...},
        "L3": {...},
        "voting": {...} (если применялось),
        "candidates": [...],
    },
}
"""

from __future__ import annotations
import time

from .l1_filename import L1FilenameClassifier
from .l2_header import L2HeaderClassifier
from .l3_semantic import L3SemanticClassifier
from ops.metrics import METRICS

from core.config import settings
from core.logging import get_logger
from db.repositories.runner_repo import RunnerRepository
from engine.content.document_content_service import DocumentContentService

logger = get_logger(__name__)


class HybridClassifier:
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

        self.l1 = L1FilenameClassifier()
        self.l2 = L2HeaderClassifier()
        self.l3 = L3SemanticClassifier()

        # Веса уровней для взвешенного голосования
        self.level_weights: dict[str, float] = {
            "L1": getattr(settings, "CLASSIFIER_L1_WEIGHT", 0.20),
            "L2": 0.40,
            "L3": 0.40,
        }

    async def classify_document(self, doc_id: str) -> dict:
        """
        Основной метод классификации одного документа с учётом Stage 7 и каскада L1→L2→L3.
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
                    "Copy classification from master",
                    doc_id=doc_id,
                    master_id=str(master.id),
                )
                details["levels_tried"].append("MASTERCOPY")
                details["MASTERCOPY"] = {
                    "type": master.doc_type,
                    "confidence": float(master.classification_confidence or 0.0),
                    "copied_from_master": str(master.id),
                }

                METRICS.classification_duration.labels(level="L_manual").observe(
                    time.time() - started_at
                )

                return {
                    "levels_tried": details["levels_tried"],
                    "candidates": [],
                    "final_type": master.doc_type,
                    "final_confidence": float(master.classification_confidence or 0.0),
                    "level": "COPIED",
                    "copied_from_master": str(master.id),
                    "language": getattr(master, "language", None),
                    "jurisdiction": getattr(master, "jurisdiction", None),
                    "applicable_triggers": list(getattr(master, "applicable_triggers", []) or []),
                    "details": details,
                }

        # Нормализуем filename / folder
        filename = getattr(doc, "filename", "") or ""
        folder = getattr(doc, "folder_path", None) or getattr(doc, "folder", "") or ""

        # --- L1: filename/folder ---
        l1_results = self.l1.classify(filename, folder)
        details["levels_tried"].append("L1")

        if l1_results:
            top_l1 = l1_results[0]
            details["L1"] = {
                "type": top_l1["type_code"],
                "confidence": top_l1["confidence"],
                "method": top_l1["method"],
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

        # --- Получаем header и snippet из контент‑сервиса ---
        header_text: str | None = None
        snippet_text: str | None = None

        if self.content_service is not None:
            header_text, snippet_text = await self.content_service.get_header_and_snippet(doc.id)
        else:
            logger.warning(
                "HybridClassifier: content_service is not configured, " "L2/L3 will be skipped",
                doc_id=str(doc.id),
            )

        # --- L2: header ---
        if header_text:
            l2_result = await self.l2.classify(
                text=header_text,
                filename=filename,
                folder_path=folder,
                text_sanitized=None,
                metadata=None,
            )
            details["levels_tried"].append("L2")

            details["L2"] = {
                "type": l2_result.doctype,
                "confidence": l2_result.confidence,
                "method": l2_result.method,
                "evidence": l2_result.evidence,
            }

            if l2_result.doctype != "UNKNOWN":
                candidates.append(
                    {
                        "type_code": l2_result.doctype,
                        "confidence": l2_result.confidence,
                        "level": "L2",
                        "method": l2_result.method,
                    }
                )
        else:
            details["L2"] = {
                "type": "UNKNOWN",
                "confidence": 0.0,
                "method": "header_pattern",
                "evidence": None,
                "note": "no_header_text",
            }

        # --- L3: semantic embeddings ---
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
                applicable_triggers = list(getattr(l3_result, "applicable_triggers") or [])

            details["L3"] = {
                "type": l3_result.doctype,
                "confidence": l3_result.confidence,
                "method": l3_result.method,
                "evidence": l3_result.evidence,
                "language": language,
                "jurisdiction": jurisdiction,
                "alternative_types": getattr(l3_result, "alternative_types", []),
            }

            if l3_result.doctype != "UNKNOWN":
                candidates.append(
                    {
                        "type_code": l3_result.doctype,
                        "confidence": l3_result.confidence,
                        "level": "L3",
                        "method": l3_result.method,
                        "language": language,
                        "jurisdiction": jurisdiction,
                    }
                )
        else:
            details["L3"] = {
                "type": "UNKNOWN",
                "confidence": 0.0,
                "method": "embedding_similarity",
                "evidence": None,
                "note": ("empty_text" if not snippet_text else "embeddings_disabled"),
            }

        # --- Fallback: взвешенное голосование или UNKNOWN ---
        details["candidates"] = candidates
        voted = self._weighted_voting(candidates)
        if voted is not None:
            details["voting"] = voted
            final_type = voted["type"]
            final_conf = voted["confidence"]
            language = voted.get("language", language)
            jurisdiction = voted.get("jurisdiction", jurisdiction)

            METRICS.classification_duration.labels(level="L3").observe(
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

        # Если голосование не сработало (нет кандидатов) — UNKNOWN

        METRICS.classification_duration.labels(level="L0").observe(
            time.time() - started_at
        )

        return {
            "levels_tried": details["levels_tried"],
            "candidates": candidates,
            "final_type": "UNKNOWN",
            "final_confidence": 0.0,
            "level": None,
            "language": language,
            "jurisdiction": jurisdiction,
            "applicable_triggers": applicable_triggers,
            "details": details,
        }

    def _weighted_voting(self, candidates: list[dict]) -> dict | None:
        """
        Взвешенное голосование по кандидатам.

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
            score = c["confidence"] * w

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
