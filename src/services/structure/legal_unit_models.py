# src/services/structure/legal_unit_models.py

"""
Legal Unit Models — типизированные модели для semantic layer поверх clause tree.

Для непрофессионального программиста:
- ClauseNode (из hierarchy_builder) — это структурная единица дерева документа.
  Она описывает "раздел 1.2 называется X, содержит элементы Y".
- LegalUnit — это юридическая единица. Она отвечает на вопрос:
  "что именно регулирует этот раздел? это определение, обязательство,
  гарантия, платёжное условие?"
- Один ClauseNode порождает ровно один LegalUnit.
- LegalUnit знает свой anchor (откуда он взят), тип, function и citability.

Этот файл — canonical source of truth для всех типов legal units.
Он не зависит от БД, MinIO или внешних сервисов.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class LegalUnitType(str, Enum):
    """
    Семантический тип юридической единицы.

    Для непрофессионального программиста:
    Это ответ на вопрос "что это за норма?".
    Например: "это определение термина", "это обязательство стороны",
    "это гарантия", "это условие платежа".

    Значения:
    - DEFINITION:          определение термина ("X означает...")
    - OBLIGATION:          обязательство стороны ("Сторона обязана...")
    - WARRANTY:            гарантия ("Продавец гарантирует...")
    - PAYMENT_TERM:        условие оплаты (сумма, срок, порядок)
    - NOTICE:              уведомление (порядок, сроки, адреса)
    - GOVERNING_LAW:       применимое право
    - JURISDICTION:        подсудность / арбитраж
    - APPENDIX_REFERENCE:  ссылка на приложение
    - GENERAL_PROVISION:   общая норма без специфической функции
    - UNKNOWN:             тип не определён
    """
    DEFINITION = "definition"
    OBLIGATION = "obligation"
    WARRANTY = "warranty"
    PAYMENT_TERM = "payment_term"
    NOTICE = "notice"
    GOVERNING_LAW = "governing_law"
    JURISDICTION = "jurisdiction"
    APPENDIX_REFERENCE = "appendix_reference"
    GENERAL_PROVISION = "general_provision"
    UNKNOWN = "unknown"


class ClauseFunction(str, Enum):
    """
    Функциональная роль клаузы в договоре.

    Для непрофессионального программиста:
    Это ответ на вопрос "для чего эта норма в договоре?".
    Например: "это норма устанавливает права", "это норма ограничивает ответственность",
    "это норма описывает процедуру".

    Значения:
    - RIGHTS:           норма устанавливает права стороны
    - OBLIGATIONS:      норма устанавливает обязанности
    - LIMITATIONS:      норма ограничивает (ответственность, права и т.п.)
    - PROCEDURES:       норма описывает процедуру (уведомление, расчёт и т.п.)
    - DEFINITIONS:      норма определяет термины
    - REPRESENTATIONS:  норма содержит заверения/гарантии
    - REMEDIES:         норма описывает средства защиты
    - BOILERPLATE:      стандартная норма (подсудность, право, реквизиты)
    - UNKNOWN:          функция не определена
    """
    RIGHTS = "rights"
    OBLIGATIONS = "obligations"
    LIMITATIONS = "limitations"
    PROCEDURES = "procedures"
    DEFINITIONS = "definitions"
    REPRESENTATIONS = "representations"
    REMEDIES = "remedies"
    BOILERPLATE = "boilerplate"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# CitabilityMetrics
# ---------------------------------------------------------------------------

@dataclass
class CitabilityMetrics:
    """
    Метрики пригодности LegalUnit для цитирования в downstream.

    Для непрофессионального программиста:
    Когда детектор хочет сослаться на конкретную норму договора,
    ему важно знать:
    - насколько этот unit структурно надёжен (confidence)?
    - есть ли у него реальный текст или только заголовок?
    - был ли он восстановлен через best-effort или построен нормально?

    citability_score:
    - 1.0 = полностью надёжен, структурный heading + body
    - 0.7 = нормальный unit без идеального parse
    - 0.4 = best-effort recovery или heading-only
    - 0.0 = технический fallback, не цитировать

    citability_band:
    - "high"   = score >= 0.7
    - "medium" = score >= 0.4
    - "low"    = score < 0.4
    """
    citability_score: float = 0.0
    citability_band: str = "low"
    has_own_text: bool = False
    has_subtree_text: bool = False
    is_heading_only: bool = False
    recovered_via_best_effort: bool = False
    parse_confidence: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "citability_score": self.citability_score,
            "citability_band": self.citability_band,
            "has_own_text": self.has_own_text,
            "has_subtree_text": self.has_subtree_text,
            "is_heading_only": self.is_heading_only,
            "recovered_via_best_effort": self.recovered_via_best_effort,
            "parse_confidence": self.parse_confidence,
        }


# ---------------------------------------------------------------------------
# CrossRefStub
# ---------------------------------------------------------------------------

@dataclass
class CrossRefStub:
    """
    Заглушка для cross-reference между LegalUnit-ами.

    Для непрофессионального программиста:
    Это "черновик" ссылки: мы знаем что в тексте упоминается
    "см. раздел 5.2" или "Приложение 1", но ещё не резолвили
    куда именно это указывает в дереве.

    source_unit_id:   effective_uid LegalUnit который содержит ссылку
    raw_ref_text:     текст ссылки как он есть в документе ("раздел 5.2")
    ref_type:         тип ссылки: "clause_ref" / "appendix_ref" / "definition_ref"
    target_hint:      строковый hint для резолвера (например "5.2" или "appendix_1")
    resolved:         True если target_unit_id уже заполнен
    target_unit_id:   effective_uid целевого LegalUnit (None если ещё не резолвлен)
    """
    source_unit_id: str
    raw_ref_text: str
    ref_type: str = "clause_ref"
    target_hint: str | None = None
    resolved: bool = False
    target_unit_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_unit_id": self.source_unit_id,
            "raw_ref_text": self.raw_ref_text,
            "ref_type": self.ref_type,
            "target_hint": self.target_hint,
            "resolved": self.resolved,
            "target_unit_id": self.target_unit_id,
        }


# ---------------------------------------------------------------------------
# LegalUnit
# ---------------------------------------------------------------------------

@dataclass
class LegalUnit:
    """
    Юридическая единица — canonical semantic atom поверх ClauseNode.

    Для непрофессионального программиста:
    - Один ClauseNode из clause tree порождает ровно один LegalUnit.
    - LegalUnit — это не просто "текст раздела", а структурированное описание:
      * что это за норма (unit_type),
      * какую функцию она выполняет (clause_function),
      * на каких страницах она находится (anchor),
      * насколько она пригодна для цитирования (citability),
      * какие cross-references она содержит (cross_refs).

    Поля:

    unit_id:         уникальный ID = effective_uid ClauseNode
    raw_uid:         номер клаузы ("1.2.3")
    scope:           пространство нумерации ("main_contract", "appendix_1")
    title:           заголовок клаузы
    level:           уровень вложенности (1 = root, 2 = subsection и т.д.)
    unit_type:       LegalUnitType — семантический тип
    clause_function: ClauseFunction — функциональная роль
    segment_id:      ID логического сегмента документа
    segment_type:    тип сегмента ("contract", "appendix", ...)
    page_start:      первая страница
    page_end:        последняя страница
    own_text:        собственный текст клаузы (без дочерних)
    subtree_text:    полный текст клаузы включая дочерние
    own_element_ids: element_ids принадлежащие только этому узлу
    topic_tags:      темы (["definitions", "purchase_price", ...]) — заполняется topic_tagger-ом
    cross_refs:      list[CrossRefStub] — ссылки внутри текста
    citability:      CitabilityMetrics — метрики цитируемости
    node_kind:       "leaf" или "section"
    semantic_node_type: тип из classifier/scorer
    recovered_via_best_effort: был ли узел восстановлен через best-effort
    fallback_reason: причина fallback если recovered_via_best_effort=True
    diagnostics:     дополнительные диагностические данные
    """

    # ── Anchor ────────────────────────────────────────────────────────────────
    unit_id: str                    # = effective_uid ClauseNode
    raw_uid: str
    scope: str
    title: str
    level: int

    # ── Semantic typing ───────────────────────────────────────────────────────
    unit_type: LegalUnitType = LegalUnitType.UNKNOWN
    clause_function: ClauseFunction = ClauseFunction.UNKNOWN

    # ── Segment context ───────────────────────────────────────────────────────
    segment_id: str = ""
    segment_type: str = "unknown"

    # ── Pages ─────────────────────────────────────────────────────────────────
    page_start: int = 1
    page_end: int = 1

    # ── Text ─────────────────────────────────────────────────────────────────
    own_text: str | None = None
    subtree_text: str | None = None
    own_element_ids: list[str] = field(default_factory=list)

    # ── Topics / cross-refs (заполняются позже) ───────────────────────────────
    topic_tags: list[str] = field(default_factory=list)
    cross_refs: list[CrossRefStub] = field(default_factory=list)

    # ── Citability ────────────────────────────────────────────────────────────
    citability: CitabilityMetrics = field(default_factory=CitabilityMetrics)

    # ── Structure metadata ────────────────────────────────────────────────────
    node_kind: str = "leaf"
    semantic_node_type: str | None = None
    recovered_via_best_effort: bool = False
    fallback_reason: str | None = None

    # ── Diagnostics ───────────────────────────────────────────────────────────
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "raw_uid": self.raw_uid,
            "scope": self.scope,
            "title": self.title,
            "level": self.level,
            "unit_type": self.unit_type.value,
            "clause_function": self.clause_function.value,
            "segment_id": self.segment_id,
            "segment_type": self.segment_type,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "own_text": self.own_text,
            "subtree_text": self.subtree_text,
            "own_element_ids": list(self.own_element_ids),
            "topic_tags": list(self.topic_tags),
            "cross_refs": [ref.to_dict() for ref in self.cross_refs],
            "citability": self.citability.to_dict(),
            "node_kind": self.node_kind,
            "semantic_node_type": self.semantic_node_type,
            "recovered_via_best_effort": self.recovered_via_best_effort,
            "fallback_reason": self.fallback_reason,
            "diagnostics": dict(self.diagnostics),
        }


# ---------------------------------------------------------------------------
# LegalUnitsSnapshot — артефакт legal_units_v1.json
# ---------------------------------------------------------------------------

@dataclass
class LegalUnitsSnapshot:
    """
    Snapshot всех LegalUnit для одного логического сегмента.

    Это финальный артефакт который сохраняется как legal_units_v1.json.

    Для непрофессионального программиста:
    - Один сегмент (договор, приложение) = один snapshot.
    - Snapshot содержит все LegalUnit этого сегмента плюс метаданные:
      сколько unit-ов построено, сколько из них с известным типом,
      какой segment_id и т.д.
    """
    document_id: str
    document_version_id: str
    segment_id: str
    segment_type: str
    segment_order: int
    is_primary_segment: bool
    units: list[LegalUnit] = field(default_factory=list)
    schema_version: str = "1"

    # Диагностика
    total_nodes_processed: int = 0
    units_with_known_type: int = 0
    units_heading_only: int = 0
    units_best_effort: int = 0
    build_warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        units_with_known = sum(
            1 for u in self.units
            if u.unit_type != LegalUnitType.UNKNOWN
        )
        return {
            "schema_version": self.schema_version,
            "document_id": self.document_id,
            "document_version_id": self.document_version_id,
            "segment": {
                "segment_id": self.segment_id,
                "segment_type": self.segment_type,
                "segment_order": self.segment_order,
                "is_primary_segment": self.is_primary_segment,
            },
            "stats": {
                "total_units": len(self.units),
                "units_with_known_type": units_with_known,
                "units_heading_only": self.units_heading_only,
                "units_best_effort": self.units_best_effort,
                "total_nodes_processed": self.total_nodes_processed,
                "build_warnings": list(self.build_warnings),
            },
            "units": [u.to_dict() for u in self.units],
        }
    

