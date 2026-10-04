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
    ВАЖНО: lowercase значения для совместимости с existing artifacts.
    """
    # ── Core types (original 13) ──────────────────────────────────────────
    DEFINITION = "definition"
    OBLIGATION = "obligation"
    WARRANTY = "warranty"
    PAYMENT_TERM = "payment_term"
    NOTICE = "notice"
    GOVERNING_LAW = "governing_law"
    JURISDICTION = "jurisdiction"
    APPENDIX_REFERENCE = "appendix_reference"
    CONFIDENTIALITY = "confidentiality"
    INDEMNIFICATION = "indemnification"
    DISPUTE_RESOLUTION = "dispute_resolution"
    TERMINATION_PROVISION = "termination_provision"
    LIABILITY_PROVISION = "liability_provision"

    # ── P0: 7 новых специфичных типов ─────────────────────────────────────
    TITLE_TRANSFER = "title_transfer"
    FORCE_MAJEURE = "force_majeure"
    AMENDMENT = "amendment"
    ENTIRE_AGREEMENT = "entire_agreement"
    SEVERABILITY = "severability"
    ASSIGNMENT = "assignment"
    PERSONAL_DATA = "personal_data"

    # ── P2: Дополнительные типы ───────────────────────────────────────────
    REPRESENTATIONS = "representations"
    EFFECTIVE_DATE = "effective_date"
    CONDITIONS_PRECEDENT = "conditions_precedent"
    COVENANTS = "covenants"
    GOVERNANCE = "governance"

    # ── Structural/Technical ──────────────────────────────────────────────
    GENERAL_PROVISION = "general_provision"
    STRUCTURAL_ANCHOR = "structural_anchor"
    TECHNICAL_FRAGMENT = "technical_fragment"
    UNKNOWN = "unknown"

    @classmethod
    def llm_eligible_values(cls) -> list[str]:
        """
        Типы которые LLM может предлагать как enrichment output.

        Исключает структурные и технические артефакты парсинга:
        - STRUCTURAL_ANCHOR: heading-only узел без семантического содержания
        - TECHNICAL_FRAGMENT: технический fallback fragment
        - UNKNOWN: LLM не должна явно предлагать unknown как ответ

        Эти типы существуют как внутренние метки пайплайна,
        а не как юридические категории договорных клауз.

        Используется в prompt construction (_prompting.py)
        вместо _enum_values(LegalUnitType) чтобы не давать модели
        escape hatch в виде структурных pseudo-labels.
        """
        _excluded = {
            cls.STRUCTURAL_ANCHOR,
            cls.TECHNICAL_FRAGMENT,
            cls.UNKNOWN,
        }
        return [
            member.value
            for member in cls
            if member not in _excluded
        ]


class ClauseFunction(str, Enum):
    """
    Функциональная роль клаузы в договоре.

    Для непрофессионального программиста:
    Это ответ на вопрос "для чего эта норма в договоре?".
    Например: "эта норма устанавливает права", "эта норма ограничивает ответственность",
    "эта норма описывает процедуру".
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
# ClauseFunction ontology helpers (Phase 13.8)
# ---------------------------------------------------------------------------

def _normalize_clause_function_key(value: Any) -> str:
    """
    Normalize raw clause-function label to a stable lookup key.

    Примеры:
    - "Representations" -> "representations"
    - "representations and warranties" -> "representations_and_warranties"
    - "governing-law" -> "governing_law"
    """
    if isinstance(value, ClauseFunction):
        return value.value

    text = str(value or "").strip().lower()
    if not text:
        return ""

    for old, new in (("-", "_"), ("/", "_"), (" ", "_")):
        text = text.replace(old, new)

    while "__" in text:
        text = text.replace("__", "_")

    return text.strip("_")


