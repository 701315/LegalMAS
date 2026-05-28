# src/api/endpoints/document_types.py

"""
HTTP‑эндпоинты для работы с типами документов (document types).

Используется:
- фронтендом MAS-DD для получения списка доступных типов документов;
- при ручной переклассификации документов (выпадающий список типов в UI).

Маршруты:
- GET /api/v1/document-types — вернуть все типы документов из YAMLRegistry
  с краткими метаданными (категория, риск, язык, юрисдикция).
"""

from fastapi import APIRouter
from pydantic import BaseModel

from classifiers.yaml_registry import YAMLRegistry

router = APIRouter(prefix="/document-types", tags=["document-types"])


class DocumentTypeItem(BaseModel):
    # Внутренний код типа, например "contract_1.6_real_estate"
    type: str
    # Человеко-понятное название типа
    name: str
    # Основная категория: "contract", "annex" и т.п.
    category: str | None = None
    # Уровень риска: "low" / "medium" / "high" / "critical"
    risk_level: str | None = None
    # Основной язык документов этого типа
    language: str | None = None
    # Юрисдикция, например "RU", "EN"
    jurisdiction: str | None = None


@router.get("", response_model=list[DocumentTypeItem])
async def list_document_types() -> list[DocumentTypeItem]:
    """
    Вернуть список всех типов документов из YAMLRegistry.

    Используется на фронтенде для выпадающего списка при ручной переклассификации.
    """
    registry = YAMLRegistry.get_instance()

    items: list[DocumentTypeItem] = []

    # YAMLRegistry.get_all_configs() возвращает список DocumentTypeConfig
    for cfg in registry.get_all_configs():
        items.append(
            DocumentTypeItem(
                type=cfg.type_code,
                name=cfg.name or cfg.type_code,
                category=cfg.category or None,
                risk_level=cfg.risk_level or None,
                language=cfg.language or None,
                jurisdiction=cfg.jurisdiction or None,
            )
        )

    # Сортируем по категории и имени для стабильного и удобного отображения
    items.sort(key=lambda x: (x.category or "", x.name))
    return items
