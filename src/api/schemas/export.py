# src/api/schemas/export.py

"""
Pydantic-схемы для API экспортов.

Зачем нужен этот файл:
- описывает формат входных данных для запроса на запуск экспорта;
- описывает формат выходных данных для статуса экспорта;
- отделяет ORM-модель Export от публичного API-контракта;
- позволяет безопасно добавлять вычисляемые поля, например download_url.

Важно:
- ORM-модель лежит в db/models/export.py и отвечает за хранение в БД;
- схемы ниже отвечают только за валидацию и сериализацию API.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# Разрешённые типы экспортов.
# Если backend позже расширится, список можно пополнить.
ExportType = Literal[
    "grid_xlsx",
    "deal_summary_xlsx",
    "report_docx",
    "aggregated_json",
]

# Разрешённые статусы экспортов.
# Пока оставляем как str, чтобы не ломать совместимость,
# но документируем ожидаемые значения.
ExportStatus = Literal[
    "pending",
    "processing",
    "completed",
    "failed",
]


class ExportRequest(BaseModel):
    """
    Тело запроса на запуск экспорта для одного run.

    Соответствует endpoint:
        POST /api/v1/runs/{run_id}/export
    """

    export_type: ExportType = Field(
        ...,
        description="Тип экспорта, например: grid_xlsx, deal_summary_xlsx, report_docx",
        examples=["deal_summary_xlsx"],
    )

    requested_by: str | None = Field(
        default=None,
        description="Идентификатор или email пользователя, запросившего экспорт",
        examples=["admin@legalmas.local"],
    )

    requester_role: str | None = Field(
        default=None,
        description="Роль пользователя в проекте на момент запроса",
        examples=["editor"],
    )


class ExportRecord(BaseModel):
    """
    Публичная API-схема одной записи экспорта.

    Это ответ, который удобно отдавать во фронт:
    - базовые поля записи Export из БД;
    - file_ref/file_refs для отладки и обратной совместимости;
    - download_url как вычисляемое поле, если файл уже готов.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    deal_id: UUID
    run_id: UUID

    export_type: ExportType = Field(
        ...,
        description="Тип экспорта",
        examples=["report_docx"],
    )

    status: ExportStatus = Field(
        ...,
        description="Статус экспорта. Для completed backend гарантирует наличие file_ref; download_url вычисляется из него.",
        examples=["completed"],
    )

    file_ref: str | None = Field(
        default=None,
        description="Основной reference на файл в storage",
        examples=["exports/deal-123/run-456/deal_summary.xlsx"],
    )

    file_refs: dict[str, Any] | None = Field(
        default=None,
        description="Дополнительные references на файлы, если экспорт создал несколько артефактов",
        examples=[{"main": "exports/deal-123/run-456/report.docx"}],
    )

    requested_by: str | None = Field(
        default=None,
        description="Кто запросил экспорт",
        examples=["admin@legalmas.local"],
    )

    requester_role: str | None = Field(
        default=None,
        description="Роль пользователя, запросившего экспорт",
        examples=["admin"],
    )

    file_size_bytes: int | None = Field(
        default=None,
        description="Размер итогового файла в байтах, если известен",
        examples=[245760],
    )

    created_at: datetime | None = Field(
        default=None,
        description="Дата создания записи экспорта",
    )

    updated_at: datetime | None = Field(
        default=None,
        description="Дата последнего обновления записи экспорта",
    )

    download_url: str | None = Field(
        default=None,
        description="Готовая ссылка на скачивание файла. Для completed должна быть доступна, если storage корректно разрешает file_ref.",
        examples=["/api/v1/exports/3fa85f64-5717-4562-b3fc-2c963f66afa6/download"],
    )

    error_message: str | None = Field(
        default=None,
        description="Текст ошибки, если экспорт завершился неуспешно",
        examples=["Export generation failed"],
    )


class ExportListResponse(BaseModel):
    """
    Ответ для списка экспортов.

    Нужен на будущее, если появится endpoint вроде:
        GET /api/v1/runs/{run_id}/exports
        GET /api/v1/deals/{deal_id}/exports
    """

    items: list[ExportRecord]
    total: int = Field(..., description="Общее количество записей")

    

