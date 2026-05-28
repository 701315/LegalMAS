# src/core/document_columns.py

"""
Описание колонок документов (общий источник правды для бэка).

Используем:
- для экспорта (Excel / Word / PDF);
- для потенциальной генерации фронтовых типов в будущем.

Важно:
- не все колонки обязаны быть "сырыми" полями ORM-модели Document;
- часть колонок может быть вычисляемой read-model колонкой
  (например, applicable_triggers_count или composition-поля);
- поле DocumentColumnDef.field поэтому трактуется как:
  * либо имя реального атрибута Document;
  * либо псевдоним вычисляемого поля, которое умеет обработать export/read layer.
"""

from dataclasses import dataclass
from typing import Literal

# Полный перечень ID колонок (синхронизирован с фронтом src/types/index.ts)
DocumentColumnId = Literal[
    "filename",
    "folder_path",
    "doc_type",
    "status",
    "human_review_status",
    "reviewed_by_person",
    "risk_level",
    "language",
    "jurisdiction_guess",
    "page_count",
    "classification_level",
    "classification_confidence",
    "applicable_triggers_count",
    "composition_type",
    "segment_count",
    "primary_segment_label",
    "is_composite_file",
    "created_at",
    "updated_at",
    "id",
    "deal_id",
]


@dataclass(frozen=True)
class DocumentColumnDef:
    """
    Описание одной колонки по документу.

    id:
        Уникальный ID колонки (используется в настройках/экспорте/фильтрации).
    label:
        Человекочитаемый заголовок (для Excel/Word/PDF и, при желании, фронта).
    description:
        Краткое описание смысла колонки.
    field:
        Имя поля в модели Document или спец. псевдоним
        (например, "applicable_triggers_count", "composition_type").
    default_visible:
        Показывается ли по умолчанию (используем и на бэке, и на фронте).
    """

    id: DocumentColumnId
    label: str
    description: str
    field: str  # имя атрибута Document или псевдоним
    default_visible: bool


# Полный список всех возможных колонок по документу.
# 1:1 с фронтовым ALL_DOCUMENT_COLUMNS.
ALL_DOCUMENT_COLUMNS: list[DocumentColumnDef] = [
    DocumentColumnDef(
        id="filename",
        label="Название документа",
        description="Имя файла документа в Data Room.",
        field="filename",
        default_visible=True,
    ),
    DocumentColumnDef(
        id="folder_path",
        label="Папка",
        description="Путь к документу в структуре Data Room.",
        field="folder_path",
        default_visible=True,
    ),
    DocumentColumnDef(
        id="doc_type",
        label="Тип документа",
        description="Классифицированный тип документа (SPA, NDA и т.п.).",
        field="doc_type",
        default_visible=True,
    ),
    DocumentColumnDef(
        id="status",
        label="Статус обработки",
        description="Текущий статус обработки документа в пайплайне.",
        field="status",
        default_visible=True,
    ),
    DocumentColumnDef(
        id="human_review_status",
        label="Проверка юриста",
        description="Человекочитаемый статус проверки юристом.",
        field="human_review_status",
        default_visible=True,
    ),
    DocumentColumnDef(
        id="reviewed_by_person",
        label="Флаг проверки",
        description="Логический флаг: документ проверен юристом.",
        field="reviewed_by_person",
        default_visible=False,
    ),
    DocumentColumnDef(
        id="risk_level",
        label="Риск",
        description="Уровень риска документа: low/medium/high/critical.",
        field="risk_level",
        default_visible=True,
    ),
    DocumentColumnDef(
        id="language",
        label="Язык",
        description="Основной язык документа (RU, EN и т.п.).",
        field="language",
        default_visible=False,
    ),
    DocumentColumnDef(
        id="jurisdiction_guess",
        label="Юрисдикция",
        description="Предполагаемая юрисдикция документа.",
        field="jurisdiction_guess",
        default_visible=False,
    ),
    DocumentColumnDef(
        id="page_count",
        label="Страницы",
        description="Количество страниц в документе.",
        field="page_count",
        default_visible=False,
    ),
    DocumentColumnDef(
        id="classification_level",
        label="Уровень классификации",
        description="Уровень, на котором был определён тип документа (L0–L4, L_manual).",
        field="classification_level",
        default_visible=False,
    ),
    DocumentColumnDef(
        id="classification_confidence",
        label="Уверенность классификации",
        description="Число 0–1, показывающее уверенность в типе документа.",
        field="classification_confidence",
        default_visible=False,
    ),
    DocumentColumnDef(
        id="applicable_triggers_count",
        label="Триггеры",
        description="Количество сработавших триггеров проверок для документа.",
        field="applicable_triggers_count",
        default_visible=False,
    ),
    DocumentColumnDef(
        id="composition_type",
        label="Композиция файла",
        description=(
            "Показывает, содержит ли файл один логический документ "
            '("single") или несколько ("multi").'
        ),
        field="composition_type",
        default_visible=True,
    ),
    DocumentColumnDef(
        id="segment_count",
        label="Сегменты",
        description="Количество логических документов (сегментов) внутри файла.",
        field="segment_count",
        default_visible=False,
    ),
    DocumentColumnDef(
        id="primary_segment_label",
        label="Основной сегмент",
        description=("Человекочитаемое название основного логического документа внутри файла."),
        field="primary_segment_label",
        default_visible=True,
    ),
    DocumentColumnDef(
        id="is_composite_file",
        label="Составной файл",
        description=("Логический флаг: файл содержит несколько логических документов."),
        field="is_composite_file",
        default_visible=False,
    ),
    DocumentColumnDef(
        id="created_at",
        label="Создан",
        description="Дата и время добавления документа в сделку.",
        field="created_at",
        default_visible=False,
    ),
    DocumentColumnDef(
        id="updated_at",
        label="Обновлён",
        description="Дата и время последнего обновления документа.",
        field="updated_at",
        default_visible=True,
    ),
    DocumentColumnDef(
        id="id",
        label="ID документа",
        description="Технический идентификатор документа (UUID).",
        field="id",
        default_visible=False,
    ),
    DocumentColumnDef(
        id="deal_id",
        label="ID сделки",
        description="Идентификатор сделки, к которой относится документ.",
        field="deal_id",
        default_visible=False,
    ),
]


# Удобные вспомогательные функции для экспорта/настроек


def get_column_by_id(column_id: DocumentColumnId) -> DocumentColumnDef:
    for col in ALL_DOCUMENT_COLUMNS:
        if col.id == column_id:
            return col
    raise KeyError(f"Unknown DocumentColumnId: {column_id!r}")


def get_columns_by_ids(ids: list[DocumentColumnId] | None) -> list[DocumentColumnDef]:
    if not ids:
        return list(ALL_DOCUMENT_COLUMNS)
    existing_ids = {col.id for col in ALL_DOCUMENT_COLUMNS}
    unknown = [c for c in ids if c not in existing_ids]
    if unknown:
        # можно логировать, но не падать; сейчас — жёстко падаем
        raise KeyError(f"Unknown column ids: {unknown!r}")
    return [get_column_by_id(cid) for cid in ids]


def get_default_visible_ids() -> list[DocumentColumnId]:
    return [c.id for c in ALL_DOCUMENT_COLUMNS if c.default_visible]
