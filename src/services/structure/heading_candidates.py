# src/services/structure/heading_candidates.py

"""
Модели и вспомогательные типы для кандидатов в заголовки.

Зачем нужен этот файл:
- отделить "сырой" результат regex-парсинга от финального решения
  (accepted / rejected / ambiguous);
- хранить признаки и причины, ПОЧЕМУ кандидат принят или отклонён;
- подготовить почву для более сложного скоринга и, при необходимости,
  локального LLM‑рефайнера — без изменения внешнего контракта
  StructureBuilder.build().
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CandidateStatus(str, Enum):
    """
    Итоговый статус кандидата.

    Для непрофессионального программиста:
    - ACCEPTED  — строка принята как заголовок;
    - REJECTED  — строка отвергнута и не попадёт в дерево;
    - AMBIGUOUS — "серый" случай, его можно потом пересмотреть (LLM или
      дополнительные правила).
    """

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    AMBIGUOUS = "ambiguous"


class PatternKind(str, Enum):
    """
    Тип шаблона, по которому строка была распознана как заголовок.

    Это нужно для диагностики:
    - numeric_full      — "1.2. Заголовок" / "1) Заголовок";
    - numeric_no_dot    — "1.2.3 Заголовок" без точки после номера;
    - numeric_sectional — "Section 3.1 Title";
    - roman_level_1     — "I. Заголовок";
    - alpha             — "A. Заголовок" / "б) Заголовок";
    - fallback_simple   — упрощённый числовой шаблон (если он будет подключён).
    """

    NUMERIC_FULL = "numeric_full"
    NUMERIC_NO_DOT = "numeric_no_dot"
    NUMERIC_SECTIONAL = "numeric_sectional"
    ROMAN_LEVEL_1 = "roman_level_1"
    ALPHA = "alpha"
    FALLBACK_SIMPLE = "fallback_simple"


@dataclass
class HeadingCandidateRaw:
    """
    "Сырой" кандидат в заголовки.

    Для непрофессионального программиста:
    - эта структура создаётся сразу после regex‑парсинга строки;
    - она НЕ решает, хороший это заголовок или плохой;
    - здесь просто аккуратно сохраняем всё, что знаем про строку.
    """

    element_index: int          # индекс элемента в body_elements
    element_id: str             # стабильный element_id (если есть, иначе fallback)
    raw_text: str               # исходный текст элемента (после normalize_spaces)
    uid: str                    # предполагаемый номер клаузы ("1", "3.1.2")
    raw_title: str              # текст после uid, ещё не очищен
    page: int                   # номер страницы
    pattern_kind: PatternKind   # тип паттерна, сработавшего на этой строке


@dataclass
class HeadingCandidateFeatures:
    """
    Вычисленные признаки кандидата.

    Важно: это просто набор фактов, здесь нет бизнес‑решения.
    Эти признаки будут использоваться скорером, чтобы решать:
    принимать, отклонять или помечать как ambiguous.
    """

    uid_depth: int                    # глубина uid: "3.1.2" -> 3
    title_len: int                    # длина заголовка в символах
    word_count: int                   # количество слов в заголовке
    has_letters: bool                 # есть ли хоть одна буква
    letters_ratio: float              # доля букв в заголовке
    digits_ratio: float               # доля цифр в заголовке
    punct_ratio: float                # доля знаков пунктуации в заголовке
    is_title_short: bool              # очень короткий заголовок (1‑2 слова)
    is_numeric_only_title: bool       # заголовок почти целиком из цифр/знаков
    is_garbage_title: bool            # заголовок похож на ".", ",", "1 ,", "7 , ,"
    looks_like_body_sentence: bool    # "телесный" текст, а не заголовок
    uid_plausible: bool               # uid разумный (не "0.0.9999.12345")
    uid_format_kind: str              # "numeric" / "roman" / "alpha" / "other"

    # Признаки контекста — будут использоваться позже:
    prev_accepted_uid: str | None = None  # предыдущий принятый uid (если есть)
    uid_is_sequential: bool = False       # uid логично продолжает последовательность
    uid_jump_too_large: bool = False      # слишком большой скачок в нумерации


@dataclass
class HeadingCandidateScored:
    """
    Кандидат после скоринга.

    Для непрофессионального программиста:
    - raw        — исходные данные о строке;
    - features   — вычисленные признаки;
    - status     — итоговое решение (accepted / rejected / ambiguous);
    - score      — численный "балл доверия" (0.0 .. 1.0);
    - reasons    — человекочитаемые причины, почему принято такое решение;
    - reviewed_by_llm / llm_override — зарезервировано для будущего, когда
      появится локальный LLM‑рефайнер.
    """

    raw: HeadingCandidateRaw
    features: HeadingCandidateFeatures
    status: CandidateStatus
    score: float
    accept_reasons: list[str] = field(default_factory=list)
    reject_reasons: list[str] = field(default_factory=list)
    reviewed_by_llm: bool = False
    llm_override: dict[str, Any] | None = None

    @property
    def is_accepted(self) -> bool:
        return self.status == CandidateStatus.ACCEPTED

    @property
    def is_rejected(self) -> bool:
        return self.status == CandidateStatus.REJECTED

    @property
    def is_ambiguous(self) -> bool:
        return self.status == CandidateStatus.AMBIGUOUS
    
    