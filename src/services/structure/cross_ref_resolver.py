# src/services/structure/cross_ref_resolver.py

"""
CrossRefResolver — резолвинг cross-references между LegalUnit.

Для непрофессионального программиста:
- LegalUnitBuilder уже извлёк из текста "черновики" ссылок (CrossRefStub):
  "раздел 5.2", "Appendix 1", "термин X", "item 5.1 of Appendix No. 8" —
  но не знает куда они ведут.
- CrossRefResolver берёт эти черновики и пытается найти
  соответствующий LegalUnit в том же document snapshot.
- После резолвинга CrossRefStub.resolved=True и target_unit_id заполнен.

Архитектурная роль:
- Вызывается после TopicTagger.
- Работает только с LegalUnit объектами — не знает про БД, MinIO, LLM.
- Rule-based: сопоставляет raw_uid, scope, title и appendix/item patterns.
- Для clause refs ищет сначала в том же scope, потом глобально.
- Для appendix refs ищет appendix root unit по scope/title/raw_uid.
- Для appendix_item_ref сначала находит appendix scope, потом item внутри него.
- Для definition refs ищет по title в definition units.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from core.logging import get_logger
from services.structure.legal_unit_models import CrossRefStub, LegalUnit, LegalUnitType

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Вспомогательные типы
# ---------------------------------------------------------------------------

@dataclass
class ResolveResult:
    """
    Итог резолвинга одной CrossRefStub.
    """

    resolved: bool
    target_unit_id: str | None
    resolve_method: str
    confidence: float


@dataclass
class CrossRefResolveReport:
    """
    Отчёт о результатах резолвинга для одного snapshot.
    """

    total_stubs: int
    resolved_count: int
    unresolved_count: int
    by_type: dict[str, dict[str, int]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_stubs": self.total_stubs,
            "resolved_count": self.resolved_count,
            "unresolved_count": self.unresolved_count,
            "resolve_rate": round(self.resolved_count / max(self.total_stubs, 1), 3),
            "by_type": self.by_type,
        }


# ---------------------------------------------------------------------------
# Нормализация
# ---------------------------------------------------------------------------

_ROMAN_MAP: dict[str, int] = {
    "I": 1,
    "II": 2,
    "III": 3,
    "IV": 4,
    "V": 5,
    "VI": 6,
    "VII": 7,
    "VIII": 8,
    "IX": 9,
    "X": 10,
    "XI": 11,
    "XII": 12,
    "XIII": 13,
    "XIV": 14,
    "XV": 15,
}


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_uid(value: Any) -> str:
    return _normalize_text(value)


def _normalize_title_key(value: Any) -> str:
    text = _normalize_text(value).lower()
    text = re.sub(r"[^\w\s№#]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _is_appendix_scope(scope: str) -> bool:
    s = _normalize_text(scope).lower()
    return "appendix" in s or "annex" in s or "schedule" in s or "exhibit" in s or "прилож" in s


def _normalize_appendix_hint(value: str) -> str:
    raw = _normalize_text(value).upper()
    raw = re.sub(r"^(NO\.?|№|#)\s*", "", raw, flags=re.IGNORECASE).strip()
    if raw in _ROMAN_MAP:
        return str(_ROMAN_MAP[raw])
    return raw.lower()


def _appendix_aliases(value: str) -> set[str]:
    normalized = _normalize_appendix_hint(value)
    aliases = {normalized}

    upper = normalized.upper()
    if upper in _ROMAN_MAP:
        aliases.add(str(_ROMAN_MAP[upper]))

    if normalized.isdigit():
        number = int(normalized)
        for roman, arabic in _ROMAN_MAP.items():
            if arabic == number:
                aliases.add(roman.lower())
                break

    return {a for a in aliases if a}


def _extract_appendix_token_from_scope(scope: str) -> str | None:
    normalized_scope = _normalize_text(scope).lower()
    if not normalized_scope:
        return None

    patterns = [
        r"(?:appendix|annex|schedule|exhibit|attachment)[\s:_-]*(?:no[\s._-]*)?([a-z0-9ivx]+)$",
        r"(?:appendix|annex|schedule|exhibit|attachment)[\s:_-]+([a-z0-9ivx]+)",
        r"(?:приложени[еяй])[\s:_-]*(?:№|#)?\s*([a-z0-9ivx]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized_scope, flags=re.IGNORECASE)
        if match:
            return _normalize_appendix_hint(match.group(1))
    return None


def _parse_appendix_item_hint(hint: str) -> tuple[str | None, str | None]:
    normalized = _normalize_text(hint)
    if not normalized:
        return None, None

    match = re.match(
        r"appendix:(?P<appendix>[^:]+):item:(?P<item>\d+(?:\.\d+)*)$",
        normalized,
        flags=re.IGNORECASE,
    )
    if not match:
        return None, None

    appendix_hint = _normalize_appendix_hint(match.group("appendix"))
    item_hint = _normalize_uid(match.group("item"))
    return appendix_hint or None, item_hint or None


# ---------------------------------------------------------------------------
# CrossRefResolver
# ---------------------------------------------------------------------------

class CrossRefResolver:
    """
    Резолвер cross-references между LegalUnit.
    """

    def resolve(self, units: list[LegalUnit]) -> CrossRefResolveReport:
        if not units:
            return CrossRefResolveReport(
                total_stubs=0,
                resolved_count=0,
                unresolved_count=0,
                by_type={},
            )

        unit_by_id = self._build_unit_by_id(units)
        uid_index = self._build_uid_index(units)
        title_index = self._build_title_index(units)
        definition_index = self._build_definition_index(units)
        scope_index = self._build_scope_index(units)
        appendix_root_index = self._build_appendix_root_index(units)
        appendix_item_index = self._build_appendix_item_index(units)

        total_stubs = 0
        resolved_count = 0
        by_type: dict[str, dict[str, int]] = {}

        for unit in units:
            for stub in unit.cross_refs:
                total_stubs += 1
                ref_type = stub.ref_type

                if ref_type not in by_type:
                    by_type[ref_type] = {"total": 0, "resolved": 0}
                by_type[ref_type]["total"] += 1

                result = self._resolve_stub(
                    stub=stub,
                    source_unit=unit,
                    unit_by_id=unit_by_id,
                    uid_index=uid_index,
                    title_index=title_index,
                    definition_index=definition_index,
                    scope_index=scope_index,
                    appendix_root_index=appendix_root_index,
                    appendix_item_index=appendix_item_index,
                )

                if result.resolved and result.target_unit_id and result.target_unit_id != unit.unit_id:
                    stub.resolved = True
                    stub.target_unit_id = result.target_unit_id
                    resolved_count += 1
                    by_type[ref_type]["resolved"] += 1

                    try:
                        setattr(stub, "resolve_method", result.resolve_method)
                        setattr(stub, "resolve_confidence", result.confidence)
                    except Exception:
                        pass

                    logger.debug(
                        "CrossRefResolver: stub resolved",
                        extra={
                            "source_unit_id": stub.source_unit_id,
                            "raw_ref_text": stub.raw_ref_text,
                            "ref_type": ref_type,
                            "target_unit_id": result.target_unit_id,
                            "resolve_method": result.resolve_method,
                            "confidence": result.confidence,
                        },
                    )

        unresolved_count = total_stubs - resolved_count

        logger.info(
            "CrossRefResolver: resolve complete",
            extra={
                "total_units": len(units),
                "total_stubs": total_stubs,
                "resolved_count": resolved_count,
                "unresolved_count": unresolved_count,
                "resolve_rate": round(resolved_count / max(total_stubs, 1), 3),
                "by_type": by_type,
            },
        )

        return CrossRefResolveReport(
            total_stubs=total_stubs,
            resolved_count=resolved_count,
            unresolved_count=unresolved_count,
            by_type=by_type,
        )

    # ── Индексы ───────────────────────────────────────────────────────────────

    def _build_unit_by_id(self, units: list[LegalUnit]) -> dict[str, LegalUnit]:
        index: dict[str, LegalUnit] = {}
        for unit in units:
            if unit.unit_id and unit.unit_id not in index:
                index[unit.unit_id] = unit
        return index

    def _build_uid_index(
        self,
        units: list[LegalUnit],
    ) -> dict[str, list[LegalUnit]]:
        """
        Индекс raw_uid -> список units.
        """
        index: dict[str, list[LegalUnit]] = {}
        for unit in units:
            normalized = _normalize_uid(unit.raw_uid)
            if normalized:
                index.setdefault(normalized, []).append(unit)
        return index

    def _build_title_index(
        self,
        units: list[LegalUnit],
    ) -> dict[str, list[LegalUnit]]:
        index: dict[str, list[LegalUnit]] = {}
        for unit in units:
            normalized = _normalize_title_key(unit.title)
            if normalized:
                index.setdefault(normalized, []).append(unit)
        return index

    def _build_definition_index(
        self,
        units: list[LegalUnit],
    ) -> dict[str, list[LegalUnit]]:
        index: dict[str, list[LegalUnit]] = {}
        for unit in units:
            if unit.unit_type != LegalUnitType.DEFINITION:
                continue
            normalized = _normalize_text(unit.title).lower().strip().strip("\"'")
            normalized = re.sub(r"^\d+(?:\.\d+)*\s+", "", normalized).strip()
            if normalized:
                index.setdefault(normalized, []).append(unit)
        return index

    def _build_scope_index(
        self,
        units: list[LegalUnit],
    ) -> dict[str, list[LegalUnit]]:
        index: dict[str, list[LegalUnit]] = {}
        for unit in units:
            scope_normalized = _normalize_text(unit.scope).lower()
            if scope_normalized:
                index.setdefault(scope_normalized, []).append(unit)
        return index

    def _build_appendix_root_index(
        self,
        units: list[LegalUnit],
    ) -> dict[str, list[LegalUnit]]:
        """
        appendix token -> appendix root candidates
        """
        index: dict[str, list[LegalUnit]] = {}

        for unit in units:
            if not _is_appendix_scope(unit.scope):
                continue

            candidates: set[str] = set()

            scope_token = _extract_appendix_token_from_scope(unit.scope)
            if scope_token:
                candidates.update(_appendix_aliases(scope_token))

            raw_uid = _normalize_uid(unit.raw_uid)
            if raw_uid:
                candidates.update(_appendix_aliases(raw_uid))

            title = _normalize_text(unit.title)
            title_match = re.search(
                r"(?:appendix|annex|schedule|exhibit|attachment|приложени[еяй])\s*(?:no\.?|№|#)?\s*([A-Z0-9IVX]+)",
                title,
                flags=re.IGNORECASE,
            )
            if title_match:
                candidates.update(_appendix_aliases(title_match.group(1)))

            if not candidates:
                continue

            is_root_like = unit.level == 1 or unit.unit_type == LegalUnitType.APPENDIX_REFERENCE
            if not is_root_like:
                continue

            for token in candidates:
                index.setdefault(token, []).append(unit)

        return index

    def _build_appendix_item_index(
        self,
        units: list[LegalUnit],
    ) -> dict[tuple[str, str], list[LegalUnit]]:
        """
        (appendix_token, raw_uid) -> units inside appendix scope
        """
        index: dict[tuple[str, str], list[LegalUnit]] = {}

        for unit in units:
            if not _is_appendix_scope(unit.scope):
                continue

            raw_uid = _normalize_uid(unit.raw_uid)
            appendix_token = _extract_appendix_token_from_scope(unit.scope)
            if not raw_uid or not appendix_token:
                continue

            for alias in _appendix_aliases(appendix_token):
                index.setdefault((alias, raw_uid), []).append(unit)

        return index

    # ── Резолвинг ────────────────────────────────────────────────────────────

    def _resolve_stub(
        self,
        *,
        stub: CrossRefStub,
        source_unit: LegalUnit,
        unit_by_id: dict[str, LegalUnit],
        uid_index: dict[str, list[LegalUnit]],
        title_index: dict[str, list[LegalUnit]],
        definition_index: dict[str, list[LegalUnit]],
        scope_index: dict[str, list[LegalUnit]],
        appendix_root_index: dict[str, list[LegalUnit]],
        appendix_item_index: dict[tuple[str, str], list[LegalUnit]],
    ) -> ResolveResult:
        ref_type = stub.ref_type
        hint = _normalize_text(stub.target_hint)

        if ref_type == "clause_ref":
            return self._resolve_clause_ref(
                source_unit=source_unit,
                hint=hint,
                uid_index=uid_index,
            )
        if ref_type == "appendix_ref":
            return self._resolve_appendix_ref(
                hint=hint,
                appendix_root_index=appendix_root_index,
                scope_index=scope_index,
                title_index=title_index,
            )
        if ref_type == "appendix_item_ref":
            return self._resolve_appendix_item_ref(
                hint=hint,
                appendix_root_index=appendix_root_index,
                appendix_item_index=appendix_item_index,
            )
        if ref_type == "definition_ref":
            return self._resolve_definition_ref(
                hint=hint,
                definition_index=definition_index,
            )

        return ResolveResult(
            resolved=False,
            target_unit_id=None,
            resolve_method="unknown_ref_type",
            confidence=0.0,
        )

    def _resolve_clause_ref(
        self,
        *,
        source_unit: LegalUnit,
        hint: str,
        uid_index: dict[str, list[LegalUnit]],
    ) -> ResolveResult:
        if not hint:
            return ResolveResult(False, None, "empty_hint", 0.0)

        candidates = uid_index.get(hint, [])
        if len(candidates) == 1:
            return ResolveResult(True, candidates[0].unit_id, "global_exact_uid", 0.9)

        if len(candidates) > 1:
            same_scope = [
                unit for unit in candidates
                if _normalize_text(unit.scope).lower() == _normalize_text(source_unit.scope).lower()
            ]
            if len(same_scope) == 1:
                return ResolveResult(True, same_scope[0].unit_id, "same_scope_exact_uid", 1.0)

            top_level = [unit for unit in candidates if unit.level == 1]
            if len(top_level) == 1:
                return ResolveResult(True, top_level[0].unit_id, "top_level_uid_disambiguation", 0.75)

        if "." in hint:
            parts = hint.split(".")
            for i in range(len(parts) - 1, 0, -1):
                shorter = ".".join(parts[:i])
                shorter_candidates = uid_index.get(shorter, [])
                if len(shorter_candidates) == 1:
                    return ResolveResult(True, shorter_candidates[0].unit_id, "fuzzy_parent_uid", 0.6)

                same_scope_shorter = [
                    unit for unit in shorter_candidates
                    if _normalize_text(unit.scope).lower() == _normalize_text(source_unit.scope).lower()
                ]
                if len(same_scope_shorter) == 1:
                    return ResolveResult(True, same_scope_shorter[0].unit_id, "same_scope_fuzzy_parent_uid", 0.7)

        return ResolveResult(False, None, "unresolved_clause_ref", 0.0)

    def _resolve_appendix_ref(
        self,
        *,
        hint: str,
        appendix_root_index: dict[str, list[LegalUnit]],
        scope_index: dict[str, list[LegalUnit]],
        title_index: dict[str, list[LegalUnit]],
    ) -> ResolveResult:
        if not hint:
            return ResolveResult(False, None, "empty_hint", 0.0)

        aliases = _appendix_aliases(hint)

        for alias in aliases:
            candidates = appendix_root_index.get(alias, [])
            if len(candidates) == 1:
                return ResolveResult(True, candidates[0].unit_id, "appendix_root_exact", 0.95)
            if len(candidates) > 1:
                root_like = [u for u in candidates if u.level == 1]
                if len(root_like) == 1:
                    return ResolveResult(True, root_like[0].unit_id, "appendix_root_level_filtered", 0.85)

        for scope_key, scoped_units in scope_index.items():
            if not _is_appendix_scope(scope_key):
                continue
            scope_token = _extract_appendix_token_from_scope(scope_key)
            if scope_token and scope_token in aliases:
                root_like = [u for u in scoped_units if u.level == 1]
                if len(root_like) == 1:
                    return ResolveResult(True, root_like[0].unit_id, "appendix_scope_match", 0.8)

        appendix_patterns = []
        for alias in aliases:
            appendix_patterns.append(
                re.compile(
                    r"(appendix|annex|schedule|exhibit|attachment|приложени[еяй])\s*(no\.?|№|#)?\s*" + re.escape(alias),
                    flags=re.IGNORECASE,
                )
            )

        for title_key, units in title_index.items():
            if not units:
                continue
            if any(pattern.search(title_key) for pattern in appendix_patterns):
                return ResolveResult(True, units[0].unit_id, "appendix_title_match", 0.7)

        return ResolveResult(False, None, "unresolved_appendix_ref", 0.0)

    def _resolve_appendix_item_ref(
        self,
        *,
        hint: str,
        appendix_root_index: dict[str, list[LegalUnit]],
        appendix_item_index: dict[tuple[str, str], list[LegalUnit]],
    ) -> ResolveResult:
        appendix_hint, item_hint = _parse_appendix_item_hint(hint)
        if not appendix_hint or not item_hint:
            return ResolveResult(False, None, "invalid_appendix_item_hint", 0.0)

        appendix_candidates = []
        for alias in _appendix_aliases(appendix_hint):
            appendix_candidates.extend(appendix_root_index.get(alias, []))

        if not appendix_candidates:
            return ResolveResult(False, None, "appendix_scope_not_found", 0.0)

        for alias in _appendix_aliases(appendix_hint):
            candidates = appendix_item_index.get((alias, item_hint), [])
            if len(candidates) == 1:
                return ResolveResult(True, candidates[0].unit_id, "appendix_scoped_exact_item", 1.0)

            if len(candidates) > 1:
                level_sorted = sorted(candidates, key=lambda u: u.level)
                return ResolveResult(True, level_sorted[0].unit_id, "appendix_scoped_ambiguous_lowest_level", 0.75)

        if "." in item_hint:
            parts = item_hint.split(".")
            for i in range(len(parts) - 1, 0, -1):
                shorter = ".".join(parts[:i])
                for alias in _appendix_aliases(appendix_hint):
                    candidates = appendix_item_index.get((alias, shorter), [])
                    if len(candidates) == 1:
                        return ResolveResult(True, candidates[0].unit_id, "appendix_scoped_fuzzy_parent_item", 0.7)

        return ResolveResult(False, None, "appendix_item_not_found", 0.0)

    def _resolve_definition_ref(
        self,
        *,
        hint: str,
        definition_index: dict[str, list[LegalUnit]],
    ) -> ResolveResult:
        if not hint:
            return ResolveResult(False, None, "empty_hint", 0.0)

        hint_normalized = hint.lower().strip().strip("\"'")
        exact = definition_index.get(hint_normalized, [])
        if len(exact) == 1:
            return ResolveResult(True, exact[0].unit_id, "exact_definition", 0.9)

        if len(exact) > 1:
            shortest_title = sorted(exact, key=lambda u: len(_normalize_text(u.title)))[0]
            return ResolveResult(True, shortest_title.unit_id, "exact_definition_shortest_title", 0.7)

        for term, candidates in definition_index.items():
            if len(hint_normalized) >= 3 and len(term) >= 3:
                if term.startswith(hint_normalized) or hint_normalized.startswith(term):
                    return ResolveResult(True, candidates[0].unit_id, "partial_definition", 0.6)

        return ResolveResult(False, None, "unresolved_definition_ref", 0.0)


        
