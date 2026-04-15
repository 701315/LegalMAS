# src/services/structure/models.py

"""
Data models for document clause tree.

Описывает результирующую структуру, которую строит Structure Builder
по layout документа и которую далее используют API и viewer.

Архитектура ClauseNode:
- own_element_ids    — элементы только самого пункта (до первого дочернего заголовка)
- subtree_element_ids — элементы пункта + всех потомков
- own_text           — материализованный текст самого пункта
- subtree_text       — материализованный текст всего поддерева
- node_kind          — "leaf" (нет детей) или "section" (есть дети)

Обратная совместимость:
- element_ids сохранён как legacy-алиас для own_element_ids.

Multi-document расширение (v2):
- ClauseTree расширен опциональными segment_* полями.
  Если segment_id не задан — поведение идентично v1 (backward compatible).
- SegmentDocument — описывает один логический документ внутри физического файла.
- CrossDocumentLink — связь между двумя сегментами (ссылка, упоминание).
- FileGraph — файловый контейнер: список сегментов + связи между ними.
- FileStructureResult — итог работы build_file_structure():
  primary_tree + все segment_trees + file_graph.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Существующие модели (не изменены)
# ---------------------------------------------------------------------------

@dataclass
class ClauseNode:
    """
    Узел дерева документа.

    Для непрофессионального программиста:
    - clause_uid:          номер пункта, например "1", "1.2", "3.1.4"
    - title:               заголовок пункта без номера
    - level:               уровень вложенности (1 = корень, 2 = подпункт и т.д.)
    - node_kind:           "leaf" если нет дочерних пунктов, "section" если есть
    - own_element_ids:     id элементов layout, принадлежащих только этому пункту
    - subtree_element_ids: id элементов этого пункта + всех вложенных пунктов
    - own_text:            текст только этого пункта (без вложенных)
    - subtree_text:        текст этого пункта и всех вложенных пунктов
    - children:            дочерние пункты
    """

    clause_uid: str
    title: str
    level: int

    # "leaf" — конечный пункт (нет детей, содержит реальный текст клаузы)
    # "section" — секция (есть дети, собственный текст обычно минимальный)
    # Заполняется в populate_subtree_element_ids после построения дерева.
    node_kind: str = "leaf"

    # Новый корректный контракт
    own_element_ids: list[str] = field(default_factory=list)
    subtree_element_ids: list[str] = field(default_factory=list)
    own_text: str | None = None
    subtree_text: str | None = None

    start_page: int = 1
    end_page: int = 1
    children: list["ClauseNode"] = field(default_factory=list)

    # ── Legacy-совместимость ────────────────────────────────────────────────
    # Старый код ожидает node.element_ids — возвращаем own_element_ids.

    @property
    def element_ids(self) -> list[str]:
        """Legacy alias → own_element_ids."""
        return self.own_element_ids

    @element_ids.setter
    def element_ids(self, value: list[str]) -> None:
        """Legacy setter → own_element_ids."""
        self.own_element_ids = list(value or [])


@dataclass
class CrossReference:
    """Перекрёстная ссылка между пунктами одного документа/сегмента."""
    source_clause_uid: str
    target_clause_uid: str
    reference_text: str  # например: "см. п. 3.2"


@dataclass
class ClauseTree:
    """
    Корневая структура дерева документа (одного логического сегмента).

    nodes_index — плоский словарь uid → ClauseNode для быстрого поиска
    по всему дереву без рекурсивного обхода.
    Заполняется в pipeline.py после build_clause_hierarchy.

    --- Поля multi-document расширения (v2) ---
    Все поля ниже опциональны и по умолчанию None/False.
    Если не заданы — to_dict() возвращает формат идентичный v1 (backward compat).

    - segment_id:          UUID-строка сегмента внутри файла (uuid5, детерминированный).
                           None означает "весь файл как один сегмент" (legacy режим).
    - segment_type:        тип логического документа:
                           contract | appendix | amendment | act | invoice |
                           schedule | other | unknown
    - segment_title:       заголовок сегмента, например "Приложение №1"
    - segment_page_range:  кортеж (page_start, page_end) страниц сегмента в файле
    - segment_order:       порядковый номер сегмента в файле (0-based)
    - is_primary_segment:  True — этот сегмент выбран как основной (primary)
                           для backward-compatible clause_tree_ref
    - schema_version:      "1.0" — legacy режим (segment_id is None)
                           "2.0" — multi-document режим (segment_id задан)
    """

    document_id: str
    root: list[ClauseNode]
    references_index: list[CrossReference]
    structure_confidence: str  # LOW | MEDIUM | HIGH
    degraded: bool = False

    # Плоский индекс uid → node. Позволяет downstream-коду делать
    # tree.nodes_index["3.2.1"] вместо рекурсивного обхода root.
    # При degraded=True — пустой словарь (деградированные чанки не индексируются).
    nodes_index: dict[str, "ClauseNode"] = field(default_factory=dict)

    # ── Multi-document поля (v2) ─────────────────────────────────────────────
    # Все опциональны. None = legacy режим, поведение идентично v1.

    # Уникальный идентификатор сегмента. Генерируется как:
    # uuid5(NAMESPACE_URL, f"{document_id}::segment::{segment_order}")
    # Детерминирован — одинаков при повторном запуске пайплайна.
    segment_id: str | None = None

    # Тип логического документа внутри файла.
    # Значения: contract | appendix | amendment | act | invoice | schedule | other | unknown
    segment_type: str | None = None

    # Человекочитаемый заголовок сегмента (если удалось определить).
    # Например: "Приложение №1", "Дополнительное соглашение №2"
    segment_title: str | None = None

    # Диапазон страниц сегмента в исходном файле: (первая_страница, последняя_страница).
    # Обе страницы включительно, нумерация с 1.
    segment_page_range: tuple[int, int] | None = None

    # Порядковый номер сегмента в файле: 0 — первый, 1 — второй и т.д.
    segment_order: int | None = None

    # True если этот сегмент выбран как основной (primary) для backward-compat
    # clause_tree_ref. Ровно один сегмент на файл должен иметь is_primary_segment=True.
    is_primary_segment: bool = False

    # Версия схемы артефакта:
    # "1.0" — legacy (segment_id не задан, whole-file tree)
    # "2.0" — multi-document режим (segment_id задан)
    schema_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        """
        Сериализует дерево в словарь для сохранения в JSON-артефакт.

        Backward compatible:
        - Если segment_id is None — возвращает формат v1, без segment_* полей.
        - Если segment_id задан — добавляет segment_* поля и schema_version="2.0".

        nodes_index не сериализуем — это runtime-индекс для in-memory use,
        в JSON он избыточен (дерево уже содержит все узлы через root/children).
        """
        result: dict[str, Any] = {
            "document_id": self.document_id,
            "root": [self._node_to_dict(n) for n in self.root],
            "references_index": [
                {
                    "source": r.source_clause_uid,
                    "target": r.target_clause_uid,
                    "text": r.reference_text,
                }
                for r in self.references_index
            ],
            "structure_confidence": self.structure_confidence,
            "degraded": self.degraded,
            "schema_version": self.schema_version,
        }

        # Добавляем segment-поля только если они заданы (v2 режим).
        # Это гарантирует, что старые consumers не увидят лишних полей.
        if self.segment_id is not None:
            result["segment_id"] = self.segment_id
        if self.segment_type is not None:
            result["segment_type"] = self.segment_type
        if self.segment_title is not None:
            result["segment_title"] = self.segment_title
        if self.segment_page_range is not None:
            # Сериализуем как список [start, end] — JSON не знает tuple
            result["segment_page_range"] = list(self.segment_page_range)
        if self.segment_order is not None:
            result["segment_order"] = self.segment_order
        # is_primary_segment сериализуем всегда — False тоже важная информация
        result["is_primary_segment"] = self.is_primary_segment

        return result

    def _node_to_dict(self, node: ClauseNode) -> dict[str, Any]:
        return {
            "clause_uid": node.clause_uid,
            "title": node.title,
            "level": node.level,
            "node_kind": node.node_kind,

            # Новый контракт
            "own_element_ids": node.own_element_ids,
            "subtree_element_ids": node.subtree_element_ids,
            "own_text": node.own_text,
            "subtree_text": node.subtree_text,

            # Legacy-совместимость
            "element_ids": node.element_ids,

            "start_page": node.start_page,
            "end_page": node.end_page,
            "children": [self._node_to_dict(c) for c in node.children],
        }


# ---------------------------------------------------------------------------
# Новые модели multi-document архитектуры (v2)
# ---------------------------------------------------------------------------

# Допустимые значения segment_type.
# Используй эти константы везде в коде — не хардкодь строки напрямую.
SEGMENT_TYPE_CONTRACT   = "contract"
SEGMENT_TYPE_APPENDIX   = "appendix"
SEGMENT_TYPE_AMENDMENT  = "amendment"
SEGMENT_TYPE_ACT        = "act"
SEGMENT_TYPE_INVOICE    = "invoice"
SEGMENT_TYPE_SCHEDULE   = "schedule"
SEGMENT_TYPE_OTHER      = "other"
SEGMENT_TYPE_UNKNOWN    = "unknown"

# Полный список допустимых типов для валидации
VALID_SEGMENT_TYPES: frozenset[str] = frozenset({
    SEGMENT_TYPE_CONTRACT,
    SEGMENT_TYPE_APPENDIX,
    SEGMENT_TYPE_AMENDMENT,
    SEGMENT_TYPE_ACT,
    SEGMENT_TYPE_INVOICE,
    SEGMENT_TYPE_SCHEDULE,
    SEGMENT_TYPE_OTHER,
    SEGMENT_TYPE_UNKNOWN,
})


def make_segment_id(document_id: str, segment_order: int) -> str:
    """
    Генерирует детерминированный segment_id.

    Для непрофессионального программиста:
    Это специальный тип UUID (uuid5), который всегда генерирует один и тот же
    результат для одинаковых входных данных. Это важно: если пайплайн
    перезапустится для того же документа, segment_id не изменится.
    Именно это нужно для REUSE_STRUCTURE стратегии.

    Аргументы:
    - document_id:    строковый ID физического файла
    - segment_order:  порядковый номер сегмента в файле (0, 1, 2, ...)

    Пример:
        make_segment_id("abc-123", 0) -> "550e8400-e29b-41d4-a716-..."
        make_segment_id("abc-123", 0) -> тот же результат при повторном вызове
        make_segment_id("abc-123", 1) -> другой UUID для второго сегмента
    """
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"{document_id}::segment::{segment_order}",
        )
    )


@dataclass
class SegmentDocument:
    """
    Один логический документ внутри физического файла.

    Для непрофессионального программиста:
    Физический файл (PDF/DOCX) может содержать несколько отдельных
    юридических документов: основной договор, приложения, акты и т.д.
    SegmentDocument описывает один такой логический документ:
    где он начинается и заканчивается в файле (по страницам и элементам),
    какой у него тип, заголовок и уникальный идентификатор.

    Поля:
    - segment_id:           UUID-строка, детерминированный (make_segment_id)
    - document_id:          ID физического файла (parent)
    - document_version_id:  ID версии документа (None если не известен при создании)
    - segment_order:        порядковый номер в файле (0-based)
    - segment_type:         тип логического документа (см. VALID_SEGMENT_TYPES)
    - segment_title:        заголовок (если определён)
    - page_start:           первая страница сегмента в файле (включительно, с 1)
    - page_end:             последняя страница сегмента в файле (включительно)
    - element_start:        индекс первого элемента в elements[] (включительно)
    - element_end:          индекс после последнего элемента (исключительно)
                            срез: elements[element_start:element_end]
    - confidence:           уверенность определения границ: LOW | MEDIUM | HIGH
    - is_primary:           True — этот сегмент основной для backward compat
    """

    segment_id: str
    document_id: str
    segment_order: int
    segment_type: str           # см. VALID_SEGMENT_TYPES
    page_start: int
    page_end: int
    element_start: int          # включительно
    element_end: int            # исключительно — elements[start:end]
    document_version_id: str | None = None
    segment_title: str | None = None
    confidence: str = "MEDIUM"  # LOW | MEDIUM | HIGH
    is_primary: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Сериализует в словарь для включения в file_graph.json."""
        return {
            "segment_id": self.segment_id,
            "document_id": self.document_id,
            "document_version_id": self.document_version_id,
            "segment_order": self.segment_order,
            "segment_type": self.segment_type,
            "segment_title": self.segment_title,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "element_start": self.element_start,
            "element_end": self.element_end,
            "confidence": self.confidence,
            "is_primary": self.is_primary,
        }


