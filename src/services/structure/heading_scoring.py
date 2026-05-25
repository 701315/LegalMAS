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
)
from services.structure.heading_patterns import normalize_spaces, _normalize_title

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

    - status           — основное решение (ACCEPTED / REJECTED / AMBIGUOUS);
    - score            — итоговый балл доверия 0.0..1.0;
    - primary_reason   — короткая причина для логов;
    - accept_reasons   — положительные explainability reasons;
    - reject_reasons   — отрицательные explainability reasons;
    - toc_match_score  — вклад TOC match в итоговую confidence-оценку;
    - toc_match_type   — exact / fuzzy / no_match / None.
    """

    status: CandidateStatus
    score: float
    primary_reason: str
    accept_reasons: list[str] = field(default_factory=list)
    reject_reasons: list[str] = field(default_factory=list)
    toc_match_score: float = 0.0
    toc_match_type: str | None = None

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


def score_heading_candidate(
    uid: str,
    title: str,
    raw_text: str,
    *,
    toc_match: dict[str, object] | None = None,
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

    accept_reasons: list[str] = []
    reject_reasons: list[str] = []

    # ── 2. TOC-строки ────────────────────────────────────────────────────────
    # Строки вида "1. Definitions .......... 4" — оглавление, не заголовок
    if looks_like_toc_line(raw_text):
        return HeadingScoreResult(
            status=CandidateStatus.REJECTED,
            score=0.0,
            primary_reason="toc_like_line",
            reject_reasons=["toc_like_line"],
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

    # ── 11. Похоже на body-предложение ───────────────────────────────────────
    # Ловит длинные фразы с глаголами и знаками конца предложения.
    # Для numeric uid уровня 2+ — спорный случай, помечаем AMBIGUOUS,
    # чтобы LLM-refiner мог досмотреть.
    if looks_like_body_sentence_title(uid, title):
        if numeric_uid and level >= 2:
            toc_bonus, toc_match_type, toc_accept_reasons = _toc_match_bonus(toc_match)
            local_accept_reasons = accept_reasons.copy()
            if toc_accept_reasons:
                local_accept_reasons.extend(toc_accept_reasons)

            return HeadingScoreResult(
                status=CandidateStatus.AMBIGUOUS,
                score=min(1.0, 0.45 + min(toc_bonus, 0.03)),
                primary_reason="body_like_sentence_title",
                accept_reasons=local_accept_reasons,
                reject_reasons=["body_like_sentence_title"],
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

    # ── 12. TOC match bonus ──────────────────────────────────────────────────
    toc_bonus, toc_match_type, toc_accept_reasons = _toc_match_bonus(toc_match)
    if toc_accept_reasons:
        accept_reasons.extend(toc_accept_reasons)

    # ── 13. Финальное решение по типу uid и уровню вложенности ───────────────

    if numeric_uid:
        if level == 1:
            # Пример: "1.", "2.", "10." — корневые разделы
            base_score = 0.95
            final_score = min(1.0, base_score + toc_bonus)
            return HeadingScoreResult(
                status=CandidateStatus.ACCEPTED,
                score=final_score,
                primary_reason="accepted",
                accept_reasons=accept_reasons + ["top_level_numeric_heading"],
                reject_reasons=reject_reasons,
                toc_match_score=toc_bonus,
                toc_match_type=toc_match_type,
            )

        if level == 2:
            # Пример: "1.1", "2.3", "10.5" — подразделы
            base_score = 0.90
            final_score = min(1.0, base_score + toc_bonus)
            return HeadingScoreResult(
                status=CandidateStatus.ACCEPTED,
                score=final_score,
                primary_reason="accepted",
                accept_reasons=accept_reasons + ["nested_numeric_heading"],
                reject_reasons=reject_reasons,
                toc_match_score=toc_bonus,
                toc_match_type=toc_match_type,
            )

        if level == 3:
            # Пример: "1.1.1", "2.3.4" — типичные leaf-клаузы,
            # критичные для построения корректного дерева и downstream анализа.
            base_score = 0.85
            final_score = min(1.0, base_score + toc_bonus)
            return HeadingScoreResult(
                status=CandidateStatus.ACCEPTED,
                score=final_score,
                primary_reason="accepted",
                accept_reasons=accept_reasons + ["deep_numeric_heading_l3"],
                reject_reasons=reject_reasons,
                toc_match_score=toc_bonus,
                toc_match_type=toc_match_type,
            )

        # level >= 4: очень глубокая вложенность — принимаем осторожно
        base_score = 0.65
        final_score = min(1.0, base_score + toc_bonus)
        return HeadingScoreResult(
            status=CandidateStatus.AMBIGUOUS,
            score=final_score,
            primary_reason="very_deep_numeric_heading",
            accept_reasons=accept_reasons + ["very_deep_numeric_heading"],
            reject_reasons=reject_reasons,
            toc_match_score=toc_bonus,
            toc_match_type=toc_match_type,
        )

    if uid_kind == "roman":
        base_score = 0.82
        final_score = min(1.0, base_score + toc_bonus)
        return HeadingScoreResult(
            status=CandidateStatus.ACCEPTED,
            score=final_score,
            primary_reason="accepted",
            accept_reasons=accept_reasons + ["roman_heading"],
            reject_reasons=reject_reasons,
            toc_match_score=toc_bonus,
            toc_match_type=toc_match_type,
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
    )


def validate_heading_candidate_with_reason(
    uid: str,
    title: str,
    raw_text: str,
    *,
    toc_match: dict | None = None,
) -> tuple[bool, str]:
    """
    Legacy-compatible bridge.

    Правило (жёсткий режим):
    - ACCEPTED  → (True, primary_reason)
    - AMBIGUOUS → (False, primary_reason)
    - REJECTED  → (False, primary_reason)
    """
    result = score_heading_candidate(uid, title, raw_text, toc_match=toc_match)
    if result.is_accepted:
        return True, result.primary_reason
    return False, result.primary_reason


def validate_heading_candidate(
    uid: str,
    title: str,
    raw_text: str,
    *,
    toc_match: dict | None = None,
) -> bool:
    """Старый бинарный интерфейс."""
    ok, _ = validate_heading_candidate_with_reason(
        uid,
        title,
        raw_text,
        toc_match=toc_match,
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
        return 0.08, "exact", ["toc_exact_match"]

    if match_type == "fuzzy":
        numeric_score = float(match_score or 0.0)
        if numeric_score >= 92:
            return 0.06, "fuzzy", ["toc_fuzzy_match_strong"]
        if numeric_score >= 87:
            return 0.045, "fuzzy", ["toc_fuzzy_match"]
        if numeric_score >= 82:
            return 0.03, "fuzzy", ["toc_fuzzy_match_weak"]

    return 0.0, match_type, []

