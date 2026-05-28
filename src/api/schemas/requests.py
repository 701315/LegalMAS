# src/api/schemas/requests.py

"""
Pydantic-схемы для DD-запросов (Request List).
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class DDRequestCreate(BaseModel):
    """
    Создание DD-запроса вручную.

    Используется, когда юрист добавляет запрос сам,
    а не только по шаблонам из YAML.
    """

    priority: str = Field(..., description="critical / high / medium")
    text: str = Field(..., min_length=1, max_length=5000)
    addressee: str = Field(
        default="Юридический советник",
        description="Кому адресован запрос (пример: 'Юридический советник')",
    )
    document_ids: list[UUID] = Field(default_factory=list)
    check_result_ids: list[UUID] = Field(default_factory=list)


class DDRequestUpdate(BaseModel):
    """
    Обновление существующего DD-запроса.
    """

    priority: str | None = None
    text: str | None = None
    addressee: str | None = None  # можно поменять адресата
    status: str | None = None  # open / in_progress / resolved


class DDRequestResponse(BaseModel):
    """
    Представление DD-запроса в ответах API.

    Новые поля:
      - check_id: по какой проверке создан запрос (если из YAML);
      - addressee: кому адресован (из dd_request_templates или ручной);
      - structured_values: какие извлечённые значения упоминаются;
      - source: откуда запрос (yaml_template / manual / aggregator).
    """

    id: UUID
    deal_id: UUID
    priority: str
    text: str
    status: str

    check_id: str | None = None
    addressee: str = "Юридический советник"
    structured_values: list[dict[str, Any]] = Field(default_factory=list)
    source: str = "manual"  # "yaml_template" | "manual" | "aggregator"

    document_refs: list[UUID]
    evidence_refs: list[UUID]
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}
