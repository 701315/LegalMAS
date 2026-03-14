# src/api/schemas/playbooks.py


"""
Pydantic-схемы для плейбуков (Playbook / PlaybookVersion) и конструктора плейбука.

Зачем нужны эти модели:
- описывают запросы/ответы для эндпоинтов /playbooks (см. endpoints/playbooks.py);
- отделяют внешнее API (что видит фронтенд) от внутренних ORM-моделей и YAML;
- позволяют документировать контракт:
  * PlaybookCreateRequest — как фронт описывает конфигурацию плейбука
    (bundles + include_ids + exclude_ids + profile + model_config_id);
  * PlaybookCreateResponse — что возвращает бэкенд после создания версии;
  * GlobalCheckInfo — краткое описание одной глобальной проверки для UI;
  * BundleInfo — описание преднастроенного набора проверок;
  * PlaybookVersionShort — упрощённое представление PlaybookVersion для списков;
  * PlaybookLineShort — логический плейбук (шаблон) для страницы выбора.
"""

from __future__ import annotations
from typing import Any, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field
from typing import Literal


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
    - указывает model_config_id, с которым плейбук будет работать;
    - опционально привязывает версию к логическому плейбуку (playbook_id).
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

    playbook_id: Optional[UUID] = Field(
        default=None,
        description=(
            "ID логического Playbook (шаблона), к которому относится эта версия. "
            "Если не задано — версия будет без привязки к линии."
        ),
    )


class PlaybookCreateResponse(BaseModel):
    """Ответ с ID созданной версии плейбука."""

    id: UUID
    name: str
    semver: str
    status: str
    playbook_id: Optional[UUID] = Field(
        default=None,
        description="ID логического Playbook, к которому привязана версия (если есть).",
    )


class PlaybookVersionShort(BaseModel):
    """Упрощённое представление PlaybookVersion (для списков/селектора)."""

    id: UUID
    name: str
    semver: str
    status: str
    playbook_id: Optional[UUID] = Field(
        default=None,
        description="ID логического Playbook (для группировки версий на UI).",
    )


class PlaybookVersionDetail(BaseModel):
    """
    Детальное представление версии плейбука.

    Используется для просмотра "состава" плейбука:
    - compiled_checks;
    - триггеры, шаблоны DD-запросов, section_markers, classification_config.
    """

    id: UUID
    name: str
    semver: str
    status: str
    playbook_id: Optional[UUID] = None
    model_config_id: Optional[UUID] = None

    compiled_checks: Optional[dict[str, Any]] = None
    trigger_definitions: Optional[dict[str, Any]] = None
    dd_request_templates: Optional[dict[str, Any]] = None
    section_markers: Optional[dict[str, Any]] = None
    classification_config: Optional[dict[str, Any]] = None


class PlaybookLineShort(BaseModel):
    """
    Логический плейбук (Playbook) для страницы выбора шаблонов.

    Используется фронтом, чтобы:
    - показать список продуктов/шаблонов (Real estate RU core, M&A RU full и т.п.);
    - фильтровать по типу сделки, юрисдикции, языку, risk_profile.
    """

    id: UUID
    code: str
    title: str
    description: Optional[str] = None
    deal_type: Optional[str] = Field(
        default=None,
        description="Deal type: real_estate, mna, nda, corporate, etc.",
    )
    jurisdiction: Optional[str] = Field(
        default=None,
        description="Основная юрисдикция, например RU, EN, DE.",
    )
    language: Optional[str] = Field(
        default=None,
        description="Основной язык документов: 'ru', 'en' и т.п.",
    )
    risk_profile: Optional[str] = Field(
        default=None,
        description="Доп. профиль/роль: standard, high, vendor, buyer и т.п.",
    )


class PlaybookCheckInfo(BaseModel):
    code: str
    title: str
    description: str | None = None
    topic_code: str
    file_path: str

class PlaybookTopicInfo(BaseModel):
    topic_code: str
    topic_name: str
    checks: list[PlaybookCheckInfo]


class PlaybookLineItemPayload(BaseModel):
    kind: Literal["topic", "check"]
    topic_code: str | None = None
    check_code: str | None = None
    order_index: int

class PlaybookLineCreate(BaseModel):
    title: str
    description: str | None = None
    deal_type: str | None = None
    jurisdiction: str | None = None
    language: str | None = None
    items: list[PlaybookLineItemPayload]

class PlaybookLineDetail(PlaybookLineShort):
    items: list[PlaybookLineItemPayload]
