# src/engine/checks/executor.py

"""
CheckExecutor: запуск одной проверки (check) для одного документа.

Назначение:
- Получить релевантный контекст через RetrievalEngine (BM25/embeddings).
- Передать контекст в HybridDetector (rules + LLM) для определения риска.
- Сформировать компактный результат проверки, пригодный для записи в CheckResult
  и дальнейшего отображения в UI/отчётах.

Важные принципы (чтобы понимать поведение в продакшене):

1) Этот класс НИКОГДА не выбрасывает исключения наружу из-за LLM/HybridDetector.
   - Даже если внутри детектора что-то пойдёт не так, мы всё равно вернём
     осмысленный словарь с result="unclear" и диагностическими флагами.

2) Все детали про LLM (ошибки, количество попыток, parse_success и т.п.)
   аккуратно прокидываются в поле raw, а затем попадут в CheckResult.quality_flags.

3) Если structured extraction (извлечение полей) падает, это НЕ ломает проверку:
   - просто оставляем structured_data=None и пишем диагноз в лог.
"""
import time

from core.config import settings
from core.logging import get_logger

from .extraction import ExtractionExecutor
from ..detectors.hybrid_detector import HybridDetector
from ..playbook.models import CheckDefinition
from ..retrieval.engine import RetrievalEngine
from src.ops.metrics import METRICS

logger = get_logger(__name__)


class CheckExecutor:
    def __init__(self, llm_client):
        # HybridDetector внутри сам решает, когда использовать rules/LLM,
        # и уже умеет безопасно обрабатывать ошибки LLM.
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
        Даже при внутренних ошибках детекторов метод возвращает осмысленный результат,
        а не выбрасывает исключение.
        """

        start_time = time.time()

        # 1. Retrieval (поиск релевантных чанков для rules/LLM)
        retriever = RetrievalEngine(chunks)

        # Простая эвристика: query = название проверки
        query = check.name

        # retrieval уже знает про context_k, но мы продублируем из playbook
        context_k = getattr(check.retrieval, "context_k", 5)

        contexts = retriever.search(query, top_k=context_k)

        # Склеенный текст контекста для rules-детектора
        joined_text = "\n\n".join(c["text"] for c in contexts)

        # 2. Hybrid detection (rules + LLM)
        # Здесь мы любыми средствами избегаем выбрасывания исключений наружу.
        try:
            detection = self.detector.run(
                text=joined_text,
                chunks=contexts,
                check=check,
            )
        except Exception as e:
            # Это спасательная сетка: сюда мы попадём только если внутри
            # HybridDetector случилось что-то совсем неожиданное.
            logger.exception(
                "CheckExecutor: HybridDetector failed with unexpected exception",
                extra={
                    "doc_id": str(getattr(doc, "id", None)),
                    "check_id": getattr(check, "id", None),
                },
            )
            # В этом случае формируем минимальный detection-словарь,
            # чтобы не ломать весь Run.
            detection = {
                "found": False,
                "confidence": 0.0,
                "method": "rules",  # по факту rules-only
                "reason": "hybrid_detector_error",
                "sources": [],
                "location": None,
                "raw": {
                    "source": "hybrid_detector_exception",
                    "error_message": str(e),
                },
            }

        found = bool(detection.get("found", False))
        confidence = float(detection.get("confidence", 0.0) or 0.0)

        # 2.1. Вытащим method и детали из detection для аналитики
        detector_method = detection.get("method")  # "rules" | "llm" | "hybrid" | None
        raw_details = detection.get("raw") or {}

        # Попробуем собрать человекочитаемый reason (объяснение)
        reason = detection.get("reason")
        if reason is None and isinstance(raw_details, dict):
            llm_details = raw_details.get("llm_details") or {}
            # reason из LLM-детали или флаг parse_success (True/False/None)
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
        except Exception as e:
            logger.exception(
                "CheckExecutor: ExtractionExecutor failed",
                extra={
                    "doc_id": str(getattr(doc, "id", None)),
                    "check_id": getattr(check, "id", None),
                },
            )
            # не роняем весь check, просто оставляем structured_data = None
            # при желании можно добавить в raw_details флаг про ошибку извлечения
            if isinstance(raw_details, dict):
                raw_details.setdefault("extraction_error", str(e))

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

        # 4. Достаём координаты evidence (для последующей подсветки в вьюере)
        page = None
        clause_uid = None
        element_id = None
        bbox = None

        if isinstance(location, dict):
            page = location.get("page")
            clause_uid = location.get("clause_uid")
            element_id = location.get("element_id")
            # bbox может лежать либо прямо в location, либо в sources[0]
            bbox = location.get("bbox")

        if bbox is None and isinstance(sources, list) and sources:
            first_src = sources[0]
            if isinstance(first_src, dict):
                # на будущее: если сюда начнём класть bbox в sources
                bbox = first_src.get("bbox", bbox)
                if page is None:
                    page = first_src.get("page")
                if clause_uid is None:
                    clause_uid = first_src.get("clause_uid")
                if element_id is None:
                    element_id = first_src.get("element_id")


        # Метрики: длительность и счётчик checks
        detector_label = detector_method or "unknown"
        try:
            duration = time.time() - start_time
            METRICS.check_duration.labels(detector_type=detector_label).observe(duration)
            METRICS.checks_executed.labels(
                detector_type=detector_label,
                result=result,
            ).inc()
        except Exception:
            # Метрики не должны ломать бизнес-логику
            logger.exception(
                "CheckExecutor: failed to update metrics",
                extra={
                    "doc_id": str(getattr(doc, "id", None)),
                    "check_id": getattr(check, "id", None),
                },
            )

        # 5. Формируем "DTO" для CheckResult
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
            # новые поля для точной привязки к фрагменту документа
            "page": page,
            "clause_uid": clause_uid,
            "element_id": element_id,
            "bbox": bbox,
        }
