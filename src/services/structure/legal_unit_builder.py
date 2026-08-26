# src/services/structure/legal_unit_builder.py

"""
LegalUnitBuilder — построение semantic layer LegalUnit поверх clause tree.

Для непрофессионального программиста:
- Вход: clause_tree (JSON dict из MinIO) + segment metadata.
- Выход: LegalUnitsSnapshot со списком LegalUnit.

Что делает этот builder:
1. Обходит все узлы clause tree (root + все дочерние рекурсивно).
2. Для каждого ClauseNode создаёт LegalUnit.
3. Определяет unit_type и clause_function по rule-based heuristics:
   - по title (regex patterns),
   - по semantic_node_type из classifier,
   - по уровню вложенности,
   - по наличию текста,
   - по scope/node_origin/content_mode.
4. Вычисляет CitabilityMetrics.
5. Извлекает CrossRefStub-ы из текста (расширенные паттерны, включая appendix/item refs).
6. Применяет TopicTagger (Этап 6) — добавляет topic_tags.
7. Применяет CrossRefResolver (Этап 6) — резолвит ссылки между units.

Что НЕ делает этот builder:
- не вызывает LLM;
- не пишет в БД или MinIO;
- не знает про chunk_builder или workers;
- не меняет clause tree.

Архитектурная роль:
- вызывается из segment_chunk_builder_v2.py как опциональный dual-write;
- результат сохраняется worker-ом в MinIO как legal_units_v1.json;
- ссылка на артефакт пишется в DocumentSegment.segment_meta["legal_units_ref"].
"""

from __future__ import annotations

import re
from typing import Any
from services.structure.legal_unit_extractor import LegalUnitExtractor
from core.logging import get_logger
from services.structure.legal_unit_models import (
    CitabilityMetrics,
    ClauseFunction,
    CrossRefStub,
    LegalUnit,
    LegalUnitsSnapshot,
    LegalUnitType,
)
from engine.content.clause_tree_builder import ClauseTreeBuilder

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns для классификации по title
# ---------------------------------------------------------------------------

_TITLE_TYPE_PATTERNS: list[tuple[re.Pattern, LegalUnitType]] = [
    # ── Definitions ────────────────────────────────────────────────────────
    (
        re.compile(
            r"\b(definitions?|defined terms?|interpretation|meanings?|"
            r"определени[яей]|термины|толкование)\b",
            re.IGNORECASE,
        ),
        LegalUnitType.DEFINITION,
    ),

    # ── Payments ───────────────────────────────────────────────────────────
    (
        re.compile(
            r"\b(payment|price|consideration|fee|remuneration|"
            r"оплат[аы]|цена|вознаграждение|платёж|стоимость|сумма)\b",
            re.IGNORECASE,
        ),
        LegalUnitType.PAYMENT_TERM,
    ),

    # ── Confidentiality ────────────────────────────────────────────────────
    (
        re.compile(
            r"\b(confidential(ity)?|non.?disclosure|secret|proprietary information|"
            r"конфиденциальност[ьи]|неразглашени[еяй]|коммерческая тайна)\b",
            re.IGNORECASE,
        ),
        LegalUnitType.CONFIDENTIALITY,
    ),

    # ── Indemnification ────────────────────────────────────────────────────
    (
        re.compile(
            r"\b(indemnif(y|ication)|hold harmless|"
            r"возмещени[еяй] убытков|возместить убытки|возместить ущерб)\b",
            re.IGNORECASE,
        ),
        LegalUnitType.INDEMNIFICATION,
    ),

    # ── Liability ──────────────────────────────────────────────────────────
    (
        re.compile(
            r"\b(liabilit(y|ies)|limitation of liability|liability cap|"
            r"cap on liability|exclusion of liability|consequential damages|indirect damages|"
            r"ответственность|ограничение ответственности|предел ответственности|"
            r"освобождени[еяй] от ответственности|косвенные убытки)\b",
            re.IGNORECASE,
        ),
        LegalUnitType.LIABILITY_PROVISION,
    ),

    # ── Warranties ─────────────────────────────────────────────────────────
    (
        re.compile(
            r"\b(warrant(y|ies)|representation|guarantee|"
            r"гарантии?|заверени[яей]|поручительство)\b",
            re.IGNORECASE,
        ),
        LegalUnitType.WARRANTY,
    ),

    # ── Notices ────────────────────────────────────────────────────────────
    (
        re.compile(
            r"\b(notice[s]?|notification|communication|correspondence|"
            r"уведомлени[яей]|извещени[яей]|сообщени[яей]|адреса?)\b",
            re.IGNORECASE,
        ),
        LegalUnitType.NOTICE,
    ),

    # ── Governing law ──────────────────────────────────────────────────────
    (
        re.compile(
            r"\b(governing law|applicable law|choice of law|"
            r"применимое право|выбор права)\b",
            re.IGNORECASE,
        ),
        LegalUnitType.GOVERNING_LAW,
    ),

    # ── Dispute resolution / arbitration ───────────────────────────────────
    (
        re.compile(
            r"\b(dispute resolution|dispute[s]?|arbitration|arbitral|mediation|"
            r"разрешение споров|урегулирование споров|арбитраж|третейский суд|"
            r"медиац(?:ия|ии)|мкас)\b",
            re.IGNORECASE,
        ),
        LegalUnitType.DISPUTE_RESOLUTION,
    ),

    # ── Jurisdiction / forum / court ───────────────────────────────────────
    (
        re.compile(
            r"\b(jurisdiction|competent court|courts? of|forum|venue|exclusive jurisdiction|"
            r"подсудность|компетентный суд|суд по месту)\b",
            re.IGNORECASE,
        ),
        LegalUnitType.JURISDICTION,
    ),

    # ── Appendices ─────────────────────────────────────────────────────────
    (
        re.compile(
            r"\b(appendix|annex|exhibit|schedule|attachment|"
            r"приложени[еяй]|приложение\s*[№#]?\s*\d|перечень)\b",
            re.IGNORECASE,
        ),
        LegalUnitType.APPENDIX_REFERENCE,
    ),

    # ── Termination ────────────────────────────────────────────────────────
    (
        re.compile(
            r"\b(terminat(e|ion)|rescind|rescission|termination for cause|"
            r"right to terminate|termination notice|"
            r"расторжени[еяй]|прекращени[еяй] договора|"
            r"право расторжения|уведомление о расторжении)\b",
            re.IGNORECASE,
        ),
        LegalUnitType.TERMINATION_PROVISION,
    ),

    # ── Generic obligations — only after specific categories ──────────────
    (
        re.compile(
            r"\b(obligation[s]?|undertaking|covenant|duty|duties|"
            r"обязательств[ао]|обязанности|обязан|должен)\b",
            re.IGNORECASE,
        ),
        LegalUnitType.OBLIGATION,
    ),
]

