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
from ..detectors.models import RetrievedChunk
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

        # Собираем важные термины для данного check'а:
        # - имя проверки (name),
        # - boost_keywords из retrieval-конфига плейбука.
        # Эти слова будут использоваться RetrievalEngine для небольшого
        # буста по заголовкам (section_title / path_titles / summary).
        raw_boost_keywords = getattr(check.retrieval, "boost_keywords", []) or []
        important_terms: list[str] = []

        # 1) добавляем name проверки
        if isinstance(check.name, str) and check.name.strip():
            important_terms.append(check.name.strip())

        # 2) добавляем boost_keywords как есть (нормализация по регистру
        # и пробелам уже делается внутри RetrievalEngine)
        for kw in raw_boost_keywords:
            if isinstance(kw, str) and kw.strip():
                important_terms.append(kw.strip())

        # 1. Retrieval (поиск релевантных чанков для rules/LLM)
        # Передаём important_terms, чтобы RetrievalEngine мог
        # учитывать их при metadata-boost'е.
        retriever = RetrievalEngine(chunks, important_terms=important_terms)

        # Расширяем query: к названию проверки добавляем boost_keywords из playbook.
        # Например: "Смена контроля" → "Смена контроля change of control смена собственника"
        boost_keywords = raw_boost_keywords
        if boost_keywords:
            query = f"{check.name} {' '.join(boost_keywords[:3])}".strip()
        else:
            query = check.name

        # retrieval уже знает про context_k, но мы продублируем из playbook.
        # max_chunks — сколько максимум чанков запрашиваем из движка (top-N кандидатов).
        retr_cfg = getattr(check, "retrieval", None) or getattr(check, "retrieval", None)
        context_k = getattr(retr_cfg, "context_k", 5)
        max_chunks = getattr(retr_cfg, "max_chunks", None) or context_k

        # Сначала берём top-N кандидатов из RetrievalEngine (max_chunks),
        # а уже потом будем выбирать context_k для детектора.
        contexts = retriever.search(query, top_k=max_chunks)

        # Преобразуем dict-чанки в RetrievedChunk, чтобы дальше весь пайплайн
        # работал с типизированной моделью и не терял структурный контекст.
        retrieved_chunks: list[RetrievedChunk] = []
        for c in contexts:
            meta = c.get("metadata", {}) or {}

            element_ids = meta.get("element_ids") or []
            # Если element_ids нет, используем id чанка как fallback.
            first_element_id = element_ids[0] if element_ids else (c.get("id") or "")

            # Страница: предпочтительно start_page (диапазон клаузы),
            # иначе page из метаданных, иначе 0.
            page = meta.get("start_page")
            if page is None:
                page = meta.get("page") or 0

            try:
                page_int = int(page)
            except (TypeError, ValueError):
                page_int = 0

            retrieved_chunks.append(
                RetrievedChunk(
                    element_id=first_element_id,
                    text=c.get("text") or "",
                    page=page_int,
                    clause_uid=meta.get("clause_uid") or "",
                    bbox=[],  # bbox можно подтягивать позже из layout по element_id
                    dense_score=0.0,       # при желании можно проставить из отдельных скорингов
                    sparse_score=0.0,
                    metadata_score=0.0,
                    combined_score=float(c.get("score") or 0.0),
                    path_titles=meta.get("path_titles") or [],
                    start_page=meta.get("start_page"),
                    end_page=meta.get("end_page"),
                    element_ids=element_ids,
                )
            )

        # На этом этапе у нас есть:
        # - contexts: список dict-чанков от RetrievalEngine,
        # - retrieved_chunks: такие же чанки, но в типизированном виде.
        #
        # Дальше:
        # 1) При необходимости делаем лёгкий rerank.
        # 2) Учитываем required_kind из retrieval-конфига, чтобы контекст
        #    для детектора в первую очередь состоял из нужного типа чанков.

        required_kind = getattr(retr_cfg, "required_kind", None)
        do_rerank = bool(getattr(retr_cfg, "rerank", True))

        # Построим словарь chunk_id -> metadata/текст, чтобы можно было
        # узнать kind и текст, когда будем считать улучшенный score.
        id_to_meta: dict[str, dict] = {}
        id_to_text: dict[str, str] = {}
        for c in contexts:
            cid = str(c.get("id") or "")
            id_to_meta[cid] = c.get("metadata", {}) or {}
            id_to_text[cid] = c.get("text") or ""

        def _simple_rerank(chunks_rc: list[RetrievedChunk]) -> list[RetrievedChunk]:
            """
            Очень простой пересортировщик поверх combined_score.

            Для непрофессионального программиста:
            - Мы берём базовый score из RetrievalEngine.
            - Немного повышаем под-clauses (subclause).
            - Немного понижаем большие разделы (section).
            - Даём небольшой бонус, если в тексте чанка есть важные слова.
            """
            important_lower = [s.lower() for s in important_terms if isinstance(s, str)]

            def _score(rc: RetrievedChunk) -> float:
                base = float(rc.combined_score or 0.0)
                cid = str(rc.element_id or "")
                meta = id_to_meta.get(cid, {})
                text = id_to_text.get(cid, "").lower()

                kind = str(meta.get("kind") or "").lower()
                if kind == "subclause":
                    base += 0.05
                elif kind == "section":
                    base -= 0.02

                # Небольшой бонус за точное вхождение важных слов.
                for term in important_lower:
                    if term and term in text:
                        base += 0.03

                return base

            return sorted(chunks_rc, key=_score, reverse=True)

        # Применяем rerank, если он включён в конфиге.
        if do_rerank and retrieved_chunks:
            retrieved_chunks = _simple_rerank(retrieved_chunks)

        # Теперь учитываем required_kind:
        # - если задан, пытаемся сначала взять чанки только этого типа,
        # - если таких чанков нет, используем полный список (fallback).
        if required_kind:
            required_kind_lower = str(required_kind).lower()
            primary: list[RetrievedChunk] = []
            fallback: list[RetrievedChunk] = []
            for rc in retrieved_chunks:
                cid = str(rc.element_id or "")
                meta = id_to_meta.get(cid, {})
                kind = str(meta.get("kind") or "").lower()
                if kind == required_kind_lower:
                    primary.append(rc)
                else:
                    fallback.append(rc)

            if primary:
                retrieved_chunks = primary + fallback

        # Ограничиваем количество чанков для детектора по context_k.
        # Важно: contexts и retrieved_chunks должны быть синхронны,
        # поэтому обрезаем их одинаково.
        if len(retrieved_chunks) > context_k:
            retrieved_chunks = retrieved_chunks[:context_k]
            contexts = contexts[:context_k]

        # Строим структурированный текстовый контекст для rules/LLM,
        # используя метаданные (clause_uid, path_titles, страницы).
        context_parts: list[str] = []
        for c, rc in zip(contexts, retrieved_chunks):
            meta = c.get("metadata", {}) or {}
            clause = meta.get("clause_uid", "") or rc.clause_uid
            # section_title оставляем как fallback, основной путь — path_titles
            section_title = meta.get("section_title", "")
            path_titles = meta.get("path_titles") or rc.path_titles or []
            start_page = meta.get("start_page") or rc.start_page
            end_page = meta.get("end_page") or rc.end_page

            header_parts: list[str] = []
            if clause:
                header_parts.append(f"Пункт {clause}")
            if path_titles:
                header_parts.append(" > ".join(path_titles))
            elif section_title:
                header_parts.append(section_title)

            if isinstance(start_page, int) and isinstance(end_page, int):
                if start_page == end_page:
                    header_parts.append(f"стр. {start_page}")
                else:
                    header_parts.append(f"стр. {start_page}–{end_page}")
            else:
                page = meta.get("page")
                if page:
                    header_parts.append(f"стр. {page}")

            header = f"[{', '.join(header_parts)}]" if header_parts else ""
            text = c.get("text") or ""
            context_parts.append(f"{header}\n{text}".strip() if header else text)

        joined_text = "\n\n---\n\n".join(context_parts)

        # 2. Hybrid detection (rules + LLM)
        # Стараемся никогда не выбрасывать исключения наружу.
        # Передаём doc_type и classification_confidence для более умной работы LLM.
        doc_type = getattr(doc, "doc_type", "") or ""
        try:
            classification_confidence = float(
                getattr(doc, "classification_confidence", 1.0) or 0.0
            )
        except (TypeError, ValueError):
            classification_confidence = 0.0

        try:
            detection = self.detector.run(
                text=joined_text,
                chunks=retrieved_chunks,
                check=check,
                doc_type=doc_type,
                classification_confidence=classification_confidence,
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
                "evidence": "",
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
            # Приводим RetrievedChunk к каноническому формату dict, который
            # ожидает ExtractionExecutor: {"id", "text", "metadata"}.
            extraction_contexts = [
                {
                    "id": rc.element_id,
                    "text": rc.text or "",
                    "metadata": {
                        "clause_uid": rc.clause_uid,
                        "page": rc.page,
                        "start_page": rc.start_page,
                        "end_page": rc.end_page,
                        "path_titles": rc.path_titles,
                        "element_ids": rc.element_ids,
                    },
                }
                for rc in retrieved_chunks
            ]

            structured_data = self.extractor.run(
                doc=doc,
                check=check,
                contexts=extraction_contexts,
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
    