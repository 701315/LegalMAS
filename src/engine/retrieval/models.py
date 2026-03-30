# src/engine/retrieval/models.py

"""
Retrieval models: универсальное представление чанка для поиска и LLM.

Простыми словами для непрофессионального программиста:

- В системе много мест, где мы работаем с кусочками текста ("чанками"):
  * clause-чанки (целые пункты договора),
  * subclause / sized-чанки (более мелкие части длинных пунктов),
  * section-чанки (крупные разделы, собранные из нескольких пунктов).

- Раньше каждый такой чанк был просто словарём формата:
    {"id": "...", "text": "...", "metadata": {...}}

- Модель RetrievalChunk вводит ЕДИНЫЙ "паспорт" чанка:
  * кто этот чанк (doc_id, clause_uid, уровень),
  * где он в документе (страницы, element_ids, путь заголовков),
  * что в нём за текст и сколько он весит в токенах,
  * краткое summary и дополнительные метаданные.

- Важно: dict-формат {"id","text","metadata"} теперь станет только
  "проводным" форматом (для API, старых мест в коде), а вся внутренняя
  логика будет работать с RetrievalChunk.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# Тип уровня чанка:
# - "section"   — крупный раздел (несколько пунктов),
# - "clause"    — исходная листовая клауза из clause tree,
# - "subclause" — под-чанк внутри длинной клаузы (sized-chunk).
ChunkKind = Literal["section", "clause", "subclause"]


class RetrievalChunk(BaseModel):
    """
    Универсальный чанк для retrieval / LLM / checks.

    Для непрофессионального программиста:

    - Каждый такой объект — это "кусок договора", с которым работает система.
    - kind показывает тип:
        * "section"   — крупный раздел,
        * "clause"    — пункт/подпункт,
        * "subclause" — маленький фрагмент внутри пункта.
    - Паспорт хранит положение чанка в документе и служебную информацию.
    """

    # Уникальный идентификатор чанка
    id: str

    # ID документа, к которому относится чанк
    doc_id: str

    # Тип чанка: section / clause / subclause
    kind: ChunkKind

    # UID клаузы из clause tree (например "1", "1.2.3", "II", "A")
    clause_uid: str | None = None

    # Уровень в иерархии clause tree (1 — верхний)
    level: int | None = None

    # Полный текст чанка
    text: str

    # Количество токенов (примерная длина для LLM/эмбеддингов)
    token_count: int = 0

    # Хлебные крошки: заголовки от корня до текущего узла
    path_titles: list[str] = Field(default_factory=list)

    # Примерные границы по страницам оригинального PDF
    start_page: int | None = None
    end_page: int | None = None

    # element_id'ы layout'а, которые входят в этот чанк
    element_ids: list[str] = Field(default_factory=list)

    # Краткое резюме чанка (может генерироваться автоматически)
    summary: str | None = None

    # Дополнительные метаданные:
    # doc_type, language, jurisdiction, triggers, роль чанка и т.п.
    meta: dict[str, Any] = Field(default_factory=dict)

    def to_legacy_dict(self) -> dict[str, Any]:
        """
        Сериализация в "старый" формат чанка для обратной совместимости.

        До введения этой модели по коду ходили словари вида:
            { "id": "...", "text": "...", "metadata": {...} }

        Чтобы не переписывать весь код сразу, мы будем:
        - внутри пользоваться RetrievalChunk,
        - в старые места отдавать результат to_legacy_dict().

        Для непрофессионального программиста:
        - metadata здесь — это "паспорт" чанка (id документа, страницы,
          пункты, заголовки), который дальше используют поиск, проверки и UI.
        """
        metadata: dict[str, Any] = {
            "doc_id": self.doc_id,
            "kind": self.kind,
            "clause_uid": self.clause_uid,
            "level": self.level,
            "path_titles": self.path_titles,
            "start_page": self.start_page,
            "end_page": self.end_page,
            "element_ids": self.element_ids,
            "token_count": self.token_count,
            "summary": self.summary,
        }

        # Добавляем все дополнительные поля из meta
        metadata.update(self.meta or {})

        # Убираем пустые/None для компактности
        metadata = {
            k: v
            for k, v in metadata.items()
            if v not in (None, [], {}, "")
        }

        return {
            "id": self.id,
            "text": self.text,
            "metadata": metadata,
        }
    