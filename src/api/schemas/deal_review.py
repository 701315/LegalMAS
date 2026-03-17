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

from typing import Any

from pydantic import BaseModel


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
    - structured_data с извлечёнными полями.
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
    - какие structured_values были использованы.
    """
    request_id: str
    priority: str
    check_id: str | None
    check_name: str | None
    addressee: str
    text: str
    document_names: list[str]
    doc_types: list[str]
    structured_values: list[dict[str, Any]]


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
    """
    document_name: str
    doc_type: str
    check_name: str
    field_name: str
    field_value: str
    field_format: str        # "money", "date", "entity_name", "text"
    page: int | None
    clause_uid: str


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


