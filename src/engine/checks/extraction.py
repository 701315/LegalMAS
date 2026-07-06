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

logger = get_logger(__name__)

LLM_DEFAULT_CONFIDENCE: float = settings.LLM_DEFAULT_CONFIDENCE
_EXTRACTION_RULES_REGEX_CONFIDENCE: float = 0.8
_EXTRACTION_RULES_KEYWORD_CONFIDENCE: float = 0.5

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

        return None, cls._build_location_fallback(base_location, fallback_reason)

    def run(
        self,
        doc: Any,
        check: CheckDefinition,
        contexts: list[dict[str, Any]],
        detection: dict[str, Any],
    ) -> dict[str, Any] | None:
        extraction_cfg: ExtractionConfig | None = getattr(check, "extraction", None)
        if not extraction_cfg or not extraction_cfg.enabled:
            return None

        mode = getattr(extraction_cfg, "mode", None)
        logger.debug(
            "ExtractionExecutor.run started",
            check_id=check.id,
            doc_id=str(getattr(doc, "id", None)),
            mode=str(mode),
        )

        # Базовый текст для извлечения: evidence из detection, а при необходимости — весь контекст.
        base_text = self._build_extraction_text(detection, contexts)
        if not base_text:
            return None

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
        if mode in {"llm", "hybrid"} and self.llm_client.is_available():
            try:
                llm_fields = self.llm_detector.extract(
                    check,
                    base_text,
                    context_pages=context_pages,
                )
            except Exception as e:
                logger.warning("LLM extraction failed", error=str(e))
                llm_fields = {}

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
                        self._build_location_fallback(
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
            return None

        return structured

    def _build_extraction_text(
        self,
        detection: dict[str, Any],
        contexts: list[dict[str, Any]],
    ) -> str:
        """
        Сформировать текст, по которому будем делать extraction.

        Приоритет:
          1) detection["evidence"], если есть.
          2) иначе текст из наиболее релевантных чанков из contexts.
             Сначала пробуем сузить список по location (element_id / clause_uid / page),
             если это не получилось — используем весь контекст.
        """
        # 1. Если LLM/Rules уже вернули готовый evidence-текст — используем его.
        evidence = detection.get("evidence") or ""
        if isinstance(evidence, str) and evidence.strip():
            return evidence

        if not contexts:
            return ""

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

        # 3. Склеиваем текст только из релевантных чанков
        parts: list[str] = []
        for c in relevant_contexts:
            text = c.get("text") or ""
            if text:
                parts.append(text)

        return "\n\n".join(parts).strip()

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
    
    