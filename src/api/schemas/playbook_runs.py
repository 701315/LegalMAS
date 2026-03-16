# src/api/schemas/playbook_runs.py

"""
Схемы для операций:
- пересборка плейбука сделки и пересчёт результатов (rebuild-and-rerun);
- история изменений плейбука по сделке.

Важный момент:

Сейчас у нас два уровня конфигурации плейбука:

1) "Рецепт" (config), который используется компилятором:
   - bundles: базовые пресеты (playbooks/bundles/*.yaml),
   - include_ids: какие check_id добавить,
   - exclude_ids: какие check_id убрать,
   - profile: глубина проверки (core/full/max).

2) Фактический состав (enabled_check_ids/disabled_check_ids),
   который фронтенд получает и редактирует через UI плашек.

Чтобы не ломать уже существующий код, мы:

- оставляем bundles/include_ids/exclude_ids/profile для текущей логики
  (пересборка из прошлой конфигурации и частичное перекрытие),
- добавляем optional-поля enabled_check_ids/disabled_check_ids,
  чтобы фронт мог прислать "готовый" набор чеков после правки UI.

Если enabled_check_ids/disabled_check_ids не заданы (пустые),
бэкенд будет использовать bundles/include_ids/exclude_ids, как раньше.
"""


from __future__ import annotations


from datetime import datetime
from typing import List, Optional
from uuid import UUID


from pydantic import BaseModel, Field


class DealPlaybookRebuildRequest(BaseModel):
    """
    Запрос на пересборку плейбука для сделки и запуск нового run.

    Варианты использования:

    1) Старый / "рецептный" режим (backward-compatible):
       - передать bundles/include_ids/exclude_ids/profile,
       - оставить enabled_check_ids/disabled_check_ids пустыми,
       - тогда конфигурация собирается из:
         * текущего PlaybookConfig компилированного плейбука,
         * перекрытий из bundles/include/exclude/profile.

    2) Новый режим "после UI-плашек":
       - фронтенд показывает юристу дерево всех доступных checks,
         стартуя, например, с конфигурации шаблона или текущего плейбука;
       - юрист снимает/ставит галочки;
       - фронтенд отправляет:
           enabled_check_ids  — итоговый список включённых check_id,
           disabled_check_ids — явно выключенные check_id (опционально),
         при этом bundles/include_ids/exclude_ids можно не заполнять.
       - на бэкенде мы можем использовать enabled_check_ids как include_ids,
         а disabled_check_ids — как exclude_ids, либо более сложную логику.

    Это позволяет эволюционно перейти от "рецептов" к явному составу,
    не ломая существующий API.
    """

    # --- "Рецепт" для компилятора (как было раньше) ---

    bundles: List[str] = Field(
        default_factory=list,
        description="Список bundle-id для нового плейбука. "
        "Если пусто и не заданы enabled_check_ids — использовать текущие из config.",
    )
    include_ids: List[str] = Field(
        default_factory=list,
        description="Чеки, которые явно добавить поверх bundles "
        "(используются, если enabled_check_ids не заданы).",
    )
    exclude_ids: List[str] = Field(
        default_factory=list,
        description="Чеки, которые явно исключить (используются, если enabled_check_ids не заданы).",
    )
    profile: Optional[str] = Field(
        default=None,
        description="Профиль глубины проверки (core/full/quick/max и т.п.). "
        "Если не задан и нет enabled_check_ids — берётся из текущего config.",
    )

    # --- Новый уровень: явный итоговый состав после UI-плашек ---

    enabled_check_ids: List[str] = Field(
        default_factory=list,
        description=(
            "Итоговый список check_id, которые должны быть включены в плейбук "
            "после правок юриста на UI. "
            "Если непустой, может использоваться как основной источник состава."
        ),
    )
    disabled_check_ids: List[str] = Field(
        default_factory=list,
        description=(
            "Список check_id, которые явно выключены юристом по сравнению с базовым набором. "
            "Может использоваться вместе с enabled_check_ids для более тонкой логики."
        ),
    )

    # На будущее можно добавить флаг "force_reclassify", но пока оставим только запуск checks.
    # через CheckRunner (run_deal_checks).


class DealPlaybookRebuildResponse(BaseModel):
    """
    Ответ после пересборки плейбука и запуска нового run.

    Используется фронтендом, чтобы:
    - обновить ID текущего плейбука проекта (Deal.playbook_version_id);
    - показать новый run как "актуальный";
    - при необходимости перейти на страницу статуса run.
    """

    deal_id: UUID
    new_playbook_version_id: UUID
    new_run_id: UUID


class DealPlaybookHistoryItem(BaseModel):
    """
    Один элемент истории изменений плейбука по сделке.

    Основан на связке Run + PlaybookVersion:
    - какой плейбук (name/semver) применялся;
    - какой run выполнялся;
    - статус run и временные метки;
    - профиль проверки.
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

    Список всех run'ов с их плейбуками (новые сначала), чтобы
    на фронтенде можно было показать:

    - как менялся плейбук по сделке (версии/semver);
    - какие запуски были по каждой версии;
    - какой run сейчас актуален.
    """

    deal_id: UUID
    items: List[DealPlaybookHistoryItem]
