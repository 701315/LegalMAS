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

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class GlobalCheckInfo(BaseModel):
    """Краткая информация о глобальном чекe для UI-списка."""

    id: str
    name: str
    description: str | None = None
    category: str | None = None
    group: str | None = None
    severity: str
    doc_types: list[str] = Field(default_factory=list)


class BundleInfo(BaseModel):
    """Информация о bundle (preset) для UI."""

    id: str
    name: str
    description: str | None = None
    check_ids: list[str]


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

    name: str | None = Field(
        default=None,
        description="Имя плейбука. Если не задано — можно сгенерировать на бэке.",
    )
    bundles: list[str] = Field(
        default_factory=list,
        description="Список bundle-id, которые будут включены (mna_core, full, ...).",
    )
    include_ids: list[str] = Field(
        default_factory=list,
        description="Чек-ID, которые нужно добавить поверх bundle'ов.",
    )
    exclude_ids: list[str] = Field(
        default_factory=list,
        description="Чек-ID, которые нужно исключить из bundle'ов.",
    )
    profile: str | None = Field(
        default=None,
        description="Профиль глубины проверки: core/full/quick и т.п.",
    )

    model_config_id: UUID | None = Field(
        description=(
            "ID ModelConfig, который будет использоваться раннером. "
            "Обязательное поле: версия плейбука всегда должна быть привязана "
            "к конкретной конфигурации модели."
        ),
    )

    semver: str | None = Field(
        default=None,
        description="Явное значение semver (если нужно задать с фронта).",
    )
    status: str | None = Field(
        default=None,
        description="Статус версии плейбука: draft/stable/default. По умолчанию draft.",
    )

    playbook_id: UUID | None = Field(
        default=None,
        description=(
            "ID логического Playbook (шаблона), к которому относится эта версия. "
            "Если не задано — версия будет без привязки к линии."
        ),
    )

    from_line_id: UUID | None = Field(
        default=None,
        description=(
            "Если задано — версия будет собрана на основе шаблона PlaybookLine "
            "с таким ID: его items будут превращены в список глобальных checks."
        ),
    )


class PlaybookCreateResponse(BaseModel):
    """Ответ с ID созданной версии плейбука."""

    id: UUID
    name: str
    semver: str
    status: str
    playbook_id: UUID | None = Field(
        default=None,
        description="ID логического Playbook, к которому привязана версия (если есть).",
    )


class PlaybookVersionShort(BaseModel):
    """Упрощённое представление PlaybookVersion (для списков/селектора)."""

    id: UUID
    name: str
    semver: str
    status: str
    playbook_id: UUID | None = Field(
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
    playbook_id: UUID | None = None
    model_config_id: UUID | None = None

    compiled_checks: dict[str, Any] | None = None
    trigger_definitions: dict[str, Any] | None = None
    dd_request_templates: dict[str, Any] | None = None
    section_markers: dict[str, Any] | None = None
    classification_config: dict[str, Any] | None = None


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
    description: str | None = None
    deal_type: str | None = Field(
        default=None,
        description="Deal type: real_estate, mna, nda, corporate, etc.",
    )
    jurisdiction: str | None = Field(
        default=None,
        description="Основная юрисдикция, например RU, EN, DE.",
    )
    language: str | None = Field(
        default=None,
        description="Основной язык документов: 'ru', 'en' и т.п.",
    )
    risk_profile: str | None = Field(
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


class ModelConfigResponse(BaseModel):
    """
    Конфигурация модели (ModelConfig) для UI.

    Используется фронтом при выборе модели, под которой будет работать playbook:
    - id — идентификатор конфигурации (UUID);
    - name — человекочитаемое имя для выпадающего списка;
    - description — краткое пояснение (опционально);
    - embeddings_primary / embeddings_fallback и т.п. можно отдать для справки.
    """

    id: UUID
    name: str
    description: str | None = None

    embeddings_primary: str | None = None
    embeddings_fallback: str | None = None


class ModelConfigCreateRequest(BaseModel):
    """
    Входные данные для создания нового профиля модели (ModelConfig).
    """

    name: str
    embeddings_primary: str = "intfloat/multilingual-e5-large"
    embeddings_fallback: str | None = "cointegrated/LaBSE"

    # Простые поля для формы. В бэке мы соберём из них JSON.
    candidate_n: int = 50
    llm_context_k: int = 5

    dense_weight: float = 0.6
    sparse_weight: float = 0.3
    metadata_boost: float = 0.1


class ModelConfigUpdateRequest(BaseModel):
    """
    Частичное обновление профиля модели.
    Все поля опциональные, можно менять только нужное.
    """

    name: str | None = None
    embeddings_primary: str | None = None
    embeddings_fallback: str | None = None

    candidate_n: int | None = None
    llm_context_k: int | None = None

    dense_weight: float | None = None
    sparse_weight: float | None = None
    metadata_boost: float | None = None
