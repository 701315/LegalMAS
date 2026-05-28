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

_DEFAULT_SCOPE = "main_contract"


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

    Это нужно для диагностики и explainability parser-layer.
    Синхронизировано по смыслу с актуальным heading_patterns.py.
    """

    NUMERIC_MAIN = "numeric_main"
    NUMERIC_TIGHT = "numeric_tight"
    NUMERIC_SECTIONAL = "numeric_sectional"
    NUMERIC_NO_DOT = "numeric_no_dot"
    LEGACY_NUMERIC_FULL = "legacy_numeric_full"
    ROMAN_LEVEL_1 = "roman_level_1"
    ALPHA = "alpha"
    FALLBACK_SIMPLE = "fallback_simple"


@dataclass(slots=True)
class HeadingCandidateRaw:
    """
    "Сырой" кандидат в заголовки.

    Для непрофессионального программиста:
    - эта структура создаётся сразу после regex‑парсинга строки;
    - она НЕ решает, хороший это заголовок или плохой;
    - здесь просто аккуратно сохраняем всё, что знаем про строку.

    ВАЖНО:
    - raw_uid — то, что вытащили непосредственно из строки;
    - effective_uid — канонический uid после scope-aware нормализации
      (если такая нормализация уже выполнена на текущем этапе);
    - scope — logical scope: main_contract / appendix_* / и т.п.
    """

    element_index: int  # индекс элемента в body_elements
    element_id: str  # стабильный element_id (если есть, иначе fallback)
    raw_text: str  # исходный текст элемента (после normalize_spaces)
    raw_uid: str  # исходный uid, распарсенный из строки
    raw_title: str  # текст после uid до cleanup/нормализации
    page: int  # номер страницы
    pattern_kind: PatternKind  # тип паттерна, сработавшего на этой строке
    scope: str = _DEFAULT_SCOPE  # main_contract / appendix_* / ...
    effective_uid: str | None = None  # scope-aware uid / canonical uid
    normalized_title: str | None = None  # title после cleanup_heading_title / normalize

    @property
    def uid(self) -> str:
        """
        Backward-compatible alias.

        Если effective_uid уже вычислен — он приоритетнее.
        Иначе возвращаем raw_uid.
        """
        return self.effective_uid or self.raw_uid

    @property
    def title(self) -> str:
        """
        Backward-compatible alias для наиболее полезной формы title.
        """
        return self.normalized_title or self.raw_title


@dataclass(slots=True)
class HeadingCandidateFeatures:
    """
    Вычисленные признаки кандидата.

    Важно: это просто набор фактов, здесь нет бизнес‑решения.
    Эти признаки используются скорером и scope-aware фильтрацией.
    """

    uid_depth: int  # глубина uid: "3.1.2" -> 3
    title_len: int  # длина заголовка в символах
    word_count: int  # количество слов в заголовке
    has_letters: bool  # есть ли хоть одна буква
    letters_ratio: float  # доля букв в заголовке
    digits_ratio: float  # доля цифр в заголовке
    punct_ratio: float  # доля знаков пунктуации в заголовке
    is_title_short: bool  # очень короткий заголовок (1-2 слова)
    is_numeric_only_title: bool  # заголовок почти целиком из цифр/знаков
    is_garbage_title: bool  # заголовок похож на ".", ",", "1 ,", "7 , ,"
    looks_like_body_sentence: bool  # "телесный" текст, а не заголовок
    uid_plausible: bool  # uid разумный (не "0.0.9999.12345")
    uid_format_kind: str  # "numeric" / "roman" / "alpha" / "other"

    # Scope / duplicate-related признаки
    scope: str = _DEFAULT_SCOPE
    duplicate_within_scope: bool = False
    duplicate_of_uid: str | None = None
    duplicate_of_element_id: str | None = None

    # Признаки контекста — используются для explainability и sequence checks
    prev_accepted_uid: str | None = None
    prev_accepted_effective_uid: str | None = None
    uid_is_sequential: bool = False
    uid_jump_too_large: bool = False


@dataclass(slots=True)
class HeadingCandidateScored:
    """
    Кандидат после скоринга.

    Для непрофессионального программиста:
    - raw         — исходные данные о строке;
    - features    — вычисленные признаки;
    - status      — итоговое решение (accepted / rejected / ambiguous);
    - score       — численный "балл доверия" (0.0 .. 1.0);
    - primary_reason — основная краткая причина решения;
    - accept_reasons / reject_reasons — детальное объяснение;
    - reviewed_by_llm / llm_override — зарезервировано для будущего.
    """

    raw: HeadingCandidateRaw
    features: HeadingCandidateFeatures
    status: CandidateStatus
    score: float
    primary_reason: str
    accept_reasons: list[str] = field(default_factory=list)
    reject_reasons: list[str] = field(default_factory=list)
    reviewed_by_llm: bool = False
    llm_override: dict[str, Any] | None = None
    decision_source: str = "deterministic_scoring"

    @property
    def is_accepted(self) -> bool:
        return self.status == CandidateStatus.ACCEPTED

    @property
    def is_rejected(self) -> bool:
        return self.status == CandidateStatus.REJECTED

    @property
    def is_ambiguous(self) -> bool:
        return self.status == CandidateStatus.AMBIGUOUS

    @property
    def scope(self) -> str:
        return self.raw.scope

    @property
    def uid(self) -> str:
        """
        Backward-compatible shortcut.
        """
        return self.raw.uid

    @property
    def raw_uid(self) -> str:
        return self.raw.raw_uid

    @property
    def effective_uid(self) -> str | None:
        return self.raw.effective_uid

    @property
    def title(self) -> str:
        return self.raw.title
