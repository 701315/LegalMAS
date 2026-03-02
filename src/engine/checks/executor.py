"""
CheckExecutor: запуск одной проверки (check) для одного документа.

Назначение:
- Получить релевантный контекст через RetrievalEngine (BM25/embeddings).
- Передать контекст в HybridDetector (rules + LLM) для определения риска.
- Сформировать компактный результат проверки, пригодный для записи в CheckResult
  и дальнейшего отображения в UI/отчётах.
"""


from src.core.config import settings
from src.core.logging import get_logger
from src.engine.checks.extraction import ExtractionExecutor
from src.engine.detectors.hybrid_detector import HybridDetector
from src.engine.playbook.models import CheckDefinition
from src.engine.retrieval.engine import RetrievalEngine

logger = get_logger(__name__)


class CheckExecutor:
    def __init__(self, llm_client):
        self.detector = HybridDetector(llm_client)
        self.extractor = ExtractionExecutor(llm_client)

    def execute(self, doc, check: CheckDefinition, chunks: list[dict]) -> dict:
        """
        Выполнить один check для одного документа.

        Args:
            doc: ORM Document.
            chunks: список чанков по документу в формате
                [{"id": ..., "text": "...", "metadata": {...}}, ...].

        Возвращает словарь с результатами проверки, пригодный для записи в CheckResult.
        """
        # 1. Retrieval (если требуется контекст)
        retriever = RetrievalEngine(chunks)

        # Пока используем простую эвристику: query = название проверки
        query = check.name

        # retrieval уже модель, поэтому просто берём context_k
        context_k = getattr(check.retrieval, "context_k", 5)

        contexts = retriever.search(query, top_k=context_k)

        # Склеенный текст контекста для rules-детектора
        joined_text = "\n\n".join(c["text"] for c in contexts)

        # 2. Hybrid detection (rules + LLM)
        try:
            detection = self.detector.run(
                text=joined_text,
                chunks=contexts,
                check=check,
            )
        except Exception:
            logger.exception(
                "HybridDetector failed",
                doc_id=str(getattr(doc, "id", None)),
                check_id=getattr(check, "id", None),
            )
            raise

        found = bool(detection.get("found", False))
        confidence = float(detection.get("confidence", 0.0) or 0.0)

        # 2.1. Вытащим method и детали из detection для аналитики
        detector_method = detection.get("method")  # "rules" | "llm" | "hybrid" | None
        raw_details = detection.get("raw") or {}

        # Попробуем собрать человекочитаемый reason (объяснение)
        reason = detection.get("reason")
        if reason is None and isinstance(raw_details, dict):
            llm_details = raw_details.get("llm_details") or {}
            reason = llm_details.get("reason") or llm_details.get("parse_success")

        # sources / location используем как есть, если детекторы их отдали
        sources = detection.get("sources")
        location = detection.get("location")

        # 2.2. Structured extraction (rules + LLM)
        structured_data = None
        try:
            structured_data = self.extractor.run(
                doc=doc,
                check=check,
                contexts=contexts,
                detection=detection,
            )
        except Exception:
            logger.exception(
                "ExtractionExecutor failed",
                doc_id=str(getattr(doc, "id", None)),
                check_id=getattr(check, "id", None),
            )
            # не роняем весь check, просто оставляем structured_data = None

        # 3. Определяем result (fail/pass/unclear) и severity
        # Пороги берём из настроек, чтобы не хардкодить.
        pass_thr = getattr(settings, "CHECK_PASS_THRESHOLD", 0.6)
        unclear_thr = getattr(settings, "CHECK_UNCLEAR_THRESHOLD", 0.3)

        if found:
            result = "fail"
            severity = check.severity_if_fail or check.severity
        else:
            if confidence >= pass_thr:
                result = "pass"
                severity = check.severity_if_pass or "pass"
            elif confidence <= unclear_thr:
                result = "unclear"
                severity = check.severity_if_unclear or check.severity
            else:
                # зона слабой уверенности в отсутствии риска
                result = "unclear"
                severity = check.severity_if_unclear or check.severity

        # 4. Формируем "DTO" для CheckResult
        # Здесь мы не создаём сам ORM-объект, а возвращаем
        # компактный словарь, из которого репозиторий уже сделает CheckResult.
        return {
            "doc_id": str(doc.id),
            "check_id": check.id,
            "check_name": check.name,
            "result": result,
            "found": found,
            "evidence": detection.get("evidence", ""),
            "confidence": confidence,
            "severity": severity,
            # поля для маппинга в CheckResult:
            # - detector_used <- detector_method
            # - value_text / evidence_ref <- evidence / reason
            "detector_method": detector_method,
            "reason": reason,
            "sources": sources,
            "location": location,
            "raw": raw_details,
            # новое поле для ORM CheckResult.structured_data
            "structured_data": structured_data,
        }
