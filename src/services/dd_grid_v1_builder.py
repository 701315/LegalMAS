# src/services/dd_grid_v1_builder.py

"""
DD Grid V1 Builder.

Строит полную runtime-структуру DD Grid V1 из:
- CheckDefinition (playbook checks),
- raw check_results dicts (из RunnerRepository.load_check_results_for_run),
- documents dict (из RunnerRepository.load_documents_for_run),
- YAMLRegistry (doc type groups / type configs).

Архитектурные принципы:
- builder не обращается к БД;
- builder не зависит от конкретных YAML/check ids;
- builder использует только универсальные playbook-driven правила;
- все lookup-операции O(1) через dict-индексы;
- malformed / partial payloads обрабатываются gracefully.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from classifiers.yaml_registry import DocumentTypeGroupConfig, YAMLRegistry
from core.logging import get_logger
from engine.checks.dd_grid_column_builder import DDGridColumnBuilder, DDGridColumnRuntime
from engine.playbook.models import CheckDefinition

logger = get_logger(__name__)

_ERROR_STATUSES: frozenset[str] = frozenset(
    {"FAILED", "TIMEOUT", "COMPUTE_FAILED", "PERSIST_FAILED"}
)
_FAILED_EXECUTION_STATUSES: frozenset[str] = frozenset(
    {"FAILED", "COMPUTE_FAILED", "PERSIST_FAILED"}
)
_TIMEOUT_EXECUTION_STATUSES: frozenset[str] = frozenset({"TIMEOUT"})
# PENDING и RUNNING разделены намеренно — у них разная семантика:
# PENDING  → check ещё не начался → эквивалентно отсутствию результата → SKIPPED
# RUNNING  → check активно выполняется прямо сейчас → IN_PROGRESS
# Оба НЕ являются ошибкой. Маппинг в FAILED был некорректен.
_PENDING_EXECUTION_STATUSES: frozenset[str] = frozenset({"PENDING"})
_RUNNING_EXECUTION_STATUSES: frozenset[str] = frozenset({"RUNNING"})
_SUCCESS_EXECUTION_STATUSES: frozenset[str] = frozenset({"SUCCESS"})

_NOT_DEFINED_STATUS_VALUES: frozenset[str] = frozenset({"missing", "not_defined", "not_found"})
_MISSING_SCALAR_VALUES: frozenset[str] = frozenset({"", "none", "null", "not_found"})

_DISPLAY_ERROR = "⚠ Ошибка"
_DISPLAY_PRESENT = "Присутствует"
_DEFAULT_SEGMENT_ID = "_default"
_DEFAULT_UNGROUPED_LABEL = "Прочие проверки"
_DEFAULT_UNGROUPED_GROUP_ID = "_ungrouped"
_DEFAULT_LOCATION_FALLBACK_REASON = "Точная ссылка на пункт документа не определена"

_PAGE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"стр\.?\s*(\d+)", re.IGNORECASE),
    re.compile(r"страниц[аеы]?\s*(\d+)", re.IGNORECASE),
    re.compile(r"page\s*(\d+)", re.IGNORECASE),
    re.compile(r"p\.?\s*(\d+)", re.IGNORECASE),
)

_REASON_METADATA_FIELDS: frozenset[str] = frozenset({"reason", "explanation", "notes"})

#: Порядок приоритета при поиске reason-like текста в metadata fields.
#: Первый найденный непустой → drawer.reason.
_REASON_METADATA_PRIORITY: tuple[str, ...] = ("reason", "explanation", "notes")

# ---------------------------------------------------------------------------
# Runtime DTOs
# ---------------------------------------------------------------------------


@dataclass
class DocumentMetaDTO:
    """Метаданные документа для DD Grid V1."""

    document_id: str
    filename: str
    doc_type: str | None
    status: str
    folder_path: str | None = None
    segment_id: str | None = None
    segment_type: str | None = None
    segment_title: str | None = None


@dataclass
class CellValueDTO:
    """
    Значение одной grid-ячейки.

    Ячейка = (document, runtime column).
    """

    cell_state: str
    display_value: str
    raw_value: Any = None
    location_clause_ref: str | None = None
    location_page: int | None = None
    location_confidence: str | None = None
    has_location_fallback: bool = False
    location_fallback_reason: str | None = None


@dataclass
class DrawerFieldDTO:
    """Детализация одной колонки в drawer."""

    column_id: str
    field_name: str
    label: str
    cell_state: str
    display_value: str
    raw_value: Any = None
    location_clause_ref: str | None = None
    location_page: int | None = None
    location_confidence: str | None = None
    has_location_fallback: bool = False
    location_fallback_reason: str | None = None


@dataclass
class DrawerContentDTO:
    """
    Контент drawer для одной пары (document, check).

    Transparency fields (B3 P0):
    - detection_level: уровень детекции (L1/L2/L3/L4).
    - confidence: уверенность модели (0.0-1.0), None для L1/L4.
    - quality_flags: технические флаги качества, None если нет caveats.

    QC audit trail (B3 P0):
    - qc_status: нормализованный API статус (pending/approved/rejected/needs_review).
    - qc_by / qc_at / qc_comment: заполняются только при явном QC-действии.

    Observability (B3 P1):
    - agent_name: имя детектора/агента (derived from detector_used).
    - model_version: версия LLM модели (from persisted raw metadata).
    - execution_time_ms: время выполнения (from started_at/finished_at).
    - retry_attempts: количество LLM-попыток (from raw.llm_attempts).
    - input_tokens: input tokens (from raw.context_tokens / raw.prompt_tokens).
    - output_tokens: output tokens (from raw.completion_tokens).
    """

    check_id: str
    check_name: str
    document_id: str
    cell_state: str
    reason: str | None
    review_status: str | None
    review_message: str | None = None
    display_text: str | None = None
    execution_status: str | None = None
    detection_level: str | None = None
    confidence: float | None = None
    quality_flags: dict[str, bool] | None = None
    qc_status: str | None = None
    qc_by: str | None = None
    qc_at: str | None = None
    qc_comment: str | None = None
    agent_name: str | None = None
    model_version: str | None = None
    execution_time_ms: int | None = None
    retry_attempts: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    fields: list[DrawerFieldDTO] = field(default_factory=list)
    evidence_items: list[str] = field(default_factory=list)


@dataclass
class CheckSubgroupDTO:
    """Runtime-представление одного check для DD Grid V1."""

    check_id: str
    check_name: str
    display_order: int
    columns: list[DDGridColumnRuntime]
    display_summary_field: str | None
    metadata_fields: list[str]


@dataclass
class GlobalGroupDTO:
    """Глобальная UX-группа checks."""

    group_id: str
    label: str
    display_order: int
    checks: list[CheckSubgroupDTO] = field(default_factory=list)


@dataclass
class DocTypeNodeDTO:
    """Один тип документа внутри doc-type class."""

    type_code: str
    name: str
    checks: list[CheckSubgroupDTO] = field(default_factory=list)


@dataclass
class DocTypeClassDTO:
    """Группа типов документов из registry.document_type_groups."""

    group_id: str
    label: str
    display_order: int
    types: list[DocTypeNodeDTO] = field(default_factory=list)


@dataclass
class DDGridV1Data:
    """
    Полная runtime-структура DD Grid V1.

    cell_values:    {document_id: {segment_id: {column_id: CellValueDTO}}}
    drawer_contents:{document_id: {segment_id: {check_id: DrawerContentDTO}}}

    segment_id нормализован: для single-segment документов = "_default".
    """

    global_groups: list[GlobalGroupDTO]
    doc_type_classes: list[DocTypeClassDTO]
    column_registry: dict[str, DDGridColumnRuntime]
    cell_values: dict[str, dict[str, dict[str, CellValueDTO]]]
    drawer_contents: dict[str, dict[str, dict[str, DrawerContentDTO]]]
    documents_meta: list[DocumentMetaDTO]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _humanize_identifier(value: str) -> str:
    """snake_case / kebab-case / mixed → Human Readable."""
    if not value:
        return ""
    cleaned = str(value).strip().replace("-", " ").replace("_", " ")
    cleaned = " ".join(part for part in cleaned.split() if part)
    if not cleaned:
        return ""
    return cleaned.title()


def _safe_str_or_none(value: Any) -> str | None:
    """Нормализовать значение к непустой строке или None."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_int_or_none(value: Any) -> int | None:
    """Безопасно привести значение к int или вернуть None."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    try:
        text = str(value).strip()
        if not text:
            return None
        return int(text)
    except (TypeError, ValueError):
        return None


def _extract_page_from_clause_ref(clause_ref: str | None) -> int | None:
    """
    Извлечь номер страницы из текстового clause_ref.

    Поддерживаем несколько языковых паттернов:
    - "стр. 8", "стр 8", "стр.8"
    - "страница 8"
    - "page 8"
    - "p. 8"
    """
    normalized_clause_ref = _safe_str_or_none(clause_ref)
    if not normalized_clause_ref:
        return None

    for pattern in _PAGE_PATTERNS:
        match = pattern.search(normalized_clause_ref)
        if match is None:
            continue

        page = _safe_int_or_none(match.group(1))
        if page is None:
            continue

        if 0 < page <= 10000:
            return page

    return None


def _normalize_location_bundle(
    *,
    location_clause_ref: str | None,
    location_page: int | None,
    location_confidence: str | None,
    has_location_fallback: bool,
    location_fallback_reason: str | None,
) -> tuple[str | None, int | None, str | None, bool, str | None]:
    """
    Нормализовать location-данные до стабильного API контракта.

    Правила:
    - если page отсутствует, пытаемся извлечь её из clause_ref;
    - если has_location_fallback=True, reason обязан быть заполнен;
    - если has_location_fallback=False, fallback reason всегда None.
    """
    normalized_clause_ref = _safe_str_or_none(location_clause_ref)
    normalized_page = (
        location_page
        if location_page is not None
        else _extract_page_from_clause_ref(normalized_clause_ref)
    )
    normalized_confidence = _safe_str_or_none(location_confidence)
    normalized_reason = _safe_str_or_none(location_fallback_reason)

    if has_location_fallback:
        if not normalized_confidence:
            normalized_confidence = "low"
        if not normalized_reason:
            normalized_reason = _DEFAULT_LOCATION_FALLBACK_REASON
    else:
        normalized_reason = None

    return (
        normalized_clause_ref,
        normalized_page,
        normalized_confidence,
        has_location_fallback,
        normalized_reason,
    )

_DETECTOR_TO_LEVEL: dict[str, str] = {
    # Rule-based detection: pattern matching, structural rules.
    "rules": "L1",
    # Field extraction mode: structured extraction without LLM presence detection.
    # llm_invoked=False in executor — deterministic retrieval + extraction pipeline.
    "extraction_only": "L1",
    # LLM single-shot presence detection.
    "llm": "L2",
    # Hybrid: rules + LLM.
    "hybrid": "L3",
}
_DETECTION_LEVELS_WITHOUT_CONFIDENCE: frozenset[str] = frozenset({"L1", "L4"})

_QC_STATUS_ADAPTER: dict[str, str] = {
    "pending": "pending",
    "confirmed": "approved",
    "rejected": "rejected",
    "overridden": "needs_review",
}


def _map_detector_to_detection_level(
    detector_used: Any,
    *,
    extraction_llm_invoked: bool = False,
    extraction_mode: str | None = None,
) -> str | None:
    """
    Привести detector_used к публичному API detection_level.

    Для extraction_only path учитываем фактический LLM-вызов:
      extraction_only + llm_invoked=False   -> L1 (deterministic extraction)
      extraction_only + llm_invoked=True + mode=llm    -> L2 (LLM extraction)
      extraction_only + llm_invoked=True + mode=hybrid -> L3 (RAG+LLM extraction)

    Для presence detection path:
      rules   -> L1
      llm     -> L2
      hybrid  -> L3
      unknown -> None
    """
    normalized = _safe_str_or_none(detector_used)
    if not normalized:
        return None

    if normalized.lower() == "extraction_only":
        if not extraction_llm_invoked:
            return "L1"
        normalized_mode = _safe_str_or_none(extraction_mode)
        if normalized_mode == "hybrid":
            return "L3"
        return "L2"

    return _DETECTOR_TO_LEVEL.get(normalized.lower())


def _normalize_confidence(
    value: Any,
    *,
    detection_level: str | None,
) -> float | None:
    """
    Нормализовать confidence к float [0.0, 1.0] или None.

    Правила:
    - L1 / L4 — confidence не применимо, возвращаем None.
    - None-like значения — None.
    - Невалидный диапазон — None + warning.
    """
    if detection_level in _DETECTION_LEVELS_WITHOUT_CONFIDENCE:
        return None

    if value is None:
        return None

    if isinstance(value, bool):
        return None

    try:
        score = float(value)
    except (TypeError, ValueError):
        logger.warning(
            "DD Grid V1: invalid confidence value, using None",
            raw_value=repr(value),
        )
        return None

    if not (0.0 <= score <= 1.0):
        logger.warning(
            "DD Grid V1: confidence out of range [0.0, 1.0], using None",
            score=score,
        )
        return None

    return score


def _normalize_quality_flags(raw_flags: Any) -> dict[str, bool] | None:
    """
    Нормализовать quality_flags к API-контракту.

    Правила:
    - допускаются только bool True значения;
    - False / non-bool / empty keys отбрасываются;
    - пустой результат -> None.
    """
    if not isinstance(raw_flags, dict) or not raw_flags:
        return None

    normalized: dict[str, bool] = {}
    for key, value in raw_flags.items():
        clean_key = str(key).strip()
        if not clean_key:
            continue
        if isinstance(value, bool) and value is True:
            normalized[clean_key] = True

    return normalized if normalized else None


def _normalize_qc_status_for_api(raw_status: Any) -> str | None:
    """
    Привести persisted QCStatus к публичному API enum.

    Persisted -> API:
      pending   -> pending
      confirmed -> approved
      rejected  -> rejected
      overridden -> needs_review

    Неизвестный/пустой статус -> None.
    """
    normalized = _safe_str_or_none(raw_status)
    if not normalized:
        return None
    return _QC_STATUS_ADAPTER.get(normalized.lower())


def _normalize_qc_at_for_api(raw_qc_at: Any) -> str | None:
    """
    Привести qc_at к ISO 8601 строке или None.

    Поддерживает datetime-объект и строку.
    """
    if raw_qc_at is None:
        return None

    if hasattr(raw_qc_at, "isoformat"):
        return raw_qc_at.isoformat()

    text = _safe_str_or_none(str(raw_qc_at))
    return text


def _normalize_structured_data(check_id: str, payload: Any) -> dict[str, Any]:
    """
    Убедиться, что structured_data имеет dict-вид.

    Malformed payload не должен валить builder.
    """
    if payload is None:
        return {}
    if isinstance(payload, dict):
        return payload

    logger.warning(
        "DD Grid V1: malformed structured_data, using empty payload",
        check_id=check_id,
        payload_type=type(payload).__name__,
    )
    return {}


def _is_missing_value(value: Any) -> bool:
    """
    Универсальная проверка на отсутствие значения.

    Важно:
    - 0 и False считаются валидными значениями;
    - пустая строка / пустой list / пустой dict → missing.
    """
    if value is None:
        return True

    if isinstance(value, str):
        return value.strip().lower() in _MISSING_SCALAR_VALUES

    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0

    return False


def _extract_field_payload(structured_data: dict[str, Any], field_name: str | None) -> Any:
    """Вернуть payload конкретного extraction field или None."""
    if not field_name:
        return None
    return structured_data.get(field_name)


def _extract_raw_value(field_payload: Any) -> Any:
    """
    Извлечь value из field payload.

    Поддерживает:
    - dict {"value": ...}
    - scalar
    - list
    - None
    """
    if isinstance(field_payload, dict):
        return field_payload.get("value")
    return field_payload


# НОВОЕ: Паттерны для извлечения номера пункта/статьи из текста результата
_CLAUSE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"[Пп]унк[тте]\s*(\d+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"[Пп]\.?\s*(\d+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"ст\.?\s*(\d+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"clause\s+(\d+(?:\.\d+)?)", re.IGNORECASE),
)


def _extract_location_bundle(
    field_payload: Any,
) -> tuple[str | None, int | None, str | None, bool, str | None]:
    """
    Извлечь location / location_fallback из field payload.
    Поддерживает как строгие структуры (dict), так и простые строки (str).
    """
    
    # --- Сценарий 1: Payload — это сразу строка (частый случай для LLM) ---
    if isinstance(field_payload, str):
        search_text = field_payload.strip()
        if search_text:
            extracted_page = None
            extracted_clause = None

            for pattern in _PAGE_PATTERNS:
                match = pattern.search(search_text)
                if match:
                    extracted_page = _safe_int_or_none(match.group(1))
                    break

            for pattern in _CLAUSE_PATTERNS:
                match = pattern.search(search_text)
                if match:
                    extracted_clause = f"п. {match.group(1)}"
                    break

            if extracted_page is not None or extracted_clause is not None:
                return (
                    extracted_clause,
                    extracted_page,
                    "low",
                    True,
                    "Извлечено из текста результата (эвристика)",
                )
        return None, None, None, False, None

    # --- Сценарий 2: Payload — это словарь ---
    if not isinstance(field_payload, dict):
        return None, None, None, False, None

    # 2.1. Строгий парсинг: ищем явный объект "location"
    location = field_payload.get("location")
    if isinstance(location, dict):
        return (
            _safe_str_or_none(location.get("clause_ref")),
            _safe_int_or_none(location.get("page")),
            _safe_str_or_none(location.get("location_confidence")),
            False,
            None,
        )

    # 2.2. Строгий парсинг: ищем явный объект "location_fallback"
    fallback = field_payload.get("location_fallback")
    if isinstance(fallback, dict):
        return (
            _safe_str_or_none(fallback.get("check_clause_uid")),
            _safe_int_or_none(fallback.get("check_page")),
            "low",
            True,
            _safe_str_or_none(fallback.get("reason")),
        )

    # 2.3. СПАСАТЕЛЬНЫЙ FALLBACK: ищем текст внутри ключа "value"
    raw_text = field_payload.get("value")
    if isinstance(raw_text, str) and raw_text.strip():
        search_text = raw_text.strip()
        extracted_page = None
        extracted_clause = None

        for pattern in _PAGE_PATTERNS:
            match = pattern.search(search_text)
            if match:
                extracted_page = _safe_int_or_none(match.group(1))
                break

        for pattern in _CLAUSE_PATTERNS:
            match = pattern.search(search_text)
            if match:
                extracted_clause = f"п. {match.group(1)}"
                break

        if extracted_page is not None or extracted_clause is not None:
            return (
                extracted_clause,
                extracted_page,
                "low",
                True,
                "Извлечено из текста результата (эвристика)",
            )

    # 4. Ничего не найдено
    return None, None, None, False, None


_DETECTOR_TO_AGENT_NAME: dict[str, str] = {
    "rules": "RulesDetector",
    "llm": "LLMDetector",
    "hybrid": "HybridDetector",
    "extraction_only": "ExtractionExecutor",
}

_EXTRACTION_LLM_AGENT_NAME = "ExtractionLLMDetector"


def _derive_agent_name(
    detector_used: Any,
    *,
    extraction_llm_invoked: bool = False,
) -> str | None:
    """
    Derived agent name from detector_used.

    Для extraction_only учитываем фактический LLM-вызов:
      extraction_only + llm_invoked=False -> ExtractionExecutor (rules-based extraction)
      extraction_only + llm_invoked=True  -> ExtractionLLMDetector (LLM extraction)
    """
    normalized = _safe_str_or_none(detector_used)
    if not normalized:
        return None

    if normalized.lower() == "extraction_only" and extraction_llm_invoked:
        return _EXTRACTION_LLM_AGENT_NAME

    return _DETECTOR_TO_AGENT_NAME.get(normalized.lower())


def _derive_execution_time_ms(
    started_at: Any,
    finished_at: Any,
) -> int | None:
    """
    Вычислить время выполнения check в миллисекундах.

    Правила:
    - оба timestamp обязательны;
    - delta <= 0 -> None (нет значимой разницы, timestamps выставлены одновременно);
    - delta > 600000 ms -> None + warning (sanity check: 10 минут max);
    - иначе valid int.
    """
    if started_at is None or finished_at is None:
        return None

    try:
        if hasattr(finished_at, "timestamp") and hasattr(started_at, "timestamp"):
            delta_ms = int((finished_at.timestamp() - started_at.timestamp()) * 1000)
        else:
            return None
    except (TypeError, ValueError, AttributeError):
        return None

    if delta_ms <= 0:
        return None

    if delta_ms > 600_000:
        logger.warning(
            "DD Grid V1: execution_time_ms exceeds 10 minutes sanity limit, using None",
            delta_ms=delta_ms,
        )
        return None

    return delta_ms


def _extract_observability_from_raw(raw_flags: Any) -> dict[str, Any]:
    """
    Извлечь observability-поля из quality_flags["raw"] payload.

    Приоритет для каждого поля:
    - model_version:   raw.model > raw.model_name > raw.llm_model
    - retry_attempts:  raw.llm_attempts (>= 1)
    - input_tokens:    raw.prompt_tokens > raw.context_tokens
    - output_tokens:   raw.completion_tokens > raw.eval_count
    - duration_ms:     raw.duration_ms (executor check-level total)
    - extraction_llm_invoked: raw.extraction_llm_invoked (bool)
    - extraction_mode:         raw.extraction_mode (str)
    """
    defaults: dict[str, Any] = {
        "model_version": None,
        "retry_attempts": None,
        "input_tokens": None,
        "output_tokens": None,
        "duration_ms": None,
        "extraction_llm_invoked": False,
        "extraction_mode": None,
    }

    if not isinstance(raw_flags, dict):
        return defaults

    raw = raw_flags.get("raw")
    if not isinstance(raw, dict):
        return defaults

    # model_version
    raw_model = (
        _safe_str_or_none(raw.get("model"))
        or _safe_str_or_none(raw.get("model_name"))
        or _safe_str_or_none(raw.get("llm_model"))
    )

    # retry_attempts: llm_attempts in raw, 1+ = valid
    raw_attempts = raw.get("llm_attempts")
    retry_attempts: int | None = None
    if raw_attempts is not None and not isinstance(raw_attempts, bool):
        try:
            parsed = int(raw_attempts)
            if parsed >= 1:
                retry_attempts = parsed
        except (TypeError, ValueError):
            pass

    # input_tokens: prefer prompt_tokens over context_tokens
    raw_input = raw.get("prompt_tokens") if raw.get("prompt_tokens") is not None \
        else raw.get("context_tokens")
    input_tokens: int | None = None
    if raw_input is not None and not isinstance(raw_input, bool):
        try:
            parsed = int(raw_input)
            if parsed >= 0:
                input_tokens = parsed
        except (TypeError, ValueError):
            pass

    # output_tokens: prefer completion_tokens over eval_count
    raw_output = raw.get("completion_tokens") if raw.get("completion_tokens") is not None \
        else raw.get("eval_count")
    output_tokens: int | None = None
    if raw_output is not None and not isinstance(raw_output, bool):
        try:
            parsed = int(raw_output)
            if parsed >= 0:
                output_tokens = parsed
        except (TypeError, ValueError):
            pass

    # duration_ms: executor check-level total execution time
    raw_duration = raw.get("duration_ms")
    duration_ms: int | None = None
    if raw_duration is not None and not isinstance(raw_duration, bool):
        try:
            parsed = int(raw_duration)
            if 0 < parsed <= 600_000:
                duration_ms = parsed
        except (TypeError, ValueError):
            pass

    # extraction_llm_invoked: was LLM actually called during extraction?
    extraction_llm_invoked = bool(raw.get("extraction_llm_invoked", False))

    # extraction_mode: "rules" | "llm" | "hybrid" | None
    extraction_mode = _safe_str_or_none(raw.get("extraction_mode"))

    return {
        "model_version": raw_model,
        "retry_attempts": retry_attempts,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "duration_ms": duration_ms,
        "extraction_llm_invoked": extraction_llm_invoked,
        "extraction_mode": extraction_mode,
    }

def _is_global_check(check: CheckDefinition) -> bool:
    """
    Определить, считать ли check глобальным.

    Defensive fallback:
    - origin == GLOBAL_PLAYBOOK → global
    - origin пустой и doc_types пустой → тоже global
    """
    origin = (check.origin or "").strip().upper()
    if origin == "GLOBAL_PLAYBOOK":
        return True
    return not origin and not check.doc_types


def _normalize_string_comparable(value: Any) -> str | None:
    """Привести значение к lowercase string для безопасного сравнения."""
    if value is None:
        return None
    return str(value).strip().lower()


def _resolve_cell_state(
    *,
    check_result: dict[str, Any] | None,
    column: DDGridColumnRuntime,
    raw_value: Any,
    status_field_value: Any,
) -> str:
    """
    Определить состояние ячейки DD Grid V1.

    Приоритет (4 состояния, применимость гарантирована планировщиком):
    1. not_executed  — нет результата
    2. error         — техническая ошибка выполнения
    3. not_defined   — результат есть, значение не найдено
    4. defined       — значение найдено
    """
    if check_result is None:
        return "not_executed"

    execution_status = _safe_str_or_none(check_result.get("execution_status"))
    if execution_status and execution_status.upper() in _ERROR_STATUSES:
        return "error"

    normalized_status = _normalize_string_comparable(status_field_value)
    normalized_present = _normalize_string_comparable(column.status_present_value)

    if normalized_status in _NOT_DEFINED_STATUS_VALUES:
        return "not_defined"

    if column.status_field and normalized_present is not None and normalized_status is not None:
        if normalized_status != normalized_present:
            return "not_defined"

    if _is_missing_value(raw_value):
        return "not_defined"

    return "defined"


def _format_scalar_for_display(value: Any) -> str:
    """Универсальное превращение raw value в display string."""
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(str(item) for item in value if str(item).strip())
    return str(value)


def _format_display_value(
    *,
    cell_state: str,
    raw_value: Any,
    column: DDGridColumnRuntime,
) -> str:
    """Форматировать текст ячейки по runtime column format."""
    if cell_state == "error":
        return _DISPLAY_ERROR
    if cell_state in {"not_defined", "not_executed"}:
        return column.fallback_display

    if column.format == "presence_only":
        return _DISPLAY_PRESENT

    if column.format == "yes_no":
        normalized = _normalize_string_comparable(raw_value)
        return "Да" if normalized in {"yes", "да", "true", "1"} else "Нет"

    if column.format == "enum":
        key = str(raw_value)
        return column.enum_labels.get(key, key)

    text = _format_scalar_for_display(raw_value)
    if column.unit and text:
        return f"{text} {column.unit}"
    return text


def _plan_status_to_cell_state(plan_status: str) -> str:
    """
    Привести plan_item.status к cell_state когда check_result отсутствует.

    failed / timeout → error (техническая ошибка на уровне плана)
    всё остальное   → not_executed (нет данных, но не ошибка)
    """
    if plan_status.lower() in ("failed", "timeout"):
        return "error"
    return "not_executed"


def _build_cell_value(
    *,
    check: CheckDefinition,
    check_result: dict[str, Any] | None,
    column: DDGridColumnRuntime,
    plan_status: str,
) -> CellValueDTO:
    """
    Построить CellValueDTO для одной runtime-колонки.

    Единый путь: состояние всегда выводится через _resolve_cell_state()
    и _format_display_value(). При отсутствии результата — ранний return
    с состоянием из plan_status без обращения к structured_data.
    """
    # Нет результата — состояние определяем по plan_status, display из column.fallback_display
    if check_result is None:
        cell_state = _plan_status_to_cell_state(plan_status)
        return CellValueDTO(
            cell_state=cell_state,
            display_value=column.fallback_display,
            raw_value=None,
            location_clause_ref=None,
            location_page=None,
            location_confidence=None,
            has_location_fallback=False,
            location_fallback_reason=None,
        )

    # Есть результат — единый путь через resolve + format
    structured_data = _normalize_structured_data(
        check.id,
        check_result.get("structured_data"),
    )

    value_payload = _extract_field_payload(structured_data, column.value_field)
    status_payload = _extract_field_payload(structured_data, column.status_field)

    raw_value = _extract_raw_value(value_payload)
    status_field_value = _extract_raw_value(status_payload)

    if column.format == "presence_only":
        raw_value = status_field_value

    cell_state = _resolve_cell_state(
        check_result=check_result,
        column=column,
        raw_value=raw_value,
        status_field_value=status_field_value,
    )

    display_value = _format_display_value(
        cell_state=cell_state,
        raw_value=raw_value,
        column=column,
    )

    location_payload = value_payload if value_payload is not None else status_payload
    (
        location_clause_ref,
        location_page,
        location_confidence,
        has_location_fallback,
        location_fallback_reason,
    ) = _extract_location_bundle(location_payload)

    # Fallback: ищем location в display_text если structured_data ничего не дал
    if not location_clause_ref and location_page is None:
        display_text = _safe_str_or_none(check_result.get("display_text"))
        if display_text:
            for pattern in _PAGE_PATTERNS:
                match = pattern.search(display_text)
                if match:
                    location_page = _safe_int_or_none(match.group(1))
                    break
            for pattern in _CLAUSE_PATTERNS:
                match = pattern.search(display_text)
                if match:
                    location_clause_ref = f"п. {match.group(1)}"
                    break
            if location_page is not None or location_clause_ref:
                has_location_fallback = True
                location_confidence = "low"
                location_fallback_reason = "Извлечено из display_text (эвристика)"

    (
        location_clause_ref,
        location_page,
        location_confidence,
        has_location_fallback,
        location_fallback_reason,
    ) = _normalize_location_bundle(
        location_clause_ref=location_clause_ref,
        location_page=location_page,
        location_confidence=location_confidence,
        has_location_fallback=has_location_fallback,
        location_fallback_reason=location_fallback_reason,
    )

    return CellValueDTO(
        cell_state=cell_state,
        display_value=display_value,
        raw_value=raw_value,
        location_clause_ref=location_clause_ref,
        location_page=location_page,
        location_confidence=location_confidence,
        has_location_fallback=has_location_fallback,
        location_fallback_reason=location_fallback_reason,
    )


def _collect_evidence_items(raw_value: Any) -> list[str]:
    """Нормализовать evidence payload к списку строк."""
    items: list[str] = []

    if raw_value is None:
        return items

    if isinstance(raw_value, list):
        for item in raw_value:
            text = _safe_str_or_none(item)
            if text:
                items.append(text)
        return items

    text = _safe_str_or_none(raw_value)
    if text:
        items.append(text)
    return items


def _combine_column_states(states: list[str]) -> str:
    """
    Свести состояния отдельных колонок к check-level состоянию для drawer.

    Приоритет: error > defined > not_defined > not_executed
    """
    if not states:
        return "not_executed"
    if any(state == "error" for state in states):
        return "error"
    if any(state == "defined" for state in states):
        return "defined"
    if any(state == "not_defined" for state in states):
        return "not_defined"
    return "not_executed"


def _has_partial_field_extraction(
    column_cells: list[tuple[DDGridColumnRuntime, CellValueDTO]],
) -> bool:
    """
    Определить, является ли успешное выполнение частичным.

    Partial = хотя бы одно поле определено, но не все runtime-поля
    вернулись успешно.
    """
    states = [cell.cell_state for _, cell in column_cells]
    has_defined = any(state == "defined" for state in states)
    has_missing_or_failed = any(
        state in {"not_defined", "error", "not_executed"} for state in states
    )
    return has_defined and has_missing_or_failed


def _normalize_execution_status_for_api(
    *,
    check_result: dict[str, Any] | None,
    column_cells: list[tuple[DDGridColumnRuntime, CellValueDTO]],
) -> str:
    """
    Нормализовать внутренний execution_status к публичному API-контракту.

    API значения:
    - SUCCESS      — check выполнен успешно, все поля найдены
    - PARTIAL      — check выполнен, часть полей не найдена
    - FAILED       — техническая ошибка выполнения
    - TIMEOUT      — превышен таймаут выполнения
    - SKIPPED      — нет результата (план есть, результата нет)
    - IN_PROGRESS  — check активно выполняется прямо сейчас
    """
    states = [cell.cell_state for _, cell in column_cells]

    if not states or check_result is None:
        return "SKIPPED"

    raw_status = (_safe_str_or_none(check_result.get("execution_status")) or "").upper()
    is_partial = _has_partial_field_extraction(column_cells)

    if raw_status == "PARTIAL":
        return "PARTIAL"

    if raw_status == "SKIPPED":
        return "SKIPPED"

    if raw_status in _TIMEOUT_EXECUTION_STATUSES:
        return "TIMEOUT"

    if raw_status in _FAILED_EXECUTION_STATUSES:
        return "FAILED"

    if raw_status in _RUNNING_EXECUTION_STATUSES:
        logger.info(
            "DD Grid V1: check is still running, returning IN_PROGRESS",
            raw_status=raw_status,
            check_id=_safe_str_or_none(check_result.get("check_id")),
            document_id=_safe_str_or_none(check_result.get("document_id")),
        )
        return "IN_PROGRESS"

    if raw_status in _PENDING_EXECUTION_STATUSES:
        logger.info(
            "DD Grid V1: check is pending (queued), returning SKIPPED",
            raw_status=raw_status,
            check_id=_safe_str_or_none(check_result.get("check_id")),
            document_id=_safe_str_or_none(check_result.get("document_id")),
        )
        return "SKIPPED"

    if raw_status in _SUCCESS_EXECUTION_STATUSES:
        return "PARTIAL" if is_partial else "SUCCESS"

    if not raw_status:
        if any(state == "error" for state in states):
            return "FAILED"
        if is_partial:
            return "PARTIAL"
        if any(state in {"defined", "not_defined"} for state in states):
            return "SUCCESS"
        return "SKIPPED"

    logger.warning(
        "DD Grid V1: unknown execution_status mapped to FAILED",
        raw_status=raw_status,
        check_id=_safe_str_or_none(check_result.get("check_id")),
        document_id=_safe_str_or_none(check_result.get("document_id")),
    )
    return "FAILED"


_PLAN_STATUS_TO_REASON: dict[str, str] = {
    "planned": "Проверка запланирована и ожидает выполнения.",
    "dispatched": "Проверка запланирована и ожидает выполнения.",
    "started": "Проверка выполняется в данный момент.",
    "failed": "Ошибка при выполнении проверки.",
    "timeout": "Превышен таймаут выполнения проверки.",
    "cancelled": "Проверка была отменена.",
    "skipped": "Проверка пропущена (результат учтён в другом плане).",
    "succeeded": "Результат ожидается.",
}

_PLAN_STATUS_TO_EXECUTION_STATUS: dict[str, str] = {
    "planned": "SKIPPED",
    "dispatched": "SKIPPED",
    "started": "IN_PROGRESS",
    "failed": "FAILED",
    "timeout": "TIMEOUT",
    "cancelled": "SKIPPED",
    "skipped": "SKIPPED",
    "succeeded": "SKIPPED",
}


def _build_drawer_content(
    *,
    check: CheckDefinition,
    doc_id: str,
    check_result: dict[str, Any] | None,
    subgroup: CheckSubgroupDTO,
    column_cells: list[tuple[DDGridColumnRuntime, CellValueDTO]],
    plan_status: str,
) -> DrawerContentDTO:
    """
    Построить drawer content для одного (document, check).

    field_details собирается один раз из column_cells — всегда,
    независимо от наличия check_result. Это устраняет дублирование кода.
    """
    # field_details — единственная сборка, всегда из готовых column_cells
    field_details: list[DrawerFieldDTO] = [
        DrawerFieldDTO(
            column_id=col.column_id,
            field_name=col.value_field or col.status_field or "",
            label=col.label,
            cell_state=cell.cell_state,
            display_value=cell.display_value,
            raw_value=cell.raw_value,
            location_clause_ref=cell.location_clause_ref,
            location_page=cell.location_page,
            location_confidence=cell.location_confidence,
            has_location_fallback=cell.has_location_fallback,
            location_fallback_reason=cell.location_fallback_reason,
        )
        for col, cell in column_cells
    ]

    cell_state = _combine_column_states([cell.cell_state for _, cell in column_cells])

    # Нет результата — возвращаем drawer с данными из plan_status
    if check_result is None:
        plan_status_lower = plan_status.lower()
        return DrawerContentDTO(
            check_id=check.id,
            check_name=check.name,
            document_id=doc_id,
            cell_state=cell_state,
            reason=_PLAN_STATUS_TO_REASON.get(plan_status_lower, "Статус проверки неизвестен."),
            review_status=None,
            review_message=None,
            display_text=None,
            execution_status=_PLAN_STATUS_TO_EXECUTION_STATUS.get(plan_status_lower, "SKIPPED"),
            detection_level=None,
            confidence=None,
            quality_flags=None,
            qc_status=None,
            qc_by=None,
            qc_at=None,
            qc_comment=None,
            agent_name=None,
            model_version=None,
            execution_time_ms=None,
            retry_attempts=None,
            input_tokens=None,
            output_tokens=None,
            fields=field_details,
            evidence_items=[],
        )

    # Есть результат — полная сборка из check_result
    structured_data = _normalize_structured_data(
        check.id,
        check_result.get("structured_data"),
    )

    evidence_items: list[str] = []
    metadata_reason: str | None = None

    for field_name in _REASON_METADATA_PRIORITY:
        payload = _extract_field_payload(structured_data, field_name)
        raw_value = _extract_raw_value(payload)
        text = _safe_str_or_none(raw_value)
        if text:
            metadata_reason = text
            break

    for field_name in subgroup.metadata_fields:
        if field_name in _REASON_METADATA_FIELDS:
            continue
        payload = _extract_field_payload(structured_data, field_name)
        raw_value = _extract_raw_value(payload)
        evidence_items.extend(_collect_evidence_items(raw_value))

    review_message = _safe_str_or_none(check_result.get("review_message"))
    display_text = _safe_str_or_none(check_result.get("display_text"))
    review_status = _safe_str_or_none(check_result.get("review_status"))
    execution_status = _normalize_execution_status_for_api(
        check_result=check_result,
        column_cells=column_cells,
    )

    _obs = _extract_observability_from_raw(check_result.get("quality_flags"))
    extraction_llm_invoked: bool = _obs["extraction_llm_invoked"]
    extraction_mode: str | None = _obs["extraction_mode"]

    detection_level = _map_detector_to_detection_level(
        check_result.get("detector_used"),
        extraction_llm_invoked=extraction_llm_invoked,
        extraction_mode=extraction_mode,
    )
    confidence = _normalize_confidence(
        check_result.get("confidence"),
        detection_level=detection_level,
    )
    quality_flags = _normalize_quality_flags(check_result.get("quality_flags"))

    qc_status = _normalize_qc_status_for_api(check_result.get("qc_status"))
    _pending_like_qc = qc_status == "pending"
    qc_by = None if _pending_like_qc else _safe_str_or_none(check_result.get("qc_by"))
    qc_at = None if _pending_like_qc else _normalize_qc_at_for_api(check_result.get("qc_at"))
    qc_comment = None if _pending_like_qc else _safe_str_or_none(check_result.get("qc_comment"))

    agent_name = _derive_agent_name(
        check_result.get("detector_used"),
        extraction_llm_invoked=extraction_llm_invoked,
    )
    execution_time_ms = _obs["duration_ms"] or _derive_execution_time_ms(
        check_result.get("started_at"),
        check_result.get("finished_at"),
    )

    return DrawerContentDTO(
        check_id=check.id,
        check_name=check.name,
        document_id=doc_id,
        cell_state=cell_state,
        reason=metadata_reason or review_message or display_text,
        review_status=review_status,
        review_message=review_message,
        display_text=display_text,
        execution_status=execution_status,
        detection_level=detection_level,
        confidence=confidence,
        quality_flags=quality_flags,
        qc_status=qc_status,
        qc_by=qc_by,
        qc_at=qc_at,
        qc_comment=qc_comment,
        agent_name=agent_name,
        model_version=_obs["model_version"],
        execution_time_ms=execution_time_ms,
        retry_attempts=_obs["retry_attempts"],
        input_tokens=_obs["input_tokens"],
        output_tokens=_obs["output_tokens"],
        fields=field_details,
        evidence_items=evidence_items,
    )


def _build_column_registry(
    checks: list[CheckDefinition],
) -> tuple[dict[str, DDGridColumnRuntime], dict[str, CheckSubgroupDTO]]:
    """
    Построить union registry всех runtime columns.

    Returns:
        (column_registry, check_subgroups)
    """
    builder = DDGridColumnBuilder()
    column_registry: dict[str, DDGridColumnRuntime] = {}
    check_subgroups: dict[str, CheckSubgroupDTO] = {}

    for check in checks:
        columns, metadata_fields, display_summary_field = builder.build_columns(check)
        if not columns:
            logger.debug(
                "DD Grid V1: check skipped because it has no runtime columns",
                check_id=check.id,
            )
            continue

        sorted_columns = sorted(columns, key=lambda c: (c.display_order, c.label.lower(), c.column_id))

        for column in sorted_columns:
            if column.column_id in column_registry:
                # Anti-collision safety net: НЕ перезаписываем существующую колонку.
                # Первая колонка выигрывает, вторая логируется как error для
                # диагностики. Это защищает cell_values от молчаливой потери данных.
                #
                # Валидация column_id уникальности должна происходить fail-fast
                # на уровне ExtractionConfig validator при loading playbook.
                # Эта проверка — последний рубеж защиты runtime.
                existing = column_registry[column.column_id]
                logger.error(
                    "DD Grid V1: duplicate runtime column id detected, keeping first occurrence",
                    check_id=check.id,
                    column_id=column.column_id,
                    kept_label=existing.label,
                    kept_value_field=existing.value_field,
                    dropped_label=column.label,
                    dropped_value_field=column.value_field,
                )
                continue
            column_registry[column.column_id] = column

        check_subgroups[check.id] = CheckSubgroupDTO(
            check_id=check.id,
            check_name=check.name,
            display_order=check.display_order,
            columns=sorted_columns,
            display_summary_field=display_summary_field,
            metadata_fields=list(metadata_fields),
        )

    return column_registry, check_subgroups


def _result_rank(result_row: dict[str, Any]) -> tuple[int, float]:
    """
    Ранг результата для выбора best row внутри одного (doc, segment, check).

    Критерии без severity (severity убран из модели отображения):
    1. result:     fail > unclear > pass
    2. confidence: выше — лучше
    """
    result_priority = {"fail": 3, "unclear": 2, "pass": 1}
    return (
        result_priority.get(str(result_row.get("result", "")).lower(), 0),
        float(result_row.get("confidence") or 0.0),
    )

def _build_plan_index(
    plan_items: list[Any],
) -> dict[tuple[str, str, str], dict[str, Any]]:
    """
    Построить индекс запланированных проверок.

    Ключ: (document_id, segment_id, check_id)
    segment_id нормализован: None → _DEFAULT_SEGMENT_ID.

    Source of truth: если записи нет в индексе,
    проверка не планировалась для этого (документ, сегмент, check).
    """
    plan_index: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in plan_items:
        doc_id = str(item.document_id)
        check_id = str(item.check_id)
        segment_id = (
            str(item.segment_id)
            if item.segment_id is not None
            else _DEFAULT_SEGMENT_ID
        )
        key = (doc_id, segment_id, check_id)
        plan_index[key] = {
            "plan_item_id": str(item.id),
            "status": str(item.status),
            "error_details": item.error_details,
        }
    return plan_index

def _build_result_index(
    check_results: list[dict[str, Any]],
) -> dict[tuple[str, str, str], dict[str, Any]]:
    """
    Построить индекс (document_id, segment_id, check_id) → best result dict.

    segment_id нормализован: None → _DEFAULT_SEGMENT_ID.
    Best-row выбирается только внутри одного (doc, segment, check).

    Tolerant Reader pattern:
    Если для (doc, check) существует ровно один result с non-default segment_id,
    создаётся дополнительный alias-ключ с _DEFAULT_SEGMENT_ID.
    Это необходимо когда plan_item создан с segment_id=None (_default),
    а persisted result содержит реальный segment UUID (single-segment docs).
    Для multi-segment docs (len > 1) alias не создаётся — каждый сегмент
    матчится строго по своему segment_id.
    """
    result_index: dict[tuple[str, str, str], dict[str, Any]] = {}

    # Вспомогательный индекс для aliasing: (doc_id, check_id) → {segment_id: best_row}
    by_doc_check: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}

    for row in check_results:
        if not isinstance(row, dict):
            logger.warning(
                "DD Grid V1: non-dict check_result encountered, skipping",
                payload_type=type(row).__name__,
            )
            continue

        document_id = _safe_str_or_none(row.get("document_id"))
        check_id = _safe_str_or_none(row.get("check_id"))
        if not document_id or not check_id:
            logger.warning(
                "DD Grid V1: check_result without document_id/check_id skipped",
                has_document_id=bool(document_id),
                has_check_id=bool(check_id),
            )
            continue

        raw_segment_id = row.get("segment_id")
        segment_id = (
            str(raw_segment_id)
            if raw_segment_id is not None
            else _DEFAULT_SEGMENT_ID
        )

        # Основной индекс — как раньше
        key = (document_id, segment_id, check_id)
        current = result_index.get(key)
        if current is None or _result_rank(row) > _result_rank(current):
            result_index[key] = row

        # Вспомогательный индекс для aliasing
        doc_check_key = (document_id, check_id)
        bucket = by_doc_check.setdefault(doc_check_key, {})
        current_bucket = bucket.get(segment_id)
        if current_bucket is None or _result_rank(row) > _result_rank(current_bucket):
            bucket[segment_id] = row

    # Tolerant Reader: alias single-segment results под "_default"
    for (document_id, check_id), segment_map in by_doc_check.items():
        # Если "_default" уже есть — alias не нужен
        if _DEFAULT_SEGMENT_ID in segment_map:
            continue

        # Только для ровно одного реального сегмента — безопасно aliasить
        if len(segment_map) == 1:
            only_segment_id, only_row = next(iter(segment_map.items()))
            alias_key = (document_id, _DEFAULT_SEGMENT_ID, check_id)
            if alias_key not in result_index:
                result_index[alias_key] = only_row
                logger.debug(
                    "DD Grid V1: single-segment alias created for _default lookup",
                    document_id=document_id,
                    check_id=check_id,
                    source_segment_id=only_segment_id,
                )

    return result_index


def _build_global_groups(
    checks: list[CheckDefinition],
    check_subgroups: dict[str, CheckSubgroupDTO],
) -> list[GlobalGroupDTO]:
    """Построить hierarchy для global checks."""
    grouped: dict[str, list[CheckDefinition]] = {}

    for check in checks:
        if check.id not in check_subgroups:
            continue
        if not _is_global_check(check):
            continue

        group_id = _safe_str_or_none(check.group) or _DEFAULT_UNGROUPED_GROUP_ID
        grouped.setdefault(group_id, []).append(check)

    groups: list[GlobalGroupDTO] = []
    for group_id, group_checks in grouped.items():
        sorted_checks = sorted(group_checks, key=lambda c: (c.display_order, c.name.lower(), c.id))
        label = (
            _DEFAULT_UNGROUPED_LABEL
            if group_id == _DEFAULT_UNGROUPED_GROUP_ID
            else (_humanize_identifier(group_id) or group_id)
        )

        groups.append(
            GlobalGroupDTO(
                group_id=group_id,
                label=label,
                display_order=min(check.display_order for check in group_checks),
                checks=[check_subgroups[check.id] for check in sorted_checks],
            )
        )

    groups.sort(key=lambda g: (g.display_order, g.label.lower(), g.group_id))
    return groups


def _build_doc_type_classes(
    checks: list[CheckDefinition],
    check_subgroups: dict[str, CheckSubgroupDTO],
    registry: YAMLRegistry,
    present_doc_types: set[str],
) -> list[DocTypeClassDTO]:
    """
    Построить hierarchy:
    document_type_group -> type -> checks

    Пустые ветки скрываются.
    """
    type_checks_by_group: dict[str, dict[str, list[CheckDefinition]]] = {}
    registry_groups: dict[str, DocumentTypeGroupConfig] = registry.get_document_type_groups()

    for check in checks:
        if check.id not in check_subgroups:
            continue
        if _is_global_check(check):
            continue
        if not check.doc_types:
            continue

        for type_code in check.doc_types:
            if type_code not in present_doc_types:
                continue

            type_config = registry.get_config(type_code)
            raw_group_id = getattr(type_config, "group", "") if type_config is not None else ""
            group_id = _safe_str_or_none(raw_group_id) or _DEFAULT_UNGROUPED_GROUP_ID

            type_checks_by_group.setdefault(group_id, {}).setdefault(type_code, []).append(check)

    classes: list[DocTypeClassDTO] = []
    for group_id, type_map in type_checks_by_group.items():
        group_config = registry_groups.get(group_id)
        group_label = (
            getattr(group_config, "label", None)
            or (_DEFAULT_UNGROUPED_LABEL if group_id == _DEFAULT_UNGROUPED_GROUP_ID else None)
            or _humanize_identifier(group_id)
            or group_id
        )
        group_display_order = getattr(group_config, "display_order", 999)

        type_nodes: list[DocTypeNodeDTO] = []
        for type_code, type_checks in type_map.items():
            type_config = registry.get_config(type_code)
            type_name = (
                _safe_str_or_none(getattr(type_config, "name", None))
                or _humanize_identifier(type_code)
                or type_code
            )
            sorted_checks = sorted(type_checks, key=lambda c: (c.display_order, c.name.lower(), c.id))
            type_nodes.append(
                DocTypeNodeDTO(
                    type_code=type_code,
                    name=type_name,
                    checks=[check_subgroups[check.id] for check in sorted_checks],
                )
            )

        type_nodes.sort(key=lambda n: (n.name.lower(), n.type_code))
        if not type_nodes:
            continue

        classes.append(
            DocTypeClassDTO(
                group_id=group_id,
                label=group_label,
                display_order=group_display_order,
                types=type_nodes,
            )
        )

    classes.sort(key=lambda c: (c.display_order, c.label.lower(), c.group_id))
    return classes


def _build_documents_meta(documents: dict[str, dict[str, Any]]) -> list[DocumentMetaDTO]:
    """Построить и отсортировать documents_meta."""
    items: list[DocumentMetaDTO] = []

    for document_id, doc_info in documents.items():
        safe_doc_info = doc_info if isinstance(doc_info, dict) else {}
        filename = (
            _safe_str_or_none(safe_doc_info.get("filename"))
            or _safe_str_or_none(safe_doc_info.get("name"))
            or str(document_id)
        )

        items.append(
            DocumentMetaDTO(
                document_id=str(document_id),
                filename=filename,
                doc_type=_safe_str_or_none(safe_doc_info.get("doc_type")),
                status=_safe_str_or_none(safe_doc_info.get("status")) or "",
                folder_path=_safe_str_or_none(safe_doc_info.get("folder_path")),
                segment_id=_safe_str_or_none(safe_doc_info.get("segment_id")),
                segment_type=_safe_str_or_none(safe_doc_info.get("segment_type")),
                segment_title=_safe_str_or_none(safe_doc_info.get("segment_title")),
            )
        )

    items.sort(key=lambda d: (d.filename.lower(), d.document_id))
    return items


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_dd_grid_v1(
    checks: list[CheckDefinition],
    check_results: list[dict[str, Any]],
    documents: dict[str, dict[str, Any]],
    registry: YAMLRegistry,
    plan_items: list[Any],
    checks_mode: str = "all",
) -> DDGridV1Data:
    """
    Построить полную структуру DD Grid V1.

    Args:
        checks:       Все playbook checks.
        check_results:Raw dict payloads из RunnerRepository.load_check_results_for_run().
        documents:    Dict {document_id: {...}} из RunnerRepository.load_documents_for_run().
        registry:     YAMLRegistry для doc-type grouping.
        plan_items:   list[RunCheckPlanItem] — источник истины о запланированных проверках.
        checks_mode:  "all" | "global_only" | "doc_type_only" — гейтинг групп.

    Returns:
        DDGridV1Data с cell_values: {doc_id: {segment_id: {column_id: CellValueDTO}}}
    """
    logger.info(
        "DD Grid V1: build started",
        checks_count=len(checks),
        check_results_count=len(check_results),
        documents_count=len(documents),
        plan_items_count=len(plan_items),
        checks_mode=checks_mode,
    )

    column_registry, check_subgroups = _build_column_registry(checks)
    result_index = _build_result_index(check_results)
    plan_index = _build_plan_index(plan_items)
    documents_meta = _build_documents_meta(documents)

    present_doc_types: set[str] = set()
    for doc_info in documents.values():
        if isinstance(doc_info, dict):
            doc_type = _safe_str_or_none(doc_info.get("doc_type"))
            if doc_type:
                present_doc_types.add(doc_type)

    # checks_mode гейтинг: не строим пустые группы для нерелевантных режимов
    global_groups = (
        _build_global_groups(checks, check_subgroups)
        if checks_mode in ("all", "global_only")
        else []
    )
    doc_type_classes = (
        _build_doc_type_classes(
            checks=checks,
            check_subgroups=check_subgroups,
            registry=registry,
            present_doc_types=present_doc_types,
        )
        if checks_mode in ("all", "doc_type_only")
        else []
    )

    grid_checks = [check for check in checks if check.id in check_subgroups]

    # Собрать все сегменты из plan_index — только те, что реально запланированы
    segments_per_doc: dict[str, set[str]] = {}
    for (doc_id, seg_id, _check_id) in plan_index:
        segments_per_doc.setdefault(doc_id, set()).add(seg_id)

    cell_values: dict[str, dict[str, dict[str, CellValueDTO]]] = {}
    drawer_contents: dict[str, dict[str, dict[str, DrawerContentDTO]]] = {}

    for document_id, doc_info in documents.items():
        doc_id_str = str(document_id)

        cell_values[doc_id_str] = {}
        drawer_contents[doc_id_str] = {}

        # Если для документа нет ни одного plan_item — пропускаем документ целиком
        segments = segments_per_doc.get(doc_id_str)
        if not segments:
            continue

        for segment_id in segments:
            cell_values[doc_id_str][segment_id] = {}
            drawer_contents[doc_id_str][segment_id] = {}

            for check in grid_checks:
                plan_info = plan_index.get((doc_id_str, segment_id, check.id))
                if plan_info is None:
                    continue

                plan_status = plan_info["status"]

                # skipped → идемпотентность: ищем реальный результат в другом плане
                # для того же (doc, segment, check). Если нашли — используем.
                # Если нет — check_result = None → not_executed (не ошибка).
                check_result = result_index.get((doc_id_str, segment_id, check.id))

                subgroup = check_subgroups[check.id]
                column_cells: list[tuple[DDGridColumnRuntime, CellValueDTO]] = []

                for column in subgroup.columns:
                    cell = _build_cell_value(
                        check=check,
                        check_result=check_result,
                        column=column,
                        plan_status=plan_status,
                    )
                    cell_values[doc_id_str][segment_id][column.column_id] = cell
                    column_cells.append((column, cell))

                drawer_contents[doc_id_str][segment_id][check.id] = _build_drawer_content(
                    check=check,
                    doc_id=doc_id_str,
                    check_result=check_result,
                    subgroup=subgroup,
                    column_cells=column_cells,
                    plan_status=plan_status,
                )

    logger.info(
        "DD Grid V1: build completed",
        global_groups=len(global_groups),
        doc_type_classes=len(doc_type_classes),
        columns=len(column_registry),
        documents_meta=len(documents_meta),
        indexed_results=len(result_index),
        indexed_plans=len(plan_index),
    )

    return DDGridV1Data(
        global_groups=global_groups,
        doc_type_classes=doc_type_classes,
        column_registry=column_registry,
        cell_values=cell_values,
        drawer_contents=drawer_contents,
        documents_meta=documents_meta,
    )


