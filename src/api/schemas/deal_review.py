# src/api/schemas/deal_review.py

"""
DTO-схемы для UI-API обзора сделки (deal review).

Эти модели описывают "готовый" JSON для фронта:
- список документов со статусами рисков;
- детальная карточка документа с проверками;
- список DD-запросов;
- список условных проверок;
- список извлечённых значений (structured values).

Они независимы от внутренних ORM-моделей и AggregatedResults —
между ними есть слой маппинга в deal_review_service.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, StrictBool, field_validator


class DocumentSummaryDTO(BaseModel):
    """
    Краткий статус документа для списка документов сделки.

    Показывает:
    - название и тип документа;
    - статус (pending / classified / quarantine и т.п.);
    - количество рисков по уровням;
    - есть ли проблемы со структурой (degraded);
    - уровень и уверенность классификации.
    """

    document_id: str
    name: str
    doc_type: str
    status: str

    critical_count: int
    high_count: int
    medium_count: int
    pass_count: int
    unclear_count: int

    has_degraded_structure: bool
    in_quarantine: bool

    classification_level: str
    classification_confidence: float


class CheckItemDTO(BaseModel):
    """
    Одна проверка (check) по документу в детальной карточке.

    Включает:
    - идентификатор и имя проверки;
    - результат и серьёзность;
    - краткий фрагмент evidence;
    - уверенность и используемый детектор;
    - флаги качества;
    - метаданные условной проверки;
    - structured_data с извлечёнными полями;
    - (опционально) метаданные сегмента для multi-document файлов.

    Canonical display semantics (NEW):
        display_text        — первичный human-readable factual текст результата.
                              Формируется result_semantics.py в result_saver.
                              Фронтенд показывает его как primary cell text.
        review_status       — canonical workflow статус:
                              "needs_review" | "ok" | "not_applicable" | "unclear"
        review_message      — advisory explanation для юриста (рекомендация системы).
        needs_manual_review — явный workflow-флаг: True → требует ручной проверки.
        ui_mode             — semantic type чека: "clause_presence" | "extraction" |
                              "risk_flag" | "comparison" | "summary" | None.
    """

    check_id: str
    check_name: str
    result: str
    severity: str
    evidence_snippet: str | None
    page: int | None
    clause_uid: str
    confidence: float | None
    detector_used: str | None
    quality_flags: dict | None
    conditional_check_triggered: bool
    trigger_name: str | None
    structured_data: dict[str, Any]
    origin: str | None = None

    # Segment metadata (optional, для multi-document физических файлов)
    segment_id: str | None = None
    segment_type: str | None = None
    segment_title: str | None = None
    segment_order: int | None = None
    is_primary_segment: bool | None = None

    # Canonical display semantics — source of truth для primary cell text.
    # None означает что result_semantics не сформировал текст (старый ран или n/a).
    # Фронтенд в этом случае использует fallback на review_status label.
    display_text: str | None = None
    review_status: str | None = None
    review_message: str | None = None
    needs_manual_review: bool = False
    ui_mode: str | None = None


class CheckMetaDTO(BaseModel):
    """
    Метаинформация о проверке для DD Matrix.

    Используется в списке checks внутри DDMatrixResponseDTO:
    - идентификатор и имя проверки;
    - источник (origin): GLOBAL_PLAYBOOK / DOCUMENT_TYPE / CONDITIONAL;
    - базовый уровень серьёзности;
    - порядок отображения (order_index);
    - список типов документов, к которым относится
      (для DOCUMENT_TYPE / CONDITIONAL).
    """

    check_id: str
    check_name: str
    origin: str  # "GLOBAL_PLAYBOOK", "DOCUMENT_TYPE" или "CONDITIONAL"
    severity: str  # "critical" / "high" / "medium"
    order_index: int
    applicable_doc_types: list[str] | None = None


class ExtractedFieldDTO(BaseModel):
    """
    Одно извлечённое поле внутри ячейки DD Matrix.

    Пример:
    - field_name: "amount", field_value: "5 000 000", field_format: "money"
    - field_name: "end_date", field_value: "01.01.2025", field_format: "date"
    """

    field_name: str
    field_value: str
    field_format: str  # "money", "date", "entity_name", "text"


class MatrixCellDTO(BaseModel):
    """
    Ячейка DD Matrix для одной проверки по одному документу.

    Содержит:
    - результат и уровень серьёзности;
    - короткий сниппет evidence, страницу, clause_uid;
    - список извлечённых полей;
    - статус QC и флаги условной проверки.

    Canonical display semantics (NEW):
        display_text        — первичный human-readable factual текст результата.
                              Формируется result_semantics.py в result_saver.
                              Фронтенд показывает его как primary cell text в DD Grid.
                              None → фронтенд использует fallback на review_status label.
        review_status       — canonical workflow статус:
                              "needs_review" | "ok" | "not_applicable" | "unclear"
        review_message      — advisory explanation для юриста (рекомендация системы).
                              Отображается в панели деталей ячейки как отдельная секция.
        needs_manual_review — явный workflow-флаг: True → ячейка требует ручной проверки.
                              Используется для фильтрации и выделения в UI.
        ui_mode             — semantic type чека: "clause_presence" | "extraction" |
                              "risk_flag" | "comparison" | "summary" | None.
                              Позволяет фронтенду выбирать правильный renderer.
    """

    result: str  # "fail" / "pass" / "unclear"
    severity: str  # "critical" / "high" / "medium" / "pass" / "unclear"
    snippet: str
    page: int | None
    clause_uid: str
    extracted: list[ExtractedFieldDTO]
    confidence: float
    qc_status: str  # "pending" / "approved" / "rejected" / "needs_review"

    qc_by: str | None = None
    qc_comment: str | None = None
    qc_at: str | None = None

    conditional_check_triggered: bool
    trigger_name: str

    # Segment / chunk provenance (опционально, для multi-document файлов).
    segment_id: str | None = None
    segment_type: str | None = None
    segment_title: str | None = None
    segment_order: int | None = None
    is_primary_segment: bool | None = None
    chunk_id: str | None = None
    chunk_index: int | None = None

    # Canonical display semantics — source of truth для primary cell text.
    # None означает что result_semantics не сформировал текст (старый ран или n/a).
    display_text: str | None = None
    review_status: str | None = None
    review_message: str | None = None
    needs_manual_review: bool = False
    ui_mode: str | None = None


class DocumentMatrixRowDTO(BaseModel):
    """
    Строка DD Matrix для одного документа.

    Содержит:
    - идентификатор и имя документа, тип, путь к папке, статус;
    - уровень и уверенность классификации;
    - словарь ячеек по check_id.
    """

    document_id: str
    document_name: str
    doc_type: str
    folder_path: str | None = None
    status: str
    classification_level: str
    classification_confidence: float
    requires_manual_review: bool = False
    results: dict[str, MatrixCellDTO]


class SegmentMatrixRowDTO(BaseModel):
    """
    Строка DD Matrix для одного логического документа (сегмента).

    Содержит:
    - идентификатор физического файла и его имя;
    - тип документа, путь к папке;
    - метаданные сегмента (segment_id, title, type, order);
    - статус файла и метрики классификации;
    - словарь ячеек по check_id.
    """

    document_id: str
    document_name: str
    doc_type: str
    folder_path: str | None = None

    segment_id: str | None = None
    segment_type: str | None = None
    segment_title: str | None = None
    segment_order: int | None = None
    is_primary_segment: bool | None = None

    status: str
    classification_level: str
    classification_confidence: float
    requires_manual_review: bool = False
    results: dict[str, MatrixCellDTO]


class DDMatrixResponseDTO(BaseModel):
    """
    Ответ DD Matrix для эндпоинта
    GET /deals/{deal_id}/runs/{run_id}/dd-matrix.

    Включает:
    - общие данные по сделке/рану;
    - список метаинформации по чекам (столбцы матрицы);
    - вспомогательные списки global_check_ids и doc_type_check_ids;
    - список строк матрицы по документам;
    - агрегированные счётчики по серьёзности и качеству доказательств.
    """

    deal_id: str
    run_id: str
    deal_name: str

    checks: list["CheckMetaDTO"]
    global_check_ids: list[str]
    doc_type_check_ids: dict[str, list[str]]

    documents: list[DocumentMatrixRowDTO]
    # Сегмент-ориентированные строки матрицы.
    # Именно они являются основным источником данных для DD Grid на фронте.
    segment_documents: list[SegmentMatrixRowDTO] = []

    total_documents: int
    total_checks: int
    severity_counts: dict[str, int]
    quarantine_count: int
    degraded_count: int
    evidence_validity_rate: float


class DocumentDetailDTO(BaseModel):
    """
    Детальная карточка документа для UI.

    Включает:
    - основные поля документа;
    - уровень и уверенность классификации;
    - список applicable_triggers;
    - список проверок (CheckItemDTO).
    """

    document_id: str
    name: str
    doc_type: str
    status: str
    classification_level: str
    classification_confidence: float
    applicable_triggers: list[str]
    checks: list[CheckItemDTO]


class DDRequestDTO(BaseModel):
    """
    DTO для одного DD-запроса в UI.

    Показывает:
    - приоритет;
    - по какой проверке создан;
    - адресата;
    - текст запроса;
    - к каким документам и типам относится;
    - какие structured_values были использованы;
    - (опционально) segment provenance для viewer navigation в multi-document файлах.
    """

    request_id: str
    priority: str
    check_id: str | None
    check_name: str | None
    addressee: str
    text: str
    document_ids: list[str]
    document_names: list[str]
    doc_types: list[str]
    structured_values: list[dict[str, Any]]

    # Segment provenance для viewer navigation
    segment_id: str | None = None
    segment_type: str | None = None
    segment_title: str | None = None
    segment_order: int | None = None
    is_primary_segment: bool | None = None
    chunk_id: str | None = None
    chunk_index: int | None = None


class ConditionalCheckDTO(BaseModel):
    """
    Условная проверка (conditional check) для отдельного списка в UI.

    Показывает:
    - документ и его тип;
    - имя триггера и проверки;
    - результат и серьёзность;
    - фрагмент evidence;
    - уверенность и флаги качества.
    """

    document_name: str
    doc_type: str
    trigger_name: str
    check_id: str
    check_name: str
    result: str
    severity: str
    evidence_snippet: str | None
    page: int | None
    confidence: float | None
    quality_flags: dict | None


class ExtractedValueDTO(BaseModel):
    """
    Одно извлечённое значение (structured value) для списка в UI.

    Например:
    - сумма договора,
    - дата окончания,
    - название стороны и т.п.

    Для multi-document файлов дополнительно может содержать сегмент,
    к которому относится значение (основной договор, приложение, акт и т.п.).
    """

    document_name: str
    doc_type: str
    check_name: str
    field_name: str
    field_value: str
    field_format: str  # "money", "date", "entity_name", "text"
    page: int | None
    clause_uid: str

    # Опциональные метаданные сегмента
    segment_id: str | None = None
    segment_type: str | None = None
    segment_title: str | None = None
    segment_order: int | None = None
    is_primary_segment: bool | None = None


class DocumentStructuredDataDTO(BaseModel):
    """
    Структурированные значения по одному документу
    в рамках конкретного run.

    Показывает:
    - сделку и run, в рамках которых выполнялась проверка;
    - идентификатор, имя и тип документа;
    - информацию о playbook (версия, название);
    - сколько значений извлечено;
    - список извлечённых значений.
    """

    deal_id: str
    run_id: str

    document_id: str
    document_name: str
    doc_type: str

    # Информация о плейбуке / профиле проверки
    playbook_version_id: str | None = None
    playbook_name: str | None = None
    profile: str | None = None  # например: "core", "extended"

    total_values: int
    values: list[ExtractedValueDTO]

    # ---------------------------------------------------------------------------
# DD Grid V1 API DTO
# ---------------------------------------------------------------------------

DDGridDetectionLevel = Literal["L1", "L2", "L3", "L4"]
DDGridQCStatus = Literal["pending", "approved", "rejected", "needs_review"]

class DDGridCellValueDTO(BaseModel):
    """
    Значение одной ячейки DD Grid V1.

    Ячейка = пересечение (document_id, column_id).
    column_id формат: '{check_id}__{field_key}'.

    cell_state:
      defined         — значение найдено, display_value форматировано по column.format.
      not_defined     — check выполнен, но значение не найдено.
      not_applicable  — check не применим к doc_type документа.
      not_executed    — check не выполнялся для этого документа.
      error           — техническая ошибка выполнения check.

    Location:
      has_location_fallback=false + clause_ref/page → exact pinpoint.
      has_location_fallback=true → approximate / check-level fallback.
      clause_ref и page могут быть null при fallback.
      location_confidence: 'high' (exact) или 'low' (fallback).
    """

    cell_state: str
    """defined | not_defined | not_applicable | not_executed | error"""

    display_value: str
    """Готовый текст для отображения в ячейке. Форматирован по column.format."""

    raw_value: Any = None
    """Сырое значение из structured_data (для tooltip / drill-down)."""

    location_clause_ref: str | None = None
    """Ссылка на клаузу (напр. 'п. 22'). None при fallback без pinpoint."""

    location_page: int | None = None
    """Номер страницы в документе. None при fallback без pinpoint."""

    location_confidence: str | None = None
    """'high' — exact; 'low' — fallback. None если location отсутствует."""

    has_location_fallback: bool = False
    """True если location из check-level fallback, а не из LLM per-field extraction."""

    location_fallback_reason: str | None = None
    """Причина fallback (напр. 'LLM не указал точную ссылку для поля')."""


class DDGridDrawerFieldDTO(BaseModel):
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


class DDGridDrawerDTO(BaseModel):
    """
    Содержимое drawer для одного (document_id, check_id).

    Показывается при клике на ячейку / строку DD Grid.

    reason: объяснение результата. Precedence:
      1. metadata field 'reason'
      2. metadata field 'explanation'
      3. metadata field 'notes'
      4. review_message (из CheckResult)
      5. display_text (из CheckResult)
      Reason-like поля не дублируются в evidence_items.

    fields: детализация по каждой runtime-колонке check.
      cell_state, display_value, raw_value, location (exact или fallback).

    evidence_items: список evidence-ссылок из EVIDENCE_LIST полей.
      reason/explanation/notes не попадают сюда.

    cell_state: сводный cell_state по всем columns check.
      Priority: error > defined > not_defined > not_executed > not_applicable.

    Дополнительно:
    - detection_level / confidence / quality_flags дают прозрачность результата;
    - qc_* поля содержат audit trail QC без отдельного round-trip;
    - execution_status возвращается в API-контракте:
      SUCCESS | PARTIAL | FAILED | TIMEOUT | SKIPPED | IN_PROGRESS.
      IN_PROGRESS означает что check ещё выполняется (Run не завершён).
    """

    check_id: str
    check_name: str
    document_id: str
    cell_state: str
    reason: str | None = None
    review_status: str | None = None
    review_message: str | None = None
    display_text: str | None = None

    execution_status: str | None = None
    """
    Статус выполнения check:
      SUCCESS     — выполнен успешно, все поля найдены.
      PARTIAL     — выполнен, часть полей не найдена.
      FAILED      — техническая ошибка (COMPUTE_FAILED / PERSIST_FAILED / FAILED).
      TIMEOUT     — превышен таймаут.
      SKIPPED     — не применим к doc_type или ещё не начался (PENDING).
      IN_PROGRESS — активно выполняется (RUNNING); возможно при просмотре
                    Grid до завершения Run.
    """

    detection_level: DDGridDetectionLevel | None = None
    """L1 | L2 | L3 | L4"""

    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    """Confidence score 0.0-1.0. None when not applicable or unavailable."""

    quality_flags: dict[str, StrictBool] | None = None
    """
    Открытый dict технических флагов качества.
    Допускаются только true-значения.
    None = технических caveats нет.
    """

    qc_status: DDGridQCStatus | None = None
    qc_by: str | None = None
    qc_at: str | None = None
    qc_comment: str | None = None

    # Observability (B3 P1)
    agent_name: str | None = None
    """
    Имя агента/детектора. Derived from detector_used.
    Примеры: 'RulesDetector', 'LLMDetector', 'HybridDetector', 'ExtractionExecutor'.
    None для legacy runs или если detector_used неизвестен.
    """

    model_version: str | None = None
    """
    Версия LLM модели. Например: 'qwen-2.5-7b', 'gpt-4-turbo-2024-04-09'.
    None для L1/L4 без LLM или если данные недоступны.
    """

    execution_time_ms: int | None = Field(default=None, ge=0, le=600000)
    """
    Время выполнения check в миллисекундах.
    Derived from started_at / finished_at.
    None если данные недоступны или delta <= 0.
    """

    retry_attempts: int | None = Field(default=None, ge=1)
    """
    Количество LLM-попыток. 1 = с первого раза.
    None для L1 без LLM или если данные недоступны.
    """

    input_tokens: int | None = Field(default=None, ge=0)
    """
    Количество input tokens (context + prompt overhead).
    None если LLM не вызывался или данные недоступны.
    """

    output_tokens: int | None = Field(default=None, ge=0)
    """
    Количество output tokens.
    None если LLM не вызывался или данные недоступны.
    """

    fields: list[DDGridDrawerFieldDTO] = Field(default_factory=list)
    evidence_items: list[str] = Field(default_factory=list)

    @field_validator("quality_flags")
    @classmethod
    def validate_quality_flags(
        cls,
        value: dict[str, StrictBool] | None,
    ) -> dict[str, StrictBool] | None:
        """
        quality_flags:
        - None, если флагов нет;
        - непустой dict;
        - только non-empty keys;
        - только true boolean values.
        """
        if value is None:
            return None

        normalized: dict[str, StrictBool] = {}
        for key, flag in value.items():
            normalized_key = str(key).strip()
            if not normalized_key:
                raise ValueError("quality_flags keys must be non-empty strings")
            if flag is not True:
                raise ValueError("quality_flags must contain only true boolean values")
            normalized[normalized_key] = True

        if not normalized:
            raise ValueError("quality_flags must be None or contain at least one true flag")

        return normalized

    @field_validator("qc_at")
    @classmethod
    def validate_qc_at(cls, value: str | None) -> str | None:
        """
        qc_at должен быть ISO 8601 string или None.
        Пустая строка нормализуется в None.
        """
        if value is None:
            return None

        normalized = value.strip()
        if not normalized:
            return None

        try:
            datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("qc_at must be a valid ISO 8601 datetime string") from exc

        return normalized


class DDGridColumnDTO(BaseModel):
    """
    Описание одной колонки DD Grid V1.

    Используется фронтом для рендеринга заголовков и выбора renderer.

    column_id формат: '{check_id}__{field_key}'.
    check_id: идентификатор check (часть column_id до '__').

    format:
      text           — plain string, + unit если задан.
      enum           — lookup: enum_labels[raw_value] → display string.
      yes_no         — boolean: 'Да' / 'Нет'.
      presence_only  — наличие: 'Присутствует'.

    fallback_display: текст ячейки при not_defined / not_executed (обычно '—').
    display_order: порядок колонки слева направо. Меньше = раньше.
    enum_labels: {canonical_value: human_label}. Пусто для non-enum колонок.
    unit: единица измерения (напр. 'дней', 'RUB'). None если не задано.
    """

    column_id: str
    check_id: str
    label: str
    format: str
    """text | enum | yes_no | presence_only"""

    fallback_display: str
    display_order: int
    enum_labels: dict[str, str] = {}
    unit: str | None = None


class DDGridCheckSubgroupDTO(BaseModel):
    """Один check как колонка-группа в DD Grid V1."""

    check_id: str
    check_name: str
    display_order: int
    columns: list[DDGridColumnDTO]
    display_summary_field: str | None = None
    metadata_fields: list[str] = []


class DDGridGlobalGroupDTO(BaseModel):
    """Группа глобальных проверок в DD Grid V1."""

    group_id: str
    label: str
    display_order: int
    checks: list[DDGridCheckSubgroupDTO]


class DDGridDocTypeNodeDTO(BaseModel):
    """Один тип документа внутри doc-type class."""

    type_code: str
    name: str
    checks: list[DDGridCheckSubgroupDTO]


class DDGridDocTypeClassDTO(BaseModel):
    """Группа типов документов из registry."""

    group_id: str
    label: str
    display_order: int
    types: list[DDGridDocTypeNodeDTO]


class DDGridDocumentMetaDTO(BaseModel):
    """Метаданные документа для DD Grid V1."""

    document_id: str
    filename: str
    doc_type: str | None = None
    status: str
    folder_path: str | None = None


class DDGridV1ResponseDTO(BaseModel):
    """
    Полная иерархическая структура DD Grid V1 для одного run.

    Endpoint: GET /deals/{deal_id}/runs/{run_id}/dd-grid-v1

    Структура:
    - global_groups: иерархия глобальных проверок
      (group → checks → columns). Сортировка: display_order → label.
    - doc_type_classes: иерархия по типам документов
      (registry group → type → checks). Пустые ветки скрыты.
    - column_registry: все runtime-колонки (column_id → spec).
      column_id формат: '{check_id}__{field_key}'.
    - cell_values: {doc_id: {column_id: CellValueDTO}}.
      Ячейка = пересечение документа и runtime-колонки.
    - drawer_contents: {doc_id: {check_id: DrawerDTO}}.
      Drawer = детальная панель при клике на ячейку.
    - documents_meta: метаданные документов, отсортированы по filename.

    Cell states:
      defined         — значение найдено, display_value форматировано.
      not_defined     — check выполнен, значение не найдено.
      not_applicable  — check не применим к doc_type документа.
      not_executed    — check не выполнялся для этого документа.
      error           — техническая ошибка выполнения.

    Location contract:
      has_location_fallback=false + clause_ref/page → exact pinpoint.
      has_location_fallback=true → approximate / unavailable (conf='low').
      clause_ref/page могут быть null при fallback.

    См. docs/dd_grid_v1_contract.md для полного API contract.
    """

    deal_id: str
    run_id: str

    global_groups: list[DDGridGlobalGroupDTO]
    doc_type_classes: list[DDGridDocTypeClassDTO]
    column_registry: dict[str, DDGridColumnDTO]
    cell_values: dict[str, dict[str, DDGridCellValueDTO]]
    drawer_contents: dict[str, dict[str, DDGridDrawerDTO]]
    documents_meta: list[DDGridDocumentMetaDTO]


    




    
