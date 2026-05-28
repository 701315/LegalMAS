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
   - по наличию текста.
4. Вычисляет CitabilityMetrics.
5. Извлекает CrossRefStub-ы из текста (базовые паттерны).
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

from core.logging import get_logger
from services.structure.legal_unit_models import (
    CitabilityMetrics,
    ClauseFunction,
    CrossRefStub,
    LegalUnit,
    LegalUnitsSnapshot,
    LegalUnitType,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Regex patterns для классификации по title
# ---------------------------------------------------------------------------

# Паттерны для определения LegalUnitType по заголовку клаузы.
# Порядок важен: более специфичные паттерны должны идти раньше.
_TITLE_TYPE_PATTERNS: list[tuple[re.Pattern, LegalUnitType]] = [
    # Определения
    (
        re.compile(
            r"\b(definitions?|defined terms?|interpretation|meanings?|"
            r"определени[яей]|термины|толкование)\b",
            re.IGNORECASE,
        ),
        LegalUnitType.DEFINITION,
    ),
    # Платёжные условия
    (
        re.compile(
            r"\b(payment|price|consideration|fee|remuneration|compensation|"
            r"оплат[аы]|цена|вознаграждение|платёж|стоимость|сумма)\b",
            re.IGNORECASE,
        ),
        LegalUnitType.PAYMENT_TERM,
    ),
    # Гарантии
    (
        re.compile(
            r"\b(warrant(y|ies)|representation|guarantee|indemnif|"
            r"гарантии?|заверени[яей]|поручительство|возмещение)\b",
            re.IGNORECASE,
        ),
        LegalUnitType.WARRANTY,
    ),
    # Уведомления
    (
        re.compile(
            r"\b(notice[s]?|notification|communication|correspondence|"
            r"уведомлени[яей]|извещени[яей]|сообщени[яей]|адреса?)\b",
            re.IGNORECASE,
        ),
        LegalUnitType.NOTICE,
    ),
    # Применимое право
    (
        re.compile(
            r"\b(governing law|applicable law|choice of law|"
            r"применимое право|право[,\s]которое|выбор права)\b",
            re.IGNORECASE,
        ),
        LegalUnitType.GOVERNING_LAW,
    ),
    # Подсудность / арбитраж
    (
        re.compile(
            r"\b(jurisdiction|arbitration|dispute resolution|"
            r"competent court|forum|venue|"
            r"подсудность|арбитраж|разрешение споров|суд)\b",
            re.IGNORECASE,
        ),
        LegalUnitType.JURISDICTION,
    ),
    # Ссылки на приложения
    (
        re.compile(
            r"\b(appendix|annex|exhibit|schedule|attachment|"
            r"приложени[еяй]|приложение\s*[№#]?\s*\d|перечень)\b",
            re.IGNORECASE,
        ),
        LegalUnitType.APPENDIX_REFERENCE,
    ),
    # Обязательства (broad pattern — идёт последним среди специфичных)
    (
        re.compile(
            r"\b(obligation[s]?|undertaking|covenant|duty|duties|"
            r"обязательств[ао]|обязанности|обязан|должен)\b",
            re.IGNORECASE,
        ),
        LegalUnitType.OBLIGATION,
    ),
]

# Паттерны для определения ClauseFunction по тексту или заголовку
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
            r"\b(remedy|remedies|indemnif|damages|compensation|"
            r"средства защиты|возмещение убытков|ущерб|компенсация)\b",
            re.IGNORECASE,
        ),
        ClauseFunction.REMEDIES,
    ),
    (
        re.compile(
            r"\b(procedure|process|mechanism|step[s]?|timeline|"
            r"порядок|процедура|механизм|этапы?|сроки?)\b",
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
            r"\b(entitled|right to|may|permitted|" r"вправе|имеет право|может)\b",
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

# Паттерны для извлечения cross-references из текста
_CLAUSE_REF_PATTERN = re.compile(
    r"""
    (?:
        (?:section|clause|article|paragraph|п\.?|ст\.?|разд\.?)\s*
        (\d+(?:\.\d+)*)
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

_APPENDIX_REF_PATTERN = re.compile(
    r"""
    (?:
        (?:appendix|annex|exhibit|schedule|attachment|приложени[еяй])\s*
        ([A-Z]|\d+|[IVX]+)
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

_DEFINITION_REF_PATTERN = re.compile(
    r'"([A-ZА-Я][^"]{1,60})"',  # термин в кавычках с большой буквы
)


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------


def _classify_unit_type(title: str, text: str | None) -> LegalUnitType:
    """
    Определить LegalUnitType по заголовку и (опционально) тексту.

    Для непрофессионального программиста:
    - Сначала проверяем title — это самый надёжный сигнал.
    - Если по title ничего не нашли — проверяем первые 500 символов текста.
    - Если и там ничего — возвращаем UNKNOWN.
    """
    for pattern, unit_type in _TITLE_TYPE_PATTERNS:
        if pattern.search(title):
            return unit_type

    if text:
        text_sample = text[:500]
        for pattern, unit_type in _TITLE_TYPE_PATTERNS:
            if pattern.search(text_sample):
                return unit_type

    return LegalUnitType.UNKNOWN


def _classify_clause_function(
    title: str,
    text: str | None,
    unit_type: LegalUnitType,
) -> ClauseFunction:
    """
    Определить ClauseFunction по заголовку, тексту и уже известному unit_type.

    Для непрофессионального программиста:
    - Сначала используем unit_type как strong prior.
    - Если unit_type=UNKNOWN или GENERAL_PROVISION — проверяем паттерны.
    """
    _type_to_function: dict[LegalUnitType, ClauseFunction] = {
        LegalUnitType.DEFINITION: ClauseFunction.DEFINITIONS,
        LegalUnitType.WARRANTY: ClauseFunction.REPRESENTATIONS,
        LegalUnitType.GOVERNING_LAW: ClauseFunction.BOILERPLATE,
        LegalUnitType.JURISDICTION: ClauseFunction.BOILERPLATE,
        LegalUnitType.NOTICE: ClauseFunction.BOILERPLATE,
        LegalUnitType.APPENDIX_REFERENCE: ClauseFunction.BOILERPLATE,
        LegalUnitType.OBLIGATION: ClauseFunction.OBLIGATIONS,
        LegalUnitType.PAYMENT_TERM: ClauseFunction.OBLIGATIONS,
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
    """
    Извлечь cross-references из текста клаузы.

    Для непрофессионального программиста:
    - Ищем упоминания вида "раздел 5.2", "Appendix 1", "термин X".
    - Создаём CrossRefStub с raw_ref_text и target_hint.
    - resolved=False — резолвинг происходит позже в cross_ref_resolver.py.
    """
    if not text:
        return []

    refs: list[CrossRefStub] = []
    seen_refs: set[str] = set()

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
    """
    Вычислить CitabilityMetrics для ClauseNode (переданного как dict).

    Для непрофессионального программиста:
    - node — это dict из ClauseNode.to_dict().
    - Читаем поля Этапа 4: citability_hint, recovered_via_best_effort,
      parse_confidence, own_text, subtree_text.
    - Вычисляем числовой score и band.
    """
    citability_hint = node.get("citability_hint")
    recovered = bool(node.get("recovered_via_best_effort", False))
    parse_confidence = node.get("parse_confidence")
    own_text = node.get("own_text") or ""
    subtree_text = node.get("subtree_text") or ""

    has_own_text = bool(own_text.strip())
    has_subtree_text = bool(subtree_text.strip())
    is_heading_only = not has_own_text and not has_subtree_text

    if citability_hint == "high":
        score = 0.9
    elif citability_hint == "medium":
        score = 0.6
    elif citability_hint == "low":
        score = 0.2
    else:
        # Fallback для старых документов без citability_hint
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
    )


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


class LegalUnitBuilder:
    """
    Строит LegalUnitsSnapshot из clause tree одного сегмента.

    Использование:
        builder = LegalUnitBuilder()
        snapshot = builder.build_from_clause_tree(
            clause_tree=tree_dict,
            segment_id="seg-uuid",
            segment_type="contract",
            segment_order=0,
            is_primary_segment=True,
            document_id="doc-uuid",
            document_version_id="ver-uuid",
        )
        artifact = snapshot.to_dict()
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
    ) -> LegalUnitsSnapshot:
        """
        Построить LegalUnitsSnapshot из clause tree одного сегмента.

        Параметры:
        - clause_tree: dict из ClauseTree.to_dict() (уже загруженный из MinIO)
        - остальные параметры: метаданные сегмента из DocumentSegment

        Порядок операций:
        1. Рекурсивный обход дерева -> создаём LegalUnit для каждого узла.
        2. TopicTagger -> добавляем topic_tags ко всем units.
        3. CrossRefResolver -> резолвим ссылки между units.
        4. Считаем финальную статистику snapshot.
        """
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

        # Шаг 1: рекурсивный обход дерева
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
            )

        snapshot.units = units

        # Шаг 2: TopicTagger — добавляем topic_tags
        # Делается после сборки ВСЕХ units чтобы не зависеть от порядка обхода.
        # Ошибка tagger-а не должна ломать весь snapshot.
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

        # Шаг 3: CrossRefResolver — резолвим ссылки между units
        # Делается после TopicTagger (порядок не критичен, но логически после).
        # Ошибка resolver-а не должна ломать весь snapshot.
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

        # Шаг 4: финальная статистика
        # Считаем после TopicTagger и CrossRefResolver — они не меняют unit_type,
        # поэтому порядок не влияет на результат.
        total_nodes = len(units)
        heading_only_count = sum(1 for u in units if u.citability.is_heading_only)
        best_effort_count = sum(1 for u in units if u.recovered_via_best_effort)
        units_with_known_type = sum(1 for u in units if u.unit_type != LegalUnitType.UNKNOWN)

        snapshot.total_nodes_processed = total_nodes
        snapshot.units_with_known_type = units_with_known_type
        snapshot.units_heading_only = heading_only_count
        snapshot.units_best_effort = best_effort_count

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
                "warnings_count": len(snapshot.build_warnings),
            },
        )

        return snapshot

    def _collect_units(
        self,
        *,
        node: dict[str, Any],
        segment_id: str,
        segment_type: str,
        units: list[LegalUnit],
        warnings: list[str],
        document_id: str,
    ) -> None:
        """
        Рекурсивно обходит дерево ClauseNode и создаёт LegalUnit для каждого узла.

        Для непрофессионального программиста:
        - Создаём unit для КАЖДОГО узла — и для листьев, и для секций.
        - Это нужно чтобы иметь anchor для любой клаузы в документе.
        - Heading-only узлы тоже получают unit, но с citability_band="low".
        - Рекурсия идёт в children — дерево может быть произвольной глубины.

        Параметры:
        - node:        dict из ClauseNode.to_dict()
        - segment_id:  ID логического сегмента
        - segment_type: тип сегмента ("contract", "appendix", ...)
        - units:       накапливаемый список LegalUnit (мутируется in-place)
        - warnings:    накапливаемый список предупреждений (мутируется in-place)
        - document_id: для логов
        """
        # Читаем все поля узла
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
        recovered = bool(node.get("recovered_via_best_effort", False))
        fallback_reason = node.get("fallback_reason") or None

        # Узлы без effective_uid — пропускаем но всё равно рекурсируем в children
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
                    )
            return

        # Классификация: unit_type и clause_function
        # own_text предпочтительнее subtree_text — он содержит только эту клаузу
        # без текста дочерних узлов которые могут "размыть" сигнал.
        classify_text = own_text or subtree_text
        unit_type = _classify_unit_type(title, classify_text)
        clause_function = _classify_clause_function(title, classify_text, unit_type)

        # Citability из полей Этапа 4
        citability = _compute_citability(node)

        # Cross-refs из own_text (не из subtree_text чтобы не дублировать)
        cross_refs = _extract_cross_refs(effective_uid, own_text)

        unit = LegalUnit(
            unit_id=effective_uid,
            raw_uid=raw_uid,
            scope=scope,
            title=title,
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
            topic_tags=[],  # заполнит TopicTagger на шаге 2
            cross_refs=cross_refs,
            citability=citability,
            node_kind=node_kind,
            semantic_node_type=semantic_node_type,
            recovered_via_best_effort=recovered,
            fallback_reason=fallback_reason,
            diagnostics={
                "unit_type_source": (
                    "title_pattern" if unit_type != LegalUnitType.UNKNOWN else "not_classified"
                ),
                "cross_refs_count": len(cross_refs),
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
                "title": title[:80] if title else None,
                "unit_type": unit_type.value,
                "clause_function": clause_function.value,
                "citability_band": citability.citability_band,
                "node_kind": node_kind,
                "recovered": recovered,
            },
        )

        # Рекурсия в children
        for child in node.get("children") or []:
            if isinstance(child, dict):
                self._collect_units(
                    node=child,
                    segment_id=segment_id,
                    segment_type=segment_type,
                    units=units,
                    warnings=warnings,
                    document_id=document_id,
                )
