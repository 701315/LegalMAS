# src/api/schemas/results.py

"""
Pydantic-схемы для результатов проверок (check_results) и evidence.

Важно для фронта:
- На уровне отдельного результата проверки (CheckResultResponse) мы
  передаём базовые данные документа:
    * document_id / document_name,
    * doc_type.
- Через другие API (эндпоинты классификации/документа) фронт также
  получает applicable_triggers для документа.
- Пара (doc_type, applicable_triggers) образует «профиль документа»,
  который UI может использовать для отображения:
    * базового типа документа (например, "договор купли-продажи недвижимости"),
    * активных сценариев (ипотека, маткапитал, наследование, судебная продажа и т.п.).
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class LocationField(BaseModel):
    page: int | None = None
    clause_uid: str | None = None
    element_id: str | None = None
    start_page: int | None = None
    end_page: int | None = None
    path_titles: list[str] | None = None


class FieldQC(BaseModel):
    status: str | None = None  # "pending" | "accepted" | "rejected" | "auto_accepted"
    by: str | None = None
    comment: str | None = None
    at: str | None = None  # ISO8601


class StructuredField(BaseModel):
    value: Any
    unit: str | None = None
    source: str | None = None
    confidence: float | None = None
    found: bool | None = True
    location: LocationField | None = None
    qc: FieldQC | None = None


StructuredDataDict = dict[str, StructuredField]


class CheckResultResponse(BaseModel):
    """
    Один результат проверки.

    Это "одна строка" в DD Grid:
    - какая проверка (check_id / check_name),
    - какой результат (fail / pass / unclear),
    - уровень риска (severity),
    - текстовое значение и уверенность,
    - откуда взято (detector_used),
    - флаги качества и QC-статус,
    - базовые данные документа,
    - structured_data и условные проверки.

    В контексте профиля документа:
    - Поле doc_type даёт базовый тип документа, к которому относится эта проверка.
    - applicable_triggers для документа в целом приходит из других эндпоинтов
      (например, из API документа/классификации).
    - Фронт может комбинировать doc_type из этой схемы и applicable_triggers
      из классификации, чтобы рисовать:
        * «тип документа»,
        * и «сценарии» (ипотека, маткапитал, наследование и т.п.)
          рядом с результатами проверок.
    """

    id: UUID
    run_id: UUID
    document_id: UUID
    check_id: str
    check_name: str
    result: str  # fail / pass / unclear
    severity: str  # critical / high / medium / pass / unclear
    value_text: str | None
    confidence: float | None
    detector_used: str | None
    quality_flags: dict | None
    qc_status: str
    qc_by: str | None
    qc_comment: str | None
    qc_at: datetime | None
    created_at: datetime

    # Новый важный атрибут: источник определения проверки
    # (глобальный плейбук, плейбук по типу документа, клиентский кастом и т.п.).
    # Это напрямую маппится из CheckResult.origin и используется фронтом
    # для переключателей "Глобальный плейбук" / "По типу документа".
    origin: str | None = None

    # Нормализованный тип источника проверки для фронта и внешнего API.
    # Значения:
    # - "global"  — проверки из глобального плейбука;
    # - "doctype" — проверки из плейбука по типу документа;
    # - "custom"  — все прочие/кастомные источники.
    origin_type: str | None = None

    # Обогащаем из таблицы documents (JOIN в репозитории/сервисе)
    document_name: str | None = None
    doc_type: str | None = None
    doc_requires_manual_review: bool | None = None  # ← сюда

    # Новое: структурированные данные по проверке
    structured_data: StructuredDataDict | None = None

    # Новое: метаданные условной проверки
    conditional_check_triggered: bool = False
    trigger_name: str | None = None

    model_config = {"from_attributes": True}


class EvidenceResponse(BaseModel):
    """
    Детальное evidence для результата проверки.

    Обычно берётся из NDJSON-файлов в MinIO (сырое и/или санитайзнутое).
    """

    result_id: UUID
    check_id: str
    check_name: str
    element_id: str | None
    snippet: str
    page: int | None
    clause_uid: str | None
    bbox: list[float] | None
    confidence: float | None
    source: str  # "raw" или "sanitized"
    quality_flags: dict | None
    structured_data: dict[str, Any] | None = None


class StructuredDataResponse(BaseModel):
    """
    DEPRECATED: использовалась для старого эндпоинта
    GET /documents/{doc_id}/structured-data, который сейчас удалён.

    Схему можно переиспользовать в будущих сценариях
    (например, для генерации отчётов), но текущий API её не возвращает.
    """

    document_id: UUID
    document_name: str
    doc_type: str | None
    extracted_values: list[dict]  # [{check_id, field_name, field_value, page, clause_uid}]
    total_extracted: int
