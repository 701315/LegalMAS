# src/classifiers/stage8/_duplicate_handler.py
"""
Обработка дубликатов документов (Stage 7 — master/family).

Логика: если документ является дубликатом и у мастера есть
классификация — копируем результат от мастера, не запуская каскад.
"""

from __future__ import annotations

from core.logging import get_logger
from db.repositories.runner_repo import RunnerRepository

logger = get_logger(__name__)


class DuplicateHandler:
    """
    Проверяет, является ли документ дубликатом, и если да —
    возвращает готовый результат на основе мастер-документа.
    """

    def __init__(self, repo: RunnerRepository) -> None:
        self.repo = repo

    def get_master_result(self, doc) -> dict | None:
        """
        Если doc является дубликатом с известным мастером — возвращает словарь
        с данными мастера. Иначе — None.

        Возвращаемый словарь:
          {master_id, doc_type, classification_confidence, language,
           jurisdiction, applicable_triggers}
        """
        if not getattr(doc, "is_duplicate", False):
            return None

        master = self.repo.get_master_document(str(doc.id))
        if master is None:
            return None

        if not getattr(master, "classification_confidence", None):
            return None

        logger.info(
            "DuplicateHandler: master copy found",
            extra={
                "doc_id": str(doc.id),
                "master_id": str(master.id),
                "master_type": master.doc_type,
                "master_confidence": float(master.classification_confidence or 0.0),
            },
        )

        return {
            "master_id": str(master.id),
            "doc_type": master.doc_type,
            "classification_confidence": float(master.classification_confidence or 0.0),
            "language": getattr(master, "language", None),
            "jurisdiction": getattr(master, "jurisdiction", None),
            "applicable_triggers": list(getattr(master, "applicable_triggers", []) or []),
        }
