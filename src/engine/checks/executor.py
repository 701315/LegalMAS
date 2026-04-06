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

4) ВАЖНО:
   - бизнес-результат (fail / pass / unclear) и техническое состояние LLM — это
     две разные плоскости;
   - поэтому мы отдельно возвращаем флаги:
       * llm_error_type
       * llm_required
       * llm_degraded
     чтобы следующий слой мог решить, считать ли check "SUCCESS" или "TIMEOUT".
"""

import time
from typing import List, Tuple

from core.config import settings
from core.logging import get_logger

from engine.content.chunking import build_chunk_summary
from engine.retrieval.tokenization import count_tokens

from .extraction import ExtractionExecutor
from ..detectors.hybrid_detector import HybridDetector
from ..detectors.models import RetrievedChunk
from ..playbook.models import CheckDefinition
from ..retrieval.engine import RetrievalEngine
from ops.metrics import METRICS

logger = get_logger(__name__)


class CheckExecutor:
    def __init__(self, llm_client):
        # HybridDetector внутри сам решает, когда использовать rules/LLM,
        # и уже умеет безопасно обрабатывать ошибки LLM.
        self.detector = HybridDetector(llm_client)
        self.extractor = ExtractionExecutor(llm_client)

    def _build_limited_context(
        self,
        contexts: list[dict],
        retrieved_chunks: list[RetrievedChunk],
        important_terms: list[str],
        max_tokens: int | None,
    ) -> Tuple[str, list[RetrievedChunk], list[dict], int, bool]:
        """
        Построить текстовый контекст для LLM с учётом лимита по токенам.

        Простыми словами:
        - мы склеиваем куски контекста в один большой текст;
        - следим, чтобы общее число токенов не вышло за пределы max_tokens;
        - если текст слишком длинный, сначала отбрасываем самые «слабые» куски;
        - если и после этого не помещается — делаем короткие summary для хвостовых кусочков;
        - возвращаем:
            joined_text        — итоговый текст для LLM,
            kept_chunks        — какие RetrievedChunk реально пошли в запрос,
            kept_context_dicts — исходные dict'ы для этих чанков,
            total_tokens       — сколько токенов занял контекст,
            truncated          — пришлось ли что‑то обрезать.
        """
        if not isinstance(max_tokens, int) or max_tokens <= 0:
            context_parts: list[str] = []
            for c, rc in zip(contexts, retrieved_chunks):
                meta = c.get("metadata", {}) or {}
                clause = meta.get("clause_uid", "") or rc.clause_uid
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
            total_tokens = count_tokens(joined_text)
            return joined_text, retrieved_chunks, contexts, total_tokens, False

        items: list[tuple[int, dict, RetrievedChunk, str]] = []
        for c, rc in zip(contexts, retrieved_chunks):
            meta = c.get("metadata", {}) or {}
            clause = meta.get("clause_uid", "") or rc.clause_uid
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
            piece = f"{header}\n{text}".strip() if header else text

            token_count = count_tokens(piece)
            items.append((token_count, c, rc, piece))

        reserve_ratio = getattr(settings, "LLM_CONTEXT_RESERVE_RATIO", 0.3)
        try:
            reserve_ratio = float(reserve_ratio)
        except (TypeError, ValueError):
            reserve_ratio = 0.3
        if reserve_ratio < 0.0:
            reserve_ratio = 0.0
        if reserve_ratio > 0.9:
            reserve_ratio = 0.9
        hard_limit = int(max_tokens * (1.0 - reserve_ratio))

        if hard_limit <= 0:
            hard_limit = max_tokens // 2 if max_tokens > 0 else 2048

        kept_items: list[tuple[int, dict, RetrievedChunk, str]] = []
        total_tokens = 0
        truncated = False

        for token_count, c, rc, piece in items:
            if total_tokens + token_count <= hard_limit:
                kept_items.append((token_count, c, rc, piece))
                total_tokens += token_count
            else:
                truncated = True
                break

        if not truncated:
            joined_text = "\n\n---\n\n".join(piece for _, _, _, piece in kept_items)
            return (
                joined_text,
                [rc for _, _, rc, _ in kept_items],
                [c for _, c, _, _ in kept_items],
                total_tokens,
                False,
            )

        compressed_items: list[tuple[int, dict, RetrievedChunk, str]] = []
        remaining_tokens = hard_limit
        important_lower = [s.lower() for s in important_terms if isinstance(s, str)]

        for token_count, c, rc, piece in kept_items:
            if token_count > remaining_tokens:
                meta = c.get("metadata", {}) or {}
                path_titles = meta.get("path_titles") or rc.path_titles or []
                original_text = c.get("text") or rc.text or ""
                summary = build_chunk_summary(path_titles, original_text)

                for term in important_lower:
                    if term and term not in summary.lower() and term in original_text.lower():
                        summary = f"{summary}\n\nКлючевой термин: {term}"
                        break

                summary_piece = summary.strip()
                summary_tokens = count_tokens(summary_piece)

                if summary_tokens > remaining_tokens:
                    truncated = True
                    continue

                compressed_items.append((summary_tokens, c, rc, summary_piece))
                remaining_tokens -= summary_tokens
                truncated = True
            else:
                compressed_items.append((token_count, c, rc, piece))
                remaining_tokens -= token_count

        if not compressed_items:
            smallest = min(items, key=lambda t: t[0])
            token_count, c, rc, piece = smallest
            piece_tokens = count_tokens(piece)

            if piece_tokens > hard_limit:
                meta = c.get("metadata", {}) or {}
                path_titles = meta.get("path_titles") or rc.path_titles or []
                original_text = c.get("text") or rc.text or ""
                summary = build_chunk_summary(path_titles, original_text)
                piece = summary.strip()
                piece_tokens = count_tokens(piece)

            compressed_items = [(piece_tokens, c, rc, piece)]
            total_tokens = piece_tokens
            truncated = True
        else:
            total_tokens = sum(t for t, _, _, _ in compressed_items)

        joined_text = "\n\n---\n\n".join(piece for _, _, _, piece in compressed_items)
        kept_chunks = [rc for _, _, rc, _ in compressed_items]
        kept_contexts = [c for _, c, _, _ in compressed_items]

        return joined_text, kept_chunks, kept_contexts, total_tokens, truncated

    def _extract_llm_runtime_flags(
        self,
        detector_method: str | None,
        detection: dict,
        raw_details: dict,
    ) -> dict:
        """
        Вытащить из detection/raw технические флаги по LLM.

        Очень важно:
        - бизнес-результат check (fail / pass / unclear) мы не меняем здесь;
        - здесь мы только вычисляем технические признаки:
          был ли сбой LLM, был ли LLM обязателен, и есть ли деградация.

        Это нужно следующему слою (CheckRunner), чтобы:
        - либо оставить execution_status="SUCCESS",
        - либо выставить execution_status="TIMEOUT"/"FAILED".
        """
        if not isinstance(raw_details, dict):
            raw_details = {}

        llm_details = raw_details.get("llm_details") or {}
        if not isinstance(llm_details, dict):
            llm_details = {}

        # Пытаемся взять ошибку сначала из верхнего уровня raw,
        # потому что HybridDetector в rules-fallback ветке может положить её именно туда.
        llm_error_type = raw_details.get("llm_error_type")
        llm_error_message = raw_details.get("llm_error_message")
        llm_attempts = raw_details.get("llm_attempts")

        # Если сверху ничего нет — пробуем взять из llm_details.
        if not llm_error_type:
            llm_error_type = llm_details.get("error_type")
        if not llm_error_message:
            llm_error_message = llm_details.get("error_message")
        if llm_attempts is None:
            llm_attempts = llm_details.get("llm_attempts")

        # Это причина/режим, который HybridDetector уже вычислил.
        # На её основе мы понимаем, был ли LLM обязателен.
        rules_llm_decision = raw_details.get("rules_llm_decision")
        if not rules_llm_decision:
            rules_llm_decision = detection.get("reason")

        # В этих случаях rules уже дали достаточно сильный ответ.
        # Если LLM упал, это деградация качества, но не повод ломать business-result.
        rules_sufficient_decisions = {
            "rules_confident_positive",
            "rules_clean_negative",
        }

        # В этих случаях без LLM мы честно ответить не можем.
        llm_required_decisions = {
            "rules_negative_suppressed_unclear",
            "rules_weak_positive_unclear",
            "rules_unclear",
        }

        llm_error_present = bool(llm_error_type)

        if rules_llm_decision in rules_sufficient_decisions:
            llm_required = False
        elif rules_llm_decision in llm_required_decisions:
            llm_required = True
        else:
            # Безопасное поведение по умолчанию:
            # если есть ошибка LLM и детектор реально шёл через llm/hybrid,
            # считаем, что LLM был важен, пока явно не доказано обратное.
            llm_required = bool(llm_error_present and detector_method in {"llm", "hybrid"})

        llm_degraded = bool(llm_error_present)

        return {
            "llm_error_type": llm_error_type,
            "llm_error_message": llm_error_message,
            "llm_attempts": llm_attempts,
            "rules_llm_decision": rules_llm_decision,
            "llm_required": llm_required,
            "llm_degraded": llm_degraded,
        }

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

        raw_boost_keywords = getattr(check.retrieval, "boost_keywords", []) or []
        important_terms: list[str] = []

        if isinstance(check.name, str) and check.name.strip():
            important_terms.append(check.name.strip())

        for kw in raw_boost_keywords:
            if isinstance(kw, str) and kw.strip():
                important_terms.append(kw.strip())

        retriever = RetrievalEngine(chunks, important_terms=important_terms)

        boost_keywords = raw_boost_keywords
        if boost_keywords:
            query = f"{check.name} {' '.join(boost_keywords[:3])}".strip()
        else:
            query = check.name

        retr_cfg = getattr(check, "retrieval", None) or getattr(check, "retrieval", None)
        context_k = getattr(retr_cfg, "context_k", 5)
        max_chunks = getattr(retr_cfg, "max_chunks", None) or context_k

        contexts = retriever.search(query, top_k=max_chunks)

        retrieved_chunks: list[RetrievedChunk] = []
        for c in contexts:
            meta = c.get("metadata", {}) or {}

            element_ids = meta.get("element_ids") or []
            first_element_id = element_ids[0] if element_ids else (c.get("id") or "")

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
                    bbox=[],
                    dense_score=0.0,
                    sparse_score=0.0,
                    metadata_score=0.0,
                    combined_score=float(c.get("score") or 0.0),
                    path_titles=meta.get("path_titles") or [],
                    start_page=meta.get("start_page"),
                    end_page=meta.get("end_page"),
                    element_ids=element_ids,
                )
            )

        required_kind = getattr(retr_cfg, "required_kind", None)
        do_rerank = bool(getattr(retr_cfg, "rerank", True))

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

                for term in important_lower:
                    if term and term in text:
                        base += 0.03

                return base

            return sorted(chunks_rc, key=_score, reverse=True)

        if do_rerank and retrieved_chunks:
            retrieved_chunks = _simple_rerank(retrieved_chunks)

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

        if len(retrieved_chunks) > context_k:
            retrieved_chunks = retrieved_chunks[:context_k]
            contexts = contexts[:context_k]

        llm_context_limit = getattr(settings, "LLM_CONTEXT_LIMIT", None)
        joined_text, retrieved_chunks, contexts, context_tokens, context_truncated = (
            self._build_limited_context(
                contexts=contexts,
                retrieved_chunks=retrieved_chunks,
                important_terms=important_terms,
                max_tokens=llm_context_limit,
            )
        )

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
            logger.exception(
                "CheckExecutor: HybridDetector failed with unexpected exception",
                extra={
                    "doc_id": str(getattr(doc, "id", None)),
                    "check_id": getattr(check, "id", None),
                },
            )
            detection = {
                "found": False,
                "evidence": "",
                "confidence": 0.0,
                "method": "rules",
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

        detector_method = detection.get("method")
        raw_details = detection.get("raw") or {}
        if not isinstance(raw_details, dict):
            raw_details = {}

        raw_details.setdefault("context_truncated", bool(context_truncated))
        raw_details.setdefault("context_tokens", int(context_tokens))

        reason = detection.get("reason")
        if reason is None and isinstance(raw_details, dict):
            llm_details = raw_details.get("llm_details") or {}
            reason = llm_details.get("reason") or llm_details.get("parse_success")

        sources = detection.get("sources")
        location = detection.get("location")

        # Вытаскиваем флаги технического состояния LLM.
        # Это отдельная плоскость по отношению к business-result.
        llm_flags = self._extract_llm_runtime_flags(
            detector_method=detector_method,
            detection=detection,
            raw_details=raw_details,
        )

        # Дублируем эти флаги ещё и в raw, чтобы downstream-слои и отладка
        # видели их в одном месте, даже если кто-то не читает верхний уровень DTO.
        raw_details.setdefault("llm_error_type", llm_flags["llm_error_type"])
        raw_details.setdefault("llm_error_message", llm_flags["llm_error_message"])
        raw_details.setdefault("llm_attempts", llm_flags["llm_attempts"])
        raw_details.setdefault("rules_llm_decision", llm_flags["rules_llm_decision"])
        raw_details.setdefault("llm_required", llm_flags["llm_required"])
        raw_details.setdefault("llm_degraded", llm_flags["llm_degraded"])

        structured_data = None
        try:
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
            if isinstance(raw_details, dict):
                raw_details.setdefault("extraction_error", str(e))

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
                result = "unclear"
                severity = check.severity_if_unclear or check.severity

        # Очень важное правило Variant B:
        # если LLM был обязателен, но упал, мы не должны выдавать это как честный pass/fail.
        # Поэтому в таком случае насильно переводим business-result в "unclear".
        if llm_flags["llm_required"] and llm_flags["llm_error_type"]:
            result = "unclear"
            severity = check.severity_if_unclear or check.severity

        page = None
        clause_uid = None
        element_id = None
        bbox = None

        if isinstance(location, dict):
            page = location.get("page")
            clause_uid = location.get("clause_uid")
            element_id = location.get("element_id")
            bbox = location.get("bbox")

        if bbox is None and isinstance(sources, list) and sources:
            first_src = sources[0]
            if isinstance(first_src, dict):
                bbox = first_src.get("bbox", bbox)
                if page is None:
                    page = first_src.get("page")
                if clause_uid is None:
                    clause_uid = first_src.get("clause_uid")
                if element_id is None:
                    element_id = first_src.get("element_id")

        detector_label = detector_method or "unknown"
        try:
            duration = time.time() - start_time
            METRICS.check_duration.labels(detector_type=detector_label).observe(duration)
            METRICS.checks_executed.labels(
                detector_type=detector_label,
                result=result,
            ).inc()
        except Exception:
            logger.exception(
                "CheckExecutor: failed to update metrics",
                extra={
                    "doc_id": str(getattr(doc, "id", None)),
                    "check_id": getattr(check, "id", None),
                },
            )

        return {
            "doc_id": str(doc.id),
            "check_id": check.id,
            "check_name": check.name,
            "result": result,
            "found": found,
            "evidence": detection.get("evidence", ""),
            "confidence": confidence,
            "severity": severity,
            "detector_method": detector_method,
            "reason": reason,
            "sources": sources,
            "location": location,
            "raw": raw_details,
            "structured_data": structured_data,
            "page": page,
            "clause_uid": clause_uid,
            "element_id": element_id,
            "bbox": bbox,
            # Новые технические поля для следующего слоя.
            "llm_error_type": llm_flags["llm_error_type"],
            "llm_error_message": llm_flags["llm_error_message"],
            "llm_attempts": llm_flags["llm_attempts"],
            "rules_llm_decision": llm_flags["rules_llm_decision"],
            "llm_required": llm_flags["llm_required"],
            "llm_degraded": llm_flags["llm_degraded"],
        }