_CLAUSE_FUNCTION_ALIASES: dict[str, ClauseFunction] = {
    # canonical
    "rights": ClauseFunction.RIGHTS,
    "obligations": ClauseFunction.OBLIGATIONS,
    "limitations": ClauseFunction.LIMITATIONS,
    "procedures": ClauseFunction.PROCEDURES,
    "definitions": ClauseFunction.DEFINITIONS,
    "representations": ClauseFunction.REPRESENTATIONS,
    "remedies": ClauseFunction.REMEDIES,
    "boilerplate": ClauseFunction.BOILERPLATE,
    "unknown": ClauseFunction.UNKNOWN,

    # rights-like
    "right": ClauseFunction.RIGHTS,
    "entitlement": ClauseFunction.RIGHTS,
    "entitlements": ClauseFunction.RIGHTS,
    "permission": ClauseFunction.RIGHTS,
    "permissions": ClauseFunction.RIGHTS,
    "option": ClauseFunction.RIGHTS,
    "options": ClauseFunction.RIGHTS,

    # obligations-like
    "obligation": ClauseFunction.OBLIGATIONS,
    "duty": ClauseFunction.OBLIGATIONS,
    "duties": ClauseFunction.OBLIGATIONS,
    "covenant": ClauseFunction.OBLIGATIONS,
    "covenants": ClauseFunction.OBLIGATIONS,
    "undertaking": ClauseFunction.OBLIGATIONS,
    "undertakings": ClauseFunction.OBLIGATIONS,

    # limitations-like
    "limitation": ClauseFunction.LIMITATIONS,
    "cap": ClauseFunction.LIMITATIONS,
    "caps": ClauseFunction.LIMITATIONS,
    "liability_cap": ClauseFunction.LIMITATIONS,
    "liability_exclusion": ClauseFunction.LIMITATIONS,
    "exclusion": ClauseFunction.LIMITATIONS,
    "exclusions": ClauseFunction.LIMITATIONS,

    # procedures-like
    "procedure": ClauseFunction.PROCEDURES,
    "process": ClauseFunction.PROCEDURES,
    "processes": ClauseFunction.PROCEDURES,
    "mechanism": ClauseFunction.PROCEDURES,
    "mechanisms": ClauseFunction.PROCEDURES,
    "steps": ClauseFunction.PROCEDURES,
    "timeline": ClauseFunction.PROCEDURES,
    "termination_mechanics": ClauseFunction.PROCEDURES,

    # definitions-like
    "definition": ClauseFunction.DEFINITIONS,
    "interpretation": ClauseFunction.DEFINITIONS,

    # representations-like
    "representation": ClauseFunction.REPRESENTATIONS,
    "warranty": ClauseFunction.REPRESENTATIONS,
    "warranties": ClauseFunction.REPRESENTATIONS,
    "representations_and_warranties": ClauseFunction.REPRESENTATIONS,
    "representation_and_warranty": ClauseFunction.REPRESENTATIONS,

    # remedies-like
    "remedy": ClauseFunction.REMEDIES,
    "indemnity": ClauseFunction.REMEDIES,
    "indemnification": ClauseFunction.REMEDIES,
    "damages": ClauseFunction.REMEDIES,
    "compensation": ClauseFunction.REMEDIES,
    "cure": ClauseFunction.REMEDIES,
    "penalty": ClauseFunction.REMEDIES,
    "penalties": ClauseFunction.REMEDIES,

    # boilerplate-like / institutional clause names
    "misc": ClauseFunction.BOILERPLATE,
    "miscellaneous": ClauseFunction.BOILERPLATE,
    "general": ClauseFunction.BOILERPLATE,
    "standard_terms": ClauseFunction.BOILERPLATE,
    "institutional": ClauseFunction.BOILERPLATE,
    "governing_law": ClauseFunction.BOILERPLATE,
    "jurisdiction": ClauseFunction.BOILERPLATE,
    "notice": ClauseFunction.BOILERPLATE,
    "notices": ClauseFunction.BOILERPLATE,
    "dispute_resolution": ClauseFunction.BOILERPLATE,
    "arbitration": ClauseFunction.BOILERPLATE,
    "entire_agreement": ClauseFunction.BOILERPLATE,
    "severability": ClauseFunction.BOILERPLATE,
    "waiver": ClauseFunction.BOILERPLATE,
    "amendment": ClauseFunction.BOILERPLATE,
}

