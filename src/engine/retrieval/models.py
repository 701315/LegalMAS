# src/engine/retrieval/models.py

"""
Retrieval models: универсальное представление чанка для поиска и LLM.

Простыми словами для непрофессионального программиста:

- В системе много мест, где мы работаем с кусочками текста ("чанками"):
  * clause-чанки (целые пункты договора),
  * subclause / sized-чанки (legacy более мелкие части длинных пунктов),
  * section-чанки (крупные разделы, собранные из нескольких пунктов),
  * legal_unit-чанки (exact legal units — новый retrieval truth после P8.8d).

- Раньше каждый такой чанк был просто словарём формата:
    {"id": "...", "text": "...", "metadata": {...}}

- Модель RetrievalChunk вводит ЕДИНЫЙ "паспорт" чанка:
  * кто этот чанк (doc_id, clause_uid, уровень),
  * где он в документе (страницы, element_ids, путь заголовков),
  * что в нём за текст и сколько он весит в токенах,
  * краткое summary и дополнительные метаданные.

- Важно: dict-формат {"id","text","metadata"} теперь остаётся только
  "проводным" форматом (для API и совместимости), а вся внутренняя
  логика должна ориентироваться на RetrievalChunk.

P8.8d — Retrieval Truth Migration:
- Retrieval truth переключён с blind sized split (`subclause`)
  на exact legal units (`legal_unit`).
- Поэтому `legal_unit` теперь является полноправным kind retrieval corpus.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# Тип уровня чанка:
# - "section"    — крупный раздел (несколько пунктов),
# - "clause"     — исходная листовая клауза из clause tree,
# - "subclause"  — legacy под-чанк внутри длинной клаузы (sized-chunk),
# - "legal_unit" — exact retrieval unit, построенный из legal unit substrate.
ChunkKind = Literal["section", "clause", "subclause", "legal_unit"]


class RetrievalChunk(BaseModel):
    """
    Универсальный чанк для retrieval / LLM / checks.

    Для непрофессионального программиста:

    - Каждый такой объект — это "кусок договора", с которым работает система.
    - kind показывает тип:
        * "section"    — крупный раздел,
        * "clause"     — пункт/подпункт,
        * "subclause"  — legacy маленький фрагмент внутри пункта,
        * "legal_unit" — exact legal unit, новый retrieval-visible слой.
    - Паспорт хранит положение чанка в документе и служебную информацию.
    """

    # Уникальный идентификатор чанка
    id: str

    # ID документа, к которому относится чанк
    doc_id: str

    # Тип чанка: section / clause / subclause / legal_unit
    kind: ChunkKind

    # Canonical identity чанка/узла.
    # Исторически поле называется clause_uid, но после Sprint 3 и P8.8d
    # сюда кладётся effective_uid / unit_id retrieval entity.
    clause_uid: str | None = None

    # Уровень в иерархии clause tree / legal unit tree (если применимо)
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
        Сериализация в "старый" формат чанка для совместимого wire-contract.

        До введения этой модели по коду ходили словари вида:
            { "id": "...", "text": "...", "metadata": {...} }

        Чтобы не переписывать весь код сразу, мы можем:
        - внутри пользоваться RetrievalChunk,
        - в старые места отдавать результат to_legacy_dict().

        Для непрофессионального программиста:
        - metadata здесь — это "паспорт" чанка (id документа, страницы,
          identity, заголовки и дополнительные retrieval-поля), который
          дальше используют поиск, проверки и UI.
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
        metadata = {k: v for k, v in metadata.items() if v not in (None, [], {}, "")}

        return {
            "id": self.id,
            "text": self.text,
            "metadata": metadata,
        }
    

    