@dataclass
class CrossDocumentLink:
    """
    Связь (ребро) между двумя сегментами одного файла.

    Для непрофессионального программиста:
    Когда один документ ссылается на другой ("см. Приложение №1",
    "в соответствии с Договором"), мы фиксируем эту связь.
    Это нужно для cross-document checks: например, если договор
    говорит "цена указана в Приложении 1", но в приложении цены нет.

    Поля:
    - source_segment_id:  ID сегмента, который содержит ссылку (откуда)
    - target_segment_id:  ID сегмента, на который ссылаются (куда)
    - link_type:          тип связи:
                          "title_mention"  — упоминание заголовка в тексте
                          "structural"     — структурная связь (нумерация)
                          "order_sequence" — связь по следованию в файле
    - reference_text:     текст, по которому определена ссылка (для объяснимости в UI)
    - confidence:         уверенность в связи (0.0 — очень низкая, 1.0 — очень высокая)
    """

    source_segment_id: str
    target_segment_id: str
    link_type: str               # title_mention | structural | order_sequence
    reference_text: str | None = None
    confidence: float = 0.5      # 0.0 — очень низкая, 1.0 — очень высокая

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_segment_id": self.source_segment_id,
            "target_segment_id": self.target_segment_id,
            "link_type": self.link_type,
            "reference_text": self.reference_text,
            "confidence": self.confidence,
        }