_CLAUSE_FUNCTION_DESCRIPTIONS: dict[ClauseFunction, str] = {
    ClauseFunction.RIGHTS:
        "Clause primarily grants a party a right, entitlement, permission, option, or ability to act.",
    ClauseFunction.OBLIGATIONS:
        "Clause primarily imposes a duty, undertaking, covenant, or mandatory performance obligation.",
    ClauseFunction.LIMITATIONS:
        "Clause primarily limits, excludes, caps, or restricts liability, damages, claims, or legal exposure.",
    ClauseFunction.PROCEDURES:
        "Clause primarily describes a process, mechanics, steps, timeline, or operational workflow.",
    ClauseFunction.DEFINITIONS:
        "Clause primarily defines the meaning of a term or interpretive rule.",
    ClauseFunction.REPRESENTATIONS:
        "Clause primarily states facts, assurances, representations, or warranties.",
    ClauseFunction.REMEDIES:
        "Clause primarily describes consequences of breach, indemnity, damages, compensation, cure, or penalty.",
    ClauseFunction.BOILERPLATE:
        "Clause is primarily an institutional or miscellaneous contract framework provision such as governing law, jurisdiction, notices, waiver, severability, amendment, or entire agreement.",
    ClauseFunction.UNKNOWN:
        "Primary function is not clear from the available clause text.",
}

_CLAUSE_FUNCTION_DECISION_RULES: dict[ClauseFunction, list[str]] = {
    ClauseFunction.RIGHTS: [
        "Use when the clause primarily grants a party a right, option, permission, or entitlement.",
        "Do not use if the main purpose is to impose a duty rather than grant a right.",
    ],
    ClauseFunction.OBLIGATIONS: [
        "Use when the clause primarily imposes a duty, mandatory action, or undertaking.",
        "Do not use merely because the text contains 'shall' or 'must' if the primary purpose is limitation, remedy, or procedure.",
    ],
    ClauseFunction.LIMITATIONS: [
        "Use when the clause primarily caps, excludes, narrows, or restricts liability, damages, remedies, or claims.",
        "Prefer this over obligations when the core effect is risk allocation through restriction.",
    ],
    ClauseFunction.PROCEDURES: [
        "Use when the clause primarily describes how something must happen: steps, mechanism, sequence, notice workflow, timeline, or termination mechanics.",
        "Prefer this over boilerplate when the clause is operational and process-oriented.",
    ],
    ClauseFunction.DEFINITIONS: [
        "Use when the clause defines a term or interpretive meaning.",
        "Prefer this whenever the clause follows a 'means / означает' pattern.",
    ],
    ClauseFunction.REPRESENTATIONS: [
        "Use when the clause primarily states assurances, facts, representations, or warranties.",
        "Prefer this for classic reps & warranties clauses.",
    ],
    ClauseFunction.REMEDIES: [
        "Use when the clause primarily addresses breach consequences, indemnity, damages, compensation, cure, or penalty.",
        "Prefer this over limitations if the main effect is recovery rather than restriction.",
    ],
    ClauseFunction.BOILERPLATE: [
        "Use for institutional contract framework clauses such as governing law, jurisdiction, notices, waiver, severability, amendment, or entire agreement.",
        "Do not use if a more specific primary function clearly applies.",
    ],
    ClauseFunction.UNKNOWN: [
        "Use only if the primary function cannot be determined reliably.",
    ],
}


def normalize_clause_function_label(value: Any) -> ClauseFunction | None:
    """
    Normalize raw / legacy / alias clause-function label to canonical ClauseFunction.

    Returns:
        - ClauseFunction if label is recognized
        - None if label is empty or not recognized
    """
    key = _normalize_clause_function_key(value)
    if not key:
        return None
    return _CLAUSE_FUNCTION_ALIASES.get(key)


def build_clause_function_ontology_payload() -> list[dict[str, Any]]:
    """
    Build stable ontology payload for prompt / explainability layers.

    UNKNOWN intentionally excluded from the main guidance payload.
    """
    ordered = [
        ClauseFunction.RIGHTS,
        ClauseFunction.OBLIGATIONS,
        ClauseFunction.LIMITATIONS,
        ClauseFunction.PROCEDURES,
        ClauseFunction.DEFINITIONS,
        ClauseFunction.REPRESENTATIONS,
        ClauseFunction.REMEDIES,
        ClauseFunction.BOILERPLATE,
    ]
    payload: list[dict[str, Any]] = []
    for function in ordered:
        payload.append({
            "name": function.value,
            "description": _CLAUSE_FUNCTION_DESCRIPTIONS[function],
            "decision_rules": list(_CLAUSE_FUNCTION_DECISION_RULES[function]),
        })
    return payload




