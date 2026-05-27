# src/services/structure/cross_ref_resolver.py

"""
CrossRefResolver — резолвинг cross-references между LegalUnit.

Для непрофессионального программиста:
- LegalUnitBuilder уже извлёк из текста "черновики" ссылок (CrossRefStub):
  "раздел 5.2", "Appendix 1", "термин X" — но не знает куда они ведут.
- CrossRefResolver берёт эти черновики и пытается найти
  соответствующий LegalUnit в том же документе.
- После резолвинга CrossRefStub.resolved=True и target_unit_id заполнен.

Архитектурная роль:
- Вызывается после TopicTagger (порядок не критичен, но логически после).
- Работает только с LegalUnit объектами — не знает про БД, MinIO, LLM.
- Rule-based: сопоставляет raw_uid и title паттерны.
- Для clause refs ищет по raw_uid (например "5.2").
- Для appendix refs ищет по scope name или title.
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

    resolved:       True если target_unit_id найден
    target_unit_id: effective_uid целевого LegalUnit (None если не найден)
    resolve_method: как был найден target ("exact_uid" / "fuzzy_uid" /
                    "scope_match" / "title_match" / "unresolved")
    confidence:     уверенность в резолвинге [0.0..1.0]
    """
    resolved: bool
    target_unit_id: str | None
    resolve_method: str
    confidence: float


