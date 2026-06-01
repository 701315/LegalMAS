# src/services/structure/_models/_recovery.py

"""
Phase 4 — Recovery Engine contracts.

Обрабатывает orphan nodes и broken structures ПОСЛЕ FSM + Resolution.

Содержит:
- RecoveryStrategyType  — тип стратегии восстановления
- TieBreakPolicy        — правила разрешения ничьих между кандидатами
- CandidateWindow       — ограниченное окно поиска parent
- RecoveryCandidate     — один кандидат на роль parent
- RecoveryDecision      — итоговое решение по одному orphan узлу
- RecoveryReport        — сводка по всем recovery операциям (per-document)

ВАЖНО по плану v5.2:
- Recovery НЕ ищет parent глобально (нет O(N²)).
- Поиск ограничен CandidateWindow (max_page_distance, max_level_delta).
- Recovery детерминирован: same input → same output.
- Strategy 4 (embeddings) НЕ активна в Wave 1 — добавляется в Phase 13.
- LLM НЕ контролирует hierarchy через recovery.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RecoveryStrategyType(str, Enum):
    """
    Тип стратегии восстановления orphan узла.

    NUMBERING_INFERENCE — вывод parent из numbering цепочки
                          (7.1 → parent 7)
    GRAMMAR_COMPATIBILITY — проверка совместимости numbering pattern
    LAYOUT_SIMILARITY   — indent / font / spacing proximity
    EMBEDDINGS          — semantic similarity (НЕ в Wave 1, Phase 13)
    BEST_EFFORT_ROOT    — не нашли parent → attach к root
    UNRECOVERED         — не удалось восстановить
    """

    NUMBERING_INFERENCE = "numbering_inference"
    GRAMMAR_COMPATIBILITY = "grammar_compatibility"
    LAYOUT_SIMILARITY = "layout_similarity"
    EMBEDDINGS = "embeddings"
    BEST_EFFORT_ROOT = "best_effort_root"
    UNRECOVERED = "unrecovered"


@dataclass(slots=True)
class TieBreakPolicy:
    """
    Правила разрешения ничьих между несколькими кандидатами на parent.

    По плану v5.2 приоритеты фиксированы:
    1. smallest page distance
    2. smallest level delta
    3. earliest appearance (наименьший elem_i)
    4. lexical uid (лексикографически меньший uid)

    Используется RecoveryEngine когда scores равны.
    """

    # Приоритеты зафиксированы — поля только для документирования
    priority_1: str = "smallest_page_distance"
    priority_2: str = "smallest_level_delta"
    priority_3: str = "earliest_appearance"
    priority_4: str = "lexical_uid"

    def rank(
        self,
        page_distance: int,
        level_delta: int,
        elem_i: int,
        uid: str,
    ) -> tuple[int, int, int, str]:
        """
        Возвращает sort key для кандидата.
        Меньше = лучше (min wins).
        """
        return (page_distance, level_delta, elem_i, uid)


@dataclass(slots=True)
class CandidateWindow:
    """
    Ограниченное окно поиска parent для orphan узла.

    Recovery НЕ ищет parent глобально — только в этом окне.
    Это защищает от O(N²) и нарушений scope boundaries.

    max_page_distance:      максимальное расстояние в страницах
    max_level_delta:        максимальная разница уровней
    compatible_token_types: допустимые типы нумерации parent
                            (None = любые)
    """

    max_page_distance: int
    max_level_delta: int
    compatible_token_types: list[str] | None = None

    def __post_init__(self) -> None:
        if self.max_page_distance < 0:
            raise ValueError(
                f"max_page_distance must be >= 0, got {self.max_page_distance}"
            )
        if self.max_level_delta < 0:
            raise ValueError(
                f"max_level_delta must be >= 0, got {self.max_level_delta}"
            )

    def allows(
        self,
        *,
        page_distance: int,
        level_delta: int,
        token_type: str | None = None,
    ) -> bool:
        """
        True если кандидат находится в пределах окна.
        """
        if page_distance > self.max_page_distance:
            return False
        if level_delta > self.max_level_delta:
            return False
        if (
            self.compatible_token_types is not None
            and token_type is not None
            and token_type not in self.compatible_token_types
        ):
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_page_distance": self.max_page_distance,
            "max_level_delta": self.max_level_delta,
            "compatible_token_types": self.compatible_token_types,
        }


# Дефолтное окно для Wave 1 (без embeddings)
DEFAULT_CANDIDATE_WINDOW = CandidateWindow(
    max_page_distance=3,
    max_level_delta=2,
    compatible_token_types=None,
)

# Окно для embedding recovery (Phase 13.4)
# Идентично DEFAULT_CANDIDATE_WINDOW — конфигурируется через settings.
EMBEDDING_CANDIDATE_WINDOW = CandidateWindow(
    max_page_distance=3,
    max_level_delta=2,
    compatible_token_types=None,
)



@dataclass(slots=True)
class RecoveryCandidate:
    """
    Один кандидат на роль parent для orphan узла.

    Создаётся RecoveryEngine для каждого потенциального parent
    в пределах CandidateWindow.
    """

    parent_uid: str
    strategy: RecoveryStrategyType
    confidence: float
    page_distance: int
    level_delta: int
    elem_i: int
    reason: str = ""

    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                f"confidence must be in [0.0, 1.0], got {self.confidence}"
            )
        if self.page_distance < 0:
            raise ValueError(f"page_distance must be >= 0, got {self.page_distance}")
        if self.level_delta < 0:
            raise ValueError(f"level_delta must be >= 0, got {self.level_delta}")

    def tiebreak_key(self, policy: TieBreakPolicy) -> tuple[int, int, int, str]:
        return policy.rank(
            page_distance=self.page_distance,
            level_delta=self.level_delta,
            elem_i=self.elem_i,
            uid=self.parent_uid,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_uid": self.parent_uid,
            "strategy": self.strategy.value,
            "confidence": self.confidence,
            "page_distance": self.page_distance,
            "level_delta": self.level_delta,
            "elem_i": self.elem_i,
            "reason": self.reason,
        }


@dataclass(slots=True)
class RecoveryDecision:
    """
    Итоговое решение RecoveryEngine по одному orphan узлу.

    recovered:       True если parent найден
    orphan_uid:      effective_uid orphan узла
    strategy_used:   какая стратегия сработала
    chosen_parent:   выбранный кандидат (None если не восстановлен)
    all_candidates:  все кандидаты рассмотренные в окне
    window:          параметры окна поиска
    """

    recovered: bool
    orphan_uid: str
    strategy_used: RecoveryStrategyType
    chosen_parent: RecoveryCandidate | None = None
    all_candidates: list[RecoveryCandidate] = field(default_factory=list)
    window: CandidateWindow | None = None

    @property
    def parent_uid(self) -> str | None:
        return self.chosen_parent.parent_uid if self.chosen_parent else None

    @property
    def recovery_confidence(self) -> float:
        return self.chosen_parent.confidence if self.chosen_parent else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "recovered": self.recovered,
            "orphan_uid": self.orphan_uid,
            "strategy_used": self.strategy_used.value,
            "parent_uid": self.parent_uid,
            "recovery_confidence": self.recovery_confidence,
            "candidates_considered": len(self.all_candidates),
            "window": self.window.to_dict() if self.window else None,
        }


@dataclass
class RecoveryReport:
    """
    Сводка по всем recovery операциям для одного документа.

    Создаётся per-document, НЕ singleton.
    Используется Phase 5 (Structural Confidence) как input.
    """

    document_id: str
    decisions: list[RecoveryDecision] = field(default_factory=list)

    def add(self, decision: RecoveryDecision) -> None:
        self.decisions.append(decision)

    @property
    def total_orphans(self) -> int:
        return len(self.decisions)

    @property
    def recovered_count(self) -> int:
        return sum(1 for d in self.decisions if d.recovered)

    @property
    def unrecovered_count(self) -> int:
        return self.total_orphans - self.recovered_count

    @property
    def orphan_ratio(self) -> float:
        """
        Используется Phase 9 (Quality Evaluation).
        Warning если > 0.1.
        """
        if self.total_orphans == 0:
            return 0.0
        return round(self.unrecovered_count / self.total_orphans, 4)

    @property
    def recovery_rate(self) -> float:
        if self.total_orphans == 0:
            return 1.0
        return round(self.recovered_count / self.total_orphans, 4)

    def by_strategy(
        self, strategy: RecoveryStrategyType
    ) -> list[RecoveryDecision]:
        return [d for d in self.decisions if d.strategy_used == strategy]

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "total_orphans": self.total_orphans,
            "recovered_count": self.recovered_count,
            "unrecovered_count": self.unrecovered_count,
            "orphan_ratio": self.orphan_ratio,
            "recovery_rate": self.recovery_rate,
            "strategies_used": {
                s.value: len(self.by_strategy(s)) for s in RecoveryStrategyType
            },
        }
    

    