# ---------------------------------------------------------------------------
# CitabilityMetrics
# ---------------------------------------------------------------------------

@dataclass
class CitabilityMetrics:
    """
    Метрики пригодности LegalUnit для цитирования в downstream.
    """

    citability_score: float = 0.0
    citability_band: str = "low"
    has_own_text: bool = False
    has_subtree_text: bool = False
    is_heading_only: bool = False
    recovered_via_best_effort: bool = False
    parse_confidence: float | None = None
    is_technical_fallback: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "citability_score": self.citability_score,
            "citability_band": self.citability_band,
            "has_own_text": self.has_own_text,
            "has_subtree_text": self.has_subtree_text,
            "is_heading_only": self.is_heading_only,
            "recovered_via_best_effort": self.recovered_via_best_effort,
            "parse_confidence": self.parse_confidence,
            "is_technical_fallback": self.is_technical_fallback,
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
    "см. раздел 5.2", "Приложение 1", "item 5.1 of Appendix No. 8",
    но ещё не резолвили куда именно это указывает в дереве.

    ref_type:
    - "clause_ref"
    - "appendix_ref"
    - "appendix_item_ref"
    - "definition_ref"

    resolve_method:
    - как именно ссылка была зарезолвлена
      ("same_scope_exact_uid", "appendix_scoped_exact_item", ...)
    resolve_confidence:
    - уверенность резолвера [0.0..1.0]
    """

    source_unit_id: str
    raw_ref_text: str
    ref_type: str = "clause_ref"
    target_hint: str | None = None
    resolved: bool = False
    target_unit_id: str | None = None
    resolve_method: str | None = None
    resolve_confidence: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_unit_id": self.source_unit_id,
            "raw_ref_text": self.raw_ref_text,
            "ref_type": self.ref_type,
            "target_hint": self.target_hint,
            "resolved": self.resolved,
            "target_unit_id": self.target_unit_id,
            "resolve_method": self.resolve_method,
            "resolve_confidence": self.resolve_confidence,
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
    """

    # ── Anchor ────────────────────────────────────────────────────────────────
    unit_id: str  # = effective_uid ClauseNode
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

    # ── Text ──────────────────────────────────────────────────────────────────
    own_text: str | None = None
    subtree_text: str | None = None
    own_element_ids: list[str] = field(default_factory=list)

    # ── Topics / cross-refs ───────────────────────────────────────────────────
    topic_tags: list[str] = field(default_factory=list)
    cross_refs: list[CrossRefStub] = field(default_factory=list)

    # ── Citability ────────────────────────────────────────────────────────────
    citability: CitabilityMetrics = field(default_factory=CitabilityMetrics)

    # ── Structure metadata ────────────────────────────────────────────────────
    node_kind: str = "leaf"
    semantic_node_type: str | None = None
    node_origin: str = "unknown"
    content_mode: str = "full_text"
    recovered_via_best_effort: bool = False
    fallback_reason: str | None = None

    # ── Diagnostics ───────────────────────────────────────────────────────────
    diagnostics: dict[str, Any] = field(default_factory=dict)

    # ── vNext: exact/retrieval extension (backward-compatible) ─────────────
    # Структурный класс unit. Это не semantic type, а structural/materialization role.
    # Пока строка, а не Enum — чтобы минимизировать blast radius.
    unit_class: str = "generic_block"

    # Exact vs retrieval text layers.
    # Пока optional: baseline legal units могут их не иметь.
    exact_text: str | None = None
    retrieval_text: str | None = None
    context_prefix: str | None = None
    context_strategy: str | None = None

    # Явные graph relations внутри legal-unit layer.
    parent_unit_id: str | None = None
    children_unit_ids: list[str] = field(default_factory=list)
    path_ids: list[str] = field(default_factory=list)

    # Source linkage for future exact-unit extraction / citation.
    source_element_ids: list[str] = field(default_factory=list)
    heading_text: str | None = None

    # B3.5: element_spans = [[element_id, page, start, end], ...] в координатах
    # retrieval_text (chunk["text"]). Используется в extraction._resolve_field_anchor
    # для точной локации цитаты (Priority 0).
    element_spans: list[list[Any]] = field(default_factory=list)


    @property
    def is_heading_only(self) -> bool:
        return bool(self.citability.is_heading_only)

    @property
    def is_technical_fallback(self) -> bool:
        return bool(self.citability.is_technical_fallback)

    @property
    def is_user_facing_semantic(self) -> bool:
        return not self.is_technical_fallback

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
            "node_origin": self.node_origin,
            "content_mode": self.content_mode,
            "recovered_via_best_effort": self.recovered_via_best_effort,
            "fallback_reason": self.fallback_reason,

            # ── vNext extension ────────────────────────────────────────────
            "unit_class": self.unit_class,
            "exact_text": self.exact_text,
            "retrieval_text": self.retrieval_text,
            "context_prefix": self.context_prefix,
            "context_strategy": self.context_strategy,
            "parent_unit_id": self.parent_unit_id,
            "children_unit_ids": list(self.children_unit_ids),
            "path_ids": list(self.path_ids),
            "source_element_ids": list(self.source_element_ids),
            "heading_text": self.heading_text,
            "element_spans": [list(sp) for sp in self.element_spans],

            "diagnostics": dict(self.diagnostics),
            "is_heading_only": self.is_heading_only,
            "is_technical_fallback": self.is_technical_fallback,
            "is_user_facing_semantic": self.is_user_facing_semantic,

        }


    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "LegalUnit":
        """
        Восстановить LegalUnit из сериализованного dict.

        Используется в LegalUnitsSnapshot.from_dict().
        Неизвестные/невалидные значения enum заменяются на UNKNOWN.
        """
        unit_type_str = str(raw.get("unit_type") or "unknown").lower()
        try:
            unit_type = LegalUnitType(unit_type_str)
        except ValueError:
            unit_type = LegalUnitType.UNKNOWN

        clause_function = (
            normalize_clause_function_label(raw.get("clause_function"))
            or ClauseFunction.UNKNOWN
        )


        citability_raw = raw.get("citability") or {}
        citability = CitabilityMetrics(
            citability_score=float(citability_raw.get("citability_score") or 0.0),
            citability_band=str(citability_raw.get("citability_band") or "low"),
            has_own_text=bool(citability_raw.get("has_own_text", False)),
            has_subtree_text=bool(citability_raw.get("has_subtree_text", False)),
            is_heading_only=bool(citability_raw.get("is_heading_only", False)),
            recovered_via_best_effort=bool(
                citability_raw.get("recovered_via_best_effort", False)
            ),
            parse_confidence=citability_raw.get("parse_confidence"),
            is_technical_fallback=bool(
                citability_raw.get("is_technical_fallback", False)
            ),
        )

        cross_refs_raw = raw.get("cross_refs") or []
        cross_refs = []
        for cr in cross_refs_raw:
            if not isinstance(cr, dict):
                continue
            cross_refs.append(
                CrossRefStub(
                    source_unit_id=str(cr.get("source_unit_id") or ""),
                    raw_ref_text=str(cr.get("raw_ref_text") or ""),
                    ref_type=str(cr.get("ref_type") or "clause_ref"),
                    target_hint=cr.get("target_hint"),
                    resolved=bool(cr.get("resolved", False)),
                    target_unit_id=cr.get("target_unit_id"),
                    resolve_method=cr.get("resolve_method"),
                    resolve_confidence=cr.get("resolve_confidence"),
                )
            )

        return cls(
            unit_id=str(raw.get("unit_id") or ""),
            raw_uid=str(raw.get("raw_uid") or ""),
            scope=str(raw.get("scope") or ""),
            title=str(raw.get("title") or ""),
            level=int(raw.get("level") or 1),
            unit_type=unit_type,
            clause_function=clause_function,
            segment_id=str(raw.get("segment_id") or ""),
            segment_type=str(raw.get("segment_type") or "unknown"),
            page_start=int(raw.get("page_start") or 1),
            page_end=int(raw.get("page_end") or 1),
            own_text=raw.get("own_text") or None,
            subtree_text=raw.get("subtree_text") or None,
            own_element_ids=list(raw.get("own_element_ids") or []),
            topic_tags=list(raw.get("topic_tags") or []),
            cross_refs=cross_refs,
            citability=citability,
            node_kind=str(raw.get("node_kind") or "leaf"),
            semantic_node_type=raw.get("semantic_node_type"),
            node_origin=str(raw.get("node_origin") or "unknown"),
            content_mode=str(raw.get("content_mode") or "full_text"),
            recovered_via_best_effort=bool(raw.get("recovered_via_best_effort", False)),
            fallback_reason=raw.get("fallback_reason"),
            diagnostics=dict(raw.get("diagnostics") or {}),
            
            unit_class=str(raw.get("unit_class") or "generic_block"),
            exact_text=raw.get("exact_text") or None,
            retrieval_text=raw.get("retrieval_text") or None,
            context_prefix=raw.get("context_prefix") or None,
            context_strategy=raw.get("context_strategy") or None,
            parent_unit_id=raw.get("parent_unit_id"),
            children_unit_ids=list(raw.get("children_unit_ids") or []),
            path_ids=list(raw.get("path_ids") or []),
            source_element_ids=list(raw.get("source_element_ids") or []),
            heading_text=raw.get("heading_text") or None,
            element_spans=[
                list(sp) for sp in (raw.get("element_spans") or [])
                if isinstance(sp, (list, tuple))
            ],
        )