@dataclass
class FileGraph:
    """
    Файловый граф — контейнер для всех логических документов внутри файла.

    Для непрофессионального программиста:
    Это "оглавление файла на уровне документов". Он знает:
    - какие логические документы есть в этом файле (поле segments)
    - какой из них главный (primary_segment_id)
    - какие связи (ссылки) существуют между документами (cross_links)

    FileGraph сохраняется как отдельный артефакт file_graph.json.
    CHUNKS и CHECKS читают его, чтобы понять с какими сегментами работать.

    Поля:
    - document_id:          ID физического файла
    - document_version_id:  ID версии документа
    - segments:             список всех SegmentDocument в файле
    - cross_links:          список связей между сегментами
    - primary_segment_id:   segment_id основного документа (обычно contract)
    - degraded:             True если хотя бы один сегмент деградировал
    - schema_version:       версия схемы артефакта (для будущих миграций)
    """

    document_id: str
    segments: list[SegmentDocument]
    cross_links: list[CrossDocumentLink]
    primary_segment_id: str | None
    document_version_id: str | None = None
    degraded: bool = False
    schema_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        """
        Сериализует в словарь для сохранения как file_graph.json.

        Это canonical handoff-контракт для CHUNKS:
        CHUNKS читают этот файл и по нему определяют,
        какие segment_clause_tree_*.json нужно загрузить.
        """
        return {
            "schema_version": self.schema_version,
            "document_id": self.document_id,
            "document_version_id": self.document_version_id,
            "primary_segment_id": self.primary_segment_id,
            "degraded": self.degraded,
            "segments": [s.to_dict() for s in self.segments],
            "cross_links": [lnk.to_dict() for lnk in self.cross_links],
        }

    @property
    def primary_segment(self) -> SegmentDocument | None:
        """
        Возвращает основной (primary) сегмент.

        Удобный shortcut: не нужно вручную искать в списке segments.
        Возвращает None если primary_segment_id не задан или не найден.
        """
        if not self.primary_segment_id:
            return None
        return next(
            (s for s in self.segments if s.segment_id == self.primary_segment_id),
            None,
        )

    @property
    def segment_count(self) -> int:
        """Количество сегментов в файле."""
        return len(self.segments)

    def get_segment(self, segment_id: str) -> SegmentDocument | None:
        """
        Найти сегмент по его segment_id.

        Возвращает None если сегмент с таким ID не найден.
        """
        return next(
            (s for s in self.segments if s.segment_id == segment_id),
            None,
        )


