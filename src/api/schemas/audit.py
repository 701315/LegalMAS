# src/api/schemas/audit.py

"""
Pydantic-схемы для endpoint'ов журнала аудита.

Контракт строго соответствует фронтовым типам:
  - AuditLogEntry (src/types/exports.ts)
  - PaginatedResponse<T> (src/types/common.ts)
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Dict, Generic, List, Optional, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, computed_field


class AuditLogEntrySchema(BaseModel):
    """
    Одна запись в журнале аудита.
    Поля совпадают с фронтовым AuditLogEntry из src/types/exports.ts.
    """

    # ConfigDict(from_attributes=True) позволяет создавать схему
    # напрямую из ORM-объекта через model_validate(orm_row)
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    deal_id: Optional[UUID] = None
    action: str
    actor: str
    actor_role: Optional[str] = None
    details: Dict[str, Any] = {}
    created_at: datetime


T = TypeVar("T")


class AuditLogPage(BaseModel):
    """
    Пагинированный ответ — точный аналог PaginatedResponse<AuditLogEntry>
    из src/types/common.ts.

    Фронт ожидает все эти поля:
      items, total, page, per_page, total_pages, has_next, has_previous
    """

    items: List[AuditLogEntrySchema]
    total: int
    page: int
    per_page: int

    # Вычисляемые поля — backend сам считает, фронту не нужно это делать
    @computed_field  # type: ignore[misc]
    @property
    def total_pages(self) -> int:
        if self.per_page <= 0:
            return 1
        return max(1, math.ceil(self.total / self.per_page))

    @computed_field  # type: ignore[misc]
    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages

    @computed_field  # type: ignore[misc]
    @property
    def has_previous(self) -> bool:
        return self.page > 1
    
    