_FUNCTION_PATTERNS: list[tuple[re.Pattern, ClauseFunction]] = [
    (
        re.compile(
            r"\b(definitions?|defined terms?|means|shall mean|"
            r"определени[яей]|означает|понимается)\b",
            re.IGNORECASE,
        ),
        ClauseFunction.DEFINITIONS,
    ),
    (
        re.compile(
            r"\b(warrant(y|ies)|represents?|representation[s]?|"
            r"гарантирует|заверяет|подтверждает)\b",
            re.IGNORECASE,
        ),
        ClauseFunction.REPRESENTATIONS,
    ),
    (
        re.compile(
            r"\b(shall not|must not|limitation|liability|cap|ceiling|"
            r"не вправе|не несёт|ограничение|предел ответственности)\b",
            re.IGNORECASE,
        ),
        ClauseFunction.LIMITATIONS,
    ),
    (
        re.compile(
            r"\b(remedy|remedies|indemnif|indemnity|indemnification|damages|compensation|"
            r"cure|penalt(y|ies)|"
            r"средства защиты|возмещени[еяй] убытков|ущерб|компенсация|неустойк[аи])\b",
            re.IGNORECASE,
        ),
        ClauseFunction.REMEDIES,
    ),
    (
        re.compile(
            r"\b(procedure|process|mechanism|step[s]?|timeline|termination|"
            r"notice period|written notice|"
            r"порядок|процедура|механизм|этапы?|сроки?|расторжени[еяй]|"
            r"уведомлени[яей]\s+о\s+расторжении)\b",
            re.IGNORECASE,
        ),
        ClauseFunction.PROCEDURES,
    ),
    (
        re.compile(
            r"\b(shall|must|obliged|required|undertakes|"
            r"обязан|должен|обязуется|обязательство)\b",
            re.IGNORECASE,
        ),
        ClauseFunction.OBLIGATIONS,
    ),
    (
        re.compile(
            r"\b(entitled|right to|may|permitted|вправе|имеет право|может)\b",
            re.IGNORECASE,
        ),
        ClauseFunction.RIGHTS,
    ),
    (
        re.compile(
            r"\b(governing law|jurisdiction|arbitration|notice[s]?|"
            r"entire agreement|severability|waiver|amendment|"
            r"применимое право|подсудность|уведомлени|вся сделка)\b",
            re.IGNORECASE,
        ),
        ClauseFunction.BOILERPLATE,
    ),
]