@dataclass
class CrossRefResolveReport:
    """
    Отчёт о результатах резолвинга для одного snapshot.

    total_stubs:      сколько CrossRefStub было на входе
    resolved_count:   сколько удалось резолвить
    unresolved_count: сколько не удалось
    by_type:          разбивка по ref_type
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
            "resolve_rate": round(
                self.resolved_count / max(self.total_stubs, 1), 3
            ),
            "by_type": self.by_type,
        }


# ---------------------------------------------------------------------------
# CrossRefResolver
# ---------------------------------------------------------------------------

class CrossRefResolver:
    """
    Резолвер cross-references между LegalUnit.

    Использование:
        resolver = CrossRefResolver()
        report = resolver.resolve(units)
        # После этого все CrossRefStub у units с resolved=True имеют target_unit_id

    Принципы:
    - Один проход по всем units строит индексы.
    - Второй проход резолвит каждую CrossRefStub.
    - Резолвинг in-place: изменяет CrossRefStub.resolved и CrossRefStub.target_unit_id.
    - Unresolved stubs остаются с resolved=False — это нормально.
    """

    def resolve(self, units: list[LegalUnit]) -> CrossRefResolveReport:
        """
        Резолвить все CrossRefStub во всех units.

        Строит индексы один раз, потом резолвит каждую stub.
        """
        if not units:
            return CrossRefResolveReport(
                total_stubs=0,
                resolved_count=0,
                unresolved_count=0,
                by_type={},
            )

        # Строим индексы для быстрого поиска
        uid_index = self._build_uid_index(units)
        title_index = self._build_title_index(units)
        definition_index = self._build_definition_index(units)
        scope_index = self._build_scope_index(units)

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
                    uid_index=uid_index,
                    title_index=title_index,
                    definition_index=definition_index,
                    scope_index=scope_index,
                )

                if result.resolved and result.target_unit_id:
                    stub.resolved = True
                    stub.target_unit_id = result.target_unit_id
                    resolved_count += 1
                    by_type[ref_type]["resolved"] += 1

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

    def _build_uid_index(
        self,
        units: list[LegalUnit],
    ) -> dict[str, str]:
        """
        Индекс raw_uid -> unit_id.

        Пример: "5.2" -> "main_contract:5.2"
        """
        index: dict[str, str] = {}
        for unit in units:
            if unit.raw_uid:
                # Нормализуем uid: убираем пробелы
                normalized = unit.raw_uid.strip()
                if normalized and normalized not in index:
                    index[normalized] = unit.unit_id
        return index

    def _build_title_index(
        self,
        units: list[LegalUnit],
    ) -> dict[str, str]:
        """
        Индекс normalized_title -> unit_id.

        Используется для fuzzy title matching.
        """
        index: dict[str, str] = {}
        for unit in units:
            if unit.title:
                # Нормализуем title: lowercase, убираем пунктуацию
                normalized = re.sub(r"[^\w\s]", "", unit.title.lower()).strip()
                if normalized and normalized not in index:
                    index[normalized] = unit.unit_id
        return index

    def _build_definition_index(
        self,
        units: list[LegalUnit],
    ) -> dict[str, str]:
        """
        Индекс defined_term -> unit_id для definition units.

        Ищем определения только среди unit_type=DEFINITION.
        Индексируем по title (который часто содержит имя термина).
        """
        index: dict[str, str] = {}
        for unit in units:
            if unit.unit_type != LegalUnitType.DEFINITION:
                continue
            if unit.title:
                # Нормализуем
                normalized = unit.title.lower().strip().strip('"\'')
                # Также удаляем uid prefix если есть ("1.1 Definitions")
                normalized = re.sub(r"^\d+(?:\.\d+)*\s+", "", normalized).strip()
                if normalized:
                    index[normalized] = unit.unit_id
        return index

    def _build_scope_index(
        self,
        units: list[LegalUnit],
    ) -> dict[str, str]:
        """
        Индекс scope -> unit_id для appendix references.

        Ищем корневые (level=1) units в appendix scopes.
        """
        index: dict[str, str] = {}
        for unit in units:
            if unit.level == 1 and unit.scope and "appendix" in unit.scope.lower():
                scope_normalized = unit.scope.lower().strip()
                if scope_normalized not in index:
                    index[scope_normalized] = unit.unit_id
        return index

    # ── Резолвинг ────────────────────────────────────────────────────────────

    def _resolve_stub(
        self,
        stub: CrossRefStub,
        uid_index: dict[str, str],
        title_index: dict[str, str],
        definition_index: dict[str, str],
        scope_index: dict[str, str],
    ) -> ResolveResult:
        """
        Попытаться резолвить одну CrossRefStub.

        Стратегия зависит от ref_type:
        - clause_ref: сначала exact uid match, потом fuzzy
        - appendix_ref: scope match, потом title match
        - definition_ref: definition index match
        """
        ref_type = stub.ref_type
        hint = (stub.target_hint or "").strip()

        if ref_type == "clause_ref":
            return self._resolve_clause_ref(hint, uid_index)
        elif ref_type == "appendix_ref":
            return self._resolve_appendix_ref(hint, scope_index, title_index)
        elif ref_type == "definition_ref":
            return self._resolve_definition_ref(hint, definition_index)
        else:
            return ResolveResult(
                resolved=False,
                target_unit_id=None,
                resolve_method="unknown_ref_type",
                confidence=0.0,
            )

    def _resolve_clause_ref(
        self,
        hint: str,
        uid_index: dict[str, str],
    ) -> ResolveResult:
        """
        Резолвить ссылку на клаузу по uid.

        Шаги:
        1. Exact match: "5.2" -> ищем "5.2" в uid_index
        2. Fuzzy match: "5.2.1" -> пробуем "5.2", "5" если "5.2.1" не найден
        """
        if not hint:
            return ResolveResult(
                resolved=False,
                target_unit_id=None,
                resolve_method="empty_hint",
                confidence=0.0,
            )

        # Exact match
        target = uid_index.get(hint)
        if target:
            return ResolveResult(
                resolved=True,
                target_unit_id=target,
                resolve_method="exact_uid",
                confidence=1.0,
            )

        # Fuzzy: пробуем укоротить uid (5.2.1 -> 5.2 -> 5)
        if "." in hint:
            parts = hint.split(".")
            for i in range(len(parts) - 1, 0, -1):
                shorter = ".".join(parts[:i])
                target = uid_index.get(shorter)
                if target:
                    return ResolveResult(
                        resolved=True,
                        target_unit_id=target,
                        resolve_method="fuzzy_uid",
                        confidence=0.7,
                    )

        return ResolveResult(
            resolved=False,
            target_unit_id=None,
            resolve_method="unresolved",
            confidence=0.0,
        )

    def _resolve_appendix_ref(
        self,
        hint: str,
        scope_index: dict[str, str],
        title_index: dict[str, str],
    ) -> ResolveResult:
        """
        Резолвить ссылку на приложение.

        Шаги:
        1. Scope match: hint="1" -> ищем scope содержащий "appendix_1"
        2. Title match: hint="A" -> ищем title содержащий "appendix a"
        """
        if not hint:
            return ResolveResult(
                resolved=False,
                target_unit_id=None,
                resolve_method="empty_hint",
                confidence=0.0,
            )

        hint_lower = hint.lower().strip()

        # Scope match
        for scope, unit_id in scope_index.items():
            if hint_lower in scope or scope.endswith(f"_{hint_lower}"):
                return ResolveResult(
                    resolved=True,
                    target_unit_id=unit_id,
                    resolve_method="scope_match",
                    confidence=0.85,
                )

        # Title match — ищем в title_index по appendix + hint
        appendix_pattern = re.compile(
            r"appendix\s*" + re.escape(hint_lower) +
            r"|annex\s*" + re.escape(hint_lower) +
            r"|приложение\s*" + re.escape(hint_lower),
            re.IGNORECASE,
        )
        for title_key, unit_id in title_index.items():
            if appendix_pattern.search(title_key):
                return ResolveResult(
                    resolved=True,
                    target_unit_id=unit_id,
                    resolve_method="title_match",
                    confidence=0.75,
                )

        return ResolveResult(
            resolved=False,
            target_unit_id=None,
            resolve_method="unresolved",
            confidence=0.0,
        )

    def _resolve_definition_ref(
        self,
        hint: str,
        definition_index: dict[str, str],
    ) -> ResolveResult:
        """
        Резолвить ссылку на определение термина.

        Шаги:
        1. Exact match по нормализованному термину
        2. Partial match если exact не нашли
        """
        if not hint:
            return ResolveResult(
                resolved=False,
                target_unit_id=None,
                resolve_method="empty_hint",
                confidence=0.0,
            )

        hint_normalized = hint.lower().strip().strip('"\'')

        # Exact match
        target = definition_index.get(hint_normalized)
        if target:
            return ResolveResult(
                resolved=True,
                target_unit_id=target,
                resolve_method="exact_definition",
                confidence=0.9,
            )

        # Partial match — проверяем startswith
        for term, unit_id in definition_index.items():
            if term.startswith(hint_normalized) or hint_normalized.startswith(term):
                if len(hint_normalized) >= 3 and len(term) >= 3:
                    return ResolveResult(
                        resolved=True,
                        target_unit_id=unit_id,
                        resolve_method="partial_definition",
                        confidence=0.6,
                    )

        return ResolveResult(
            resolved=False,
            target_unit_id=None,
            resolve_method="unresolved",
            confidence=0.0,
        )
    

