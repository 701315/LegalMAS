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
  языковые поля сделки, технические поля (created_at, last_run_id и т.п.).
- DealCreate — данные, которые фронтенд отправляет при создании новой сделки
  на экране "Новый проект".
- DealPlaybookHistoryItem — отдельная запись истории смены playbook‑версии
  для сделки, построенная на основе записей аудита.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from core.constants import PIIMode


def _normalize_language_code(value: str | None) -> str | None:
    """
    Привести код языка к единому виду.

    Для непрофессионального программиста:
    - пользователь или фронт могут прислать "ru", "Ru", " en ";
    - в БД и API мы хотим хранить единый формат: "RU", "EN";
    - пустые строки здесь не допускаются.
    """
    if value is None:
        return None

    normalized = value.strip().upper()
    if not normalized:
        raise ValueError("Language code must not be empty.")

    return normalized


def _normalize_languages_list(value: list[str] | None) -> list[str] | None:
    """
    Нормализовать список языков:
    - убрать пустые строки,
    - привести к UPPERCASE,
    - убрать дубликаты с сохранением порядка.
    """
    if value is None:
        return None

    normalized: list[str] = []
    seen: set[str] = set()

    for item in value:
        lang = _normalize_language_code(item)
        if lang is None:
            continue
        if lang not in seen:
            normalized.append(lang)
            seen.add(lang)

    return normalized or None


class DealResponse(BaseModel):
    """
    Краткая информация о сделке для списка сделок и детальной карточки.

    Используется:
    - в списке сделок на главной странице;
    - на странице "Обзор сделки";
    - в launch/overview UI для показа языков сделки и статуса language discovery.
    """

    id: UUID
    tenant_id: UUID

    name: str
    summary: str | None = None
    deal_type: str | None = None
    jurisdiction: str | None = None

    # Список языков документов сделки (обновляется deal-level discovery).
    languages: list[str] | None = None

    # Deal-level статус pre-run language discovery:
    # pending / processing / completed / failed / partial.
    language_discovery_status: str | None = None

    # Основной язык анализа сделки.
    # Это значение выбирает человек явно.
    primary_language: str | None = None

    status: str
    pii_mode: str
    profile: str

    playbook_version_id: UUID | None = None
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

    # Режим проверок последнего запуска:
    # - "global_only"         — только глобальный плейбук;
    # - "doc_type_only"       — только проверки по типам документов;
    # - "global_and_doc_type" — оба слоя.
    last_run_checks_mode: Literal["global_only", "doc_type_only", "global_and_doc_type"] | None = (
        None
    )

    # Стратегия пайплайна последнего запуска:
    # - "REUSE_STRUCTURE" / "FULL_RERUN" / другие значения.
    # Тип str оставлен более широким, чтобы новые стратегии
    # не требовали немедленных правок на фронте.
    last_run_pipeline_strategy: str | None = None

    @field_validator("primary_language")
    @classmethod
    def validate_primary_language(cls, value: str | None) -> str | None:
        return _normalize_language_code(value)

    @field_validator("languages")
    @classmethod
    def validate_languages(cls, value: list[str] | None) -> list[str] | None:
        return _normalize_languages_list(value)

    model_config = {"from_attributes": True}


class DealCreate(BaseModel):
    """
    Данные для создания новой сделки (проекта) через API.

    Production-правило:
    - основной язык анализа выбирает человек;
    - backend не должен определять его автоматически.
    """

    name: str
    summary: str | None = Field(default=None, max_length=5000)
    deal_type: str | None = None
    jurisdiction: str | None = None
    languages: list[str] | None = None

    # Явный выбор человека: основной язык анализа.
    primary_language: str | None = None

    # По умолчанию — локальный режим ПДн
    pii_mode: str = PIIMode.LOCAL_ONLY.value

    # Профиль проверок
    profile: str = "full"

    playbook_version_id: UUID | None = None
    metadata_: dict | None = None

    @field_validator("primary_language")
    @classmethod
    def validate_primary_language(cls, value: str | None) -> str | None:
        return _normalize_language_code(value)

    @field_validator("languages")
    @classmethod
    def validate_languages(cls, value: list[str] | None) -> list[str] | None:
        return _normalize_languages_list(value)

    @model_validator(mode="after")
    def validate_language_consistency(self) -> "DealCreate":
        """
        Проверка согласованности языков.

        Для непрофессионального программиста:
        - если пользователь указал список languages и отдельно primary_language,
          основной язык должен входить в этот список;
        - это защищает от нелогичных данных.
        """
        if (
            self.primary_language is not None
            and self.languages is not None
            and self.primary_language not in self.languages
        ):
            raise ValueError("primary_language must be one of the values from languages.")

        return self


class DealUpdate(BaseModel):
    """
    Частичное обновление сделки (PATCH /api/v1/deals/{deal_id}).

    Поддерживаем:
    - summary;
    - languages;
    - primary_language.

    Это нужно, чтобы UI мог принудительно требовать от человека
    выбор основного языка анализа.
    """

    summary: str | None = Field(default=None, max_length=5000)
    languages: list[str] | None = None
    primary_language: str | None = None

    @field_validator("primary_language")
    @classmethod
    def validate_primary_language(cls, value: str | None) -> str | None:
        return _normalize_language_code(value)

    @field_validator("languages")
    @classmethod
    def validate_languages(cls, value: list[str] | None) -> list[str] | None:
        return _normalize_languages_list(value)

    @model_validator(mode="after")
    def validate_language_consistency(self) -> "DealUpdate":
        if (
            self.primary_language is not None
            and self.languages is not None
            and self.primary_language not in self.languages
        ):
            raise ValueError("primary_language must be one of the values from languages.")

        return self


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