_CLAUSE_REF_PATTERN = re.compile(
    r"""
    (?:
        (?:section|clause|article|paragraph|item|п\.?|ст\.?|разд\.?|пункт(?:а|е|ом)?)
        \s*
        (\d+(?:\.\d+)*)
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

_APPENDIX_REF_PATTERN = re.compile(
    r"""
    (?:
        (?:appendix|annex|exhibit|schedule|attachment|приложени[еяй])
        \s*
        (?:no\.?|[№#])?
        \s*
        ([A-Z]|\d+|[IVX]+)
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

_APPENDIX_ITEM_REF_PATTERN = re.compile(
    r"""
    (?:
        (?:item|clause|section|п\.?|пункт(?:а|е|ом)?)
        \s*
        (\d+(?:\.\d+)*)
        \s+
        (?:of|in|under|в|из|согласно|according\ to)
        \s+
        (?:appendix|annex|exhibit|schedule|attachment|приложени[еяй])
        \s*
        (?:no\.?|[№#])?
        \s*
        ([A-Z]|\d+|[IVX]+)
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

_DEFINITION_REF_PATTERN = re.compile(
    r'"([A-ZА-Я][^"]{1,60})"',
)


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _looks_like_appendix_scope(scope: str) -> bool:
    s = _normalize_text(scope).lower()
    return s.startswith("appendix") or s.startswith("приложение")


def _looks_like_technical_chunk_title(title: str) -> bool:
    t = _normalize_text(title).lower()
    return bool(
        t.startswith("chunk ")
        or t.startswith("[technical fallback]")
        or t.startswith("fragment ")
    )


def _safe_semantic_title(
    *,
    title: str,
    raw_uid: str,
    scope: str,
    is_technical_fallback: bool,
    is_heading_only: bool,
) -> str:
    normalized_title = _normalize_text(title)
    if is_technical_fallback:
        return ""

    if normalized_title and not _looks_like_technical_chunk_title(normalized_title):
        return normalized_title

    if _looks_like_appendix_scope(scope) and raw_uid:
        return f"Appendix {raw_uid}"

    if is_heading_only and raw_uid:
        return f"Section {raw_uid}"

    return normalized_title


def _classify_unit_type(
    *,
    title: str,
    text: str | None,
    scope: str,
    node_kind: str,
    content_mode: str,
    node_origin: str,
    raw_uid: str,
    semantic_node_type: Any,
    is_technical_fallback: bool,
) -> LegalUnitType:
    if is_technical_fallback:
        return LegalUnitType.UNKNOWN

    normalized_scope = _normalize_text(scope).lower()
    normalized_kind = _normalize_text(node_kind).lower()
    normalized_content_mode = _normalize_text(content_mode).lower()
    normalized_node_origin = _normalize_text(node_origin).lower()
    normalized_semantic_node_type = _normalize_text(semantic_node_type).lower()

    if _looks_like_appendix_scope(normalized_scope):
        return LegalUnitType.APPENDIX_REFERENCE

    if normalized_content_mode == "heading_only":
        return LegalUnitType.UNKNOWN

    if normalized_semantic_node_type in {"definition", "definitions"}:
        return LegalUnitType.DEFINITION
    if normalized_semantic_node_type in {"payment", "payment_term"}:
        return LegalUnitType.PAYMENT_TERM
    if normalized_semantic_node_type in {"warranty", "representation"}:
        return LegalUnitType.WARRANTY
    if normalized_semantic_node_type in {"notice"}:
        return LegalUnitType.NOTICE
    if normalized_semantic_node_type in {"governing_law", "choice_of_law"}:
        return LegalUnitType.GOVERNING_LAW
    if normalized_semantic_node_type in {"jurisdiction", "forum"}:
        return LegalUnitType.JURISDICTION
    if normalized_semantic_node_type in {"dispute_resolution", "arbitration", "mediation"}:
        return LegalUnitType.DISPUTE_RESOLUTION
    if normalized_semantic_node_type in {"confidentiality", "non_disclosure"}:
        return LegalUnitType.CONFIDENTIALITY
    if normalized_semantic_node_type in {"indemnification", "indemnity"}:
        return LegalUnitType.INDEMNIFICATION
    if normalized_semantic_node_type in {"termination", "termination_provision"}:
        return LegalUnitType.TERMINATION_PROVISION
    if normalized_semantic_node_type in {
        "liability",
        "liability_provision",
        "limitation_of_liability",
    }:
        return LegalUnitType.LIABILITY_PROVISION

    for pattern, unit_type in _TITLE_TYPE_PATTERNS:
        if pattern.search(title):
            return unit_type

    if text:
        text_sample = text[:500]
        for pattern, unit_type in _TITLE_TYPE_PATTERNS:
            if pattern.search(text_sample):
                return unit_type

    if normalized_kind in {"root", "branch"} and raw_uid.isdigit():
        return LegalUnitType.OBLIGATION

    if normalized_node_origin == "semantic":
        return LegalUnitType.UNKNOWN

    return LegalUnitType.UNKNOWN


def _classify_clause_function(
    *,
    title: str,
    text: str | None,
    unit_type: LegalUnitType,
    scope: str,
    content_mode: str,
    is_technical_fallback: bool,
) -> ClauseFunction:
    if is_technical_fallback:
        return ClauseFunction.UNKNOWN

    if _looks_like_appendix_scope(scope):
        return ClauseFunction.BOILERPLATE

    if _normalize_text(content_mode).lower() == "heading_only":
        return ClauseFunction.UNKNOWN

    _type_to_function: dict[LegalUnitType, ClauseFunction] = {
        LegalUnitType.DEFINITION: ClauseFunction.DEFINITIONS,
        LegalUnitType.WARRANTY: ClauseFunction.REPRESENTATIONS,
        LegalUnitType.GOVERNING_LAW: ClauseFunction.BOILERPLATE,
        LegalUnitType.JURISDICTION: ClauseFunction.BOILERPLATE,
        LegalUnitType.NOTICE: ClauseFunction.BOILERPLATE,
        LegalUnitType.APPENDIX_REFERENCE: ClauseFunction.BOILERPLATE,
        LegalUnitType.DISPUTE_RESOLUTION: ClauseFunction.BOILERPLATE,
        LegalUnitType.GENERAL_PROVISION: ClauseFunction.BOILERPLATE,

        LegalUnitType.OBLIGATION: ClauseFunction.OBLIGATIONS,
        LegalUnitType.PAYMENT_TERM: ClauseFunction.OBLIGATIONS,
        LegalUnitType.CONFIDENTIALITY: ClauseFunction.OBLIGATIONS,

        LegalUnitType.INDEMNIFICATION: ClauseFunction.REMEDIES,
        LegalUnitType.TERMINATION_PROVISION: ClauseFunction.PROCEDURES,
        LegalUnitType.LIABILITY_PROVISION: ClauseFunction.LIMITATIONS,

        LegalUnitType.STRUCTURAL_ANCHOR: ClauseFunction.UNKNOWN,
        LegalUnitType.TECHNICAL_FRAGMENT: ClauseFunction.UNKNOWN,
    }

    if unit_type in _type_to_function:
        return _type_to_function[unit_type]

    search_text = title + " " + (text[:300] if text else "")
    for pattern, function in _FUNCTION_PATTERNS:
        if pattern.search(search_text):
            return function

    return ClauseFunction.UNKNOWN


def _extract_cross_refs(
    unit_id: str,
    text: str | None,
) -> list[CrossRefStub]:
    if not text:
        return []

    refs: list[CrossRefStub] = []
    seen_refs: set[str] = set()

    for match in _APPENDIX_ITEM_REF_PATTERN.finditer(text):
        raw_text = match.group(0).strip()
        item_hint = match.group(1)
        appendix_hint = match.group(2)
        key = f"appendix_item:{appendix_hint}:{item_hint}"
        if key not in seen_refs:
            seen_refs.add(key)
            refs.append(
                CrossRefStub(
                    source_unit_id=unit_id,
                    raw_ref_text=raw_text,
                    ref_type="appendix_item_ref",
                    target_hint=f"appendix:{appendix_hint}:item:{item_hint}",
                    resolved=False,
                )
            )

    for match in _CLAUSE_REF_PATTERN.finditer(text):
        raw_text = match.group(0).strip()
        target_hint = match.group(1)
        key = f"clause:{target_hint}"
        if key not in seen_refs:
            seen_refs.add(key)
            refs.append(
                CrossRefStub(
                    source_unit_id=unit_id,
                    raw_ref_text=raw_text,
                    ref_type="clause_ref",
                    target_hint=target_hint,
                    resolved=False,
                )
            )

    for match in _APPENDIX_REF_PATTERN.finditer(text):
        raw_text = match.group(0).strip()
        target_hint = match.group(1)
        key = f"appendix:{target_hint}"
        if key not in seen_refs:
            seen_refs.add(key)
            refs.append(
                CrossRefStub(
                    source_unit_id=unit_id,
                    raw_ref_text=raw_text,
                    ref_type="appendix_ref",
                    target_hint=target_hint,
                    resolved=False,
                )
            )

    for match in _DEFINITION_REF_PATTERN.finditer(text):
        term = match.group(1).strip()
        if len(term) < 2 or len(term) > 60:
            continue
        key = f"def:{term.lower()}"
        if key not in seen_refs:
            seen_refs.add(key)
            refs.append(
                CrossRefStub(
                    source_unit_id=unit_id,
                    raw_ref_text=f'"{term}"',
                    ref_type="definition_ref",
                    target_hint=term,
                    resolved=False,
                )
            )

    return refs


def _compute_citability(node: dict[str, Any]) -> CitabilityMetrics:
    citability_hint = node.get("citability_hint")
    recovered = bool(node.get("recovered_via_best_effort", False))
    parse_confidence = node.get("parse_confidence")
    own_text = node.get("own_text") or ""
    subtree_text = node.get("subtree_text") or ""
    content_mode = str(node.get("content_mode") or "full_text").strip().lower()
    node_origin = str(node.get("node_origin") or "unknown").strip().lower()

    has_own_text = bool(own_text.strip())
    has_subtree_text = bool(subtree_text.strip())
    has_own_element_ids = bool(node.get("own_element_ids"))
    is_heading_only = content_mode == "heading_only" or (
        not has_own_text and not has_subtree_text and not has_own_element_ids
    )
    is_technical_fallback = (
        content_mode == "technical_fragment"
        or node_origin == "technical_fallback"
        or bool(node.get("diagnostics", {}).get("degraded_chunk", False))
    )

    if is_technical_fallback:
        return CitabilityMetrics(
            citability_score=0.0,
            citability_band="low",
            has_own_text=has_own_text,
            has_subtree_text=has_subtree_text,
            is_heading_only=False,
            recovered_via_best_effort=False,
            parse_confidence=parse_confidence,
            is_technical_fallback=True,
        )

    if citability_hint == "high":
        score = 0.9
    elif citability_hint == "medium":
        score = 0.6
    elif citability_hint == "low":
        score = 0.2
    else:
        if is_heading_only:
            score = 0.1
        elif recovered:
            score = 0.4
        elif has_own_text:
            score = 0.8
        elif has_subtree_text:
            score = 0.6
        else:
            score = 0.3

    if parse_confidence is not None:
        try:
            pc = float(parse_confidence)
            if 0.0 <= pc <= 1.0 and pc < 0.5:
                score = score * 0.8
        except (TypeError, ValueError):
            pass

    if recovered and score > 0.5:
        score = min(score, 0.65)

    score = round(max(0.0, min(1.0, score)), 3)

    if score >= 0.7:
        band = "high"
    elif score >= 0.4:
        band = "medium"
    else:
        band = "low"

    return CitabilityMetrics(
        citability_score=score,
        citability_band=band,
        has_own_text=has_own_text,
        has_subtree_text=has_subtree_text,
        is_heading_only=is_heading_only,
        recovered_via_best_effort=recovered,
        parse_confidence=parse_confidence,
        is_technical_fallback=False,
    )


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

class LegalUnitBuilder:
    """
    Строит LegalUnitsSnapshot из clause tree одного сегмента.
    """

    def build_from_clause_tree(
        self,
        *,
        clause_tree: dict[str, Any],
        segment_id: str,
        segment_type: str,
        segment_order: int,
        is_primary_segment: bool,
        document_id: str,
        document_version_id: str,
        element_index: dict[str, dict[str, Any]] | None = None,
    ) -> LegalUnitsSnapshot:
        snapshot = LegalUnitsSnapshot(
            document_id=str(document_id),
            document_version_id=str(document_version_id),
            segment_id=segment_id,
            segment_type=segment_type,
            segment_order=segment_order,
            is_primary_segment=is_primary_segment,
        )

        root_nodes = clause_tree.get("root") or []
        if not isinstance(root_nodes, list):
            snapshot.build_warnings.append(
                f"clause_tree.root is not a list: {type(root_nodes).__name__}"
            )
            logger.warning(
                "LegalUnitBuilder: clause_tree root is not a list",
                extra={
                    "document_id": document_id,
                    "segment_id": segment_id,
                    "root_type": type(root_nodes).__name__,
                },
            )
            return snapshot

        logger.info(
            "LegalUnitBuilder: building legal units from clause tree",
            extra={
                "document_id": document_id,
                "document_version_id": document_version_id,
                "segment_id": segment_id,
                "segment_type": segment_type,
                "root_count": len(root_nodes),
            },
        )

        units: list[LegalUnit] = []

        for root_node in root_nodes:
            if not isinstance(root_node, dict):
                snapshot.build_warnings.append(
                    f"root node is not a dict: {type(root_node).__name__}"
                )
                continue

            self._collect_units(
                node=root_node,
                segment_id=segment_id,
                segment_type=segment_type,
                units=units,
                warnings=snapshot.build_warnings,
                document_id=document_id,
                element_index=element_index,
                parent_unit_id=None,
                ancestor_titles=[],
                ancestor_path_ids=[],
            )

        # P8.8d: post-pass — восстановить parent/children linkage и path_ids.
        # _collect_units задаёт parent_unit_id и path_ids для каждого unit,
        # а здесь мы достраиваем children_unit_ids у родителей.
        unit_by_id = {u.unit_id: u for u in units if u.unit_id}

        for unit in units:
            if unit.parent_unit_id and unit.parent_unit_id in unit_by_id:
                parent = unit_by_id[unit.parent_unit_id]
                if unit.unit_id not in parent.children_unit_ids:
                    parent.children_unit_ids.append(unit.unit_id)


        # ── vNext: optional extraction of exact sub-units ────────────────
        # НЕ ломает старый pipeline:
        # - если element_index не передан → работаем как раньше
        # - если extractor не нашёл children → parent остаётся как есть
        if element_index is not None:
            units = self._extract_definition_sub_units(
                units=units,
                element_index=element_index,
                warnings=snapshot.build_warnings,
                document_id=document_id,
                segment_id=segment_id,
            )

        snapshot.units = units

        try:
            from services.structure.topic_tagger import TopicTagger

            tagger = TopicTagger()
            tagger.tag_units(snapshot.units)
        except Exception as tagger_exc:
            snapshot.build_warnings.append(f"topic_tagger failed: {tagger_exc}")
            logger.warning(
                "LegalUnitBuilder: topic_tagger failed, units will have empty topic_tags",
                extra={"document_id": document_id, "error": str(tagger_exc)},
            )

        try:
            from services.structure.cross_ref_resolver import CrossRefResolver

            resolver = CrossRefResolver()
            resolver.resolve(snapshot.units)
        except Exception as resolver_exc:
            snapshot.build_warnings.append(f"cross_ref_resolver failed: {resolver_exc}")
            logger.warning(
                "LegalUnitBuilder: cross_ref_resolver failed, cross_refs remain unresolved",
                extra={"document_id": document_id, "error": str(resolver_exc)},
            )

        total_nodes = len(units)
        heading_only_count = sum(1 for u in units if u.citability.is_heading_only)
        best_effort_count = sum(1 for u in units if u.recovered_via_best_effort)
        units_with_known_type = sum(1 for u in units if u.unit_type != LegalUnitType.UNKNOWN)
        technical_fallback_units = sum(
            1 for u in units if bool(u.diagnostics.get("is_technical_fallback", False))
        )

        snapshot.total_nodes_processed = total_nodes
        snapshot.units_with_known_type = units_with_known_type
        snapshot.units_heading_only = heading_only_count
        snapshot.units_best_effort = best_effort_count

        snapshot.build_warnings.extend(
            [
                f"technical_fallback_units={technical_fallback_units}"
            ] if technical_fallback_units else []
        )

        logger.info(
            "LegalUnitBuilder: legal units built",
            extra={
                "document_id": document_id,
                "document_version_id": document_version_id,
                "segment_id": segment_id,
                "total_units": total_nodes,
                "units_with_known_type": units_with_known_type,
                "units_heading_only": heading_only_count,
                "units_best_effort": best_effort_count,
                "technical_fallback_units": technical_fallback_units,
                "warnings_count": len(snapshot.build_warnings),
            },
        )

        return snapshot


    def _extract_definition_sub_units(
        self,
        *,
        units: list[LegalUnit],
        element_index: dict[str, dict[str, Any]],
        warnings: list[str],
        document_id: str,
        segment_id: str,
    ) -> list[LegalUnit]:
        """
        Optional second pass:
        materialize definition_item children inside parent DEFINITION units.

        Политика:
        - parent остаётся в snapshot как structural context unit;
        - children добавляются сразу после parent;
        - parent demote:
            * unit_class = "section"
            * unit_type = STRUCTURAL_ANCHOR
            * clause_function = UNKNOWN
            * citability = low
            * own_text / exact_text / retrieval_text = None
        - children получают high citability и exact_text.

        ВАЖНО:
        - этот pass безопасен и не меняет поведение если children не найдены.
        - currently applied only to parent units с unit_type == DEFINITION.
        """
        if not units:
            return units

        extractor = LegalUnitExtractor()
        existing_unit_ids = {u.unit_id for u in units if u.unit_id}

        result_units: list[LegalUnit] = []

        extracted_parents = 0
        extracted_children_total = 0

        for unit in units:
            result_units.append(unit)

            if unit.unit_type != LegalUnitType.DEFINITION:
                continue
            if unit.is_technical_fallback:
                continue
            if unit.children_unit_ids:
                continue
            if not unit.own_element_ids:
                continue

            try:
                children = extractor.extract_definition_sub_units(
                    parent_unit=unit,
                    element_index=element_index,
                    existing_unit_ids=existing_unit_ids,
                )
            except Exception as exc:
                warnings.append(
                    f"definition_sub_unit_extraction_failed:{unit.unit_id}:{exc}"
                )
                logger.warning(
                    "LegalUnitBuilder: definition sub-unit extraction failed",
                    extra={
                        "document_id": document_id,
                        "segment_id": segment_id,
                        "parent_unit_id": unit.unit_id,
                        "error": str(exc),
                    },
                )
                continue

            if not children:
                continue

            # Parent demotion (context-only / structural anchor)
            unit.children_unit_ids = [child.unit_id for child in children]
            unit.unit_class = "section"
            unit.unit_type = LegalUnitType.STRUCTURAL_ANCHOR
            unit.clause_function = ClauseFunction.UNKNOWN
            unit.own_text = None
            unit.exact_text = None
            unit.retrieval_text = None
            unit.context_prefix = None
            unit.context_strategy = None
            unit.heading_text = unit.heading_text or unit.title

            # Parent остаётся в snapshot, но не должен конкурировать с children
            unit.citability.citability_score = 0.1
            unit.citability.citability_band = "low"
            unit.citability.has_own_text = False
            unit.citability.is_heading_only = True

            unit.diagnostics["sub_units_materialized"] = len(children)
            unit.diagnostics["sub_units_materialized_kind"] = "definition_item"

            for child in children:
                # children пока без cross_refs/topic_tags;
                # TopicTagger и CrossRefResolver пойдут ниже на весь snapshot.
                child.cross_refs = _extract_cross_refs(
                    child.unit_id,
                    child.own_text or child.exact_text,
                )
                result_units.append(child)
                existing_unit_ids.add(child.unit_id)

            extracted_parents += 1
            extracted_children_total += len(children)

            logger.info(
                "LegalUnitBuilder: definition children materialized",
                extra={
                    "document_id": document_id,
                    "segment_id": segment_id,
                    "parent_unit_id": unit.unit_id,
                    "children_count": len(children),
                },
            )

        if extracted_children_total:
            warnings.append(
                f"definition_sub_units_materialized={extracted_children_total}"
            )

        logger.info(
            "LegalUnitBuilder: definition sub-unit extraction pass complete",
            extra={
                "document_id": document_id,
                "segment_id": segment_id,
                "extracted_parents": extracted_parents,
                "extracted_children_total": extracted_children_total,
            },
        )

        return result_units

    def _collect_units(
        self,
        *,
        node: dict[str, Any],
        segment_id: str,
        segment_type: str,
        units: list[LegalUnit],
        warnings: list[str],
        document_id: str,
        element_index: dict[str, dict[str, Any]] | None = None,
        parent_unit_id: str | None = None,
        ancestor_titles: list[str] | None = None,
        ancestor_path_ids: list[str] | None = None,
    ) -> None:
        effective_uid = str(node.get("effective_uid") or "").strip()
        raw_uid = str(node.get("raw_uid") or "").strip()
        scope = str(node.get("scope") or "").strip()
        title = str(node.get("title") or "").strip()
        level = int(node.get("level") or 1)
        node_kind = str(node.get("node_kind") or "leaf")
        own_text = node.get("own_text") or None
        subtree_text = node.get("subtree_text") or None
        own_element_ids = list(node.get("own_element_ids") or [])
        page_start = int(node.get("start_page") or 1)
        page_end = int(node.get("end_page") or page_start)
        semantic_node_type = node.get("semantic_node_type") or None
        node_origin = str(node.get("node_origin") or "unknown").strip()
        content_mode = str(node.get("content_mode") or "full_text").strip()
        recovered = bool(node.get("recovered_via_best_effort", False))
        fallback_reason = node.get("fallback_reason") or None
        diagnostics = dict(node.get("diagnostics") or {})
        current_ancestor_titles: list[str] = list(ancestor_titles or [])
        current_path_ids: list[str] = list(ancestor_path_ids or [])

        if not effective_uid:
            warnings.append(f"node missing effective_uid: raw_uid={raw_uid!r}")
            logger.warning(
                "LegalUnitBuilder: node missing effective_uid, skipping unit creation",
                extra={
                    "document_id": document_id,
                    "segment_id": segment_id,
                    "raw_uid": raw_uid,
                    "title": title[:80] if title else None,
                },
            )
            for child in node.get("children") or []:
                if isinstance(child, dict):
                    self._collect_units(
                        node=child,
                        segment_id=segment_id,
                        segment_type=segment_type,
                        units=units,
                        warnings=warnings,
                        document_id=document_id,
                        element_index=element_index,
                        parent_unit_id=parent_unit_id,
                        ancestor_titles=current_ancestor_titles,
                        ancestor_path_ids=current_path_ids,
                    )
            return

        is_technical_fallback = (
            content_mode.lower() == "technical_fragment"
            or node_origin.lower() == "technical_fallback"
            or bool(diagnostics.get("degraded_chunk", False))
        )

        # P8.8d/e: deterministic exact text projection from own_element_ids.
        # Выполняем сборку текста ДО вычисления citability, чтобы избежать timing bug
        # и ложного срабатывания флага is_heading_only.
        exact_text: str | None = None
        if element_index is not None and own_element_ids:
            materialized = ClauseTreeBuilder.materialize_text_from_element_ids(
                element_ids=own_element_ids,
                element_index=element_index,
            )
            if materialized:
                exact_text = materialized
                # Backfill own_text в локальную переменную, если в дереве его не было
                if not own_text:
                    own_text = exact_text
                    # Синхронизируем обратно в node dict, чтобы _compute_citability его увидел
                    node["own_text"] = own_text

        citability = _compute_citability(node)
        is_heading_only = bool(citability.is_heading_only)
        semantic_title = _safe_semantic_title(
            title=title,
            raw_uid=raw_uid,
            scope=scope,
            is_technical_fallback=is_technical_fallback,
            is_heading_only=is_heading_only,
        )

        # Заголовки предков
        parent_titles = list(current_ancestor_titles)
        context_prefix: str | None = None
        if parent_titles:
            context_prefix = "\n".join(t for t in parent_titles if t).strip() or None

        retrieval_text: str | None = None
        if exact_text:
            if context_prefix:
                retrieval_text = f"{context_prefix}\n\n{exact_text}"
            else:
                retrieval_text = exact_text

        heading_text = semantic_title or title or None
        source_element_ids = list(own_element_ids)
        path_ids = current_path_ids + ([effective_uid] if effective_uid else [])

        if is_technical_fallback:
            unit_type = LegalUnitType.UNKNOWN
            clause_function = ClauseFunction.UNKNOWN
            cross_refs: list[CrossRefStub] = []
            recovered = False
            fallback_reason = fallback_reason or "technical_fallback"
            if _looks_like_technical_chunk_title(title):
                warnings.append(
                    f"technical fallback node detected for unit_id={effective_uid}"
                )
        else:
            classify_text = own_text or subtree_text
            unit_type = _classify_unit_type(
                title=semantic_title or title,
                text=classify_text,
                scope=scope,
                node_kind=node_kind,
                content_mode=content_mode,
                node_origin=node_origin,
                raw_uid=raw_uid,
                semantic_node_type=semantic_node_type,
                is_technical_fallback=is_technical_fallback,
            )
            clause_function = _classify_clause_function(
                title=semantic_title or title,
                text=classify_text,
                unit_type=unit_type,
                scope=scope,
                content_mode=content_mode,
                is_technical_fallback=is_technical_fallback,
            )
            cross_refs = _extract_cross_refs(effective_uid, own_text or subtree_text)

        unit = LegalUnit(
            unit_id=effective_uid,
            raw_uid=raw_uid,
            scope=scope,
            title=semantic_title,
            level=level,
            unit_type=unit_type,
            clause_function=clause_function,
            segment_id=segment_id,
            segment_type=segment_type,
            page_start=page_start,
            page_end=page_end,
            own_text=own_text,
            subtree_text=subtree_text,
            own_element_ids=own_element_ids,
            topic_tags=[],
            cross_refs=cross_refs,
            citability=citability,
            node_kind=node_kind,
            semantic_node_type=semantic_node_type,
            node_origin=node_origin,
            content_mode=content_mode,
            recovered_via_best_effort=recovered,
            fallback_reason=fallback_reason,

            # ── P8.8d: exact retrieval substrate ──────────────────────────
            exact_text=exact_text,
            retrieval_text=retrieval_text,
            context_prefix=context_prefix,
            context_strategy="ancestor_heading_prefix" if context_prefix else None,
            parent_unit_id=parent_unit_id,
            children_unit_ids=[],
            path_ids=path_ids,
            source_element_ids=source_element_ids,
            heading_text=heading_text,

            diagnostics={
                "unit_type_source": (
                    "technical_fallback"
                    if is_technical_fallback
                    else ("title_pattern" if unit_type != LegalUnitType.UNKNOWN else "not_classified")
                ),
                "cross_refs_count": len(cross_refs),
                "is_technical_fallback": is_technical_fallback,
                "is_appendix_scope": _looks_like_appendix_scope(scope),
                "is_heading_only": is_heading_only,
                "raw_title": title,
                "semantic_title_sanitized": semantic_title != title,
                "user_facing_semantic": not is_technical_fallback,
                "has_exact_text": exact_text is not None,
                "has_retrieval_text": retrieval_text is not None,
                "has_context_prefix": context_prefix is not None,
            },
        )

        units.append(unit)

        logger.debug(
            "LegalUnitBuilder: unit created",
            extra={
                "document_id": document_id,
                "segment_id": segment_id,
                "unit_id": effective_uid,
                "raw_uid": raw_uid,
                "title": semantic_title[:80] if semantic_title else None,
                "raw_title": title[:80] if title else None,
                "unit_type": unit_type.value,
                "clause_function": clause_function.value,
                "citability_band": citability.citability_band,
                "node_kind": node_kind,
                "node_origin": node_origin,
                "content_mode": content_mode,
                "recovered": recovered,
                "is_technical_fallback": is_technical_fallback,
                "parent_unit_id": parent_unit_id,
                "path_depth": len(path_ids),
                "has_exact_text": exact_text is not None,
                "has_retrieval_text": retrieval_text is not None,
            },
        )

        next_ancestor_titles = list(current_ancestor_titles)
        if heading_text:
            next_ancestor_titles.append(heading_text)

        next_path_ids = path_ids

        for child in node.get("children") or []:
            if isinstance(child, dict):
                self._collect_units(
                    node=child,
                    segment_id=segment_id,
                    segment_type=segment_type,
                    units=units,
                    warnings=warnings,
                    document_id=document_id,
                    element_index=element_index,
                    parent_unit_id=effective_uid,
                    ancestor_titles=next_ancestor_titles,
                    ancestor_path_ids=next_path_ids,
                )


