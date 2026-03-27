# src/api/schemas/results.py

"""
Pydantic-схемы для результатов проверок (check_results) и evidence.
"""

from uuid import UUID
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel



class LocationField(BaseModel):
    page: Optional[int] = None
    clause_uid: Optional[str] = None
    element_id: Optional[str] = None
    start_page: Optional[int] = None
    end_page: Optional[int] = None
    path_titles: Optional[list[str]] = None

class FieldQC(BaseModel):
    status: Optional[str] = None  # "pending" | "accepted" | "rejected" | "auto_accepted"
    by: Optional[str] = None
    comment: Optional[str] = None
    at: Optional[str] = None      # ISO8601

class StructuredField(BaseModel):
    value: Any
    unit: Optional[str] = None
    source: Optional[str] = None
    confidence: Optional[float] = None
    found: Optional[bool] = True
    location: Optional[LocationField] = None
    qc: Optional[FieldQC] = None

StructuredDataDict = Dict[str, StructuredField]


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
    """

    id: UUID
    run_id: UUID
    document_id: UUID
    check_id: str
    check_name: str
    result: str               # fail / pass / unclear
    severity: str             # critical / high / medium / pass / unclear
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
    source: str               # "raw" или "sanitized"
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
    extracted_values: list[dict]   # [{check_id, field_name, field_value, page, clause_uid}]
    total_extracted: int


