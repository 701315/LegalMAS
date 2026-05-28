# src/api/schemas/pagination.py

"""
Generic-схемы для пагинации в REST API.
"""

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Универсальный формат ответа для пагинированных списков.

    Пример:
    {
        "items": [...],
        "total": 123,
        "page": 1,
        "per_page": 20,
        "total_pages": 7,
        "has_next": true,
        "has_previous": false
    }
    """

    items: list[T]
    total: int
    page: int
    per_page: int
    total_pages: int
    has_next: bool
    has_previous: bool
