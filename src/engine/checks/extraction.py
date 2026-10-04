# src/engine/checks/extraction.py

"""
ExtractionExecutor: structured data extraction for a check.

Назначение:
- На основе ExtractionConfig в CheckDefinition извлечь структурированные поля
  из того же контекста, который используется для детекции риска.
- Вернуть payload, пригодный для записи в CheckResult.structured_data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from core.config import settings
from core.logging import get_logger
from engine.extraction_normalization import (
    is_null_like_value,
    normalize_scalar_null_like_value,
    normalize_to_allowed_values,
)
from ..detectors.extraction_llm_detector import ExtractionLLMDetector
from ..llm.client import LLMClient
from ..playbook.models import (
    CheckDefinition,
    ExtractionConfig,
    ExtractionFieldConfig,
    ExtractionFieldType,
)

from core.anchors.models import CheckAnchor, CheckAnchorMethod
from core.anchors.clause_ref_parser import extract_clause_marker_values
from .citation_resolver import resolve_quote_in_source

logger = get_logger(__name__)

LLM_DEFAULT_CONFIDENCE: float = settings.LLM_DEFAULT_CONFIDENCE
_EXTRACTION_RULES_REGEX_CONFIDENCE: float = 0.8

# Structural marker contract — mirrors services/dd_grid_v1_builder.
# Bare "__preamble__" or scope-prefixed "main_contract:__preamble__".
# Internal segment identifiers, not user-facing clause references.
_STRUCTURAL_MARKER_RE = re.compile(r"^__[a-z][a-z0-9_]*__$")
_SCOPED_STRUCTURAL_MARKER_RE = re.compile(r"^[A-Za-z0-9_]+:__[a-z][a-z0-9_]*__$")


def _is_structural_marker_uid(value: Any) -> bool:
    """True if value is a structural marker (bare or scope-prefixed)."""
    if not isinstance(value, str):
        return False
    text = value.strip()
    if _STRUCTURAL_MARKER_RE.match(text):
        return True
    return bool(_SCOPED_STRUCTURAL_MARKER_RE.match(text))
_EXTRACTION_RULES_KEYWORD_CONFIDENCE: float = 0.5

# Минимальный grounding score для использования LLM evidence в extraction.
# Если LLMDetector вернул grounding_score ниже этого порога —
# evidence считается недостаточно заземлённым в реальном тексте.
# В этом случае extraction игнорирует detection["evidence"] и использует
# context-based fallback (чанки из contexts).
# Значение 0.1: хотя бы 10% токенов evidence должно встречаться в чанках.
# Для rules-based detection grounding_score отсутствует — evidence всегда используется.
_EXTRACTION_MIN_GROUNDING_SCORE: float = 0.1

@dataclass(slots=True)
class ExtractionExecutionResult:
    """
    Structured extraction result with optional observability telemetry
    and per-field citation anchors (B3).

    anchors:
        Список CheckAnchor, построенных из per-field location.quote
        финального structured_data. Один anchor на поле.
        Пустой список, если ни одно поле не принесло quote
        или резолвер не смог заземлить цитату (anchor_method=NONE).
    """

    structured_data: dict[str, Any] | None
    telemetry: dict[str, Any] | None = None
    anchors: list[CheckAnchor] = field(default_factory=list)

def _is_null_value(raw: Any) -> bool:
    """
    Backward-compatible wrapper over shared extraction normalization helper.
    """
    return is_null_like_value(raw)


class ExtractionExecutor:
    """
    Исполнитель structured-data извлечения.

    Интерфейс:
      run(doc, check, contexts, detection) -> dict | None

    На вход:
      - doc: ORM Document (для идентификатора).
      - check: CheckDefinition с полем extraction: ExtractionConfig | None.
      - contexts: тот же список чанков, что использовался в CheckExecutor
        (List[Dict] с ключами "id", "text", "metadata").
      - detection: словарь DetectionResult-подобного вида из HybridDetector.

    На выход:
      - dict с извлечёнными полями или None, если extraction отключён или ничего не нашли.
    """

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or LLMClient()
        self.llm_detector = ExtractionLLMDetector(self.llm_client)

    @staticmethod
    def _extract_context_pages(contexts: list[dict[str, Any]]) -> list[int]:
        """
        Extract distinct pages covered by extraction contexts.

        Used for per-field location validation:
        LLM-provided page must belong to one of these pages.
        """
        pages: set[int] = set()

        for ctx in contexts or []:
            meta = ctx.get("metadata") or {}
            for key in ("page", "start_page", "end_page"):
                raw_page = meta.get(key)
                if isinstance(raw_page, int) and not isinstance(raw_page, bool) and raw_page > 0:
                    pages.add(raw_page)

        return sorted(pages)

    @staticmethod
    def _build_location_fallback(
        base_location: dict[str, Any] | None,
        reason: str,
    ) -> dict[str, Any]:
        """
        Build honest field-level location fallback referencing check-level evidence.
        """
        check_page: int | None = None
        check_clause_uid: str | None = None

        if isinstance(base_location, dict):
            raw_page = base_location.get("page")
            if not isinstance(raw_page, int):
                raw_page = base_location.get("start_page")
            if isinstance(raw_page, int) and not isinstance(raw_page, bool) and raw_page > 0:
                check_page = raw_page

            raw_clause_uid = base_location.get("clause_uid")
            if raw_clause_uid is not None and str(raw_clause_uid).strip():
                check_clause_uid = str(raw_clause_uid).strip()

        return {
            "reason": reason,
            "check_clause_uid": check_clause_uid,
            "check_page": check_page,
        }

    @classmethod
    def _build_location_fallback_or_reason_only(
        cls,
        base_location: dict[str, Any] | None,
        reason: str,
    ) -> dict[str, Any]:
        """
        Build location fallback but drop structural-marker base_location.

        If base_location.clause_uid is a structural marker
        (__preamble__, scope:__header__), its page and clause_uid are not
        user-facing anchors. Return reason-only fallback to avoid misleading
        "п. __preamble__, стр. N" references in the UI.

        Valid base_location (e.g. main_contract:12.1) is preserved.
        """
        if isinstance(base_location, dict) and _is_structural_marker_uid(
            base_location.get("clause_uid")
        ):
            return {"reason": reason}
        return cls._build_location_fallback(base_location, reason)

    @classmethod
    def _resolve_field_location_bundle(
        cls,
        *,
        location: Any,
        location_fallback: Any,
        base_location: dict[str, Any] | None,
        default_reason: str = "Точная ссылка не определена, см. общий evidence",
    ) -> tuple[Any, dict[str, Any] | None]:
        """
        Resolve exact location vs honest fallback for a field.

        If exact location exists -> fallback is dropped.
        If exact location is absent -> fallback is built from check-level evidence.
        """
        if location is not None:
            return location, None

        fallback_reason = default_reason
        if isinstance(location_fallback, dict):
            raw_reason = location_fallback.get("reason")
            if raw_reason and str(raw_reason).strip():
                fallback_reason = str(raw_reason).strip()

        return None, cls._build_location_fallback_or_reason_only(
            base_location, fallback_reason
        )


    @staticmethod
    def _extract_numeric_core(clause_ref: str) -> list[str]:
        """
        B7.9.2: backward-compatible wrapper over the universal clause_ref
        parser (core.anchors.clause_ref_parser).

        Previously this method used a numeric-only regex
        (r"\\d+(?:\\.\\d+)*"), which:
          - did not recognize letter markers ("п. S", "Приложение А");
          - matched page references ("стр. 3") as if they were clause
            numbers, so "пункт S, ..., стр. 1" yielded ["1"] instead of
            ["S"].

        The universal parser separates clause markers from page refs and
        understands numeric, latin, cyrillic, mixed, and appendix markers,
        including comma/semicolon-separated lists after a single prefix.
        The method name is preserved for backward compatibility.
        """
        return extract_clause_marker_values(clause_ref)


    @staticmethod
    def _apply_anchor_page_to_field_location(
        payload: dict[str, Any],
        anchor: CheckAnchor,
    ) -> None:
        """
        B3.5: обновить per-field location.page точной страницей из anchor.

        UI читает structured_data[field]['location']['page'], а check-level
        anchor идёт в check_results.page (уже правильный). Раньше эти
        значения расходились: anchor.page = точная страница из element_spans
        через Priority 0, а per-field location.page оставалось LLM-значением
        = start_page чанка.

        Обновляем только location.page. Другие поля (quote, clause_ref,
        location_confidence) не трогаем — это независимые атрибуты
        LLM-ответа.
        """
        if not isinstance(payload, dict):
            return
        loc = payload.get("location")
        if not isinstance(loc, dict):
            return
        page = getattr(anchor, "page", None)
        if not isinstance(page, int) or isinstance(page, bool) or page < 1:
            return
        if loc.get("page") == page:
            return
        loc["page"] = page

    @staticmethod
    def _resolve_field_anchor(
        *,
        quote: str,
        source_text: str,
        fallback_clause_uid: str | None,
        fallback_page: int | None,
        chunk_map: list[tuple[int, int, dict[str, Any], Any]] | None = None,
        field_page: int | None = None,
        field_clause_ref: str | None = None,
    ) -> CheckAnchor | None:
        """
        Построить CheckAnchor из per-field цитаты (B3).

        Вход:
            quote              — дословная цитата поля (уже нормализованная).
            source_text        — base_text, по которому делался extraction.
            fallback_clause_uid — check-level clause_uid (для clause_only ступени).
            fallback_page      — check-level page (для page_only ступени).

        Возврат:
            CheckAnchor | None. None, если:
            - quote пустая;
            - source_text пустой;
            - резолвер вернул anchor_method=NONE (нет даже page/clause fallback).

        Никогда не бросает: resolve_quote_in_source — pure function,
        возвращает CheckAnchor(method=NONE) в худшем случае.
        """
        if not quote or not quote.strip():
            return None
        if not source_text:
            return None

        anchor = resolve_quote_in_source(
            quote=quote,
            source_text=source_text,
            layout_elements=[],
            fallback_clause_uid=fallback_clause_uid,
            fallback_page=fallback_page,
        )

        if anchor.anchor_method == CheckAnchorMethod.NONE:
            return None

        # B6.2/R10 v4 — приоритет источников provenance:
        #   1) field_location (LLM + R21) — самый точный, содержит page
        #      и clause_ref конкретного поля;
        #   2) chunk_map (owner-chunk по span) — точный на уровне чанка;
        #   3) fallback (top-1 base_location) — уже применён внутри
        #      resolve_quote_in_source, дополнительных действий не требует.
        updates: dict[str, Any] = {}

        # ── Приоритет 0 (B3.5): element_spans через owner-chunk ─────────
        # anchor.span_start — в координатах склеенного source_text
        # (chunk_map даёт [start, end] каждого context'а в этом тексте).
        # element_spans живут в координатах chunk["text"] своего context'а.
        # Ищем owner-chunk по span_start, сдвигаем span в локальные
        # координаты чанка, берём страницу по max-overlap.
        if (
            chunk_map
            and anchor.span_start is not None
            and anchor.span_end is not None
        ):
            _owner_ctx = None
            _owner_start = None
            for _entry in chunk_map:
                if not isinstance(_entry, (list, tuple)) or len(_entry) < 3:
                    continue
                _s_ctx = _entry[0]
                _e_ctx = _entry[1]
                _ctx = _entry[2]
                if not isinstance(_s_ctx, int) or not isinstance(_e_ctx, int):
                    continue
                if _s_ctx <= anchor.span_start < _e_ctx:
                    _owner_ctx = _ctx
                    _owner_start = _s_ctx
                    break
            if _owner_ctx is not None and _owner_start is not None:
                _meta = _owner_ctx.get("metadata") or {}
                _spans = _meta.get("element_spans")
                if isinstance(_spans, list) and _spans:
                    _local_start = anchor.span_start - _owner_start
                    _local_end = anchor.span_end - _owner_start
                    _best_page: int | None = None
                    _best_overlap = 0
                    for _sp in _spans:
                        if not isinstance(_sp, (list, tuple)) or len(_sp) < 4:
                            continue
                        _pg = _sp[1]
                        _s = _sp[2]
                        _e = _sp[3]
                        if (
                            not isinstance(_pg, int)
                            or isinstance(_pg, bool)
                            or _pg < 1
                            or not isinstance(_s, int)
                            or not isinstance(_e, int)
                        ):
                            continue
                        _ov = max(0, min(_e, _local_end) - max(_s, _local_start))
                        if _ov > _best_overlap:
                            _best_overlap = _ov
                            _best_page = _pg
                    if _best_page is not None:
                        updates["page"] = _best_page

        # ── Приоритет 1: field_location (fallback) ───────────────────────
        # Применяется только если element_spans не дали точной страницы.
        if (
            "page" not in updates
            and isinstance(field_page, int)
            and not isinstance(field_page, bool)
            and field_page >= 1
        ):
            updates["page"] = field_page

        if field_clause_ref and chunk_map:
            cores = ExtractionExecutor._extract_numeric_core(field_clause_ref)
            for core in cores:
                found = False
                for entry in chunk_map:
                    _s, _e, _ctx, _rc = entry
                    meta = _ctx.get("metadata") or {}
                    raw_uid = meta.get("raw_uid")
                    if raw_uid is None:
                        eff = meta.get("effective_uid") or getattr(_rc, "clause_uid", None)
                        raw_uid = eff.split(":")[-1] if isinstance(eff, str) and ":" in eff else eff
                    if raw_uid is not None and str(raw_uid) == core:
                        eff_uid = meta.get("effective_uid") or getattr(_rc, "clause_uid", None)
                        if eff_uid:
                            updates["clause_uid"] = str(eff_uid).strip()
                        if "page" not in updates:
                            fp = (
                                meta.get("page")
                                or meta.get("start_page")
                                or getattr(_rc, "page", None)
                            )
                            if isinstance(fp, int) and not isinstance(fp, bool) and fp >= 1:
                                updates["page"] = fp
                        found = True
                        break
                if found:
                    break

        # ── Приоритет 1b: синтез scope из родительского chunk (B6.2.1) ────
        # Случай: LLM дала clause_ref="п. 8.1.2", но точного sub-chunk'а
        # main_contract:8.1.2 в chunk_map нет. Есть родитель main_contract:8
        # (raw_uid="8"). Синтезируем: {scope родителя}:{numeric core}.
        # Универсально: работает для любого scope (main_contract, appendix_1)
        # и любого уровня вложенности (8 → 8.1.2, 8.1 → 8.1.2.3).
        # Срабатывает только если core является расширением raw_uid ("8.1.2"
        # начинается с "8.") — защита от ложных совпадений ("8" vs "9.1.2").
        if "clause_uid" not in updates and field_clause_ref and chunk_map:
            cores_1b = ExtractionExecutor._extract_numeric_core(field_clause_ref)
            for core_1b in cores_1b:
                for entry in chunk_map:
                    _s, _e, _ctx, _rc = entry
                    meta = _ctx.get("metadata") or {}
                    raw_uid = meta.get("raw_uid")
                    eff_uid = (
                        meta.get("effective_uid")
                        or getattr(_rc, "clause_uid", None)
                    )
                    if not raw_uid or not eff_uid:
                        continue
                    if not str(core_1b).startswith(str(raw_uid) + "."):
                        continue
                    eff_uid_str = str(eff_uid)
                    if ":" not in eff_uid_str:
                        continue
                    scope = eff_uid_str.rsplit(":", 1)[0]
                    if not scope:
                        continue
                    updates["clause_uid"] = f"{scope}:{core_1b}"
                    if "page" not in updates:
                        fp = (
                            meta.get("page")
                            or meta.get("start_page")
                            or getattr(_rc, "page", None)
                        )
                        if isinstance(fp, int) and not isinstance(fp, bool) and fp >= 1:
                            updates["page"] = fp
                    break
                if "clause_uid" in updates:
                    break

        # ── Приоритет 2: chunk_map (owner-chunk по span) ─────────────────
        if not updates and chunk_map is not None and anchor.span_start is not None and anchor.span_end is not None:
            mid = (anchor.span_start + anchor.span_end) // 2
            owner_entry = None
            for entry in chunk_map:
                _s, _e, _ctx, _rc = entry
                if _s <= mid < _e:
                    owner_entry = entry
                    break
            if owner_entry is None:
                for entry in chunk_map:
                    _s, _e, _ctx, _rc = entry
                    if _s <= anchor.span_start < _e:
                        owner_entry = entry
                        break
            if owner_entry is not None:
                _s, _e, owner_ctx, owner_rc = owner_entry
                meta = owner_ctx.get("metadata") or {}
                new_clause_uid = (
                    meta.get("effective_uid")
                    or meta.get("clause_uid")
                    or getattr(owner_rc, "clause_uid", None)
                )
                new_page = (
                    meta.get("page")
                    or meta.get("start_page")
                    or getattr(owner_rc, "page", None)
                )
                if new_clause_uid and str(new_clause_uid).strip():
                    updates["clause_uid"] = str(new_clause_uid).strip()
                if isinstance(new_page, int) and not isinstance(new_page, bool) and new_page >= 1:
                    updates["page"] = new_page

        if not updates:
            return anchor

        return anchor.model_copy(update=updates)


    def run(
        self,
        doc: Any,
        check: CheckDefinition,
        contexts: list[dict[str, Any]],
        detection: dict[str, Any],
    ) -> dict[str, Any] | None:
        """
        Backward-compatible wrapper over run_with_telemetry().
        """
        return self.run_with_telemetry(
            doc=doc,
            check=check,
            contexts=contexts,
            detection=detection,
        ).structured_data

    def run_with_telemetry(
        self,
        doc: Any,
        check: CheckDefinition,
        contexts: list[dict[str, Any]],
        detection: dict[str, Any],
    ) -> ExtractionExecutionResult:
        extraction_cfg: ExtractionConfig | None = getattr(check, "extraction", None)
        if not extraction_cfg or not extraction_cfg.enabled:
            return ExtractionExecutionResult(structured_data=None, telemetry=None)

        mode = getattr(extraction_cfg, "mode", None)
        logger.debug(
            "ExtractionExecutor.run started",
            check_id=check.id,
            doc_id=str(getattr(doc, "id", None)),
            mode=str(mode),
        )

        # Базовый текст для извлечения: evidence из detection, а при необходимости — весь контекст.
        base_text, chunk_map = self._build_extraction_text(detection, contexts)
        if not base_text:
            return ExtractionExecutionResult(structured_data=None, telemetry=None)

        # Локация риска из HybridDetector: page / clause_uid / element_id / ...
        # Это check-level fallback provenance, а НЕ точная per-field location.
        # Если LLM не вернул валидную location для конкретного поля,
        # мы сохраняем location_fallback со ссылкой на общий evidence.
        raw_location = detection.get("location") or None
        base_location: dict[str, Any] | None = None
        if isinstance(raw_location, dict):
            base_location = {
                "page": raw_location.get("page"),
                "clause_uid": raw_location.get("clause_uid"),
                "element_id": raw_location.get("element_id"),
                "start_page": raw_location.get("start_page"),
                "end_page": raw_location.get("end_page"),
                "path_titles": raw_location.get("path_titles"),
            }

        structured: dict[str, dict[str, Any]] = {}
        anchors: list[CheckAnchor] = []
        context_pages = self._extract_context_pages(contexts)

        # 1. RULES часть (работает для mode == rules и для hybrid/llm как baseline)
        for field_cfg in extraction_cfg.fields or []:
            field_result = self._extract_field(field_cfg, base_text)
            if field_result is not None:
                # Rules-based extraction usually does not know precise per-field anchor.
                # Preserve honest semantics: exact location stays None,
                # check-level evidence is exposed via location_fallback.
                exact_location, location_fallback = self._resolve_field_location_bundle(
                    location=field_result.get("location"),
                    location_fallback=field_result.get("location_fallback"),
                    base_location=base_location,
                )
                field_result["location"] = exact_location
                if location_fallback is not None:
                    field_result["location_fallback"] = location_fallback
                structured[field_cfg.name] = field_result

        # 2. LLM / HYBRID часть
        # Если mode == "llm" или "hybrid" и LLM доступен, подтянем значения из LLM.
        llm_telemetry: dict[str, Any] | None = None
        if mode in {"llm", "hybrid"} and self.llm_client.is_available():
            try:
                llm_result = self.llm_detector.extract_with_telemetry(
                    check,
                    base_text,
                    context_pages=context_pages,
                )

                logger.debug(
                    "ExtractionExecutor: raw LLM extraction fields",
                    extra={
                        "check_id": check.id,
                        "llm_fields": llm_result.fields,
                        "llm_telemetry": llm_result.telemetry,
                    },
                )

                llm_fields = llm_result.fields
                llm_telemetry = llm_result.telemetry
            except Exception as e:
                logger.warning("LLM extraction failed", error=str(e))
                llm_fields = {}
                llm_telemetry = {
                    "provider": None,
                    "model": None,
                    "tokens_used": None,
                    "prompt_tokens": None,
                    "completion_tokens": None,
                    "duration_ms": None,
                    "llm_attempts": None,
                    "parse_success": None,
                    "error_type": "unexpected_exception",
                    "error_message": str(e),
                }

            if llm_fields:
                for field_cfg in extraction_cfg.fields or []:
                    name = field_cfg.name
                    llm_payload = llm_fields.get(name)
                    if not llm_payload:
                        continue

                    value_raw = llm_payload.get("value")

                    # Null-like значения не выбрасываем сразу:
                    # если allowed_values содержит 'not_found', превращаем в него.
                    if _is_null_value(value_raw):
                        normalized_null = self._validate_allowed_values(field_cfg, None)
                        if normalized_null is None:
                            logger.debug(
                                "LLM returned null-like value for field, skipping",
                                field_name=name,
                                value_raw=str(value_raw),
                                check_id=check.id,
                            )
                            continue
                        value_raw = normalized_null

                    conf_raw = llm_payload.get("confidence", LLM_DEFAULT_CONFIDENCE)
                    try:
                        confidence_llm = float(conf_raw)
                    except (TypeError, ValueError):
                        confidence_llm = LLM_DEFAULT_CONFIDENCE

                    # B6.2/R23: флаг truncated JSON (salvage Pass 2).
                    # Пробрасывается из _normalize_fields в structured_data.<field>._truncated,
                    # чтобы downstream (DD Grid / UI) мог показать badge "частичные данные".
                    raw_truncated = bool(llm_payload.get("_truncated", False))

                    raw_field_location = llm_payload.get("location")
                    raw_field_location_fallback = llm_payload.get("location_fallback")

                    exact_location, location_fallback = self._resolve_field_location_bundle(
                        location=raw_field_location,
                        location_fallback=raw_field_location_fallback,
                        base_location=base_location,
                    )

                    # Приводим к типу поля.
                    value_cast = self._cast_value(field_cfg, value_raw)
                    value_cast = self._validate_allowed_values(field_cfg, value_cast)
                    if value_cast is None:
                        logger.debug(
                            "LLM value discarded after allowed_values check",
                            field_name=name,
                            raw=str(value_raw),
                            check_id=check.id,
                        )
                        continue

                    replacement_payload = {
                        "value": value_cast,
                        "unit": field_cfg.unit,
                        "source": "llm",
                        "confidence": confidence_llm,
                        "found": True,
                        "location": exact_location,
                    }
                    if location_fallback is not None:
                        replacement_payload["location_fallback"] = location_fallback
                    if raw_truncated:
                        replacement_payload["_truncated"] = True

                    if name not in structured:
                        structured[name] = replacement_payload
                    else:
                        # оба дали значение — если LLM увереннее, заменим
                        if confidence_llm > structured[name].get("confidence", 0.0):
                            structured[name] = replacement_payload

        # 3. Нормализация: гарантируем запись для каждого поля из extraction_cfg
        for field_cfg in extraction_cfg.fields or []:
            name = field_cfg.name

            if name in structured:
                field = structured[name]
                field.setdefault("unit", field_cfg.unit)
                field.setdefault("source", field.get("source", "rules"))
                try:
                    field["confidence"] = float(field.get("confidence", 0.0))
                except (TypeError, ValueError):
                    field["confidence"] = 0.0
                field.setdefault("found", True)

                # Honest per-field location semantics:
                # - exact location in "location"
                # - check-level fallback in "location_fallback"
                field.setdefault("location", None)
                if field.get("location") is None and field.get("found"):
                    field.setdefault(
                        "location_fallback",
                        self._build_location_fallback_or_reason_only(
                            base_location,
                            "Точная ссылка не определена, см. общий evidence",
                        ),
                    )
                else:
                    field.pop("location_fallback", None)

                field.setdefault(
                    "qc",
                    {
                        "status": "pending",
                        "by": None,
                        "comment": None,
                        "at": None,
                    },
                )
                continue

            # поле вообще не найдено ни rules, ни LLM — создаём "пустую" запись
            structured[name] = {
                "value": None,
                "unit": field_cfg.unit,
                "source": "none",
                "confidence": 0.0,
                "found": False,
                "location": None,
                "location_fallback": None,
                "qc": {
                    "status": "pending",
                    "by": None,
                    "comment": None,
                    "at": None,
                },
            }


        # 3b. Build per-field anchors from final structured_data (B3.1c).
        # Anchors collected AFTER rules/LLM merge settled — one anchor per field,
        # no duplicates, no ordering dependency between branches.

        for field_cfg in extraction_cfg.fields or []:
            payload = structured.get(field_cfg.name)
            if not payload:
                continue
            location = payload.get("location")
            if not isinstance(location, dict):
                continue
            quote = location.get("quote")
            if not isinstance(quote, str) or not quote.strip():
                continue

            # B6.2/R10 v4: per-field location от LLM (валидирован R21) —
            # приоритетный источник page/clause_ref для anchor.
            field_page = location.get("page")
            if not (
                isinstance(field_page, int)
                and not isinstance(field_page, bool)
                and field_page >= 1
            ):
                field_page = None
            field_clause_ref = location.get("clause_ref")
            if not (isinstance(field_clause_ref, str) and field_clause_ref.strip()):
                field_clause_ref = None

            field_anchor = self._resolve_field_anchor(
                quote=quote,
                source_text=base_text,
                fallback_clause_uid=(
                    base_location.get("clause_uid")
                    if isinstance(base_location, dict)
                    else None
                ),
                fallback_page=(
                    base_location.get("page")
                    if isinstance(base_location, dict)
                    else None
                ),
                chunk_map=chunk_map,
                field_page=field_page,
                field_clause_ref=field_clause_ref,
            )
            if field_anchor is not None:
                anchors.append(field_anchor)
                # B3.5: обновить per-field location.page значением anchor.
                # Только для точных методов (EXACT_SPAN / FUZZY_SPAN) —
                # CLAUSE_ONLY / PAGE_ONLY не несут точной страницы,
                # перезапись ими испортит LLM-значение.
                if field_anchor.anchor_method in (
                    CheckAnchorMethod.EXACT_SPAN,
                    CheckAnchorMethod.FUZZY_SPAN,
                ):
                    self._apply_anchor_page_to_field_location(
                        payload, field_anchor,
                    )


        # 4. Дополнительная валидация required-полей после merge rules + LLM.
        for field_cfg in extraction_cfg.fields or []:
            if not getattr(field_cfg, "required", False):
                continue

            name = field_cfg.name
            payload = structured.get(name)
            if not payload:
                logger.warning(
                    "ExtractionExecutor: required field missing in structured payload",
                    field_name=name,
                    check_id=check.id,
                )
                continue

            value = payload.get("value")
            if value is None or (isinstance(value, str) and not value.strip()):
                logger.warning(
                    "ExtractionExecutor: required field has empty value",
                    field_name=name,
                    check_id=check.id,
                    source=payload.get("source"),
                )

        if not structured:
            extraction_mode = str(mode) if mode is not None else None
            llm_invoked = bool(
                isinstance(llm_telemetry, dict)
                and llm_telemetry.get("llm_invoked") is True
            )
            telemetry = {
                "extraction_mode": extraction_mode,
                "extraction_llm_invoked": llm_invoked,
                **(llm_telemetry or {}),
            }
            return ExtractionExecutionResult(
                structured_data=None,
                telemetry=telemetry,
                anchors=anchors,
            )

        extraction_mode = str(mode) if mode is not None else None
        telemetry: dict[str, Any] | None = None

        llm_invoked = bool(
            isinstance(llm_telemetry, dict)
            and llm_telemetry.get("llm_invoked") is True
        )

        if mode in {"llm", "hybrid"}:
            telemetry = {
                "extraction_mode": extraction_mode,
                "extraction_llm_invoked": llm_invoked,
                **(llm_telemetry or {}),
            }
        else:
            telemetry = {
                "extraction_mode": extraction_mode,
                "extraction_llm_invoked": False,
            }

        return ExtractionExecutionResult(
            structured_data=structured or None,
            telemetry=telemetry,
            anchors=anchors,
        )

    def _build_extraction_text(
        self,
        detection: dict[str, Any],
        contexts: list[dict[str, Any]],
    ) -> tuple[str, list[tuple[int, int, dict[str, Any]]] | None]:
        """
        Сформировать текст, по которому будем делать extraction.

        Приоритет:
          1) detection["evidence"], если есть И grounding_score достаточный.
             Grounding score читается из detection["raw"]["llm_details"]["grounding_score"],
             куда его пишет LLMDetector._build_result().
             Если grounding_score отсутствует (rules-detection) — evidence надёжен
             по определению (rules детерминированы, не галлюцинируют).
             Если grounding_score есть, но ниже _EXTRACTION_MIN_GROUNDING_SCORE —
             evidence игнорируется: extraction на выдуманном тексте хуже чем на
             реальных чанках.
          2) иначе текст из наиболее релевантных чанков из contexts.
             Сначала пробуем сузить список по location (element_id / clause_uid / page),
             если это не получилось — используем весь контекст.
        """
        # 1. Evidence с grounding-проверкой.
        evidence = detection.get("evidence") or ""
        if isinstance(evidence, str) and evidence.strip():
            # Читаем grounding_score из raw.llm_details если он там есть.
            # LLMDetector._build_result() пишет его в details,
            # HybridDetector._flatten_llm_result() прокидывает через raw["llm_details"].
            raw = detection.get("raw") or {}
            llm_details = raw.get("llm_details") or {}
            grounding_score: float | None = (
                llm_details.get("grounding_score")
                if isinstance(llm_details, dict)
                else None
            )

            # Логика выбора:
            # - grounding_score отсутствует → detection от rules или field_extraction_only
            #   → evidence надёжен, используем его
            # - grounding_score >= порога → evidence достаточно заземлён → используем
            # - grounding_score < порога → evidence слабо заземлён → игнорируем,
            #   идём к context-based fallback ниже
            if grounding_score is None or grounding_score >= _EXTRACTION_MIN_GROUNDING_SCORE:
                # B6.2/R10: chunk_map от executor.py (_build_limited_context).
                # Передаётся в detection["_evidence_chunk_map"] для field_extraction.
                # None для risk-detection (нет ключа) или summary-компрессии.
                _ev_cmap = detection.get("_evidence_chunk_map")
                if not isinstance(_ev_cmap, list):
                    _ev_cmap = None
                return evidence, _ev_cmap
            else:
                logger.debug(
                    "ExtractionExecutor._build_extraction_text: "
                    "skipping ungrounded LLM evidence, using context fallback",
                    grounding_score=grounding_score,
                    threshold=_EXTRACTION_MIN_GROUNDING_SCORE,
                    evidence_preview=evidence[:100],
                )
                # Не возвращаем — падаем ниже на context-based логику

        if not contexts:
            return "", None

        # 2. Пытаемся сузить контекст по location
        raw_location = detection.get("location") or {}
        loc_element_id = None
        loc_clause_uid = None
        loc_page = None
        loc_start_page = None
        loc_end_page = None
        loc_element_ids: list[str] = []

        if isinstance(raw_location, dict):
            loc_element_id = raw_location.get("element_id")
            loc_clause_uid = raw_location.get("clause_uid")
            loc_page = raw_location.get("page")
            loc_start_page = raw_location.get("start_page")
            loc_end_page = raw_location.get("end_page")
            loc_element_ids = raw_location.get("element_ids") or []
            if not isinstance(loc_element_ids, list):
                loc_element_ids = []

        # Нормализуем ссылки на element_id'ы в строковый список
        loc_element_ids_str = {str(eid) for eid in loc_element_ids if eid is not None}
        if loc_element_id is not None:
            loc_element_ids_str.add(str(loc_element_id))

        # 2.1. Фильтрация по element_id / element_ids
        # Если location явно ссылается на конкретный элемент, пытаемся взять
        # только те чанки, которые содержат этот element_id.
        filtered_by_element: list[dict[str, Any]] = []
        if loc_element_ids_str:
            for c in contexts:
                meta = c.get("metadata") or {}
                ctx_element_ids = meta.get("element_ids") or []
                if not isinstance(ctx_element_ids, list):
                    ctx_element_ids = []
                ctx_element_ids_str = {str(eid) for eid in ctx_element_ids if eid is not None}

                # Также можно сравнить сам id чанка как fallback.
                chunk_id = c.get("id")
                if chunk_id is not None:
                    ctx_element_ids_str.add(str(chunk_id))

                if loc_element_ids_str & ctx_element_ids_str:
                    filtered_by_element.append(c)

        # 2.2. Фильтрация по clause_uid, если по element_id ничего не нашли
        filtered_by_clause: list[dict[str, Any]] = []
        if not filtered_by_element and loc_clause_uid:
            loc_clause_uid_str = str(loc_clause_uid)
            for c in contexts:
                meta = c.get("metadata") or {}
                # Читаем effective_uid (canonical Sprint 3+) или clause_uid (legacy).
                # loc_clause_uid после наших правок executor.py содержит effective_uid.
                ctx_clause_uid = meta.get("effective_uid") or meta.get("clause_uid")
                if ctx_clause_uid is not None and str(ctx_clause_uid) == loc_clause_uid_str:
                    filtered_by_clause.append(c)

        # 2.3. Фильтрация по страницам, если ни element_id, ни clause_uid не помогли
        filtered_by_page: list[dict[str, Any]] = []
        if (
            not filtered_by_element
            and not filtered_by_clause
            and (loc_page is not None or loc_start_page is not None or loc_end_page is not None)
        ):
            try:
                sp = int(loc_start_page) if loc_start_page is not None else int(loc_page)
            except (TypeError, ValueError):
                sp = None
            try:
                ep = int(loc_end_page) if loc_end_page is not None else int(loc_page)
            except (TypeError, ValueError):
                ep = None

            if sp is not None and ep is not None:
                for c in contexts:
                    meta = c.get("metadata") or {}
                    ctx_start = meta.get("start_page") or meta.get("page")
                    ctx_end = meta.get("end_page") or meta.get("page")
                    try:
                        ctx_start_i = int(ctx_start) if ctx_start is not None else None
                        ctx_end_i = int(ctx_end) if ctx_end is not None else None
                    except (TypeError, ValueError):
                        ctx_start_i = ctx_end_i = None

                    if ctx_start_i is None and ctx_end_i is None:
                        continue

                    # Пересечение диапазонов страниц
                    if ctx_start_i is None:
                        ctx_start_i = ctx_end_i
                    if ctx_end_i is None:
                        ctx_end_i = ctx_start_i

                    if ctx_end_i >= sp and ctx_start_i <= ep:
                        filtered_by_page.append(c)

        # Выбираем итоговый список чанков для extraction
        if filtered_by_element:
            relevant_contexts = filtered_by_element
        elif filtered_by_clause:
            relevant_contexts = filtered_by_clause
        elif filtered_by_page:
            relevant_contexts = filtered_by_page
        else:
            # Fallback: если сузить не удалось, используем весь контекст, как раньше.
            relevant_contexts = contexts

        # 3. Склеиваем текст только из релевантных чанков.
        # B6.2/R10: одновременно строим chunk_map — [(start, end, context_dict), ...]
        # для per-field provenance (анкор поля ссылается на chunk, где
        # цитата реально найдена).
        parts: list[str] = []
        chunk_map: list[tuple[int, int, dict[str, Any], Any]] = []
        cursor = 0
        separator = "\n\n"
        for c in relevant_contexts:
            text = c.get("text") or ""
            if not text:
                continue
            if parts:
                cursor += len(separator)
            start = cursor
            parts.append(text)
            cursor += len(text)
            # rc=None: contexts-ветвь не имеет доступа к retrieved_chunks;
            # metadata context содержит effective_uid/page/raw_uid — их достаточно.
            chunk_map.append((start, cursor, c, None))

        joined = separator.join(parts)
        stripped = joined.strip()
        if not stripped:
            return "", chunk_map

        # strip() сдвигает offsets — корректируем chunk_map.
        lead = len(joined) - len(joined.lstrip())
        if lead:
            new_len = len(stripped)
            shifted: list[tuple[int, int, dict[str, Any]]] = []
            for (s, e, c, _rc) in chunk_map:
                s2, e2 = s - lead, e - lead
                if e2 <= 0 or s2 >= new_len:
                    continue
                shifted.append((max(0, s2), min(new_len, e2), c))
            chunk_map = shifted

        return stripped, chunk_map

    def _extract_field(
        self,
        field_cfg: ExtractionFieldConfig,
        text: str,
    ) -> dict[str, Any] | None:
        for pattern in field_cfg.regex_patterns or []:
            try:
                m = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
            except re.error as e:
                logger.warning(
                    "Invalid regex pattern in ExtractionFieldConfig",
                    field_name=field_cfg.name,
                    pattern=pattern,
                    error=str(e),
                )
                continue

            if m:
                raw_value = m.group(1) if m.groups() else m.group(0)

                if _is_null_value(raw_value):
                    continue

                # ↓ ВСЁ внутри if m: — правильный отступ
                value = self._cast_value(field_cfg, raw_value)
                value = self._validate_allowed_values(field_cfg, value)
                if value is None:
                    continue  # попробуем следующий паттерн
                return {
                    "value": value,
                    "unit": field_cfg.unit,
                    "source": "rules",
                    "confidence": _EXTRACTION_RULES_REGEX_CONFIDENCE,
                    "found": True,
                }

        # keyword_hints — без изменений, там всё корректно
        if field_cfg.keyword_hints:
            lowered = text.lower()
            hits = [kw for kw in field_cfg.keyword_hints if kw.lower() in lowered]
            if hits:
                if field_cfg.type == ExtractionFieldType.BOOLEAN:
                    value: Any = True
                else:
                    value = ", ".join(hits)

                if _is_null_value(value):
                    return None
                value = self._validate_allowed_values(field_cfg, value)
                if value is None:
                    return None
                return {
                    "value": value,
                    "unit": field_cfg.unit,
                    "source": "rules",
                    "confidence": _EXTRACTION_RULES_KEYWORD_CONFIDENCE,
                    "found": True,
                }

        return None

    def _cast_value(self, field_cfg: ExtractionFieldConfig, raw_value: Any) -> Any:
        """
        Привести найденное значение к типу из ExtractionFieldConfig.

        Поддержка:
          - NUMBER: к float / int при возможности.
          - BOOLEAN: по простым паттернам ("yes/no", "да/нет", "true/false").
          - EVIDENCE_LIST: сохранить как есть.
          - STRING / CLAUSE_REF: как есть.
        """
        if field_cfg.type == ExtractionFieldType.EVIDENCE_LIST:
            return raw_value

        raw_value = normalize_scalar_null_like_value(raw_value)
        if raw_value is None:
            return None

        field_type = field_cfg.type

        if field_type == ExtractionFieldType.NUMBER:
            cleaned = str(raw_value).replace(" ", "").replace(",", ".")
            try:
                num = float(cleaned)
                if num.is_integer():
                    return int(num)
                return num
            except ValueError:
                return raw_value

        if field_type == ExtractionFieldType.BOOLEAN:
            v = str(raw_value).strip().lower()
            true_vals = {"yes", "true", "1", "да", "верно"}
            false_vals = {"no", "false", "0", "нет", "неверно"}
            if v in true_vals:
                return True
            if v in false_vals:
                return False
            return raw_value

        return raw_value

    def _validate_allowed_values(
        self,
        field_cfg: ExtractionFieldConfig,
        value: Any,
    ) -> Any | None:
        """
        Проверить значение против allowed_values из конфига поля.

        Поведение:
        - если allowed_values не задан — возвращаем value как есть;
        - null-like -> 'not_found', если он разрешён, иначе None;
        - case-insensitive exact match -> канонический вариант из YAML;
        - иначе None c warning.
        """
        allowed: list[Any] = getattr(field_cfg, "allowed_values", None) or []
        if not allowed:
            return value

        canonical_allowed = [getattr(item, "value", item) for item in allowed]
        normalized = normalize_to_allowed_values(value, canonical_allowed)
        if normalized is not None:
            return normalized

        if is_null_like_value(value):
            return None

        logger.warning(
            "ExtractionExecutor: value not in allowed_values — discarding",
            field_name=field_cfg.name,
            value=str(value),
            allowed_values=[str(a) for a in allowed],
            check_id=getattr(field_cfg, "check_id", getattr(field_cfg, "check_id", "unknown")),
        )
        return None
    
    