@dataclass
class FileStructureResult:
    """
    Итоговый результат работы build_file_structure().

    Для непрофессионального программиста:
    Когда STRUCTURE обрабатывает файл в новом (v2) режиме, она возвращает
    не одно дерево (как раньше), а этот объект, который содержит:
    - primary_tree:    дерево основного сегмента (для backward compat)
    - segment_trees:   список деревьев всех сегментов
    - file_graph:      граф файла (список сегментов + связи между ними)

    Worker использует этот объект для сохранения всех артефактов.

    Поля:
    - primary_tree:    ClauseTree основного (primary) сегмента.
                       Это то, что сохраняется в legacy clause_tree_ref.
    - segment_trees:   ClauseTree для каждого сегмента, в том же порядке
                       что file_graph.segments.
    - file_graph:      FileGraph с метаданными всех сегментов и связями.
    """

    primary_tree: ClauseTree
    segment_trees: list[ClauseTree]
    file_graph: FileGraph

    @property
    def primary_segment_id(self) -> str | None:
        """Shortcut: ID основного сегмента из file_graph."""
        return self.file_graph.primary_segment_id

    @property
    def segment_count(self) -> int:
        """Количество сегментов."""
        return len(self.segment_trees)

    def get_tree_for_segment(self, segment_id: str) -> ClauseTree | None:
        """
        Найти дерево по segment_id.

        Для непрофессионального программиста:
        Если у тебя есть segment_id и нужно получить его ClauseTree —
        используй этот метод вместо ручного перебора segment_trees.

        Возвращает None если дерево для такого сегмента не найдено.
        """
        return next(
            (t for t in self.segment_trees if t.segment_id == segment_id),
            None,
        )
    

    