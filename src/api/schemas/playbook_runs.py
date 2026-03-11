"""
Схемы для операций:
- пересборка плейбука сделки и пересчёт результатов (rebuild-and-rerun);
- история изменений плейбука по сделке.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class DealPlaybookRebuildRequest(BaseModel):
    """
    Запрос на пересборку плейбука для сделки и запуск нового run.

    Варианты:
    - передать полную новую конфигурацию (bundles/include/exclude/profile);
    - оставить поля пустыми, чтобы использовать текущую конфигурацию
      из PlaybookVersion.compiled_checks.meta.config.
    """

    bundles: List[str] = Field(
        default_factory=list,
        description="Список bundle-id для нового плейбука. Если пусто — использовать текущие.",
    )
    include_ids: List[str] = Field(
        default_factory=list,
        description="Чеки, которые явно добавить поверх bundles.",
    )
    exclude_ids: List[str] = Field(
        default_factory=list,
        description="Чеки, которые явно исключить.",
    )
    profile: Optional[str] = Field(
        default=None,
        description="Профиль глубины проверки (core/full/quick и т.п.).",
    )

    # На будущее можно добавить флаг "force_reclassify", но пока оставим только run_checks.


class DealPlaybookRebuildResponse(BaseModel):
    """
    Ответ после пересборки плейбука и запуска нового run.

    Используется фронтендом, чтобы:
    - обновить ID текущего плейбука проекта;
    - показать новый run как "актуальный".
    """

    deal_id: UUID
    new_playbook_version_id: UUID
    new_run_id: UUID


class DealPlaybookHistoryItem(BaseModel):
    """
    Один элемент истории изменений плейбука по сделке.

    Основан на связке Run + PlaybookVersion.
    """

    run_id: UUID
    playbook_version_id: UUID
    playbook_name: str
    playbook_semver: str
    run_status: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    profile: str


class DealPlaybookHistoryResponse(BaseModel):
    """
    История плейбуков для сделки.

    Список всех run'ов с их плейбуками (новые сначала).
    """

    deal_id: UUID
    items: List[DealPlaybookHistoryItem]
