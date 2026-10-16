# src/engine/llm/token_budget.py
"""
Единый источник правды для оценки токенов, аллокации бюджета
и инвариантов промптов LLM.

Принципы:
1. Один TokenCounter на весь пайплайн.
2. Один ModelLimits, выводимый из settings.
3. Все тексты, влияющие на бюджет, измеряются через TokenCounter.
4. Каждый этап, отдающий текст дальше, проверяет инвариант «влезает».
5. Ошибка бюджета — явное исключение, а не silent fallback.

Этот модуль сознательно не подключён к production-коду на момент
создания. Подключение делается отдельной задачей, чтобы не смешивать
срочный bugfix с рефакторингом.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

from core.config import settings


class TokenCounter:
    """
    Консервативная оценка количества токенов в тексте.

    Округление — всегда ВВЕРХ. Никогда не занижаем реальный размер:
    safety-critical для предотвращения overflow context window.
    """
    __slots__ = ("chars_per_token",)

    def __init__(self, chars_per_token: float) -> None:
        if chars_per_token <= 0:
            raise ValueError(
                f"chars_per_token must be > 0, got {chars_per_token}"
            )
        self.chars_per_token = float(chars_per_token)

    @classmethod
    @lru_cache(maxsize=1)
    def from_settings(cls) -> "TokenCounter":
        return cls(
            float(getattr(settings, "LLM_TOKENIZER_CHARS_PER_TOKEN", 2.2))
        )

    def count(self, text: str) -> int:
        if not text:
            return 0
        return max(1, math.ceil(len(text) / self.chars_per_token))

    def chars_for(self, tokens: int) -> int:
        """Сколько символов влезает в N токенов. Округление ВНИЗ."""
        if tokens <= 0:
            return 0
        return max(1, int(tokens * self.chars_per_token))

    def tokens_for(self, chars: int) -> int:
        """Сколько токенов занимают N символов. Округление ВВЕРХ."""
        if chars <= 0:
            return 0
        return max(1, math.ceil(chars / self.chars_per_token))


@dataclass(frozen=True)
class ModelLimits:
    n_ctx: int
    max_output_tokens: int
    safety_margin: int

    @property
    def max_prompt_tokens(self) -> int:
        return self.n_ctx - self.max_output_tokens - self.safety_margin

    @classmethod
    @lru_cache(maxsize=1)
    def from_settings(cls) -> "ModelLimits":
        limits = cls(
            n_ctx=int(settings.LLM_CONTEXT_LIMIT),
            max_output_tokens=int(settings.LLM_MAX_TOKENS),
            safety_margin=int(settings.LLM_SAFETY_MARGIN_TOKENS),
        )
        if limits.max_prompt_tokens <= 0:
            raise ValueError(
                f"Invalid LLM limits: max_prompt_tokens="
                f"{limits.max_prompt_tokens} (n_ctx={limits.n_ctx}, "
                f"max_output={limits.max_output_tokens}, "
                f"safety={limits.safety_margin})"
            )
        return limits


class BudgetExhausted(Exception):
    """Фиксированная часть промпта не оставляет места под переменную."""


class BudgetViolation(Exception):
    """Готовый текст превышает выделенный бюджет — это баг, не fallback."""


@dataclass(frozen=True)
class PromptBudget:
    """
    Аллокация бюджета одного LLM-вызова:
    фиксированная часть (skeleton + ChatML) + переменная (фрагмент).

    Инвариант: fixed_tokens + flexible_budget_tokens ≤ max_prompt_tokens.
    """
    limits: ModelLimits
    counter: TokenCounter
    fixed_parts: dict[str, str]
    flexible_budget_tokens: int

    @classmethod
    def allocate(
        cls,
        *,
        fixed_parts: dict[str, str],
        min_flexible_tokens: int,
        limits: ModelLimits | None = None,
        counter: TokenCounter | None = None,
    ) -> "PromptBudget":
        limits = limits or ModelLimits.from_settings()
        counter = counter or TokenCounter.from_settings()

        fixed_tokens = sum(counter.count(s) for s in fixed_parts.values())
        flexible = limits.max_prompt_tokens - fixed_tokens
        if flexible < min_flexible_tokens:
            raise BudgetExhausted(
                f"fixed={fixed_tokens}, min_flexible={min_flexible_tokens}, "
                f"max_prompt={limits.max_prompt_tokens}"
            )
        return cls(
            limits=limits,
            counter=counter,
            fixed_parts=dict(fixed_parts),
            flexible_budget_tokens=flexible,
        )

    @property
    def flexible_budget_chars(self) -> int:
        return self.counter.chars_for(self.flexible_budget_tokens)

    def assert_fits(self, text: str, *, part: str) -> None:
        used = self.counter.count(text)
        if used > self.flexible_budget_tokens:
            raise BudgetViolation(
                f"{part} uses {used} tokens, budget is "
                f"{self.flexible_budget_tokens}"
            )


            