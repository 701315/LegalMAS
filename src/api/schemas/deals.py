# src/api/schemas/deals.py

"""
Pydantic‑схемы для работы со сделками в REST API.

Эти модели используются для:
- выдачи информации о сделках на фронт (списки, детальные карточки);
- приёма данных при создании новых проектов;
- отображения истории смены плейбуков.

Основные схемы:
- DealResponse — полное представление сделки для UI: базовые атрибуты,
  playbook, выбранный профиль модели (model_config_id / model_config_name),
  технические поля (created_at, last_run_id и т.п.).
- DealCreate — данные, которые фронтенд отправляет при создании новой сделки
  на экране "Новый проект".
- DealPlaybookHistoryItem — отдельная запись истории смены playbook‑версии
  для сделки, построенная на основе записей аудита.
"""

from uuid import UUID
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from core.constants import DealStatus, PIIMode


class DealResponse(BaseModel):
    """
    Краткая информация о сделке для списка сделок и детальной карточки.

    Используется:
    - в списке сделок на главной странице;
    - на странице "Обзор сделки" (там же отображаются playbook и профиль модели).
    """

    id: UUID
    tenant_id: UUID

    name: str
    summary: str | None = None
    deal_type: str | None = None
    jurisdiction: str | None = None
    # Список языков документов сделки (из документов).
    languages: list[str] | None = None
    # Новый атрибут: основной язык сделки, выбирается пользователем
    # из списка languages на отдельном шаге.
    primary_language: str | None = None

    # Можно оставить как str, чтобы не тянуть enum на фронт
    status: str  # или DealStatus
    pii_mode: str  # или PIIMode
    profile: str

    # Связанные настройки анализа
    playbook_version_id: UUID | None = None

    # Новый явный выбор профиля модели на уровне сделки
    model_config_id: UUID | None = None

    # Человекочитаемое имя профиля, который фактически будет использоваться:
    # либо явный профиль сделки, либо профиль из PlaybookVersion.
    model_config_name: str | None = None

    # Флаг для UI: есть ли документы,
    # переклассифицированные вручную и требующие перезапуска анализа.
    has_pending_manual_reclassifications: bool = False

    metadata_: dict | None = None

    created_at: datetime
    updated_at: datetime | None = None

    # ID последнего запуска анализа по сделке (если был)
    last_run_id: UUID | None = None

    # НОВОЕ: агрегированная информация о последнем Run

    # Режим проверок последнего запуска:
    # - "global_only"         — только глобальный плейбук;
    # - "doc_type_only"       — только проверки по типам документов;
    # - "global_and_doc_type" — оба слоя.
    last_run_checks_mode: Literal[
        "global_only", "doc_type_only", "global_and_doc_type"
    ] | None = None

    # Стратегия пайплайна последнего запуска:
    # - "REUSE_STRUCTURE" / "FULL_RERUN" / другие значения.
    # Тип str оставлен более широким, чтобы новые стратегии
    # не требовали немедленных правок на фронте.
    last_run_pipeline_strategy: str | None = None

    model_config = {"from_attributes": True}


class DealCreate(BaseModel):
    """
    Данные для создания новой сделки (проекта) через API.
    Используется фронтом на экране "Новый проект".
    """

    name: str
    summary: str | None = Field(default=None, max_length=5000)
    deal_type: str | None = None
    jurisdiction: str | None = None
    languages: list[str] | None = None

    # по умолчанию — локальный режим ПДн
    pii_mode: str = PIIMode.LOCAL_ONLY.value
    # профиль проверок
    profile: str = "full"

    playbook_version_id: UUID | None = None
    metadata_: dict | None = None
    # Профиль модели при создании можно пока не задавать,
    # выбор делаем уже после, через PATCH /deals/{id}/model-config.
    # Если захочешь — можно добавить сюда:
    # model_config_id: UUID | None = None


class DealUpdate(BaseModel):
    """
    Частичное обновление сделки (PATCH /api/v1/deals/{deal_id}).
    Пока поддерживаем только summary.
    """
    summary: str | None = Field(default=None, max_length=5000)
    

class DealPlaybookHistoryItem(BaseModel):
    """
    Одна запись истории смены playbook-версии для сделки.
    Строится на основе AuditLog с action='SET_DEAL_PLAYBOOK'.
    """

    created_at: datetime
    actor: str
    actor_role: str | None = None
    old_playbook_version_id: UUID | None = None
    new_playbook_version_id: UUID | None = None
    playbook_id: UUID | None = None
    playbook_name: str | None = None
    semver: str | None = None