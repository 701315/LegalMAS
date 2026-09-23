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
from typing import Any

from core.anchors.models import CheckAnchor, CheckAnchorMethod
from core.config import settings
from core.logging import get_logger
from engine.content.chunking import build_chunk_summary
from engine.retrieval.tokenization import count_tokens
from ops.metrics import METRICS

from ..detectors.hybrid_detector import HybridDetector
from engine.checks.semantic_context import SemanticEnrichmentContext
from ..detectors.models import RetrievedChunk
from ..playbook.models import (
    CheckDefinition,
    DetectorType,
    PresenceSignalConfig,
)
from ..retrieval.engine import RetrievalEngine
from .citation_resolver import resolve_quote_in_source
from .extraction import ExtractionExecutor
from .extraction_semantics import (
    RESERVED_METADATA_FIELDS as _RESERVED_METADATA_FIELDS,
    iter_meaningful_fields,
)

logger = get_logger(__name__)

# Источник (raw["source"]), при котором presence-чек считается "клаузы нет"
_PRESENCE_NOT_FOUND_SOURCES = {
    "rules_clean_negative",
    "both_not_found_llm_preferred",
}

def _get_field_presentation_from_check(
    check: "CheckDefinition | None",
    field_name: str,
) -> str:
    """
    Get presentation role for a field from check.extraction.fields.

    Returns 'fact' as default when check or field config is not available.
    """
    if check is None:
        return "fact"
    extraction = getattr(check, "extraction", None)
    if extraction is None:
        return "fact"
    fields = getattr(extraction, "fields", None)
    if not isinstance(fields, list):
        return "fact"
    for field_cfg in fields:
        if getattr(field_cfg, "name", None) == field_name:
            presentation = getattr(field_cfg, "presentation", None)
            if presentation and str(presentation).strip():
                return str(presentation).strip()
            return "fact"
    return "fact"


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

    @staticmethod
    def _empty_provenance() -> dict[str, Any]:
        return {
            "page": None,
            "clause_uid": None,
            "element_id": None,
            "bbox": None,
            "segment_id": None,
            "segment_type": None,
            "segment_title": None,
            "segment_order": None,
            "is_primary_segment": None,
            "chunk_id": None,
            "chunk_index": None,
        }

    @classmethod
    def _extract_detector_provenance(
        cls,
        location: dict | None,
        sources: list | None,
    ) -> dict[str, Any]:
        """
        Извлечь provenance из detector output (location/sources).
        Это primary source, если detector реально заполнил anchors.
        """
        prov = cls._empty_provenance()

        if isinstance(location, dict):
            prov["page"] = location.get("page")
            prov["clause_uid"] = location.get("clause_uid")
            prov["element_id"] = location.get("element_id")
            prov["bbox"] = location.get("bbox")
            prov["segment_id"] = location.get("segment_id")
            prov["segment_type"] = location.get("segment_type")
            prov["segment_title"] = location.get("segment_title")
            prov["segment_order"] = location.get("segment_order")
            prov["is_primary_segment"] = location.get("is_primary_segment")
            prov["chunk_id"] = location.get("chunk_id")
            prov["chunk_index"] = location.get("chunk_index")

        if isinstance(sources, list) and sources:
            first_src = sources[0]
            if isinstance(first_src, dict):
                if prov["bbox"] is None:
                    prov["bbox"] = first_src.get("bbox")
                if prov["page"] is None:
                    prov["page"] = first_src.get("page")
                if prov["clause_uid"] is None:
                    prov["clause_uid"] = first_src.get("effective_uid") or first_src.get("clause_uid")
                if prov["element_id"] is None:
                    prov["element_id"] = first_src.get("element_id")

                if prov["segment_id"] is None:
                    prov["segment_id"] = first_src.get("segment_id")
                if prov["segment_type"] is None:
                    prov["segment_type"] = first_src.get("segment_type")
                if prov["segment_title"] is None:
                    prov["segment_title"] = first_src.get("segment_title")
                if prov["segment_order"] is None:
                    prov["segment_order"] = first_src.get("segment_order")
                if prov["is_primary_segment"] is None:
                    prov["is_primary_segment"] = first_src.get("is_primary_segment")

                if prov["chunk_id"] is None:
                    prov["chunk_id"] = first_src.get("chunk_id")
                if prov["chunk_index"] is None:
                    prov["chunk_index"] = first_src.get("chunk_index")

        return prov

    @classmethod
    def _extract_primary_context_provenance(
        cls,
        contexts: list[dict],
        retrieved_chunks: list[RetrievedChunk],
    ) -> dict[str, Any]:
        """
        Fallback provenance для extraction-only path.
        Если detector не дал anchors, берём provenance из top-ranked retrieval chunk.
        """
        prov = cls._empty_provenance()

        if not contexts or not retrieved_chunks:
            return prov

        c = contexts[0] or {}
        rc = retrieved_chunks[0]
        meta = c.get("metadata", {}) or {}

        prov["page"] = (
            meta.get("page")
            or meta.get("start_page")
            or getattr(rc, "page", None)
            or getattr(rc, "start_page", None)
        )
        prov["clause_uid"] = (
            meta.get("effective_uid")
            or meta.get("clause_uid")
            or getattr(rc, "clause_uid", None)
        )
        # element_id — это layout UUID формата "ru:node:3:0004",
        # НЕ retrieval chunk id. Список layout UUID лежит в
        # canonical metadata["element_ids"] (заполняется в
        # normalize_snapshot_chunk_metadata). c.get("id") возвращает
        # compound "{doc_id}:{effective_uid}", что ломает viewer overlay.
        layout_element_ids = meta.get("element_ids") or []
        prov["element_id"] = (
            (layout_element_ids[0] if layout_element_ids else None)
            or meta.get("element_id")
            or None
        )
        prov["segment_id"] = (
            meta.get("segment_id")
            or getattr(rc, "segment_id", None)
        )
        prov["segment_type"] = (
            meta.get("segment_type")
            or getattr(rc, "segment_type", None)
        )
        prov["segment_title"] = (
            meta.get("segment_title")
            or getattr(rc, "segment_title", None)
        )

        seg_order = meta.get("segment_order")
        if seg_order is None:
            seg_order = getattr(rc, "segment_order", None)
        prov["segment_order"] = seg_order

        is_primary = meta.get("is_primary_segment")
        if is_primary is None:
            is_primary = getattr(rc, "is_primary_segment", None)
        prov["is_primary_segment"] = is_primary

        # chunk_id — canonical "{doc_id}:{kind}:{effective_uid}:{idx}".
        # В canonical metadata это поле называется "fragment_id"
        # (см. chunk_canonicalization.build_sized_chunks_from_leaf).
        # meta["chunk_id"] и rc.chunk_id не заполняются в новом pipeline,
        # оставлены как legacy fallback. c.get("id") — compound
        # "{doc_id}:{effective_uid}", используется только если ничего
        # другого нет.
        prov["chunk_id"] = (
            meta.get("fragment_id")
            or meta.get("chunk_id")
            or getattr(rc, "chunk_id", None)
            or c.get("id")
        )

        chunk_index = meta.get("chunk_index")
        if chunk_index is None:
            chunk_index = getattr(rc, "chunk_index", None)
        prov["chunk_index"] = chunk_index

        # bbox_union (B0.4): union bbox of chunk's elements on its page.
        # Packed as dict so B5 (viewer) can use union + page + element_ids
        # for highlight. Legacy records (pre-B0.4) keep bbox=None.
        bbox_union = meta.get("bbox_union")
        if isinstance(bbox_union, list) and len(bbox_union) == 4:
            prov["bbox"] = {
                "union": list(bbox_union),
                "page": prov.get("page"),
                "element_ids": list(layout_element_ids or []),
            }

        return prov

    @classmethod
    def _merge_provenance(
        cls,
        primary: dict[str, Any] | None,
        fallback: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """
        Merge provenance with 'primary wins' policy.
        """
        out = cls._empty_provenance()
        primary = primary or {}
        fallback = fallback or {}

        for key in out.keys():
            out[key] = (
                primary.get(key)
                if primary.get(key) is not None
                else fallback.get(key)
            )
        return out

    @staticmethod
    def _build_context_provenance_trace(
        contexts: list[dict],
        retrieved_chunks: list[RetrievedChunk],
        max_items: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Compact trace of retrieval contexts used to build LLM prompt context.
        Stores metadata only, not full text.
        """
        out: list[dict[str, Any]] = []

        for idx, (c, rc) in enumerate(zip(contexts, retrieved_chunks)):
            if idx >= max_items:
                break

            meta = (c or {}).get("metadata", {}) or {}
            out.append(
                {
                    "rank": idx,
                    "element_id": c.get("id"),
                    "chunk_id": meta.get("chunk_id") or getattr(rc, "chunk_id", None) or c.get("id"),
                    "chunk_index": (
                        meta.get("chunk_index")
                        if meta.get("chunk_index") is not None
                        else getattr(rc, "chunk_index", None)
                    ),
                    "page": (
                        meta.get("page")
                        or meta.get("start_page")
                        or getattr(rc, "page", None)
                        or getattr(rc, "start_page", None)
                    ),
                    "clause_uid": (
                        meta.get("effective_uid")
                        or meta.get("clause_uid")
                        or getattr(rc, "clause_uid", None)
                    ),
                    "segment_id": meta.get("segment_id") or getattr(rc, "segment_id", None),
                    "segment_type": meta.get("segment_type") or getattr(rc, "segment_type", None),
                    "segment_title": meta.get("segment_title") or getattr(rc, "segment_title", None),
                    "score": getattr(rc, "combined_score", None),
                    "score_breakdown": (c or {}).get("score_breakdown"),
                }
            )

        return out

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

    @staticmethod
    def _is_field_extraction_check(check: CheckDefinition | None) -> bool:
        """
        Determine whether check should run in extraction-only mode.

        Rules:
        1. explicit ui_mode == "field_extraction" -> True
        2. any other explicit non-empty ui_mode   -> False
        3. missing/blank ui_mode                  -> fallback to extraction.enabled
        """
        if check is None:
            return False

        raw_ui_mode = getattr(check, "ui_mode", None)
        ui_mode = str(raw_ui_mode).strip().lower() if raw_ui_mode is not None else ""

        if ui_mode == "field_extraction":
            return True

        if ui_mode:
            return False

        extraction = getattr(check, "extraction", None)
        if extraction is None:
            return False

        return bool(getattr(extraction, "enabled", False))

    @staticmethod
    def _has_meaningful_extraction(
        structured_data: dict | None,
        check: CheckDefinition | None = None,
    ) -> bool:
        """
        Canonical business-level success predicate for field_extraction checks.

        Delegates meaningful-field semantics to extraction_semantics.iter_meaningful_fields()
        so that executor and result_semantics use one shared rule-set.
        """
        if not isinstance(structured_data, dict) or not structured_data:
            return False

        return bool(
            iter_meaningful_fields(
                structured_data,
                presentation_resolver=lambda field_name: _get_field_presentation_from_check(
                    check, field_name
                ),
            )
        )

    @staticmethod
    def _classify_presence_signal(
        structured_data: dict | None,
        signal: PresenceSignalConfig,
    ) -> str:
        """Return presence-gate verdict.

        Returns one of:
            "present" | "missing" | "unclear" | "undeclared" | "not_extracted"
        """
        if not isinstance(structured_data, dict):
            return "not_extracted"

        payload = structured_data.get(signal.field)
        if not isinstance(payload, dict):
            return "not_extracted"

        if not payload.get("found"):
            return "not_extracted"

        return signal.classify(payload.get("value"))

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_risk_anchors(
        detection: dict[str, Any],
        contexts: list[dict[str, Any]],
    ) -> list[CheckAnchor]:
        """
        Собрать CheckAnchor для риск-детекции / rules_only (B3.3).

        Логика:
        - только для positive finding (detection["found"] is True);
        - quote = detection["evidence"] (строка);
        - пытаемся найти точное место цитаты в каждом context.text;
        - первый EXACT_SPAN / FUZZY_SPAN — победа;
        - иначе — первый clause_only / page_only (из detection.location);
        - иначе — пусто (никогда не возвращаем anchor_method=NONE).

        layout_elements=[] для MVP: span есть, element_ids пустые.
        Реальные layout_elements будут подключены в B3.5.

        Никогда не бросает.
        """
        if not isinstance(detection, dict):
            return []
        if not detection.get("found"):
            return []

        evidence = detection.get("evidence")
        if not isinstance(evidence, str) or not evidence.strip():
            return []
        quote = evidence.strip()

        # Fallback clause_uid / page из check-level location.
        fallback_clause_uid: str | None = None
        fallback_page: int | None = None
        location = detection.get("location")
        if isinstance(location, dict):
            raw_uid = location.get("clause_uid")
            if isinstance(raw_uid, str) and raw_uid.strip():
                fallback_clause_uid = raw_uid.strip()

            raw_page = location.get("page")
            if isinstance(raw_page, int) and not isinstance(raw_page, bool) and raw_page > 0:
                fallback_page = raw_page

        fallback_anchor: CheckAnchor | None = None

        for ctx in contexts or []:
            if not isinstance(ctx, dict):
                continue
            ctx_text = ctx.get("text")
            if not isinstance(ctx_text, str) or not ctx_text:
                continue

            anchor = resolve_quote_in_source(
                quote=quote,
                source_text=ctx_text,
                layout_elements=[],
                fallback_clause_uid=fallback_clause_uid,
                fallback_page=fallback_page,
            )

            # Exact/fuzzy — strongest, возвращаем сразу.
            if anchor.anchor_method in (
                CheckAnchorMethod.EXACT_SPAN,
                CheckAnchorMethod.FUZZY_SPAN,
            ):
                return [anchor]

            # Сохраняем слабый fallback (clause_only / page_only) как запас.
            if (
                anchor.anchor_method != CheckAnchorMethod.NONE
                and fallback_anchor is None
            ):
                fallback_anchor = anchor

        return [fallback_anchor] if fallback_anchor is not None else []



    def execute(
        self,
        doc,
        check: CheckDefinition,
        chunks: list[dict],
        semantic_context: "SemanticEnrichmentContext | None" = None,
        chunks_metadata: dict[str, Any] | None = None,
    ) -> dict:
        """
        Выполнить один check для одного документа.

        Args:
            doc:    ORM Document.
            chunks: список чанков [{"id": ..., "text": "...", "metadata": {...}}, ...].
            chunks_metadata:
                {
                    "truncated": bool,
                    "original_count": int,
                    "kept_count": int,
                }
                Метаданные подготовки chunks из ChunksPreparer.
                Если truncated=True — документ был обработан по частичному corpus.

        Возвращает словарь, пригодный для записи в CheckResult.
        Никогда не выбрасывает исключение: при любых внутренних ошибках
        возвращает result="unclear" с диагностикой в raw.

        Field-extraction invariant:
        - checks with ui_mode="field_extraction" skip generic presence detection;
        - checks without explicit ui_mode, but with extraction.enabled=True,
          also use extraction-only mode by convention;
        - business result for such checks is derived from structured extraction,
          not from presence confidence.
        """
        start_time = time.time()

        retr_cfg = getattr(check, "retrieval", None)

        raw_boost_keywords = getattr(retr_cfg, "boost_keywords", []) or []
        raw_negative_keywords = getattr(retr_cfg, "negative_keywords", []) or []
        raw_preferred_unit_types = getattr(retr_cfg, "preferred_unit_types", []) or []
        raw_excluded_unit_types = getattr(retr_cfg, "excluded_unit_types", []) or []
        raw_preferred_clause_functions = (
            getattr(retr_cfg, "preferred_clause_functions", []) or []
        )
        raw_retrieval_query = getattr(retr_cfg, "retrieval_query", None)
        raw_position_bias = getattr(retr_cfg, "position_bias", None)
        raw_retrieval_profile_id = getattr(retr_cfg, "retrieval_profile", None)

        def _normalize_retrieval_phrase(value: Any) -> str:
            if not isinstance(value, str):
                return ""
            cleaned = value.replace("_", " ").replace("-", " ")
            cleaned = " ".join(cleaned.split())
            return cleaned.strip()

        important_terms: list[str] = []

        normalized_check_name = _normalize_retrieval_phrase(check.name)
        if normalized_check_name:
            important_terms.append(normalized_check_name)

        for kw in raw_boost_keywords:
            normalized_kw = _normalize_retrieval_phrase(kw)
            if normalized_kw and normalized_kw not in important_terms:
                important_terms.append(normalized_kw)

        explicit_retrieval_query = _normalize_retrieval_phrase(raw_retrieval_query)

        if explicit_retrieval_query:
            query = explicit_retrieval_query
        else:
            fallback_query_parts: list[str] = []
            if normalized_check_name:
                fallback_query_parts.append(normalized_check_name)
            for term in important_terms:
                if term and term not in fallback_query_parts:
                    fallback_query_parts.append(term)
            query = " ".join(fallback_query_parts).strip()

        retriever = RetrievalEngine(
            chunks,
            important_terms=important_terms,
            negative_keywords=raw_negative_keywords,
            preferred_unit_types=raw_preferred_unit_types,
            excluded_unit_types=raw_excluded_unit_types,
            preferred_clause_functions=raw_preferred_clause_functions,
            position_bias=raw_position_bias,
            retrieval_profile_id=raw_retrieval_profile_id,
        )

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
                    bbox=list(meta.get("bbox_union") or []),
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
            meta = c.get("metadata", {}) or {}
            text = c.get("text") or ""

            # Primary index by chunk id
            id_to_meta[cid] = meta
            id_to_text[cid] = text

            # Secondary index by element_ids
            # RetrievedChunk.element_id часто равен первому element_id чанка,
            # а не самому chunk id. Без этого rerank lookup теряет metadata/text.
            for eid in meta.get("element_ids") or []:
                eid_str = str(eid).strip()
                if eid_str and eid_str not in id_to_meta:
                    id_to_meta[eid_str] = meta
                    id_to_text[eid_str] = text

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

        # ── Semantic enrichment scoring ───────────────────────────────────────
        # Apply soft multipliers to combined_score based on semantic_context.
        # Runs before _simple_rerank so semantic signals feed into sort order.
        # Only active when:
        #   - semantic_context is available and enrichment was loaded
        #   - check has enrichment_hints configured
        # All multipliers are soft (never zero): base retrieval always preserved.
        _enrichment_hints = getattr(check, "enrichment_hints", None)
        if (
            semantic_context is not None
            and semantic_context.enrichment_available
            and _enrichment_hints is not None
        ):
            _pref_seg_types = {
                t.lower().strip()
                for t in (getattr(_enrichment_hints, "preferred_segment_types", None) or [])
                if t and t.strip()
            }
            _excl_seg_types = {
                t.lower().strip()
                for t in (getattr(_enrichment_hints, "excluded_segment_types", None) or [])
                if t and t.strip()
            }
            _pref_clause_funcs = {
                f.lower().strip()
                for f in (getattr(_enrichment_hints, "preferred_clause_functions", None) or [])
                if f and f.strip()
            }
            _seg_type_lower = (semantic_context.segment_type or "").lower().strip()
            _seg_clause_funcs = semantic_context.clause_functions  # frozenset[str]

            _semantic_multiplier = 1.0

            # Preferred segment type: boost
            if _pref_seg_types and _seg_type_lower in _pref_seg_types:
                _semantic_multiplier *= 1.4

            # Excluded segment type: penalty
            if _excl_seg_types and _seg_type_lower in _excl_seg_types:
                _semantic_multiplier *= 0.6

            # Preferred clause function match: boost
            if _pref_clause_funcs and (_pref_clause_funcs & _seg_clause_funcs):
                _semantic_multiplier *= 1.5

            # Apply multiplier to all chunks if non-neutral
            if _semantic_multiplier != 1.0:
                _adjusted: list[RetrievedChunk] = []
                for _rc in retrieved_chunks:
                    _new_score = float(_rc.combined_score or 0.0) * _semantic_multiplier
                    _adjusted.append(
                        RetrievedChunk(
                            element_id=_rc.element_id,
                            text=_rc.text,
                            page=_rc.page,
                            clause_uid=_rc.clause_uid,
                            bbox=_rc.bbox,
                            dense_score=_rc.dense_score,
                            sparse_score=_rc.sparse_score,
                            metadata_score=_rc.metadata_score,
                            combined_score=_new_score,
                            path_titles=_rc.path_titles,
                            start_page=_rc.start_page,
                            end_page=_rc.end_page,
                            element_ids=_rc.element_ids,
                        )
                    )
                retrieved_chunks = _adjusted

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
                meta_for_kind = id_to_meta.get(cid) or {}
                kind = str(
                    meta_for_kind.get("chunk_kind")
                    or meta_for_kind.get("kind")
                    or ""
                ).lower()
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

        # ------------------------------------------------------------------
        # Budget reservation for field_extraction checks.
        #
        # Проблема (найдена при live-тесте run_id=f48e95af-74fe-4d76-93b2-b45edb9347dd):
        # _build_limited_context() резервировал под joined_text ВЕСЬ
        # LLM_CONTEXT_LIMIT, не зная, что для field_extraction checks этот
        # же самый joined_text ЗАТЕМ передаётся как evidence в
        # ExtractionExecutor -> ExtractionLLMDetector.extract_with_telemetry(),
        # который СВЕРХУ добавляет свой собственный prompt skeleton
        # (llm_prompt_extraction + fields schema + few-shot + example_json).
        #
        # Итог: два независимых бюджета молча складывались и легко
        # превышали реальный n_ctx модели. Ollama тихо обрезала контекст
        # на своей стороне, JSON от LLM приходил битым/усечённым,
        # _parse_response() ловил JSONDecodeError, extraction_llm_invoked
        # не проставлялся -> ни warning в app.log, ни записи в
        # llm_usage_events, structured_data = все поля "not found",
        # хотя нужные данные физически присутствовали в документе.
        #
        # Фикс: для field_extraction checks заранее вычитаем из общего
        # лимита оценочный размер extraction-промпта (skeleton + output +
        # safety margin), чтобы _build_limited_context() резервировал
        # joined_text только под ОСТАТОК бюджета.
        # ------------------------------------------------------------------
        llm_context_limit = getattr(settings, "LLM_CONTEXT_LIMIT", None)

        _is_field_extraction_precheck = self._is_field_extraction_check(check)
        if _is_field_extraction_precheck and isinstance(llm_context_limit, int) and llm_context_limit > 0:
            _extraction_cfg_precheck = getattr(check, "extraction", None)
            _extraction_max_tokens = (
                int(getattr(_extraction_cfg_precheck, "llm_max_tokens", None) or 0)
                or int(getattr(settings, "LLM_EXTRACTION_MAX_TOKENS", 900))
            )
            _extraction_prompt_text = (
                getattr(_extraction_cfg_precheck, "llm_prompt_extraction", None) or ""
            )

            # ВАЖНО: держать этот коэффициент синхронизированным с
            # ExtractionLLMDetector.extract_with_telemetry() (token_factor=3.8).
            # Если там изменится значение — обновить и здесь.
            _EXTRACTION_TOKEN_FACTOR = 3.8
            _extraction_skeleton_tokens_estimate = int(
                len(_extraction_prompt_text.split()) * _EXTRACTION_TOKEN_FACTOR
            )
            _extraction_safety_margin = int(
                getattr(settings, "LLM_SAFETY_MARGIN_TOKENS", 512)
            )

            _reserved_for_extraction = (
                _extraction_max_tokens
                + _extraction_skeleton_tokens_estimate
                + _extraction_safety_margin
            )

            _min_context_floor = int(
                getattr(settings, "LLM_MIN_CONTEXT_FLOOR_TOKENS", 512)
            )

            llm_context_limit = max(
                _min_context_floor,
                llm_context_limit - _reserved_for_extraction,
            )

            logger.debug(
                "CheckExecutor: reserved extraction budget before building joined_text",
                extra={
                    "check_id": getattr(check, "id", None),
                    "reserved_for_extraction": _reserved_for_extraction,
                    "extraction_skeleton_tokens_estimate": _extraction_skeleton_tokens_estimate,
                    "extraction_max_tokens": _extraction_max_tokens,
                    "adjusted_context_budget_for_joined_text": llm_context_limit,
                },
            )

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

        # ── Structural context augmentation ───────────────────────────────────
        # Prepend a compact structural preamble to joined_text for LLM.
        # Helps LLM understand which part of the document it is reading.
        # Only added when semantic_context carries segment/enrichment info.
        # If enrichment is absent: joined_text remains unchanged.
        if semantic_context is not None:
            _struct_block = semantic_context.to_prompt_block()
            if _struct_block:
                joined_text = _struct_block + "\n\n" + joined_text

        # Field-extraction checks do not need generic presence detection.
        # We skip the presence phase entirely and let structured extraction
        # drive both factual output and business result.
        is_field_extraction = self._is_field_extraction_check(check)

        if is_field_extraction:
            logger.debug(
                "CheckExecutor: skipping presence detection for field_extraction check",
                extra={
                    "doc_id": str(getattr(doc, "id", None)),
                    "check_id": getattr(check, "id", None),
                    "ui_mode": getattr(check, "ui_mode", None),
                    "extraction_enabled": bool(
                        getattr(getattr(check, "extraction", None), "enabled", False)
                    ),
                },
            )
            # Pass the already-budgeted joined_text as evidence so that
            # ExtractionExecutor._build_extraction_text() uses the same
            # token-limited text that was built by _build_limited_context(),
            # instead of re-joining raw context chunks without a budget.
            #
            # Invariant: joined_text is always a str at this point
            # (_build_limited_context never returns None).
            # For field_extraction checks the detector is skipped entirely,
            # so evidence would otherwise be "" and _build_extraction_text()
            # would fall back to re-concatenating all raw context chunks —
            # bypassing the token budget computed above.
            # R15: field_extraction не вызывает детектор, но downstream
            # (extraction.py) ожидает detection["location"] для anchor'ов
            # field_extraction. Заполняем из top-1 retrieved chunk (после
            # rerank) — наиболее релевантный чанк для extraction в этом чеке.
            # Ключи должны совпадать с теми, что читает
            # extraction.py::run_with_telemetry (raw_location.get(...)).
            location: dict | None = None
            if retrieved_chunks:
                _rc = retrieved_chunks[0]
                location = {
                    "page": _rc.page,
                    "clause_uid": _rc.clause_uid or None,
                    "element_id": _rc.element_id,
                    "start_page": _rc.start_page,
                    "end_page": _rc.end_page,
                    "path_titles": list(_rc.path_titles or []),
                }

            detection = {
                "found": True,
                "evidence": joined_text,
                "confidence": 1.0,
                "method": "extraction_only",
                "reason": "field_extraction_skip_presence",
                "sources": [],
                "location": location,
                "raw": {
                    "source": "field_extraction_mode",
                    "llm_invoked": False,
                    "rules_llm_decision": "skip_presence_for_extraction",
                },
            }
        else:
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

        # Честно пробрасываем truncation уровня corpus, а не только truncation
        # LLM prompt context. Это отдельный сигнал качества:
        # - context_truncated = обрезали prompt под токен-бюджет
        # - chunks_truncated  = ChunksPreparer обрезал corpus по MAX_CHUNKS_PER_DOC
        if isinstance(chunks_metadata, dict) and chunks_metadata.get("truncated") is True:
            raw_details.setdefault("chunks_truncated", True)
            raw_details.setdefault(
                "chunks_original_count",
                int(chunks_metadata.get("original_count", len(chunks))),
            )
            raw_details.setdefault(
                "chunks_kept_count",
                int(chunks_metadata.get("kept_count", len(chunks))),
            )

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
        extraction_telemetry: dict[str, Any] | None = None
        extraction_anchors: list[CheckAnchor] = []
        try:
            extraction_contexts: list[dict[str, Any]] = []

            for c, rc in zip(contexts, retrieved_chunks):
                ctx_meta = dict(c.get("metadata") or {})

                extraction_contexts.append(
                    {
                        "id": c.get("id") or rc.element_id,
                        "text": c.get("text") or rc.text or "",
                        "score_breakdown": c.get("score_breakdown"),
                        "metadata": {
                            "clause_uid": (
                                ctx_meta.get("clause_uid")
                                or ctx_meta.get("effective_uid")
                                or rc.clause_uid
                            ),
                            "effective_uid": (
                                ctx_meta.get("effective_uid")
                                or ctx_meta.get("clause_uid")
                                or rc.clause_uid
                            ),
                            "page": (
                                ctx_meta.get("page")
                                or ctx_meta.get("start_page")
                                or rc.page
                            ),
                            "start_page": (
                                ctx_meta.get("start_page")
                                if ctx_meta.get("start_page") is not None
                                else rc.start_page
                            ),
                            "end_page": (
                                ctx_meta.get("end_page")
                                if ctx_meta.get("end_page") is not None
                                else rc.end_page
                            ),
                            "path_titles": ctx_meta.get("path_titles") or rc.path_titles,
                            "element_ids": ctx_meta.get("element_ids") or rc.element_ids,
                            "bbox_union": ctx_meta.get("bbox_union"),

                            # canonical retrieval provenance
                            "chunk_id": (
                                ctx_meta.get("chunk_id")
                                or c.get("id")
                                or getattr(rc, "chunk_id", None)
                                or rc.element_id
                            ),
                            "chunk_index": (
                                ctx_meta.get("chunk_index")
                                if ctx_meta.get("chunk_index") is not None
                                else getattr(rc, "chunk_index", None)
                            ),

                            # IMPORTANT:
                            # Preserve segment-aware provenance from the original retrieval chunk metadata.
                            # RetrievedChunk currently does not carry full segment metadata,
                            # so using only rc.* would lose segment_id/segment_type in context_trace
                            # and extraction provenance.
                            "segment_id": ctx_meta.get("segment_id"),
                            "segment_type": ctx_meta.get("segment_type"),
                            "segment_title": ctx_meta.get("segment_title"),
                            "segment_order": ctx_meta.get("segment_order"),
                            "is_primary_segment": ctx_meta.get("is_primary_segment"),
                        },
                    }
                )

            context_trace = self._build_context_provenance_trace(
                extraction_contexts,
                retrieved_chunks,
                max_items=5,
            )
            extraction_result = self.extractor.run_with_telemetry(
                doc=doc,
                check=check,
                contexts=extraction_contexts,
                detection=detection,
            )
            structured_data = extraction_result.structured_data
            extraction_telemetry = extraction_result.telemetry
            extraction_anchors = list(extraction_result.anchors)
        except Exception as e:
            logger.exception(
                "CheckExecutor: ExtractionExecutor failed",
                extra={
                    "doc_id": str(getattr(doc, "id", None)),
                    "check_id": getattr(check, "id", None),
                },
            )
            raw_details.setdefault("extraction_error", str(e))
            structured_data = None
            extraction_telemetry = {
                "extraction_mode": None,
                "extraction_llm_invoked": False,
                "error_type": "unexpected_exception",
                "error_message": str(e),
            }

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

        if is_field_extraction:
            presence_signal = (
                getattr(check.extraction, "presence_signal", None)
                if check.extraction is not None
                else None
            )

            if presence_signal is not None:
                gate_verdict = self._classify_presence_signal(
                    structured_data, presence_signal
                )
                raw_details["presence_signal"] = gate_verdict

                if gate_verdict == "present":
                    result = "pass"
                    severity = check.severity_if_pass or "pass"
                elif gate_verdict == "missing":
                    result = "missing_required_clause"
                    severity = check.severity_if_fail or check.severity
                elif gate_verdict == "unclear":
                    result = "unclear"
                    severity = check.severity_if_unclear or check.severity
                else:
                    # "undeclared" or "not_extracted" — fail-safe.
                    result = "unclear"
                    severity = check.severity_if_unclear or check.severity
                    logger.warning(
                        "CheckExecutor: presence_signal gate returned %s; "
                        "falling back to unclear (fail-safe)",
                        gate_verdict,
                        extra={
                            "doc_id": str(getattr(doc, "id", None)),
                            "check_id": getattr(check, "id", None),
                            "gate_field": presence_signal.field,
                        },
                    )
            else:
                has_meaningful_extraction = self._has_meaningful_extraction(
                    structured_data,
                    check,
                )

                if has_meaningful_extraction:
                    result = "pass"
                    severity = check.severity_if_pass or "pass"
                else:
                    result = "unclear"
                    severity = check.severity_if_unclear or check.severity
                    raw_details["extraction_empty"] = True

            logger.debug(
                "CheckExecutor: field_extraction business result mapped",
                extra={
                    "doc_id": str(getattr(doc, "id", None)),
                    "check_id": getattr(check, "id", None),
                    "presence_signal_declared": presence_signal is not None,
                    "presence_signal_verdict": (
                        raw_details.get("presence_signal")
                        if presence_signal is not None
                        else None
                    ),
                    "result": result,
                    "severity": severity,
                },
            )
        elif is_presence_check and found:
            # Presence/compliance check: found=True means the required clause
            # or factual element IS present → pass.
            # This is the inverse of risk-detection logic.
            result = "pass"
            severity = check.severity_if_pass or "pass"
        elif is_presence_check and not found:
            # Presence check: required clause/element NOT found.
            # For deterministic detectors (rules-only) this is a definitive absence.
            # For hybrid/LLM detectors the absence certainty depends on
            # whether the detector completed without degradation.
            _detector_is_deterministic = (
                detector_method == "rules"
                or getattr(check, "detector_type", None) == DetectorType.RULES
            )
            if _detector_is_deterministic or is_presence_not_found:
                result = "missing_required_clause"
                severity = check.severity_if_fail or check.severity
            else:
                result = "unclear"
                severity = check.severity_if_unclear or check.severity
        elif found:
            # Confidence-based fail→unclear downgrade (P0-3b).
            # Если detector нашёл что-то (found=True), но уверенность низкая —
            # это не полноценный fail, это "возможный риск требующий проверки".
            # Порог берём из config: FAIL_CONFIDENCE_UNCLEAR_THRESHOLD (0.50).
            # Это мягче чем CONFIDENCE_MANUAL_REVIEW_THRESHOLD (0.55) —
            # сначала даём шанс остаться fail, если confidence чуть выше нуля,
            # и только при совсем слабом сигнале переводим в unclear.
            # B6.2/R04: per-check override приоритетнее глобального.
            # check.fail_unclear_threshold — параметр бизнес-правила конкретного
            # чека; None = использовать global default.
            _check_thr = getattr(check, "fail_unclear_threshold", None)
            if _check_thr is not None:
                _fail_unclear_thr = float(_check_thr)
            else:
                _fail_unclear_thr = float(
                    getattr(settings, "FAIL_CONFIDENCE_UNCLEAR_THRESHOLD", 0.50)
                )
            if confidence < _fail_unclear_thr:
                result = "unclear"
                severity = check.severity_if_unclear or check.severity
                raw_details.setdefault("low_confidence_fail_flag", True)
                logger.debug(
                    "CheckExecutor: low-confidence positive detection downgraded to unclear",
                    extra={
                        "doc_id": str(getattr(doc, "id", None)),
                        "check_id": getattr(check, "id", None),
                        "confidence": confidence,
                        "threshold": _fail_unclear_thr,
                    },
                )
            else:
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
        if not is_field_extraction and llm_flags["llm_required"] and llm_flags["llm_error_type"]:
            result = "unclear"
            severity = check.severity_if_unclear or check.severity

        # ------------------------------------------------------------------
        # Provenance extraction
        # ------------------------------------------------------------------
        detector_provenance = self._extract_detector_provenance(location, sources)
        retrieval_provenance = self._extract_primary_context_provenance(
            extraction_contexts if "extraction_contexts" in locals() else [],
            retrieved_chunks,
        )
        provenance = self._merge_provenance(
            detector_provenance,
            retrieval_provenance,
        )

        page = provenance["page"]
        clause_uid = provenance["clause_uid"]
        element_id = provenance["element_id"]
        bbox = provenance["bbox"]
        segment_id = provenance["segment_id"]
        segment_type = provenance["segment_type"]
        segment_title = provenance["segment_title"]
        segment_order = provenance["segment_order"]
        is_primary_segment = provenance["is_primary_segment"]
        chunk_id = provenance["chunk_id"]
        chunk_index = provenance["chunk_index"]

        # ------------------------------------------------------------------
        # Metrics
        # ------------------------------------------------------------------
        detector_label = detector_method or "unknown"
        duration = time.time() - start_time
        check_duration_ms = int(duration * 1000)

        raw_details.setdefault("duration_ms", check_duration_ms)

        if isinstance(extraction_telemetry, dict):
            raw_details.setdefault("extraction_mode", extraction_telemetry.get("extraction_mode"))
            raw_details.setdefault(
                "extraction_llm_invoked",
                extraction_telemetry.get("extraction_llm_invoked"),
            )

            # If extraction telemetry contains real LLM runtime metadata,
            # expose aggregate flattened keys for persistence/read-path.
            if extraction_telemetry.get("model"):
                raw_details["model"] = extraction_telemetry.get("model")
            if extraction_telemetry.get("provider"):
                raw_details["provider"] = extraction_telemetry.get("provider")
            if extraction_telemetry.get("tokens_used") is not None:
                raw_details["tokens_used"] = extraction_telemetry.get("tokens_used")
            if extraction_telemetry.get("prompt_tokens") is not None:
                raw_details["prompt_tokens"] = extraction_telemetry.get("prompt_tokens")
            if extraction_telemetry.get("completion_tokens") is not None:
                raw_details["completion_tokens"] = extraction_telemetry.get("completion_tokens")
            if extraction_telemetry.get("llm_attempts") is not None:
                raw_details["llm_attempts"] = extraction_telemetry.get("llm_attempts")
            if extraction_telemetry.get("parse_success") is not None:
                raw_details["parse_success"] = extraction_telemetry.get("parse_success")

            raw_details.setdefault("extraction_telemetry", extraction_telemetry)

        try:
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

        # ── B3.4: assemble anchors (extraction + risk) ────────────────────────
        # Приоритет: extraction anchors (per-field quotes). Если пусто —
        # падаем на риск-путь (evidence-based). Дубли исключены.
        check_anchors: list[CheckAnchor] = list(extraction_anchors)
        if not check_anchors and found:
            check_anchors.extend(
                self._collect_risk_anchors(detection, contexts)
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
            "anchors": [a.model_dump(mode="json") for a in check_anchors],
            "page": page,
            "clause_uid": clause_uid,
            "element_id": element_id,
            "bbox": bbox,
            "segment_id": segment_id,
            "segment_type": segment_type,
            "segment_title": segment_title,
            "segment_order": segment_order,
            "is_primary_segment": is_primary_segment,
            "chunk_id": chunk_id,
            "chunk_index": chunk_index,
            "provenance": provenance,
            "context_trace": context_trace if "context_trace" in locals() else [],
            "llm_error_type": llm_flags["llm_error_type"],
            "llm_error_message": llm_flags["llm_error_message"],
            "llm_attempts": llm_flags["llm_attempts"],
            "rules_llm_decision": llm_flags["rules_llm_decision"],
            "llm_required": llm_flags["llm_required"],
            "llm_degraded": llm_flags["llm_degraded"],
            # ── Semantic enrichment signals ────────────────────────────────────
            # Passed downstream to result_normalizer → quality_flags.
            # False/None/[] when semantic_context was not available.
            "semantic_enrichment_used": (
                semantic_context.enrichment_available
                if semantic_context is not None
                else False
            ),
            "semantic_segment_type": (
                semantic_context.segment_type
                if semantic_context is not None
                else None
            ),
            "semantic_clause_functions": (
                sorted(semantic_context.clause_functions)
                if semantic_context is not None and semantic_context.clause_functions
                else []
            ),
        }


