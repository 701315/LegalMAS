# src/services/structure/heading_scoring.py

"""
Scoring / decision слой для heading detection.

Задача этого модуля:
- принимать raw heading hypothesis (uid, title, raw_text);
- использовать feature/predicate слой из heading_features.py;
- учитывать TOC match как дополнительный structural signal;
- возвращать структурированное решение: accepted / rejected / ambiguous;
- сохранять explainability: score + accept_reasons + reject_reasons.

ВАЖНО:
- Это НЕ слой построения дерева.
- Это НЕ regex parser.
- Это НЕ LLM-refiner.
- Это deterministic decision layer между parse_raw_heading(...)
  и дальнейшей сборкой ClauseTree.

TOC integration policy:
- TOC match не должен отменять жёсткие reject-guards;
- exact/fuzzy TOC match может повышать confidence;
- stale/noisy TOC не должен сам по себе приводить к accepted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from services.structure.heading_features import (
    alpha_uid_is_plausible,
    classify_uid_kind,
    digit_uid_without_textual_title,
    has_letters,
    is_bad_heading_title,
    is_garbage_heading_title,
    looks_like_body_sentence_title,
    looks_like_toc_line,
    roman_uid_is_plausible,
    uid_is_plausible,
    starts_with_quoted_term,
    looks_like_definition_term_title,
    looks_like_lowercase_continuation,
    looks_like_substantive_clause_line,
)

from services.structure.heading_patterns import normalize_spaces, _normalize_title

from services.structure.models import (
    SEMANTIC_ELEMENT_TYPE_SECTION_HEADING as SEMANTIC_TYPE_SECTION_HEADING,
    SEMANTIC_ELEMENT_TYPE_SUBSECTION_HEADING as SEMANTIC_TYPE_SUBSECTION_HEADING,
    SEMANTIC_ELEMENT_TYPE_DEFINITION_ITEM as SEMANTIC_TYPE_DEFINITION_ITEM,
    SEMANTIC_ELEMENT_TYPE_APPENDIX_HEADING as SEMANTIC_TYPE_APPENDIX_HEADING,
    SEMANTIC_ELEMENT_TYPE_SIGNATURE_BLOCK as SEMANTIC_TYPE_SIGNATURE_BLOCK,
    SEMANTIC_ELEMENT_TYPE_LIST_ITEM as SEMANTIC_TYPE_LIST_ITEM,
)
from services.structure.legal_heading_rules import (
    looks_like_definition_item,
    looks_like_appendix_heading,
    looks_like_signature_or_requisites_heading,
    build_numeric_uid_continuity,
)

from core.logging import get_logger

logger = get_logger(__name__)


class CandidateStatus(str, Enum):
    """
    Итоговый статус кандидата.

    - ACCEPTED  — уверенно принимаем как заголовок;
    - REJECTED  — уверенно отклоняем;
    - AMBIGUOUS — пограничный случай (можно досмотреть LLM-refiner'ом).
    """

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    AMBIGUOUS = "ambiguous"


@dataclass(slots=True)
class HeadingScoreResult:
    """
    Результат scoring-слоя.

    - status                  — основное решение (ACCEPTED / REJECTED / AMBIGUOUS);
    - score                   — итоговый балл доверия 0.0..1.0;
    - primary_reason          — короткая причина для логов;
    - accept_reasons          — положительные explainability reasons;
    - reject_reasons          — отрицательные explainability reasons;
    - toc_match_score         — вклад TOC match в итоговую confidence-оценку;
    - toc_match_type          — exact / fuzzy / no_match / None;
    - semantic_element_type   — финальный semantic type, вычисленный scorer-ом;
    - continuity_bonus        — бонус/штраф от continuity signals (0.0 = нейтральный);
    - legal_negative_signals  — список сработавших legal negative rules.
    """

    status: CandidateStatus
    score: float
    primary_reason: str
    accept_reasons: list[str] = field(default_factory=list)
    reject_reasons: list[str] = field(default_factory=list)
    toc_match_score: float = 0.0
    toc_match_type: str | None = None
    semantic_element_type: str | None = None
    continuity_bonus: float = 0.0
    legal_negative_signals: list[str] = field(default_factory=list)

    @property
    def is_accepted(self) -> bool:
        return self.status == CandidateStatus.ACCEPTED

    @property
    def is_rejected(self) -> bool:
        return self.status == CandidateStatus.REJECTED

    @property
    def is_ambiguous(self) -> bool:
        return self.status == CandidateStatus.AMBIGUOUS


_NUMERIC_UID_RE = re.compile(r"^\d+(?:\.\d+)*$")


def _is_strict_numeric_uid(uid: str) -> bool:
    return bool(_NUMERIC_UID_RE.fullmatch((uid or "").strip()))


def level_from_uid(uid: str) -> int:
    """
    Определить глубину numeric uid:
    - "1" -> 1
    - "2.3" -> 2
    - "4.1.5" -> 3

    Для roman/alpha uid возвращаем 1.
    """
    normalized = normalize_spaces(uid)
    if not _is_strict_numeric_uid(normalized):
        return 1
    return normalized.count(".") + 1


def _is_effectively_empty_title(title: str) -> bool:
    """
    Строки вроде "", " ", "-", "--", ",", ".", ", ,", "- -"
    считаем пустыми/пунктуационными — это не заголовок.
    """
    if not title:
        return True

    stripped = normalize_spaces(title).strip()
    if not stripped:
        return True

    cleaned = re.sub(r"[\s\.,;:!?()\[\]{}\-–—_+/\\|\"'`~№]+", "", stripped)
    return not cleaned


def _looks_too_long_for_heading(title: str, *, level: int) -> bool:
    """
    Грубый, но полезный guard:
    - level 1 headings могут быть длиннее;
    - level 2-3 уже должны быть компактнее;
    - очень длинные title чаще являются clause body, а не heading.
    """
    normalized = normalize_spaces(title)
    word_count = len(normalized.split())

    if level <= 1:
        return len(normalized) > 220 or word_count > 22
    if level == 2:
        return len(normalized) > 180 or word_count > 18
    return len(normalized) > 150 or word_count > 16


def _normalize_element_type(element_type: str | None) -> str:
    return normalize_spaces(str(element_type or "")).lower()


def _is_recoverable_toc_like_element_type(element_type: str | None) -> bool:
    normalized = _normalize_element_type(element_type)
    return normalized in {
        "toc_false_positive",
    }


def _is_strong_heading_element_type(element_type: str | None) -> bool:
    normalized = _normalize_element_type(element_type)
    return normalized in {
        "heading_candidate",
        "section_heading",
        "subsection_heading",
        "appendix_heading",
    }


def _clamp_score(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _resolve_semantic_type_in_scorer(
    *,
    uid: str,
    title: str,
    raw_text: str,
    element_type: str | None,
    classifier_semantic_type: str | None,
) -> str:
    """
    Финальный resolver semantic_element_type внутри scorer-а.

    Принцип:
    - если classifier уже дал semantic_type — доверяем ему;
    - но проверяем по тексту через legal_heading_rules,
      так как classifier работал по element_type, а scorer знает uid и title;
    - appendix heading и definition item имеют приоритет над generic heading.

    Зачем это нужно:
    classifier работал с сырым текстом element-а (до parse_raw_heading),
    а scorer уже знает распарсенный uid и title — это более точный контекст.
    """
    # Доверяем classifier если он уже дал специфичный semantic type
    if classifier_semantic_type in {
        SEMANTIC_TYPE_DEFINITION_ITEM,
        SEMANTIC_TYPE_APPENDIX_HEADING,
        SEMANTIC_TYPE_SIGNATURE_BLOCK,
        SEMANTIC_TYPE_LIST_ITEM,
    }:
        return classifier_semantic_type

    # Дополнительная проверка по title/raw_text на уровне scorer-а
    # (у нас уже есть распарсенный title — более чистый контекст)
    if looks_like_appendix_heading(raw_text) or looks_like_appendix_heading(title):
        return SEMANTIC_TYPE_APPENDIX_HEADING

    if looks_like_definition_item(raw_text) or looks_like_definition_item(title):
        return SEMANTIC_TYPE_DEFINITION_ITEM

    if looks_like_signature_or_requisites_heading(raw_text):
        return SEMANTIC_TYPE_SIGNATURE_BLOCK

    # Для numeric uid определяем section vs subsection
    if _is_strict_numeric_uid(uid):
        level = level_from_uid(uid)
        if level == 1:
            return SEMANTIC_TYPE_SECTION_HEADING
        return SEMANTIC_TYPE_SUBSECTION_HEADING

    # Если classifier уже дал section/subsection — доверяем
    if classifier_semantic_type in {
        SEMANTIC_TYPE_SECTION_HEADING,
        SEMANTIC_TYPE_SUBSECTION_HEADING,
    }:
        return classifier_semantic_type

    return SEMANTIC_TYPE_SECTION_HEADING


def _compute_continuity_bonus(
    continuity_signals: dict[str, object] | None,
) -> tuple[float, list[str]]:
    """
    Вычисляет бонус/штраф от continuity signals для scorer-а.

    Принцип:
    - если после heading идёт body → небольшой бонус к confidence;
    - если после heading сразу идёт ещё heading → небольшой штраф;
    - если рядом definition-like строки → штраф;
    - если next starts_with_lowercase → штраф (continuation signal).

    Диапазон возвращаемого бонуса: -0.06 .. +0.04

    Это НЕБОЛЬШИЕ корректировки, а не решающие факторы.
    Они не должны превращать REJECTED в ACCEPTED и наоборот.
    """
    if not continuity_signals:
        return 0.0, []

    bonus = 0.0
    reasons: list[str] = []

    # Позитивный сигнал: после heading идёт body
    if continuity_signals.get("continuity_body_positive"):
        bonus += 0.03
        reasons.append("continuity_body_after_heading")

    # Негативный: после heading сразу другой heading
    if continuity_signals.get("continuity_heading_negative"):
        bonus -= 0.03
        reasons.append("continuity_next_is_heading")

    # Негативный: рядом definition-like строка
    if continuity_signals.get("continuity_definition_negative"):
        bonus -= 0.04
        reasons.append("continuity_definition_negative")

    # Негативный: next line начинается со строчной — признак continuation
    if continuity_signals.get("next_starts_with_lowercase"):
        bonus -= 0.02
        reasons.append("continuity_next_lowercase_start")

    # Дополнительный позитив: next line имеет substantive verb
    # (это значит after heading идёт реальный legal clause body)
    if continuity_signals.get("next_has_substantive_verb"):
        bonus += 0.02
        reasons.append("continuity_next_has_substantive_verb")

    bonus = max(-0.06, min(0.04, bonus))
    return round(bonus, 4), reasons


def score_heading_candidate(
    uid: str,
    title: str,
    raw_text: str,
    *,
    toc_match: dict[str, object] | None = None,
    element_type: str | None = None,
    semantic_element_type: str | None = None,
    continuity_signals: dict[str, object] | None = None,
    prev_heading_uid: str | None = None,
    next_heading_uid: str | None = None,
) -> HeadingScoreResult:
    
    """
    Основной deterministic scorer для heading candidate.

    Вход:
    - uid: распарсенный heading uid;
    - title: распарсенный heading title;
    - raw_text: исходная строка элемента;
    - toc_match: опциональный TOC match payload, уже подготовленный builder-ом.

    Порядок проверок (важен — не менять без понимания последствий):
    1. Нормализация входных данных
    2. TOC-строки
    3. Пустой uid / пустой title
    4. Effectively empty title (только пунктуация)
    5. Слишком короткий небуквенный title
    6. Нет букв совсем
    7. Мусорный / плохой title (garbage / bad)
    8. Вычисление uid_kind / numeric_uid / level
    9. Plausibility uid формата
    10. digit_uid без текстового title
    11. Похоже на body-предложение
    12. TOC match bonus
    13. Финальное решение по типу uid и уровню вложенности

    TOC policy:
    - TOC match используется только после прохождения жёстких reject-guards;
    - exact/fuzzy TOC match повышает confidence, но не заменяет базовые признаки;
    - stale/no_match TOC остаётся нейтральным сигналом.
    """

    # ── 1. Нормализация ──────────────────────────────────────────────────────
    raw_text = normalize_spaces(raw_text)
    uid = normalize_spaces(uid)
    level = level_from_uid(uid) if uid else 1
    title = _normalize_title(normalize_spaces(title), uid_depth=level)

    normalized_element_type = _normalize_element_type(element_type)
    recoverable_toc_like_type = _is_recoverable_toc_like_element_type(
        normalized_element_type
    )
    strong_heading_element_type = _is_strong_heading_element_type(
        normalized_element_type
    )

    accept_reasons: list[str] = []
    reject_reasons: list[str] = []
    legal_negative_signals: list[str] = []

    # ── 1a. Classifier semantic type как дополнительный сигнал ───────────────
    # Читаем semantic_element_type, который проставил element_classifier.
    # Это позволяет scorer-у учитывать уже вычисленные юридические признаки.
    classifier_semantic = str(semantic_element_type or "").strip().lower()

    # ── 1b. Ранние legal negative guards по semantic type ────────────────────
    # Если classifier уже определил definition_item / signature_block —
    # это жёсткий сигнал до любого uid-based scoring.
    # Appendix heading — мягкий: он сам по себе не heading в смысле ClauseTree,
    # но мы не режем его жёстко, а помечаем как ambiguous ниже.

    if classifier_semantic == SEMANTIC_TYPE_DEFINITION_ITEM:
        legal_negative_signals.append("semantic_type_definition_item_by_classifier")

    if classifier_semantic == SEMANTIC_TYPE_SIGNATURE_BLOCK:
        legal_negative_signals.append("semantic_type_signature_block_by_classifier")

    if classifier_semantic == SEMANTIC_TYPE_APPENDIX_HEADING:
        legal_negative_signals.append("semantic_type_appendix_heading_by_classifier")

    # ── 1c. Continuity bonus (вычисляем заранее, применяем позже) ────────────
    continuity_bonus, continuity_reasons = _compute_continuity_bonus(continuity_signals)

    # ── 1d. Monotonic UID series check ────────────────────────────────────────
    # Проверяем, является ли этот uid частью нормальной числовой последовательности.
    # Это дополнительный positive сигнал для scorer-а.
    uid_continuity = build_numeric_uid_continuity(
        prev_uid=prev_heading_uid,
        current_uid=uid,
        next_uid=next_heading_uid,
    )
    uid_is_in_monotonic_series = (
        uid_continuity.get("prev_is_next_peer")
        or uid_continuity.get("next_is_next_peer")
        or uid_continuity.get("current_is_child_of_prev")
        or uid_continuity.get("next_is_child_of_current")
    )
    if uid_is_in_monotonic_series:
        accept_reasons.append("uid_monotonic_series")

    # ── 2. TOC-строки ────────────────────────────────────────────────────────
    # Строки вида "1. Definitions .......... 4" — оглавление, не заголовок
    if looks_like_toc_line(raw_text):
        toc_bonus, toc_match_type, toc_accept_reasons = _toc_match_bonus(toc_match)

        if recoverable_toc_like_type:
            local_accept_reasons = accept_reasons.copy()
            local_reject_reasons = ["toc_like_line", "recoverable_toc_like_element_type"]
            if toc_accept_reasons:
                local_accept_reasons.extend(toc_accept_reasons)

            score = 0.34
            if toc_match_type == "exact":
                score += 0.08
            elif toc_match_type == "fuzzy":
                score += min(toc_bonus, 0.05)

            if strong_heading_element_type:
                score += 0.04

            return HeadingScoreResult(
                status=CandidateStatus.AMBIGUOUS,
                score=_clamp_score(score),
                primary_reason="toc_like_line_recoverable",
                accept_reasons=local_accept_reasons,
                reject_reasons=local_reject_reasons,
                toc_match_score=toc_bonus,
                toc_match_type=toc_match_type,
            )

        return HeadingScoreResult(
            status=CandidateStatus.REJECTED,
            score=0.0,
            primary_reason="toc_like_line",
            reject_reasons=["toc_like_line"],
            toc_match_score=toc_bonus,
            toc_match_type=toc_match_type,
        )

    # ── 3. Пустой uid / пустой title ─────────────────────────────────────────
    if not uid or not title:
        return HeadingScoreResult(
            status=CandidateStatus.REJECTED,
            score=0.0,
            primary_reason="empty_uid_or_title",
            reject_reasons=["empty_uid_or_title"],
        )

    # ── 4. Title только из пунктуации/пробелов ───────────────────────────────
    # Ловит: "-", "--", ", ,", "- -", "..."
    if _is_effectively_empty_title(title):
        return HeadingScoreResult(
            status=CandidateStatus.REJECTED,
            score=0.0,
            primary_reason="empty_or_punct_only_title",
            reject_reasons=["empty_or_punct_only_title"],
        )

    # ── 5. Слишком короткий небуквенный title ────────────────────────────────
    if len(title) <= 2 and not has_letters(title):
        return HeadingScoreResult(
            status=CandidateStatus.REJECTED,
            score=0.0,
            primary_reason="too_short_non_textual_title",
            reject_reasons=["too_short_non_textual_title"],
        )

    # ── 6. Нет букв совсем ───────────────────────────────────────────────────
    if not has_letters(title):
        return HeadingScoreResult(
            status=CandidateStatus.REJECTED,
            score=0.05,
            primary_reason="title_without_letters",
            reject_reasons=["title_without_letters"],
        )

    # ── 7. Мусорный / плохой title ───────────────────────────────────────────
    # ВАЖНО: эти проверки идут ДО вычисления uid_kind и plausibility.
    # Смысл: мусорный title дисквалифицирует кандидата независимо от uid.
    if is_garbage_heading_title(title):
        return HeadingScoreResult(
            status=CandidateStatus.REJECTED,
            score=0.0,
            primary_reason="garbage_heading_title",
            reject_reasons=["garbage_heading_title"],
        )

    if is_bad_heading_title(title):
        return HeadingScoreResult(
            status=CandidateStatus.REJECTED,
            score=0.05,
            primary_reason="bad_heading_title",
            reject_reasons=["bad_heading_title"],
        )

    # ── 8. Вычисляем свойства uid ────────────────────────────────────────────
    uid_kind = classify_uid_kind(uid)
    numeric_uid = _is_strict_numeric_uid(uid)

    # ── 9. Plausibility uid формата ──────────────────────────────────────────
    # Отсекаем нереалистичные uid: 0.0.9999, 999.999.999 и т.п.
    if numeric_uid:
        if not uid_is_plausible(uid):
            return HeadingScoreResult(
                status=CandidateStatus.REJECTED,
                score=0.05,
                primary_reason="implausible_numeric_uid",
                reject_reasons=["implausible_numeric_uid"],
            )
        accept_reasons.append("plausible_numeric_uid")

    elif roman_uid_is_plausible(uid):
        accept_reasons.append("plausible_roman_uid")

    elif alpha_uid_is_plausible(uid):
        accept_reasons.append("plausible_alpha_uid")

    else:
        return HeadingScoreResult(
            status=CandidateStatus.REJECTED,
            score=0.05,
            primary_reason="unsupported_uid_format",
            reject_reasons=["unsupported_uid_format"],
        )

    # ── 10. digit_uid без текстового title ───────────────────────────────────
    # Проверяем ПОСЛЕ plausibility: если uid нереалистичен, причина уже выдана выше.
    # Ловит: uid "1" с title "42 700" или "3.2.1" с title "1234"
    if digit_uid_without_textual_title(uid, title):
        return HeadingScoreResult(
            status=CandidateStatus.REJECTED,
            score=0.05,
            primary_reason="digit_uid_without_textual_title",
            accept_reasons=accept_reasons.copy(),
            reject_reasons=["digit_uid_without_textual_title"],
        )

    # ── 11. Похоже на definition/body/substantive clause ─────────────────────
    # Это главный блок против ложных section headings.
    # Numeric uid сам по себе НЕ должен превращать clause sentence в heading.

    if starts_with_quoted_term(title) or looks_like_definition_term_title(title):
        if numeric_uid and level >= 2:
            toc_bonus, toc_match_type, toc_accept_reasons = _toc_match_bonus(toc_match)
            local_accept_reasons = accept_reasons.copy()
            if toc_accept_reasons:
                local_accept_reasons.extend(toc_accept_reasons)

            local_reject_reasons = ["definition_like_title"]
            score = 0.42 + min(toc_bonus, 0.03)

            if recoverable_toc_like_type:
                score -= 0.08
                local_reject_reasons.append("recoverable_toc_like_penalty")

            if strong_heading_element_type:
                score += 0.03

            return HeadingScoreResult(
                status=CandidateStatus.AMBIGUOUS,
                score=_clamp_score(score),
                primary_reason="definition_like_title",
                accept_reasons=local_accept_reasons,
                reject_reasons=local_reject_reasons,
                toc_match_score=min(toc_bonus, 0.03),
                toc_match_type=toc_match_type,
            )

        return HeadingScoreResult(
            status=CandidateStatus.REJECTED,
            score=0.10,
            primary_reason="definition_like_title",
            accept_reasons=accept_reasons.copy(),
            reject_reasons=["definition_like_title"],
        )

    if looks_like_lowercase_continuation(title):
        return HeadingScoreResult(
            status=CandidateStatus.REJECTED,
            score=0.08,
            primary_reason="lowercase_continuation_title",
            accept_reasons=accept_reasons.copy(),
            reject_reasons=["lowercase_continuation_title"],
        )

    if _looks_too_long_for_heading(title, level=level) or looks_like_substantive_clause_line(title):
        if numeric_uid and level >= 2:
            toc_bonus, toc_match_type, toc_accept_reasons = _toc_match_bonus(toc_match)
            local_accept_reasons = accept_reasons.copy()
            if toc_accept_reasons:
                local_accept_reasons.extend(toc_accept_reasons)

            local_reject_reasons = ["substantive_clause_like_title"]
            score = 0.46 + min(toc_bonus, 0.03)

            if recoverable_toc_like_type:
                score -= 0.08
                local_reject_reasons.append("recoverable_toc_like_penalty")

            if strong_heading_element_type:
                score += 0.03

            return HeadingScoreResult(
                status=CandidateStatus.AMBIGUOUS,
                score=_clamp_score(score),
                primary_reason="substantive_clause_like_title",
                accept_reasons=local_accept_reasons,
                reject_reasons=local_reject_reasons,
                toc_match_score=min(toc_bonus, 0.03),
                toc_match_type=toc_match_type,
            )

        return HeadingScoreResult(
            status=CandidateStatus.REJECTED,
            score=0.12,
            primary_reason="substantive_clause_like_title",
            accept_reasons=accept_reasons.copy(),
            reject_reasons=["substantive_clause_like_title"],
        )

    # Ловит длинные фразы с глаголами и знаками конца предложения.
    # Для numeric uid уровня 2+ — спорный случай, помечаем AMBIGUOUS,
    # чтобы LLM-refiner мог досмотреть.
    if looks_like_body_sentence_title(uid, title):
        if numeric_uid and level >= 2:
            toc_bonus, toc_match_type, toc_accept_reasons = _toc_match_bonus(toc_match)
            local_accept_reasons = accept_reasons.copy()
            if toc_accept_reasons:
                local_accept_reasons.extend(toc_accept_reasons)

            local_reject_reasons = ["body_like_sentence_title"]
            score = 0.45 + min(toc_bonus, 0.03)

            if recoverable_toc_like_type:
                score -= 0.08
                local_reject_reasons.append("recoverable_toc_like_penalty")

            if strong_heading_element_type:
                score += 0.03

            return HeadingScoreResult(
                status=CandidateStatus.AMBIGUOUS,
                score=_clamp_score(score),
                primary_reason="body_like_sentence_title",
                accept_reasons=local_accept_reasons,
                reject_reasons=local_reject_reasons,
                toc_match_score=min(toc_bonus, 0.03),
                toc_match_type=toc_match_type,
            )

        return HeadingScoreResult(
            status=CandidateStatus.REJECTED,
            score=0.10,
            primary_reason="body_like_sentence_title",
            accept_reasons=accept_reasons.copy(),
            reject_reasons=["body_like_sentence_title"],
        )

    # ── 11a. Legal negative guards по legal_heading_rules ────────────────────
    # Это дополнительная проверка поверх heading_features.py.
    # legal_heading_rules знает о юридических паттернах, которых нет в features.

    # Appendix heading — не section heading в обычном смысле.
    # Если uid = 1 уровень и raw_text выглядит как appendix — помечаем ambiguous.
    if looks_like_appendix_heading(raw_text):
        legal_negative_signals.append("looks_like_appendix_heading_by_scorer")
        reject_reasons.append("appendix_heading")
        toc_bonus_local, toc_match_type_local, toc_accept_local = _toc_match_bonus(toc_match)
        score = 0.60 + min(toc_bonus_local, 0.03) + continuity_bonus
        return HeadingScoreResult(
            status=CandidateStatus.AMBIGUOUS,
            score=_clamp_score(score),
            primary_reason="appendix_heading",
            accept_reasons=accept_reasons + toc_accept_local,
            reject_reasons=reject_reasons,
            toc_match_score=toc_bonus_local,
            toc_match_type=toc_match_type_local,
            semantic_element_type=SEMANTIC_TYPE_APPENDIX_HEADING,
            continuity_bonus=continuity_bonus,
            legal_negative_signals=legal_negative_signals,
        )

    # Definition item через legal_heading_rules — более строгая проверка,
    # чем heading_features.looks_like_definition_term_title.
    # heading_features уже ловит часть случаев, но legal_heading_rules
    # знает про юридические definition lead patterns.
    if looks_like_definition_item(raw_text) or looks_like_definition_item(title):
        legal_negative_signals.append("looks_like_definition_item_by_scorer")
        if numeric_uid and level >= 2:
            toc_bonus_local, toc_match_type_local, toc_accept_local = _toc_match_bonus(toc_match)
            score = 0.40 + min(toc_bonus_local, 0.03) + continuity_bonus
            if recoverable_toc_like_type:
                score -= 0.08
            return HeadingScoreResult(
                status=CandidateStatus.AMBIGUOUS,
                score=_clamp_score(score),
                primary_reason="definition_item_by_legal_rules",
                accept_reasons=accept_reasons + toc_accept_local,
                reject_reasons=reject_reasons + ["definition_item_by_legal_rules"],
                toc_match_score=toc_bonus_local,
                toc_match_type=toc_match_type_local,
                semantic_element_type=SEMANTIC_TYPE_DEFINITION_ITEM,
                continuity_bonus=continuity_bonus,
                legal_negative_signals=legal_negative_signals,
            )
        return HeadingScoreResult(
            status=CandidateStatus.REJECTED,
            score=0.08,
            primary_reason="definition_item_by_legal_rules",
            accept_reasons=accept_reasons,
            reject_reasons=reject_reasons + ["definition_item_by_legal_rules"],
            toc_match_score=0.0,
            toc_match_type=None,
            semantic_element_type=SEMANTIC_TYPE_DEFINITION_ITEM,
            continuity_bonus=continuity_bonus,
            legal_negative_signals=legal_negative_signals,
        )

    # Signature / requisites block — жёсткий reject
    if looks_like_signature_or_requisites_heading(raw_text):
        legal_negative_signals.append("looks_like_signature_or_requisites_by_scorer")
        return HeadingScoreResult(
            status=CandidateStatus.REJECTED,
            score=0.0,
            primary_reason="signature_or_requisites_block",
            accept_reasons=accept_reasons,
            reject_reasons=reject_reasons + ["signature_or_requisites_block"],
            toc_match_score=0.0,
            toc_match_type=None,
            semantic_element_type=SEMANTIC_TYPE_SIGNATURE_BLOCK,
            continuity_bonus=continuity_bonus,
            legal_negative_signals=legal_negative_signals,
        )

    # ── 12. TOC match bonus ──────────────────────────────────────────────────
    toc_bonus, toc_match_type, toc_accept_reasons = _toc_match_bonus(toc_match)
    if toc_accept_reasons:
        accept_reasons.extend(toc_accept_reasons)

    # ── 12a. Применяем continuity bonus ──────────────────────────────────────
    if continuity_reasons:
        accept_reasons.extend(
            r for r in continuity_reasons if not r.startswith("continuity_next")
        )
        reject_reasons.extend(
            r for r in continuity_reasons if r.startswith("continuity_next")
        )

    # ── 12b. Финальный semantic type ─────────────────────────────────────────
    resolved_semantic_type = _resolve_semantic_type_in_scorer(
        uid=uid,
        title=title,
        raw_text=raw_text,
        element_type=element_type,
        classifier_semantic_type=classifier_semantic or None,
    )

    # ── 13. Финальное решение по типу uid и уровню вложенности ───────────────

    if numeric_uid:
        if level == 1:
            base_score = 0.90
            if strong_heading_element_type:
                base_score += 0.03
            if recoverable_toc_like_type:
                base_score -= 0.05

            final_score = _clamp_score(base_score + toc_bonus + continuity_bonus)

            return HeadingScoreResult(
                status=CandidateStatus.ACCEPTED,
                score=final_score,
                primary_reason="accepted",
                accept_reasons=accept_reasons + ["top_level_numeric_heading"],
                reject_reasons=reject_reasons,
                toc_match_score=toc_bonus,
                toc_match_type=toc_match_type,
                semantic_element_type=resolved_semantic_type,
                continuity_bonus=continuity_bonus,
                legal_negative_signals=legal_negative_signals,
            )

        if level == 2:
            base_score = 0.78
            if strong_heading_element_type:
                base_score += 0.04
            if recoverable_toc_like_type:
                base_score -= 0.06

            final_score = _clamp_score(base_score + toc_bonus + continuity_bonus)
            status = CandidateStatus.ACCEPTED if final_score >= 0.86 else CandidateStatus.AMBIGUOUS
            primary_reason = (
                "accepted"
                if status == CandidateStatus.ACCEPTED
                else "nested_numeric_heading_needs_confirmation"
            )
            
            return HeadingScoreResult(
                status=status,
                score=final_score,
                primary_reason=primary_reason,
                accept_reasons=accept_reasons + ["nested_numeric_heading"],
                reject_reasons=reject_reasons,
                toc_match_score=toc_bonus,
                toc_match_type=toc_match_type,
                semantic_element_type=resolved_semantic_type,
                continuity_bonus=continuity_bonus,
                legal_negative_signals=legal_negative_signals,
            )

        if level == 3:
            base_score = 0.68
            if strong_heading_element_type:
                base_score += 0.04
            if recoverable_toc_like_type:
                base_score -= 0.06

            final_score = _clamp_score(base_score + toc_bonus + continuity_bonus)
            status = CandidateStatus.ACCEPTED if final_score >= 0.82 else CandidateStatus.AMBIGUOUS
            primary_reason = (
                "accepted"
                if status == CandidateStatus.ACCEPTED
                else "deep_numeric_heading_needs_confirmation"
            )

            return HeadingScoreResult(
                status=status,
                score=final_score,
                primary_reason=primary_reason,
                accept_reasons=accept_reasons + ["deep_numeric_heading_l3"],
                reject_reasons=reject_reasons,
                toc_match_score=toc_bonus,
                toc_match_type=toc_match_type,
                semantic_element_type=resolved_semantic_type,
                continuity_bonus=continuity_bonus,
                legal_negative_signals=legal_negative_signals,
            )

        base_score = 0.58
        final_score = min(1.0, base_score + toc_bonus)
        return HeadingScoreResult(
            status=CandidateStatus.AMBIGUOUS,
            score=final_score,
            primary_reason="very_deep_numeric_heading",
            accept_reasons=accept_reasons + ["very_deep_numeric_heading"],
            reject_reasons=reject_reasons,
            toc_match_score=toc_bonus,
            toc_match_type=toc_match_type,
            semantic_element_type=resolved_semantic_type,
            continuity_bonus=continuity_bonus,
            legal_negative_signals=legal_negative_signals,
        )

    if uid_kind == "roman":
        base_score = 0.76
        final_score = min(1.0, base_score + toc_bonus)
        status = CandidateStatus.ACCEPTED if final_score >= 0.82 else CandidateStatus.AMBIGUOUS
        primary_reason = "accepted" if status == CandidateStatus.ACCEPTED else "roman_heading_needs_confirmation"
        return HeadingScoreResult(
            status=status,
            score=final_score,
            primary_reason=primary_reason,
            accept_reasons=accept_reasons + ["roman_heading"],
            reject_reasons=reject_reasons,
            toc_match_score=toc_bonus,
            toc_match_type=toc_match_type,
            semantic_element_type=resolved_semantic_type,
            continuity_bonus=continuity_bonus,
            legal_negative_signals=legal_negative_signals,
        )

    if uid_kind == "alpha":
        base_score = 0.60
        final_score = min(1.0, base_score + toc_bonus)
        return HeadingScoreResult(
            status=CandidateStatus.AMBIGUOUS,
            score=final_score,
            primary_reason="alpha_heading",
            accept_reasons=accept_reasons + ["alpha_heading"],
            reject_reasons=reject_reasons,
            toc_match_score=toc_bonus,
            toc_match_type=toc_match_type,
            semantic_element_type=resolved_semantic_type,
            continuity_bonus=continuity_bonus,
            legal_negative_signals=legal_negative_signals,
        )

    base_score = 0.50
    final_score = min(1.0, base_score + toc_bonus)
    return HeadingScoreResult(
        status=CandidateStatus.AMBIGUOUS,
        score=final_score,
        primary_reason="fallback_ambiguous",
        accept_reasons=accept_reasons,
        reject_reasons=reject_reasons,
        toc_match_score=toc_bonus,
        toc_match_type=toc_match_type,
        semantic_element_type=resolved_semantic_type,
        continuity_bonus=continuity_bonus,
        legal_negative_signals=legal_negative_signals,
    )


def validate_heading_candidate_with_reason(
    uid: str,
    title: str,
    raw_text: str,
    *,
    toc_match: dict | None = None,
    element_type: str | None = None,
    semantic_element_type: str | None = None,
    continuity_signals: dict[str, object] | None = None,
    prev_heading_uid: str | None = None,
    next_heading_uid: str | None = None,
) -> tuple[bool, str]:
    """
    Legacy-compatible bridge.

    Правило (жёсткий режим):
    - ACCEPTED  → (True, primary_reason)
    - AMBIGUOUS → (False, primary_reason)
    - REJECTED  → (False, primary_reason)
    """
    result = score_heading_candidate(
        uid,
        title,
        raw_text,
        toc_match=toc_match,
        element_type=element_type,
        semantic_element_type=semantic_element_type,
        continuity_signals=continuity_signals,
        prev_heading_uid=prev_heading_uid,
        next_heading_uid=next_heading_uid,
    )
    if result.is_accepted:
        return True, result.primary_reason
    return False, result.primary_reason


def validate_heading_candidate(
    uid: str,
    title: str,
    raw_text: str,
    *,
    toc_match: dict | None = None,
    element_type: str | None = None,
    semantic_element_type: str | None = None,
    continuity_signals: dict[str, object] | None = None,
    prev_heading_uid: str | None = None,
    next_heading_uid: str | None = None,
) -> bool:
    """Старый бинарный интерфейс."""
    ok, _ = validate_heading_candidate_with_reason(
        uid,
        title,
        raw_text,
        toc_match=toc_match,
        element_type=element_type,
        semantic_element_type=semantic_element_type,
        continuity_signals=continuity_signals,
        prev_heading_uid=prev_heading_uid,
        next_heading_uid=next_heading_uid,
    )
    return ok

def _toc_match_bonus(
    toc_match: dict[str, object] | None,
) -> tuple[float, str | None, list[str]]:
    """
    Возвращает вклад TOC match в confidence scorer-а.

    Правила:
    - exact match даёт максимальный бонус;
    - fuzzy match даёт градуированный бонус по similarity score;
    - stale / missing-in-body TOC entry бонус не даёт;
    - отсутствие TOC match — это нейтральный случай, не штраф.

    Возвращает:
    - bonus: float 0.0..0.08
    - match_type: exact / fuzzy / no_match / None
    - reasons: explainability reasons для accept_reasons
    """
    if not toc_match:
        return 0.0, None, []

    match_type = str(toc_match.get("match_type") or "").strip() or None
    match_score = toc_match.get("match_score")
    toc_missing_in_body = bool(toc_match.get("toc_missing_in_body"))

    if toc_missing_in_body:
        return 0.0, match_type or "no_match", []

    if match_type == "exact":
        return 0.05, "exact", ["toc_exact_match"]

    if match_type == "fuzzy":
        numeric_score = float(match_score or 0.0)
        if numeric_score >= 92:
            return 0.04, "fuzzy", ["toc_fuzzy_match_strong"]
        if numeric_score >= 87:
            return 0.03, "fuzzy", ["toc_fuzzy_match"]
        if numeric_score >= 82:
            return 0.02, "fuzzy", ["toc_fuzzy_match_weak"]

    return 0.0, match_type, []