# ---------------------------------------------------------------------------
# LegalUnitsSnapshot — артефакт legal_units_v1.json
# ---------------------------------------------------------------------------

@dataclass
class LegalUnitsSnapshot:
    """
    Snapshot всех LegalUnit для одного логического сегмента.
    """

    document_id: str
    document_version_id: str
    segment_id: str
    segment_type: str
    segment_order: int
    is_primary_segment: bool
    units: list[LegalUnit] = field(default_factory=list)
    schema_version: str = "2"

    # Диагностика
    total_nodes_processed: int = 0
    units_with_known_type: int = 0
    units_heading_only: int = 0
    units_best_effort: int = 0
    build_warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        units_with_known = sum(1 for u in self.units if u.unit_type != LegalUnitType.UNKNOWN)
        technical_fallback_units = sum(1 for u in self.units if u.is_technical_fallback)
        structural_anchor_units = sum(1 for u in self.units if u.unit_type == LegalUnitType.STRUCTURAL_ANCHOR)

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
                "technical_fallback_units": technical_fallback_units,
                "structural_anchor_units": structural_anchor_units,
                "total_nodes_processed": self.total_nodes_processed,
                "build_warnings": list(self.build_warnings),
            },
            "units": [u.to_dict() for u in self.units],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LegalUnitsSnapshot":
        """
        Восстановить LegalUnitsSnapshot из сериализованного dict.

        Используется в Phase 12.1.6 для восстановления snapshot
        перед применением enrichment projection.
        Неизвестные поля игнорируются (forward-compatible).
        """
        segment = data.get("segment") or {}
        stats = data.get("stats") or {}

        units_raw = data.get("units") or []
        units = []
        for u in units_raw:
            if not isinstance(u, dict):
                continue
            try:
                units.append(LegalUnit.from_dict(u))
            except Exception:
                continue

        return cls(
            document_id=str(data.get("document_id") or ""),
            document_version_id=str(data.get("document_version_id") or ""),
            segment_id=str(segment.get("segment_id") or ""),
            segment_type=str(segment.get("segment_type") or "unknown"),
            segment_order=int(segment.get("segment_order") or 0),
            is_primary_segment=bool(segment.get("is_primary_segment", False)),
            units=units,
            schema_version=str(data.get("schema_version") or "2"),
            total_nodes_processed=int(stats.get("total_nodes_processed") or 0),
            units_with_known_type=int(stats.get("units_with_known_type") or 0),
            units_heading_only=int(stats.get("units_heading_only") or 0),
            units_best_effort=int(stats.get("units_best_effort") or 0),
            build_warnings=list(stats.get("build_warnings") or []),
        )


