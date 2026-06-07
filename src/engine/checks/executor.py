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

from core.config import settings
from core.logging import get_logger
from engine.content.chunking import build_chunk_summary
from engine.retrieval.tokenization import count_tokens
from ops.metrics import METRICS

from ..detectors.hybrid_detector import HybridDetector
from ..detectors.models import RetrievedChunk
from ..playbook.models import CheckDefinition
from ..retrieval.engine import RetrievalEngine
from .extraction import ExtractionExecutor

logger = get_logger(__name__)

# Источник (raw["source"]), при котором presence-чек считается "клаузы нет"
_PRESENCE_NOT_FOUND_SOURCES = {
    "rules_clean_negative",
    "both_not_found_llm_preferred",
}


class CheckExecutor:
    def __init__(self, llm_client):
        self.detector = HybridDetector(llm_client)
        self.extractor = ExtractionExecutor(llm_client)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_chunk_piece(c: dict, rc: RetrievedChunk) -> str:
        """
        Сформировать текстовый кусок для одного чанка: заголовок + текст.
        Вынесено, чтобы не дублировать логику в двух ветках _build_limited_context.
        """
        meta = c.get("metadata", {}) or {}
        # Для отображения в LLM-промпте берём raw_uid (читаемый "5.2"),
        # а не effective_uid ("main_contract:5.2").
        # Читаем effective_uid из metadata если есть, потом clause_uid как fallback.
        _raw_clause = meta.get("effective_uid", "") or meta.get("clause_uid", "") or rc.clause_uid
        # Показываем только raw_uid часть без scope prefix
        clause = _raw_clause.split(":")[-1] if ":" in _raw_clause else _raw_clause
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
        return f"{header}\n{text}".strip() if header else text

    def _build_limited_context(
        self,
        contexts: list[dict],
        retrieved_chunks: list[RetrievedChunk],
        important_terms: list[str],
        max_tokens: int | None,
    ) -> tuple[str, list[RetrievedChunk], list[dict], int, bool]:
        """
        Построить текстовый контекст для LLM с учётом лимита по токенам.

        Возвращает:
            joined_text        — итоговый текст для LLM,
            kept_chunks        — RetrievedChunk, которые попали в запрос,
            kept_context_dicts — исходные dict'ы для этих чанков,
            total_tokens       — сколько токенов занял контекст,
            truncated          — пришлось ли что-то обрезать.
        """
        # Ветка без лимита: склеиваем всё как есть
        if not isinstance(max_tokens, int) or max_tokens <= 0:
            context_parts = [
                self._build_chunk_piece(c, rc) for c, rc in zip(contexts, retrieved_chunks)
            ]
            joined_text = "\n\n---\n\n".join(context_parts)
            total_tokens = count_tokens(joined_text)
            return joined_text, retrieved_chunks, contexts, total_tokens, False

        # Строим items: (score, token_count, context_dict, retrieved_chunk, piece_text)
        # score берём из combined_score чанка — он уже отражает rerank-приоритет.
        # Сортируем по убыванию score, чтобы наиболее релевантные чанки
        # попадали в контекст первыми при обрезке по hard_limit.
        items: list[tuple[float, int, dict, RetrievedChunk, str]] = []
        for c, rc in zip(contexts, retrieved_chunks):
            piece = self._build_chunk_piece(c, rc)
            score = float(rc.combined_score or 0.0)
            items.append((score, count_tokens(piece), c, rc, piece))

        items.sort(key=lambda t: t[0], reverse=True)

        reserve_ratio = getattr(settings, "LLM_CONTEXT_RESERVE_RATIO", 0.3)
        try:
            reserve_ratio = float(reserve_ratio)
        except (TypeError, ValueError):
            reserve_ratio = 0.3
        reserve_ratio = max(0.0, min(0.9, reserve_ratio))
        hard_limit = int(max_tokens * (1.0 - reserve_ratio))
        if hard_limit <= 0:
            hard_limit = max_tokens // 2 if max_tokens > 0 else 2048

        # Жадный набор чанков до hard_limit
        kept_items: list[tuple[float, int, dict, RetrievedChunk, str]] = []
        total_tokens = 0
        truncated = False

        for score, token_count, c, rc, piece in items:
            if total_tokens + token_count <= hard_limit:
                kept_items.append((score, token_count, c, rc, piece))
                total_tokens += token_count
            else:
                truncated = True
                # НЕ break — продолжаем, вдруг следующий чанк меньше по токенам.
                # Это bin-packing: берём все чанки, которые влезают, не только первые N.
                continue

        if not truncated:
            joined_text = "\n\n---\n\n".join(piece for _, _, _, _, piece in kept_items)
            return (
                joined_text,
                [rc for _, _, _, rc, _ in kept_items],
                [c for _, _, c, _, _ in kept_items],
                total_tokens,
                False,
            )

        # Компрессия: заменяем чанки, не влезшие целиком, на summary
        compressed_items: list[tuple[float, int, dict, RetrievedChunk, str]] = []
        remaining_tokens = hard_limit
        important_lower = [s.lower() for s in important_terms if isinstance(s, str)]

        for score, token_count, c, rc, piece in kept_items:
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

                compressed_items.append((score, summary_tokens, c, rc, summary_piece))
                remaining_tokens -= summary_tokens
                truncated = True
            else:
                compressed_items.append((score, token_count, c, rc, piece))
                remaining_tokens -= token_count

        # Аварийный fallback: берём самый маленький чанк
        if not compressed_items:
            top_candidates = items[:3] if len(items) >= 3 else items
            _, token_count, c, rc, piece = min(top_candidates, key=lambda t: t[1])

            piece_tokens = count_tokens(piece)

            if piece_tokens > hard_limit:
                meta = c.get("metadata", {}) or {}
                path_titles = meta.get("path_titles") or rc.path_titles or []
                original_text = c.get("text") or rc.text or ""
                piece = build_chunk_summary(path_titles, original_text).strip()
                piece_tokens = count_tokens(piece)

            # score=0.0 — fallback-чанк, в sort по start_page это нейтрально
            compressed_items = [(0.0, piece_tokens, c, rc, piece)]  # ← 5-tuple ✓
            total_tokens = piece_tokens
            truncated = True
        else:
            total_tokens = sum(t for _, t, _, _, _ in compressed_items)  # ← 5-распаковка ✓

        # Восстанавливаем исходный порядок по позиции в документе (start_page),
        # а не по score — LLM лучше читает связный нарратив, чем чанки по relevance.
        compressed_items.sort(key=lambda t: (t[3].start_page or 0, t[3].page or 0))

        joined_text = "\n\n---\n\n".join(piece for _, _, _, _, piece in compressed_items)
        kept_chunks = [rc for _, _, _, rc, _ in compressed_items]
        kept_contexts = [c for _, _, c, _, _ in compressed_items]

        return joined_text, kept_chunks, kept_contexts, total_tokens, truncated

    def _extract_llm_runtime_flags(
        self,
        detector_method: str | None,
        detection: dict,
        raw_details: dict,
    ) -> dict:
        """
        Вытащить из detection/raw технические флаги по LLM.

        Бизнес-результат (fail/pass/unclear) здесь не меняется.
        Только вычисляем: был ли сбой LLM, был ли LLM обязателен, есть ли деградация.
        """
        if not isinstance(raw_details, dict):
            raw_details = {}

        llm_details = raw_details.get("llm_details") or {}
        if not isinstance(llm_details, dict):
            llm_details = {}

        # Ошибку берём сначала из верхнего уровня raw (HybridDetector кладёт её туда
        # в rules-fallback ветке), затем из llm_details.
        llm_error_type = raw_details.get("llm_error_type") or llm_details.get("error_type")
        llm_error_message = raw_details.get("llm_error_message") or llm_details.get("error_message")
        llm_attempts = raw_details.get("llm_attempts") or llm_details.get("llm_attempts")

        rules_llm_decision = raw_details.get("rules_llm_decision") or detection.get("reason")

        rules_sufficient_decisions = {
            "rules_confident_positive",
            "rules_clean_negative",
        }
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
            llm_required = bool(llm_error_present and detector_method in {"llm", "hybrid"})

        return {
            "llm_error_type": llm_error_type,
            "llm_error_message": llm_error_message,
            "llm_attempts": llm_attempts,
            "rules_llm_decision": rules_llm_decision,
            "llm_required": llm_required,
            "llm_degraded": llm_error_present,
        }

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def execute(self, doc, check: CheckDefinition, chunks: list[dict]) -> dict:
        """
        Выполнить один check для одного документа.

        Args:
            doc:    ORM Document.
            chunks: список чанков [{"id": ..., "text": "...", "metadata": {...}}, ...].

        Возвращает словарь, пригодный для записи в CheckResult.
        Никогда не выбрасывает исключение: при любых внутренних ошибках
        возвращает result="unclear" с диагностикой в raw.
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
        query = (
            f"{check.name} {' '.join(boost_keywords[:3])}".strip() if boost_keywords else check.name
        )

        retr_cfg = getattr(check, "retrieval", None)
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
                    # clause_uid: читаем effective_uid (canonical) или clause_uid (legacy)
                    # effective_uid появился в Sprint 3 как canonical identity.
                    # clause_uid оставлен как fallback для старых чанков.
                    clause_uid=meta.get("effective_uid") or meta.get("clause_uid") or "",
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
            important_lower = [s.lower() for s in important_terms if isinstance(s, str)]

            def _score(rc: RetrievedChunk) -> float:
                """
                Эвристический rerank поверх combined_score.

                combined_score остаётся главным сигналом релевантности.
                kind / keywords дают только небольшой ограниченный сдвиг.
                """
                base = float(rc.combined_score or 0.0)

                cid = str(rc.element_id or "")
                meta = id_to_meta.get(cid) or {}
                text = (id_to_text.get(cid) or "").lower()
                kind = str(meta.get("chunk_kind") or meta.get("kind") or "").lower()

                # Небольшой bonus/penalty за тип фрагмента.
                # P8.8d: legal_unit — новый primary retrieval substrate,
                # получает тот же бонус, что раньше subclause.
                kind_bonus = 0.0
                if kind in ("legal_unit", "subclause"):
                    kind_bonus = 0.05
                elif kind == "section":
                    kind_bonus = -0.02

                # Суммарный keyword-бонус с жёстким cap
                keyword_bonus = 0.0
                for term in important_lower:
                    if term and term in text:
                        keyword_bonus += 0.03
                # ограничиваем влияние keyword-бонуса, чтобы не перебить base
                keyword_bonus = min(keyword_bonus, 0.09)

                return base + kind_bonus + keyword_bonus

            return sorted(chunks_rc, key=_score, reverse=True)

        if do_rerank and retrieved_chunks:
            # Строим индекс contexts по element_id ДО rerank,
            # чтобы после пересортировки retrieved_chunks восстановить
            # правильные пары (rc, context_dict).
            _ctx_by_id: dict[str, dict] = {}
            for _c, _rc in zip(contexts, retrieved_chunks):
                _ctx_by_id[str(_rc.element_id)] = _c

            retrieved_chunks = _simple_rerank(retrieved_chunks)

            # Восстанавливаем contexts в том же порядке, что и retrieved_chunks после rerank.
            # Чанки без совпадения (теоретически невозможно) пропускаем с guard.
            contexts = [
                _ctx_by_id[str(rc.element_id)]
                for rc in retrieved_chunks
                if str(rc.element_id) in _ctx_by_id
            ]
            # Если после фильтрации размеры разошлись — обрезаем retrieved_chunks по contexts
            if len(contexts) != len(retrieved_chunks):
                retrieved_chunks = retrieved_chunks[: len(contexts)]

        if required_kind:
            required_kind_lower = str(required_kind).lower()
            # Строим индекс contexts по element_id для ресинхронизации после перестановки
            _ctx_by_id_kind: dict[str, dict] = {
                str(rc.element_id): c for rc, c in zip(retrieved_chunks, contexts)
            }
            primary: list[RetrievedChunk] = []
            fallback: list[RetrievedChunk] = []
            for rc in retrieved_chunks:
                cid = str(rc.element_id or "")
                kind = str(id_to_meta.get(cid, {}).get("kind") or "").lower()
                (primary if kind == required_kind_lower else fallback).append(rc)
            if primary:
                retrieved_chunks = primary + fallback
                # Синхронизируем contexts в том же новом порядке
                contexts = [
                    _ctx_by_id_kind[str(rc.element_id)]
                    for rc in retrieved_chunks
                    if str(rc.element_id) in _ctx_by_id_kind
                ]
                if len(contexts) != len(retrieved_chunks):
                    retrieved_chunks = retrieved_chunks[: len(contexts)]

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
            classification_confidence = float(getattr(doc, "classification_confidence", 1.0) or 0.0)
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
        if reason is None:
            llm_details = raw_details.get("llm_details") or {}
            reason = llm_details.get("reason") or llm_details.get("parse_success")

        sources = detection.get("sources")
        location = detection.get("location")

        llm_flags = self._extract_llm_runtime_flags(
            detector_method=detector_method,
            detection=detection,
            raw_details=raw_details,
        )

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
                        # clause_uid содержит effective_uid после нашей правки выше.
                        # Дублируем под обоими ключами чтобы extraction.py
                        # мог находить по любому из них без изменения своей логики.
                        "clause_uid": rc.clause_uid,
                        "effective_uid": rc.clause_uid,
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
            raw_details.setdefault("extraction_error", str(e))

        # ------------------------------------------------------------------
        # Business-result mapping
        # ------------------------------------------------------------------
        pass_thr = getattr(settings, "CHECK_PASS_THRESHOLD", 0.6)
        unclear_thr = getattr(settings, "CHECK_UNCLEAR_THRESHOLD", 0.3)

        is_presence_check = getattr(check, "ui_mode", None) == "clause_presence"
        is_presence_not_found = (
            is_presence_check
            and not found
            and raw_details.get("source") in _PRESENCE_NOT_FOUND_SOURCES
        )

        if found:
            result = "fail"
            severity = check.severity_if_fail or check.severity
        elif is_presence_not_found:
            result = "missing_required_clause"
            severity = check.severity_if_fail or check.severity
        else:
            if confidence >= pass_thr:
                result = "pass"
                severity = check.severity_if_pass or "pass"
            elif confidence >= unclear_thr:
                result = "unclear"
                severity = check.severity_if_unclear or check.severity
            else:
                result = "unclear"
                severity = check.severity_if_unclear or check.severity
                raw_details.setdefault("low_confidence_flag", True)

        # Variant B: LLM был обязателен, но упал → не выдавать честный pass/fail
        if llm_flags["llm_required"] and llm_flags["llm_error_type"]:
            result = "unclear"
            severity = check.severity_if_unclear or check.severity

        # ------------------------------------------------------------------
        # Location extraction
        # ------------------------------------------------------------------
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
                bbox = first_src.get("bbox")
                if page is None:
                    page = first_src.get("page")
                if clause_uid is None:
                    # effective_uid (canonical Sprint 3) или clause_uid (legacy)
                    clause_uid = first_src.get("effective_uid") or first_src.get("clause_uid")

        # ------------------------------------------------------------------
        # Metrics
        # ------------------------------------------------------------------
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
            "llm_error_type": llm_flags["llm_error_type"],
            "llm_error_message": llm_flags["llm_error_message"],
            "llm_attempts": llm_flags["llm_attempts"],
            "rules_llm_decision": llm_flags["rules_llm_decision"],
            "llm_required": llm_flags["llm_required"],
            "llm_degraded": llm_flags["llm_degraded"],
        }
