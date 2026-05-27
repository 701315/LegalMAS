# src/services/structure/toc_guard.py

"""
TOC Guard — policy layer для structural pipeline.

Роль модуля:
- принимать ParsedTOC + TOCReliabilityResult как факты от parser;
- выносить policy decision: reliable_toc / partial_toc / reject_toc;
- вычислять false_positive_indexes и recoverable_indexes
  как ИНДЕКСЫ ЭЛЕМЕНТОВ (source_element_indexes), а не entry_index;
- не делать никакого matching, parsing или scoring самостоятельно.

Ключевой контракт индексов:
- false_positive_indexes: set[int] — индексы элементов документа,
  которые guard считает НЕ TOC-строками (body/definition-like).
  Classifier должен помечать их как toc_false_positive.
- recoverable_indexes: set[int] — индексы элементов документа,
  которые входят в корректные TOC entries и должны сохраняться
  как body candidates при partial_toc / reject_toc.

Эти индексы всегда относятся к тому списку elements,
на котором был вызван detect_toc_block / parse_toc_entries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.logging import get_logger
from services.structure.toc_parser import ParsedTOC, ParsedTOCEntry, TOCReliabilityResult

logger = get_logger(__name__)

# ── Публичные константы решений ───────────────────────────────────────────────

TOC_GUARD_RELIABLE = "reliable_toc"
TOC_GUARD_PARTIAL = "partial_toc"
TOC_GUARD_REJECT = "reject_toc"

_VALID_DECISIONS: frozenset[str] = frozenset(
    {TOC_GUARD_RELIABLE, TOC_GUARD_PARTIAL, TOC_GUARD_REJECT}
)

# ── Helpers нормализации ──────────────────────────────────────────────────────


def _norm_index_set(values: Any) -> set[int]:
    """
    Приводит любую коллекцию к set[int] неотрицательных индексов.
    Неконвертируемые значения молча пропускаются.
    """
    out: set[int] = set()
    for value in values or []:
        try:
            iv = int(value)
        except Exception:
            continue
        if iv >= 0:
            out.add(iv)
    return out


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


# ── Dataclass verdict ─────────────────────────────────────────────────────────


@dataclass(slots=True)
class TOCGuardVerdict:
    """
    Policy-решение TOC guard.

    Поля:
        decision: reliable_toc / partial_toc / reject_toc.
        toc_quality: high / partial / low / none — человекочитаемый уровень.
        toc_reliability: float 0.0–1.0, копия partial_reliability из parser.
        suppress_body_elements: True только при reliable_toc.
        preserve_body_candidates: True при partial_toc и reject_toc.
        reasons: объяснение решения для diagnostics/логов.
        false_positive_indexes: ELEMENT indexes — не TOC, а body-like строки.
        recoverable_indexes: ELEMENT indexes — корректные TOC entries,
            которые при partial/reject надо сохранять как body candidates.
        diagnostics: дополнительные числовые поля для pipeline diagnostics.
    """

    decision: str
    toc_quality: str
    toc_reliability: float
    suppress_body_elements: bool
    preserve_body_candidates: bool
    reasons: list[str] = field(default_factory=list)
    false_positive_indexes: set[int] = field(default_factory=set)
    recoverable_indexes: set[int] = field(default_factory=set)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Нормализуем decision
        decision = str(self.decision or "").strip().lower() or TOC_GUARD_REJECT
        if decision not in _VALID_DECISIONS:
            raise ValueError(
                f"Unsupported TOC guard decision: {decision!r}. "
                f"Expected one of {sorted(_VALID_DECISIONS)}"
            )
        self.decision = decision

        # Нормализуем остальные поля
        self.toc_quality = str(self.toc_quality or "").strip().lower() or "none"
        self.toc_reliability = max(0.0, min(1.0, _safe_float(self.toc_reliability)))
        self.suppress_body_elements = bool(self.suppress_body_elements)
        self.preserve_body_candidates = bool(self.preserve_body_candidates)
        self.reasons = [
            str(x).strip()
            for x in (self.reasons or [])
            if str(x).strip()
        ]
        self.false_positive_indexes = _norm_index_set(self.false_positive_indexes)
        self.recoverable_indexes = _norm_index_set(self.recoverable_indexes)
        self.diagnostics = dict(self.diagnostics or {})

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "toc_quality": self.toc_quality,
            "toc_reliability": self.toc_reliability,
            "suppress_body_elements": self.suppress_body_elements,
            "preserve_body_candidates": self.preserve_body_candidates,
            "reasons": list(self.reasons),
            "false_positive_indexes": sorted(self.false_positive_indexes),
            "recoverable_indexes": sorted(self.recoverable_indexes),
            "diagnostics": dict(self.diagnostics),
        }


# ── Helpers для анализа entry text ───────────────────────────────────────────


def _entry_text(entry: ParsedTOCEntry) -> str:
    """
    Возвращает максимально полный текст TOC entry для false positive detection.

    Приоритет:
    1. raw_text — самый полный, включает page hint и форматирование.
    2. title — очищенный заголовок.
    3. normalized_title — fallback.
    """
    return (entry.raw_text or entry.title or entry.normalized_title or "").strip()


def _entry_source_element_indexes(entry: ParsedTOCEntry) -> set[int]:
    """
    Возвращает set[int] из source_element_indexes entry.

    Только неотрицательные значения.
    Это ключ: false_positive_indexes и recoverable_indexes
    должны быть element indexes, не entry_index.
    """
    return {
        int(idx)
        for idx in (entry.source_element_indexes or [])
        if isinstance(idx, int) and idx >= 0
    }


def _looks_substantive(text: str) -> bool:
    """
    Строка выглядит как substantive body clause, а не TOC-заголовок.

    Признаки:
    - слишком много слов для заголовка;
    - юридические/обязательственные маркеры;
    - кавычки (типичны для определений и назначений).
    """
    if not text:
        return False

    words = text.split()
    lower = text.lower()

    if len(words) >= 18:
        return True

    if len(text) >= 140:
        return True

    # Юридические маркеры, типичные для тела договора
    markers = (
        "обяз", "долж", "вправе", "обязан", "гарант", "ответствен",
        "убыт", "неустой", "расторжен", "оплат", "цена", "расчет",
        "передач", "товар", "имуще", "продав", "покупат",
        "стороны договорились", "настоящ",
    )
    if any(marker in lower for marker in markers):
        return True

    if "«" in text or "»" in text:
        return True

    return False


def _looks_definition_like(text: str) -> bool:
    """
    Строка выглядит как определение термина, а не TOC-заголовок.

    Признаки:
    - явные слова-определители;
    - кавычки + двоеточие (типичный шаблон определения в договоре);
    - завершение точкой с запятой у длинной строки.
    """
    if not text:
        return False

    lower = text.lower()

    if " означает " in lower or " понимается " in lower:
        return True

    if ("«" in text and "»" in text) or ('"' in text and ":" in text):
        return True

    if len(text.split()) >= 8 and text.endswith(";"):
        return True

    return False


# ── Основная функция ──────────────────────────────────────────────────────────


def evaluate_toc_guard(
    parsed_toc: ParsedTOC,
    reliability: TOCReliabilityResult,
    *,
    document_id: str | None = None,
) -> TOCGuardVerdict:
    """
    Вычисляет policy verdict для TOC.

    Принимает:
    - parsed_toc: ParsedTOC — результат parse_toc_entries().
    - reliability: TOCReliabilityResult — результат compute_partial_reliability().

    Возвращает:
    - TOCGuardVerdict с decision, suppress flags и element indexes.

    Решения:
    - reliable_toc: высокая reliability, мало false positives, мало stale.
      suppress_body_elements=True — pipeline может убрать TOC block из body.
    - partial_toc: средняя reliability или есть false positives.
      suppress_body_elements=False, preserve_body_candidates=True.
    - reject_toc: низкая reliability или TOC не обнаружен.
      suppress_body_elements=False, preserve_body_candidates=True.

    Важно про индексы:
    - false_positive_indexes и recoverable_indexes — это ELEMENT indexes,
      взятые из entry.source_element_indexes.
    - stale entries (toc_missing_in_body) НЕ считаются false positive.
      Они влияют только на decision через stale_ratio.
    """
    doc_id = str(document_id or "").strip()

    # ── Ранний reject при пустом TOC ─────────────────────────────────────────

    if not parsed_toc.detected or not parsed_toc.entries:
        verdict = TOCGuardVerdict(
            decision=TOC_GUARD_REJECT,
            toc_quality="none",
            toc_reliability=0.0,
            suppress_body_elements=False,
            preserve_body_candidates=True,
            reasons=["toc_not_detected_or_empty"],
            false_positive_indexes=set(),
            recoverable_indexes=set(),
            diagnostics={
                "entries_total": 0,
                "false_positive_count": 0,
                "recoverable_count": 0,
                "stale_entries": 0,
                "stale_ratio": 0.0,
                "false_positive_ratio": 0.0,
                "partial_reliability": 0.0,
                "confidence_band": "none",
                "is_reliable": False,
            },
        )
        logger.debug(
            "STRUCTURE toc_guard_verdict",
            extra={"document_id": doc_id, **verdict.to_dict()},
        )
        return verdict

    # ── Читаем reliability напрямую по snake_case атрибутам ──────────────────
    # Никаких getattr со строками — работаем с типизированным dataclass.

    rel_score: float = reliability.partial_reliability
    band: str = reliability.confidence_band
    is_rel: bool = reliability.is_reliable
    rel_reasons: list[str] = list(reliability.reasons or [])

    entries = parsed_toc.entries

    # ── Классифицируем каждую entry по element indexes ────────────────────────
    #
    # ВАЖНО: используем entry.source_element_indexes, а НЕ entry.entry_index.
    # entry_index — это порядковый номер entry в списке ParsedTOC.entries,
    # он не имеет смысла для classifier или pipeline.
    # source_element_indexes — это индексы реальных элементов документа.

    false_positive_indexes: set[int] = set()
    recoverable_candidate_indexes: set[int] = set()
    stale_count = 0

    for entry in entries:
        text = _entry_text(entry)
        source_indexes = _entry_source_element_indexes(entry)

        # Считаем stale отдельно — это не false positive.
        # Stale = entry была в TOC, но не нашла match в body headings.
        # Это может быть из-за плохого matching, а не из-за природы строки.
        if entry.toc_missing_in_body:
            stale_count += 1

        # False positive = строка по своей природе не является TOC-заголовком.
        # Это substantive clause или definition — она должна остаться в body.
        is_false_positive = _looks_substantive(text) or _looks_definition_like(text)

        if is_false_positive:
            # Все element indexes этой entry — false positives.
            false_positive_indexes.update(source_indexes)
        else:
            # Корректные TOC entries: их element indexes могут быть recoverable
            # при partial_toc / reject_toc.
            recoverable_candidate_indexes.update(source_indexes)

    # ── Считаем ratio для decision ────────────────────────────────────────────

    # Считаем fp_ratio по числу entries, а не по числу element indexes.
    # Это более стабильная метрика: один длинный multiline entry
    # не должен перевешивать всё просто потому что у него много source indexes.
    fp_entries_count = sum(
        1 for entry in entries
        if _looks_substantive(_entry_text(entry)) or _looks_definition_like(_entry_text(entry))
    )
    total_entries = len(entries)

    fp_ratio: float = fp_entries_count / total_entries
    stale_ratio: float = stale_count / total_entries

    # ── Формируем reasons ─────────────────────────────────────────────────────

    reasons: list[str] = list(rel_reasons)

    if false_positive_indexes:
        reasons.append("toc_contains_false_positive_like_entries")
    if stale_count:
        reasons.append("toc_contains_stale_entries")

    # ── Policy decision ───────────────────────────────────────────────────────

    if is_rel and band == "high" and fp_ratio <= 0.10 and stale_ratio <= 0.20:
        # Надёжный TOC: pipeline может suppress TOC block из body.
        decision = TOC_GUARD_RELIABLE
        quality = "high"
        suppress_body_elements = True
        preserve_body_candidates = False
        # В reliable режиме recoverable_indexes не нужны —
        # suppression идёт по semantic types в pipeline, не по этому списку.
        final_recoverable: set[int] = set()

    elif rel_score >= 0.45 and fp_ratio <= 0.35:
        # Частичный TOC: аннотируем, но не suppress.
        decision = TOC_GUARD_PARTIAL
        quality = "partial"
        suppress_body_elements = False
        preserve_body_candidates = True
        # Recoverable = корректные TOC entries, которые надо сохранить в body.
        final_recoverable = recoverable_candidate_indexes

    else:
        # Слабый TOC или много false positives: полностью игнорируем для body.
        decision = TOC_GUARD_REJECT
        quality = "low"
        suppress_body_elements = False
        preserve_body_candidates = True
        final_recoverable = recoverable_candidate_indexes

    # ── Собираем verdict ──────────────────────────────────────────────────────

    verdict = TOCGuardVerdict(
        decision=decision,
        toc_quality=quality,
        toc_reliability=rel_score,
        suppress_body_elements=suppress_body_elements,
        preserve_body_candidates=preserve_body_candidates,
        reasons=reasons,
        false_positive_indexes=false_positive_indexes,
        recoverable_indexes=final_recoverable,
        diagnostics={
            "entries_total": total_entries,
            "false_positive_entries_count": fp_entries_count,
            "false_positive_element_count": len(false_positive_indexes),
            "recoverable_element_count": len(final_recoverable),
            "stale_entries": stale_count,
            "stale_ratio": round(stale_ratio, 4),
            "false_positive_ratio": round(fp_ratio, 4),
            "partial_reliability": round(rel_score, 4),
            "confidence_band": band,
            "is_reliable": is_rel,
        },
    )

    logger.info(
        "STRUCTURE toc_guard_verdict",
        extra={"document_id": doc_id, **verdict.to_dict()},
    )
    return verdict

