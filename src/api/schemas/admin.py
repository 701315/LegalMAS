# src/api/schemas/admin.py

"""
Pydantic схемы для административного API.

Содержит:
- Схемы для управления tenant'ами (клиентами системы).
- Схемы для управления пользователями tenant'а.
- Устаревшие схемы YAML-инструкций (сохранены).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


# ── YAML Instructions (существующие схемы) ────────────────────────────────


class YamlInstructionDTO(BaseModel):
    """Метаданные YAML-инструкции для типа документа."""

    doc_type: str
    filename: str
    checks_count: int
    triggers_count: int
    dd_request_templates_count: int
    has_structured_extraction: bool
    profiles: list[str] | None = None
    error: str | None = None


# ── Tenant schemas ─────────────────────────────────────────────────────────


class TenantCreate(BaseModel):
    """
    Данные для создания нового клиента (tenant'а).

    Поля:
    - name: отображаемое название (например "Ромашка Лигал");
    - slug: уникальный идентификатор (латиница, цифры, дефис);
    - notes: произвольные заметки администратора (опционально).
    """

    name: str = Field(..., min_length=1, max_length=500)
    slug: str = Field(
        ...,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$|^[a-z0-9]$",
        description="Только строчные латинские буквы, цифры и дефис",
    )
    notes: str | None = Field(default=None, max_length=2000)


class TenantUpdate(BaseModel):
    """Частичное обновление tenant'а. Передавать только изменяемые поля."""

    name: str | None = Field(default=None, min_length=1, max_length=500)
    notes: str | None = None
    clear_notes: bool = False


class TenantResponse(BaseModel):
    """Ответ API с данными tenant'а."""

    id: uuid.UUID
    name: str
    slug: str
    is_active: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TenantWithStats(TenantResponse):
    """
    Tenant с дополнительной статистикой.
    Используется в списке tenant'ов для superadmin.
    """

    users_count: int = 0
    deals_count: int = 0


# ── User schemas ───────────────────────────────────────────────────────────


class UserCreate(BaseModel):
    """
    Данные для создания нового пользователя в tenant'е.

    Поля:
    - email     : уникальный email (используется для логина);
    - password  : пароль в открытом виде (хэшируется на сервере);
    - full_name : полное имя для отображения в UI (опционально);
    - system_role: системная роль: tenant_admin или member.
    """

    email: str = Field(..., min_length=1, max_length=320)
    password: str = Field(..., min_length=6, max_length=128)
    full_name: str | None = Field(default=None, max_length=500)
    system_role: str = Field(
        default="member",
        description="Системная роль: tenant_admin или member",
    )


class UserUpdate(BaseModel):
    """Частичное обновление пользователя."""

    full_name: str | None = None
    clear_full_name: bool = False
    system_role: str | None = None
    password: str | None = Field(default=None, min_length=6, max_length=128)
    is_active: bool | None = None


class UserResponse(BaseModel):
    """Ответ API с данными пользователя."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    full_name: str | None
    system_role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


    