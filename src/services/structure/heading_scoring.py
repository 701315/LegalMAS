# src/services/structure/heading_scoring.py

"""
Scoring / decision слой для heading detection.

Задача этого модуля:
- принимать raw heading hypothesis (uid, title, raw_text);
- использовать feature/predicate слой из heading_features.py;
- возвращать структурированное решение: accepted / rejected / ambiguous;
- сохранять explainability: score + accept_reasons + reject_reasons.

ВАЖНО:
- Это НЕ слой построения дерева.
- Это НЕ regex parser.
- Это НЕ LLM-refiner.
- Это deterministic decision layer между parse_raw_heading(...)
  и дальнейшей сборкой ClauseTree.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from services.structure.heading_features import (
    classify_uid_kind,
    digit_uid_without_textual_title,
    has_letters,
    is_bad_heading_title,
    is_garbage_heading_title,
    level_from_uid,
    looks_like_body_sentence_title,
    looks_like_toc_line,
    alpha_uid_is_plausible,
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

    - status         — основное решение (ACCEPTED / REJECTED / AMBIGUOUS);
    - score          — балл доверия 0.0..1.0;
    - primary_reason — короткая причина для логов;
    - accept_reasons / reject_reasons — полное объяснение решения.
    """
    status: CandidateStatus
    score: float
    primary_reason: str
    accept_reasons: list[str] = field(default_factory=list)
    reject_reasons: list[str] = field(default_factory=list)

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
) -> HeadingScoreResult:
    """
    Основной deterministic scorer для heading candidate.

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
    10. digit_uid без текстового title (после plausibility — чтобы причина была точной)
    11. Похоже на body-предложение
    12. Финальное решение по типу uid и уровню вложенности
    """

    # ── 1. Нормализация ──────────────────────────────────────────────────────
    raw_text = normalize_spaces(raw_text)

    # uid нормализуем и сразу считаем level, чтобы передать его в _normalize_title
    uid = normalize_spaces(uid)
    level = level_from_uid(uid) if uid else 1

    # теперь можем корректно нормализовать title с учётом глубины
    title = _normalize_title(title, uid_depth=level)

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
    # Вычисляем только после мусорного фильтра, чтобы не тратить ресурсы на мусор
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
            return HeadingScoreResult(
                status=CandidateStatus.AMBIGUOUS,
                score=0.45,
                primary_reason="body_like_sentence_title",
                accept_reasons=accept_reasons.copy(),
                reject_reasons=["body_like_sentence_title"],
            )
        return HeadingScoreResult(
            status=CandidateStatus.REJECTED,
            score=0.10,
            primary_reason="body_like_sentence_title",
            accept_reasons=accept_reasons.copy(),
            reject_reasons=["body_like_sentence_title"],
        )

    # ── 12. Финальное решение по типу uid и уровню вложенности ───────────────

    if numeric_uid:
        if level == 1:
            # Пример: "1.", "2.", "10." — корневые разделы
            return HeadingScoreResult(
                status=CandidateStatus.ACCEPTED,
                score=0.95,
                primary_reason="accepted",
                accept_reasons=accept_reasons + ["top_level_numeric_heading"],
                reject_reasons=reject_reasons,
            )

        if level == 2:
            # Пример: "1.1", "2.3", "10.5" — подразделы
            return HeadingScoreResult(
                status=CandidateStatus.ACCEPTED,
                score=0.90,
                primary_reason="accepted",
                accept_reasons=accept_reasons + ["nested_numeric_heading"],
                reject_reasons=reject_reasons,
            )

        if level == 3:
            # Пример: "1.1.1", "2.3.4" — клаузы третьего уровня.
            # Это самые важные leaf-узлы для risk-анализа — принимаем уверенно.
            # (Было AMBIGUOUS 0.70 — исправлено: эти пункты нужны как leaf-клаузы)
            return HeadingScoreResult(
                status=CandidateStatus.ACCEPTED,
                score=0.85,
                primary_reason="accepted",
                accept_reasons=accept_reasons + ["deep_numeric_heading_l3"],
                reject_reasons=reject_reasons,
            )

        # level >= 4: очень глубокая вложенность — принимаем осторожно
        # Пример: "1.1.1.1", "2.3.4.5" — редко встречается, помечаем AMBIGUOUS
        return HeadingScoreResult(
            status=CandidateStatus.AMBIGUOUS,
            score=0.65,
            primary_reason="very_deep_numeric_heading",
            accept_reasons=accept_reasons + ["very_deep_numeric_heading"],
            reject_reasons=reject_reasons,
        )

    if uid_kind == "roman":
        # Пример: "I.", "II.", "III." — романские заголовки
        return HeadingScoreResult(
            status=CandidateStatus.ACCEPTED,
            score=0.82,
            primary_reason="accepted",
            accept_reasons=accept_reasons + ["roman_heading"],
            reject_reasons=reject_reasons,
        )

    if uid_kind == "alpha":
        # Пример: "A.", "B.", "C." — буквенные подпункты
        return HeadingScoreResult(
            status=CandidateStatus.AMBIGUOUS,
            score=0.60,
            primary_reason="alpha_heading",
            accept_reasons=accept_reasons + ["alpha_heading"],
            reject_reasons=reject_reasons,
        )

    # Всё остальное — неопределённо
    return HeadingScoreResult(
        status=CandidateStatus.AMBIGUOUS,
        score=0.50,
        primary_reason="fallback_ambiguous",
        accept_reasons=accept_reasons,
        reject_reasons=reject_reasons,
    )


def validate_heading_candidate_with_reason(
    uid: str,
    title: str,
    raw_text: str,
) -> tuple[bool, str]:
    """
    Legacy-compatible bridge.

    Правило (жёсткий режим):
    - ACCEPTED  → (True, primary_reason)
    - AMBIGUOUS → (False, primary_reason)
    - REJECTED  → (False, primary_reason)
    """
    result = score_heading_candidate(uid, title, raw_text)
    if result.is_accepted:
        return True, result.primary_reason
    return False, result.primary_reason


def validate_heading_candidate(
    uid: str,
    title: str,
    raw_text: str,
) -> bool:
    """Старый бинарный интерфейс."""
    ok, _ = validate_heading_candidate_with_reason(uid, title, raw_text)
    return ok

