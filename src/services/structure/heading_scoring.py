# src/services/structure/heading_scoring.py

"""
Scoring / decision слой для heading detection.

Задача этого модуля:
- принимать raw heading hypothesis (uid, title, raw_text);
- использовать feature/predicate слой из heading_features.py;
- возвращать структурированное решение:
  accepted / rejected / ambiguous;
- сохранять explainability: score + accept_reasons + reject_reasons.

ВАЖНО:
- Это НЕ слой построения дерева.
- Это НЕ regex parser.
- Это НЕ LLM-refiner.
- Это deterministic decision layer между parse_raw_heading(...) и
  дальнейшей сборкой ClauseTree.
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
    - AMBIGUOUS — пограничный случай, который можно позже досмотреть
      дополнительными эвристиками или LLM-refiner.
    """

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    AMBIGUOUS = "ambiguous"


@dataclass(slots=True)
class HeadingScoreResult:
    """
    Результат scoring-слоя.

    Для непрофессионального программиста:
    - status — основное решение;
    - score  — условный балл доверия 0.0 .. 1.0;
    - accept_reasons / reject_reasons — объяснение решения;
    - primary_reason — короткая причина для логов и совместимости.
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
    Случаи вроде "", " ", "-", "--", ",", ".", ", ,", "- -"
    считаем пустыми/пунктуационными и не считаем заголовком.
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

    Принципы:
    - сначала нормализуем вход;
    - затем как можно раньше отсекаем явный мусор;
    - потом проверяем plausibility uid;
    - и только после этого принимаем / помечаем как ambiguous.
    """

    raw_text = normalize_spaces(raw_text)
    title = _normalize_title(title)
    uid = normalize_spaces(uid)

    accept_reasons: list[str] = []
    reject_reasons: list[str] = []

    # TOC-подобные строки не считаем heading candidate
    if looks_like_toc_line(raw_text):
        return HeadingScoreResult(
            status=CandidateStatus.REJECTED,
            score=0.0,
            primary_reason="toc_like_line",
            accept_reasons=[],
            reject_reasons=["toc_like_line"],
        )

    # Пустой uid или пустой title сразу отбрасываем
    if not uid or not title:
        return HeadingScoreResult(
            status=CandidateStatus.REJECTED,
            score=0.0,
            primary_reason="empty_uid_or_title",
            accept_reasons=[],
            reject_reasons=["empty_uid_or_title"],
        )

    # Title, состоящий только из пробелов/пунктуации — тоже мусор
    if _is_effectively_empty_title(title):
        return HeadingScoreResult(
            status=CandidateStatus.REJECTED,
            score=0.0,
            primary_reason="empty_or_punct_only_title",
            accept_reasons=[],
            reject_reasons=["empty_or_punct_only_title"],
        )

    # Очень короткий небуквенный title — почти гарантированный мусор
    if len(title) <= 2 and not has_letters(title):
        return HeadingScoreResult(
            status=CandidateStatus.REJECTED,
            score=0.0,
            primary_reason="too_short_non_textual_title",
            accept_reasons=[],
            reject_reasons=["too_short_non_textual_title"],
        )

    # Если букв нет совсем, это не заголовок
    if not has_letters(title):
        return HeadingScoreResult(
            status=CandidateStatus.REJECTED,
            score=0.05,
            primary_reason="title_without_letters",
            accept_reasons=[],
            reject_reasons=["title_without_letters"],
        )

    if digit_uid_without_textual_title(uid, title):
        return HeadingScoreResult(
            status=CandidateStatus.REJECTED,
            score=0.05,
            primary_reason="digit_uid_without_textual_title",
            accept_reasons=accept_reasons.copy(),
            reject_reasons=["digit_uid_without_textual_title"],
        )

    # Явный мусор / плохой title
    if is_garbage_heading_title(title):
        return HeadingScoreResult(
            status=CandidateStatus.REJECTED,
            score=0.0,
            primary_reason="garbage_heading_title",
            accept_reasons=[],
            reject_reasons=["garbage_heading_title"],
        )

    if is_bad_heading_title(title):
        return HeadingScoreResult(
            status=CandidateStatus.REJECTED,
            score=0.05,
            primary_reason="bad_heading_title",
            accept_reasons=[],
            reject_reasons=["bad_heading_title"],
        )

    uid_kind = classify_uid_kind(uid)
    numeric_uid = _is_strict_numeric_uid(uid)
    level = level_from_uid(uid) if uid else 1

    # Проверка plausibility формата uid
    if numeric_uid:
        if not uid_is_plausible(uid):
            return HeadingScoreResult(
                status=CandidateStatus.REJECTED,
                score=0.05,
                primary_reason="implausible_numeric_uid",
                accept_reasons=[],
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
            accept_reasons=[],
            reject_reasons=["unsupported_uid_format"],
        )

    # Похоже на обычное предложение из body, а не на заголовок
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

    # Финальное решение по типу uid и глубине
    if numeric_uid:
        if level == 1:
            return HeadingScoreResult(
                status=CandidateStatus.ACCEPTED,
                score=0.95,
                primary_reason="accepted",
                accept_reasons=accept_reasons + ["top_level_numeric_heading"],
                reject_reasons=reject_reasons,
            )

        if level == 2:
            return HeadingScoreResult(
                status=CandidateStatus.ACCEPTED,
                score=0.90,
                primary_reason="accepted",
                accept_reasons=accept_reasons + ["nested_numeric_heading"],
                reject_reasons=reject_reasons,
            )

        if level >= 3:
            return HeadingScoreResult(
                status=CandidateStatus.AMBIGUOUS,
                score=0.70,
                primary_reason="deep_numeric_heading",
                accept_reasons=accept_reasons + ["deep_numeric_heading"],
                reject_reasons=reject_reasons,
            )

    if uid_kind == "roman":
        return HeadingScoreResult(
            status=CandidateStatus.ACCEPTED,
            score=0.82,
            primary_reason="accepted",
            accept_reasons=accept_reasons + ["roman_heading"],
            reject_reasons=reject_reasons,
        )

    if uid_kind == "alpha":
        return HeadingScoreResult(
            status=CandidateStatus.AMBIGUOUS,
            score=0.60,
            primary_reason="alpha_heading",
            accept_reasons=accept_reasons + ["alpha_heading"],
            reject_reasons=reject_reasons,
        )

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

    Правило ПОКА (жёсткий режим для чистки мусора):
    - ACCEPTED  -> (True, primary_reason)
    - AMBIGUOUS -> (False, primary_reason)
    - REJECTED  -> (False, primary_reason)

    Позже можно будет вернуть AMBIGUOUS через feature-flag.
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
    """
    Старый бинарный интерфейс.
    """
    ok, _ = validate_heading_candidate_with_reason(uid, title, raw_text)
    return ok

