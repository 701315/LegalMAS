"""
Pydantic-схемы для плейбуков (PlaybookVersion) и конструктора плейбука.

Зачем нужны эти модели:
- описывают запросы/ответы для эндпоинтов /playbooks (см. endpoints/playbooks.py);
- отделяют внешнее API (что видит фронтенд) от внутренних ORM-моделей и YAML;
- позволяют документировать контракт:
  * PlaybookCreateRequest — как фронт описывает конфигурацию плейбука
    (bundles + include_ids + exclude_ids + profile + model_config_id);
  * PlaybookCreateResponse — что возвращает бэкенд после создания версии;
  * GlobalCheckInfo — краткое описание одной глобальной проверки для UI;
  * BundleInfo — описание преднастроенного набора проверок;
  * PlaybookVersionShort — упрощённое представление PlaybookVersion для списков.
"""


from __future__ import annotations

from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class GlobalCheckInfo(BaseModel):
    """Краткая информация о глобальном чекe для UI-списка."""

    id: str
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    group: Optional[str] = None
    severity: str
    doc_types: List[str] = Field(default_factory=list)


class BundleInfo(BaseModel):
    """Информация о bundle (preset) для UI."""

    id: str
    name: str
    description: Optional[str] = None
    check_ids: List[str]


class PlaybookCreateRequest(BaseModel):
    """
    Запрос на создание новой версии плейбука.

    Варианты:
    - пользователь выбирает один или несколько bundles;
    - добавляет/убирает отдельные check_ids;
    - задаёт профиль глубины (profile);
    - указывает model_config_id, с которым плейбук будет работать.
    """

    name: Optional[str] = Field(
        default=None,
        description="Имя плейбука. Если не задано — можно сгенерировать на бэке.",
    )
    bundles: List[str] = Field(
        default_factory=list,
        description="Список bundle-id, которые будут включены (mna_core, full, ...).",
    )
    include_ids: List[str] = Field(
        default_factory=list,
        description="Чек-ID, которые нужно добавить поверх bundle'ов.",
    )
    exclude_ids: List[str] = Field(
        default_factory=list,
        description="Чек-ID, которые нужно исключить из bundle'ов.",
    )
    profile: Optional[str] = Field(
        default=None,
        description="Профиль глубины проверки: core/full/quick и т.п.",
    )

    model_config_id: UUID = Field(
        ...,
        description="ID ModelConfig, который будет использоваться раннером.",
    )

    semver: Optional[str] = Field(
        default=None,
        description="Явное значение semver (если нужно задать с фронта).",
    )
    status: Optional[str] = Field(
        default=None,
        description="Статус версии плейбука: draft/stable/default. По умолчанию draft.",
    )


class PlaybookCreateResponse(BaseModel):
    """Ответ с ID созданной версии плейбука."""

    id: UUID
    name: str
    semver: str
    status: str


class PlaybookVersionShort(BaseModel):
    """Упрощённое представление PlaybookVersion (для списков/селектора)."""

    id: UUID
    name: str
    semver: str
    status: str
