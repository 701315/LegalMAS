# src/engine/content/citation_resolver.py

"""
CitationResolver — извлечение точных цитат из текста для findings.

Для непрофессионального программиста:
- Когда детектор находит проблему в договоре, он должен показать
  конкретную цитату: "вот точный текст который подтверждает находку".
- CitationResolver принимает finding (результат детектора) и список
  LegalUnit, и возвращает точную цитату с позицией в тексте.

Что возвращает resolver:
- anchor_uid:       effective_uid клаузы (= LegalUnit.unit_id)
- anchor_title:     заголовок клаузы
- quoted_text:      цитата — фрагмент текста клаузы
- quote_start_char: позиция начала цитаты в own_text узла
- quote_end_char:   позиция конца цитаты
- page_start:       первая страница клаузы
- page_end:         последняя страница клаузы
- source_unit_id:   unit_id LegalUnit из которого взята цитата

Архитектурная роль:
- вызывается после детектора, перед save_check_result;
- не знает про БД, MinIO, LLM;
- pure функции без side effects;
- работает с LegalUnit objects или с raw dict из legal_units_v1.json.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Модели
# ---------------------------------------------------------------------------

@dataclass
class CitationAnchor:
    """
    Точный anchor для одного finding.

    Для непрофессионального программиста:
    - Это структура которая говорит "вот откуда взята информация для finding".
    - anchor_uid — это canonical ID клаузы в документе.
    - quoted_text — это дословная цитата из текста договора.
    - Если цитату не удалось найти — quoted_text=None, это нормально.

    Все поля опциональны кроме anchor_uid — это минимум для citation.
    """

    # Canonical identity клаузы
    anchor_uid: str                   # effective_uid клаузы ("main_contract:5.2")
    anchor_title: str | None = None   # заголовок клаузы

    # Цитата
    quoted_text: str | None = None        # фрагмент текста
    quote_start_char: int | None = None   # позиция начала в own_text
    quote_end_char: int | None = None     # позиция конца в own_text

    # Страницы
    page_start: int | None = None
    page_end: int | None = None

    # Источник
    source_unit_id: str | None = None  # unit_id откуда взята цитата

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchor_uid": self.anchor_uid,
            "anchor_title": self.anchor_title,
            "quoted_text": self.quoted_text,
            "quote_start_char": self.quote_start_char,
            "quote_end_char": self.quote_end_char,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "source_unit_id": self.source_unit_id,
        }

    @property
    def has_quote(self) -> bool:
        return bool(self.quoted_text and self.quoted_text.strip())

    @property
    def has_page(self) -> bool:
        return self.page_start is not None


@dataclass
class CitationResolveResult:
    """
    Результат резолвинга citation для одного finding.

    anchor:          CitationAnchor если удалось найти
    resolve_method:  как нашли цитату
    confidence:      уверенность [0.0..1.0]
    fallback_used:   True если использовался fallback (не идеальный anchor)
    """
    anchor: CitationAnchor | None
    resolve_method: str
    confidence: float
    fallback_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchor": self.anchor.to_dict() if self.anchor else None,
            "resolve_method": self.resolve_method,
            "confidence": self.confidence,
            "fallback_used": self.fallback_used,
        }


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _normalize_text_for_search(text: str) -> str:
    """
    Нормализовать текст для нечёткого поиска.

    Убираем лишние пробелы и переносы строк чтобы
    цитата из LLM могла найтись в тексте клаузы
    даже если форматирование немного отличается.
    """
    return re.sub(r"\s+", " ", text.strip())


def _find_quote_in_text(
    quote: str,
    source_text: str,
    *,
    min_quote_len: int = 20,
) -> tuple[int, int] | None:
    """
    Найти позицию цитаты в тексте.

    Для непрофессионального программиста:
    - Пробуем найти цитату дословно (exact match).
    - Если не нашли — пробуем нормализованный поиск (убираем лишние пробелы).
    - Если цитата слишком короткая (< min_quote_len) — не ищем, слишком много шума.

    Возвращает (start, end) или None если не нашли.
    """
    if not quote or not source_text:
        return None

    quote = quote.strip()
    if len(quote) < min_quote_len:
        return None

    # Exact match
    idx = source_text.find(quote)
    if idx >= 0:
        return idx, idx + len(quote)

    # Normalized match — убираем лишние пробелы в обоих текстах
    normalized_quote = _normalize_text_for_search(quote)
    normalized_source = _normalize_text_for_search(source_text)

    if len(normalized_quote) < min_quote_len:
        return None

    idx = normalized_source.find(normalized_quote)
    if idx >= 0:
        # Возвращаем позицию в нормализованном тексте
        # (приближение — в оригинале позиция может отличаться)
        return idx, idx + len(normalized_quote)

    return None


def _extract_sentence_around_position(
    text: str,
    position: int,
    *,
    max_chars: int = 300,
) -> str:
    """
    Извлечь предложение вокруг заданной позиции в тексте.

    Для непрофессионального программиста:
    - Иногда детектор знает "где-то здесь" но не знает точную цитату.
    - Эта функция берёт позицию и возвращает фрагмент текста вокруг неё.
    - Старается остановиться на границе предложения.
    """
    if not text or position < 0 or position >= len(text):
        return ""

    # Ищем начало: идём влево до точки или начала текста
    start = max(0, position - max_chars // 2)
    while start > 0 and text[start - 1] not in ".!?\n":
        if position - start >= max_chars // 2:
            break
        start -= 1

    # Ищем конец: идём вправо до точки или конца текста
    end = min(len(text), position + max_chars // 2)
    while end < len(text) and text[end - 1] not in ".!?\n":
        if end - position >= max_chars // 2:
            break
        end += 1

    return text[start:end].strip()


def _build_anchor_from_unit_dict(unit_dict: dict[str, Any]) -> CitationAnchor:
    """
    Построить CitationAnchor из dict единицы LegalUnit.to_dict().

    Для непрофессионального программиста:
    - unit_dict — это то что приходит из legal_units_v1.json;
    - мы извлекаем anchor_uid, title, страницы.
    - quoted_text пока None — он заполняется отдельно если есть evidence.
    """
    return CitationAnchor(
        anchor_uid=str(unit_dict.get("unit_id") or ""),
        anchor_title=unit_dict.get("title") or None,
        page_start=unit_dict.get("page_start") or None,
        page_end=unit_dict.get("page_end") or None,
        source_unit_id=str(unit_dict.get("unit_id") or ""),
    )


# ---------------------------------------------------------------------------
# CitationResolver
# ---------------------------------------------------------------------------

class CitationResolver:
    """
    Резолвер цитат для findings.

    Использование:
        resolver = CitationResolver()

        # Из clause_uid которую уже знает детектор:
        result = resolver.resolve_from_clause_uid(
            clause_uid="main_contract:5.2",
            evidence_text="The parties agree to arbitration",
            units_by_uid=units_index,
        )

        # Из finding с topic_tags (через evidence bundle):
        result = resolver.resolve_from_topics(
            topics=["governing_law"],
            evidence_text="English law shall govern",
            units=legal_units,
        )

        anchor = result.anchor
        # anchor.anchor_uid, anchor.quoted_text, anchor.page_start ...

    Принципы:
    - Всегда возвращает CitationResolveResult, никогда не бросает исключение.
    - Если цитату найти не удалось — anchor.quoted_text = None, это нормально.
    - Если unit не найден — anchor = None, confidence = 0.
    """

    def resolve_from_clause_uid(
        self,
        clause_uid: str,
        evidence_text: str | None,
        units_by_uid: dict[str, dict[str, Any]],
    ) -> CitationResolveResult:
        """
        Резолвить citation по известному clause_uid.

        Для непрофессионального программиста:
        - Детектор уже знает какой clause_uid относится к finding.
        - Мы ищем этот unit в индексе и извлекаем цитату.

        Параметры:
        - clause_uid:   effective_uid клаузы ("main_contract:5.2")
        - evidence_text: текст evidence от детектора (может быть цитатой)
        - units_by_uid: индекс unit_id -> unit dict из legal_units_v1.json
        """
        clause_uid = (clause_uid or "").strip()
        if not clause_uid:
            return CitationResolveResult(
                anchor=None,
                resolve_method="empty_clause_uid",
                confidence=0.0,
            )

        unit_dict = units_by_uid.get(clause_uid)
        if unit_dict is None:
            # Пробуем найти по частичному совпадению (raw_uid без scope)
            raw_uid = clause_uid.split(":")[-1] if ":" in clause_uid else clause_uid
            for uid, unit in units_by_uid.items():
                if uid.endswith(f":{raw_uid}") or unit.get("raw_uid") == raw_uid:
                    unit_dict = unit
                    break

        if unit_dict is None:
            logger.debug(
                "CitationResolver: unit not found for clause_uid",
                extra={"clause_uid": clause_uid},
            )
            return CitationResolveResult(
                anchor=None,
                resolve_method="unit_not_found",
                confidence=0.0,
            )

        anchor = _build_anchor_from_unit_dict(unit_dict)

        # Пробуем найти цитату в own_text
        own_text = unit_dict.get("own_text") or ""
        if evidence_text and own_text:
            pos = _find_quote_in_text(evidence_text, own_text)
            if pos is not None:
                start, end = pos
                anchor.quoted_text = own_text[start:end]
                anchor.quote_start_char = start
                anchor.quote_end_char = end
                return CitationResolveResult(
                    anchor=anchor,
                    resolve_method="exact_quote_in_own_text",
                    confidence=0.95,
                )

        # Если evidence_text сам выглядит как цитата — используем его
        if evidence_text and len(evidence_text.strip()) >= 20:
            # Проверяем что evidence_text содержится в own_text или subtree_text
            subtree_text = unit_dict.get("subtree_text") or ""
            search_in = own_text or subtree_text

            if search_in and evidence_text.strip() in search_in:
                anchor.quoted_text = evidence_text.strip()
                return CitationResolveResult(
                    anchor=anchor,
                    resolve_method="evidence_text_as_quote",
                    confidence=0.85,
                )

        # Fallback: берём первые 300 символов own_text как цитату
        if own_text and own_text.strip():
            snippet = own_text.strip()[:300]
            # Обрезаем по последнему пробелу чтобы не резать слово
            if len(snippet) == 300:
                last_space = snippet.rfind(" ")
                if last_space > 200:
                    snippet = snippet[:last_space]
            anchor.quoted_text = snippet
            anchor.quote_start_char = 0
            anchor.quote_end_char = len(snippet)
            return CitationResolveResult(
                anchor=anchor,
                resolve_method="own_text_snippet_fallback",
                confidence=0.6,
                fallback_used=True,
            )

        # Нет текста — возвращаем anchor без цитаты
        return CitationResolveResult(
            anchor=anchor,
            resolve_method="anchor_only_no_text",
            confidence=0.4,
            fallback_used=True,
        )

    def resolve_from_topics(
        self,
        topics: list[str],
        evidence_text: str | None,
        units: list[dict[str, Any]],
        *,
        preferred_unit_types: list[str] | None = None,
    ) -> CitationResolveResult:
        """
        Резолвить citation по темам (topic_tags).

        Для непрофессионального программиста:
        - Иногда детектор знает только тему ("governing_law") но не знает clause_uid.
        - Мы ищем units у которых есть совпадение с темами.
        - Если нашли несколько — выбираем с лучшим citability.

        Параметры:
        - topics:               список тем для поиска
        - evidence_text:        текст evidence от детектора
        - units:                список unit dict-ов из legal_units_v1.json
        - preferred_unit_types: приоритетные типы units (например ["governing_law"])
        """
        if not topics or not units:
            return CitationResolveResult(
                anchor=None,
                resolve_method="empty_topics_or_units",
                confidence=0.0,
            )

        topics_set = set(t.lower().strip() for t in topics if t)

        # Ищем units с совпадением тем
        candidates: list[tuple[dict[str, Any], int]] = []  # (unit, score)

        for unit in units:
            unit_topics = set(
                t.lower().strip()
                for t in (unit.get("topic_tags") or [])
                if t
            )
            topic_matches = len(unit_topics & topics_set)

            if topic_matches == 0:
                continue

            # Score
            score = topic_matches * 10

            # Bonus за preferred_unit_types
            if preferred_unit_types:
                unit_type = str(unit.get("unit_type") or "").lower()
                if unit_type in [t.lower() for t in preferred_unit_types]:
                    score += 20

            # Bonus за citability
            citability = unit.get("citability") or {}
            citability_band = str(citability.get("citability_band") or "low").lower()
            if citability_band == "high":
                score += 5
            elif citability_band == "medium":
                score += 2

            candidates.append((unit, score))

        if not candidates:
            return CitationResolveResult(
                anchor=None,
                resolve_method="no_units_match_topics",
                confidence=0.0,
            )

        # Сортируем по score убывание, потом по page_start
        candidates.sort(key=lambda x: (-x[1], int(x[0].get("page_start") or 1)))
        best_unit, best_score = candidates[0]

        # Строим anchor
        anchor = _build_anchor_from_unit_dict(best_unit)

        # Пробуем найти цитату
        own_text = best_unit.get("own_text") or ""
        if evidence_text and own_text:
            pos = _find_quote_in_text(evidence_text, own_text)
            if pos is not None:
                start, end = pos
                anchor.quoted_text = own_text[start:end]
                anchor.quote_start_char = start
                anchor.quote_end_char = end
                return CitationResolveResult(
                    anchor=anchor,
                    resolve_method="topic_match_with_quote",
                    confidence=min(0.9, best_score / 30),
                )

        # Fallback: snippet из own_text
        if own_text and own_text.strip():
            snippet = own_text.strip()[:300]
            if len(snippet) == 300:
                last_space = snippet.rfind(" ")
                if last_space > 200:
                    snippet = snippet[:last_space]
            anchor.quoted_text = snippet
            anchor.quote_start_char = 0
            anchor.quote_end_char = len(snippet)
            return CitationResolveResult(
                anchor=anchor,
                resolve_method="topic_match_snippet_fallback",
                confidence=min(0.65, best_score / 40),
                fallback_used=True,
            )

        return CitationResolveResult(
            anchor=anchor,
            resolve_method="topic_match_no_text",
            confidence=min(0.4, best_score / 50),
            fallback_used=True,
        )

    def resolve_from_exec_result(
        self,
        exec_result: dict[str, Any],
        units: list[dict[str, Any]],
        *,
        units_by_uid: dict[str, dict[str, Any]] | None = None,
    ) -> CitationResolveResult:
        """
        Главный метод: резолвить citation из exec_result детектора.

        Для непрофессионального программиста:
        - Детектор возвращает exec_result — это dict с результатом проверки.
        - Этот метод пытается найти лучший anchor для этого finding.
        - Приоритет: clause_uid > topic_tags > fallback первого unit.

        Стратегии (в порядке приоритета):
        1. Если в exec_result есть clause_uid — ищем по нему.
        2. Если есть source_unit_id — ищем по нему.
        3. Если есть topics в raw — ищем по темам.
        4. Fallback: первый unit из списка с лучшим citability.

        Параметры:
        - exec_result:  dict от детектора
        - units:        список unit dict-ов
        - units_by_uid: опциональный индекс unit_id -> unit dict
                        (если не передан — строится из units)
        """
        if units_by_uid is None:
            units_by_uid = {
                str(u.get("unit_id") or ""): u
                for u in units
                if u.get("unit_id")
            }

        evidence_text = (
            exec_result.get("evidence")
            or str(exec_result.get("reason") or "")
            or None
        )
        if evidence_text:
            evidence_text = evidence_text.strip() or None

        # Стратегия 1: по clause_uid
        clause_uid = (exec_result.get("clause_uid") or "").strip()
        if clause_uid:
            result = self.resolve_from_clause_uid(
                clause_uid=clause_uid,
                evidence_text=evidence_text,
                units_by_uid=units_by_uid,
            )
            if result.anchor is not None:
                return result

        # Стратегия 2: по source_unit_id из raw
        raw = exec_result.get("raw") or {}
        source_unit_id = ""
        if isinstance(raw, dict):
            source_unit_id = (raw.get("source_unit_id") or "").strip()
        if source_unit_id:
            result = self.resolve_from_clause_uid(
                clause_uid=source_unit_id,
                evidence_text=evidence_text,
                units_by_uid=units_by_uid,
            )
            if result.anchor is not None:
                return result

        # Стратегия 3: по topics из raw или exec_result
        topics: list[str] = []
        if isinstance(raw, dict):
            raw_topics = raw.get("topics") or raw.get("topic_tags") or []
            if isinstance(raw_topics, list):
                topics = [str(t) for t in raw_topics if t]

        if not topics:
            # Пробуем угадать тему из check_id
            check_id = (exec_result.get("check_id") or "").lower()
            if "governing_law" in check_id:
                topics = ["governing_law"]
            elif "jurisdiction" in check_id:
                topics = ["jurisdiction", "arbitration"]
            elif "liability" in check_id:
                topics = ["liability_cap", "liability"]
            elif "payment" in check_id:
                topics = ["payment_terms", "purchase_price"]
            elif "warranty" in check_id:
                topics = ["warranties", "representations"]
            elif "termination" in check_id:
                topics = ["termination", "termination_rights"]
            elif "notice" in check_id:
                topics = ["notices"]
            elif "confidential" in check_id:
                topics = ["confidentiality"]
            elif "definition" in check_id:
                topics = ["definitions"]

        if topics:
            result = self.resolve_from_topics(
                topics=topics,
                evidence_text=evidence_text,
                units=units,
            )
            if result.anchor is not None:
                return result

        # Стратегия 4: fallback — первый unit с лучшим citability
        if units:
            citability_order = {"high": 3, "medium": 2, "low": 1}
            sorted_units = sorted(
                units,
                key=lambda u: (
                    -citability_order.get(
                        str((u.get("citability") or {}).get("citability_band") or "low").lower(),
                        0,
                    ),
                    int(u.get("page_start") or 1),
                ),
            )
            best_unit = sorted_units[0]
            anchor = _build_anchor_from_unit_dict(best_unit)

            own_text = best_unit.get("own_text") or ""
            if own_text.strip():
                snippet = own_text.strip()[:200]
                anchor.quoted_text = snippet
                anchor.quote_start_char = 0
                anchor.quote_end_char = len(snippet)

            return CitationResolveResult(
                anchor=anchor,
                resolve_method="best_citability_fallback",
                confidence=0.2,
                fallback_used=True,
            )

        return CitationResolveResult(
            anchor=None,
            resolve_method="no_units_available",
            confidence=0.0,
        )

    @staticmethod
    def build_units_index(units: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """
        Построить индекс unit_id -> unit dict для быстрого поиска.

        Для непрофессионального программиста:
        - Вызови один раз перед серией resolve_from_clause_uid вызовов.
        - Индекс строится за O(n), каждый lookup — O(1).
        """
        index: dict[str, dict[str, Any]] = {}
        for unit in units:
            unit_id = str(unit.get("unit_id") or "").strip()
            if unit_id and unit_id not in index:
                index[unit_id] = unit
        return index
    

