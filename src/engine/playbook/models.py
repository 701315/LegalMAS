# src/engine/playbook/models.py

"""
Playbook Data Models.

A Playbook is a YAML file defining a set of checks (inspections)
to run on a document. Each check specifies:
- What to look for (keywords, patterns, or LLM prompt)
- How to look for it (rules, llm, or hybrid)
- How severe a finding is (critical, high, medium)
- What document types it applies to

These Pydantic models validate the YAML structure and provide
typed access to check definitions.
"""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# ────────────────────────── DETECTOR CONFIG ──────────────────────────


class DetectorType(str, Enum):
    """How the check is performed."""

    RULES = "rules"  # Keyword/regex search only
    LLM = "llm"  # LLM-only analysis
    HYBRID = "hybrid"  # Rules first, LLM as fallback


class KeywordMode(str, Enum):
    """How multiple keywords are combined."""

    ANY = "any"  # At least one keyword found → match
    ALL = "all"  # All keywords must be found → match


class RulesConfig(BaseModel):
    """Configuration for rules-based detection."""

    keywords: list[str] = Field(default_factory=list)
    keyword_mode: KeywordMode = KeywordMode.ANY
    regex_patterns: list[str] = Field(default_factory=list)
    clause_patterns: list[str] = Field(default_factory=list)  # Match clause_uid


class LLMConfig(BaseModel):
    """Configuration for LLM-based detection."""

    # Inline prompt text (has highest priority if not empty)
    prompt_template: str = ""

    # Name of prompt file in prompts/ (used by LLMDetector._resolve_prompt)
    prompt_file: str | None = None

    # How many chunks to include in prompt
    context_k: int = 5
    temperature: float = 0.0
    max_tokens: int = 500


class EvidenceConfig(BaseModel):
    """Configuration for evidence requirements."""

    required: bool = True  # Must provide evidence snippet
    min_snippet_length: int = 20
    max_snippet_length: int = 500


class RetrievalConfig(BaseModel):
    """
    Retrieval / chunk selection config for a check.

    Управляет тем:
    - сколько чанков брать в контекст (context_k),
    - какие дополнительные keywords можно использовать для поиска,
    - включён ли rerank,
    - фильтрами по metadata (page, section_title, clause_uid, и т.д.).
    """

    context_k: int = 5
    max_chunks: int | None = None
    boost_keywords: list[str] = Field(default_factory=list)
    rerank: bool = True
    filters: dict[str, Any] = Field(default_factory=dict)


# ────────────────────────── NEW CONDITIONAL ──────────────────────────


class TriggerCondition(BaseModel):
    """
    Условие по триггеру (Stage 8).

    Пример:
      - name: "land_plot_sale"
        state: "on"
    """

    name: str
    state: Literal["on", "off"] = "on"


class StructuredDataCondition(BaseModel):
    field: str
    op: Literal[
        "==",
        "!=",
        ">",
        ">=",
        "<",
        "<=",
        "in",
        "not_in",
        "is_null",
        "not_null",
    ]
    value: Any | None = None

    @field_validator("value")
    @classmethod
    def _validate_value_for_op(cls, v, info):
        # info: ValidationInfo, значения других полей доступны через info.data
        op = info.data.get("op") if hasattr(info, "data") else None
        if op in ("is_null", "not_null"):
            # Для is_null/not_null value не требуется
            return None
        if op in ("in", "not_in") and v is not None and not isinstance(v, list):
            raise ValueError(f"value для op={op} должен быть списком")
        return v


class ConditionalConfig(BaseModel):
    """
    Условия включения проверки (новая модель Stage 8).

    Поддерживает три уровня:

    1) Старое простое поле trigger (один триггер) — для обратной совместимости.
       Пример:
         conditional:
           trigger: "land_plot_sale"

    2) Список trigger-условий:
         conditional:
           triggers:
             - name: "land_plot_sale"
               state: "on"

    3) Условия по structured_data:
         conditional:
           when:
             - field: "price_amount"
               op: ">"
               value: 10000000

    Группы triggers и when внутри себя объединяются по AND.
    Между группами работает logic: AND/OR.
    """

    # ── старое поле для совместимости ──
    trigger: str | None = None  # имя триггера из applicable_triggers

    # ── новая логика Stage 8 ──
    triggers: list[TriggerCondition] = Field(default_factory=list)
    when: list[StructuredDataCondition] = Field(default_factory=list)

    # Границы по уровню классификации (как раньше), можно использовать и дальше
    min_level: str | None = None
    max_level: str | None = None

    # Логика объединения групп triggers и when
    logic: Literal["AND", "OR"] = "AND"

    # Зарезервировано на будущее для более сложных условий.
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("logic")
    @classmethod
    def _validate_logic(cls, v, values):
        # Если используется только старое поле trigger — ничего не проверяем
        if values.get("trigger"):
            return v

        # Если включены новые условия, но они пустые — конфигурационная ошибка
        has_triggers = bool(values.get("triggers"))
        has_when = bool(values.get("when"))
        enabled_new_conditions = has_triggers or has_when

        if enabled_new_conditions and not (has_triggers or has_when):
            # Теоретически сюда не попадём, но оставим на всякий случай
            raise ValueError("conditional: заданы новые поля, но triggers/when пустые")

        return v


# ────────────────────────── EXTRACTION ───────────────────────────────


class ExtractionFieldType(str, Enum):
    """Тип значения, которое мы хотим извлечь."""

    STRING = "string"
    NUMBER = "number"
    DATE = "date"
    BOOLEAN = "boolean"
    CLAUSE_REF = "clause_ref"  # ссылка на клаузу / chunk id


class ExtractionFieldConfig(BaseModel):
    """
    Описание одного извлекаемого поля.

    Примеры:
    - termination_notice_days: NUMBER, unit="days"
    - governing_law: STRING, allowed_values=["RU", "EN", "DE"]
    """

    name: str
    type: ExtractionFieldType = ExtractionFieldType.STRING
    description: str = ""

    # Подсказки для rules-based извлечения
    regex_patterns: list[str] = Field(default_factory=list)
    keyword_hints: list[str] = Field(default_factory=list)

    # Инструкция для LLM по этому полю
    llm_instructions: str = ""

    # Пост-условия / валидация
    required: bool = False
    allowed_values: list[str] = Field(default_factory=list)
    unit: str | None = None  # "days", "%", "RUB", и т.п.

    # Дополнительные поля Stage 8 (если захочешь использовать):
    min_value: float | None = None
    max_value: float | None = None


class ExtractionMode(str, Enum):
    """Режим извлечения значений."""

    RULES = "rules"
    LLM = "llm"
    HYBRID = "hybrid"


class ExtractionConfig(BaseModel):
    """
    Конфигурация структурированного извлечения для check.

    Если enabled=False — check работает как обычная проверка (pass/fail),
    без попытки вытащить дополнительные поля.
    """

    enabled: bool = False
    mode: ExtractionMode = ExtractionMode.HYBRID
    fields: list[ExtractionFieldConfig] = Field(default_factory=list)

    # Нужно ли сохранять результат извлечения в structured_data в CheckResult
    store_payload: bool = True

    @field_validator("fields")
    @classmethod
    def _validate_fields_if_enabled(cls, v, info):
        # info: ValidationInfo, реальные значения — в info.data
        enabled = info.data.get("enabled", False) if hasattr(info, "data") else False
        if enabled and not v:
            raise ValueError("extraction.enabled=true, но fields пустой")
        return v


# ────────────────────────── CHECK & PLAYBOOK ─────────────────────────


class CheckDefinition(BaseModel):
    """
    A single check (inspection) defined in a playbook.

    Example:
        id: coc_001
        name: Change of Control
        description: Check if the contract contains a change of control clause
        doc_types: [SPA, SHA]
        severity: critical
        detector:
            type: hybrid
            rules:
                keywords: ["смена контроля", "change of control"]
            llm:
                prompt_template: "Does this contract contain..."
    """

    id: str
    name: str
    description: str = ""
    doc_types: list[str] = Field(default_factory=list)  # Empty = all types

    # NEW: scope определяет, на каком уровне выполняется проверка
    scope: Literal["document", "family", "deal"] = "document"

    # Базовая severity по умолчанию
    severity: str = "medium"  # critical, high, medium

    # Outcome-зависимая severity (опционально)
    severity_if_fail: str | None = None
    severity_if_pass: str | None = None
    severity_if_unclear: str | None = None

    detector_type: DetectorType = DetectorType.RULES
    rules: RulesConfig = Field(default_factory=RulesConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    evidence: EvidenceConfig = Field(default_factory=EvidenceConfig)

    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    conditional: ConditionalConfig | None = None
    extraction: ExtractionConfig | None = None


class PlaybookDefinition(BaseModel):
    """
    Complete playbook with metadata and checks.

    Loaded from a YAML file and validated via Pydantic.
    """

    name: str = "Default Playbook"
    version: str = "1.0.0"
    description: str = ""
    jurisdiction: str = "RU"
    languages: list[str] = Field(default_factory=lambda: ["RU", "EN"])
    checks: list[CheckDefinition] = Field(default_factory=list)

    def get_checks_for_doc_type(self, doc_type: str) -> list[CheckDefinition]:
        """Get checks applicable to a specific document type."""
        result: list[CheckDefinition] = []
        for check in self.checks:
            if not check.doc_types:
                # No restriction → applies to all types
                result.append(check)
            elif doc_type in check.doc_types:
                result.append(check)
        return result

    def get_conditional_checks(
        self,
        doc_type: str,
        applicable_triggers: list[str],
    ) -> list[CheckDefinition]:
        """
        Получить список checks для doc_type с учётом триггеров.

        Для обратной совместимости:
        - если check.conditional отсутствует или пустой → включаем check;
        - если в conditional указан старый trigger и он есть в applicable_triggers → включаем;
        - если используются новые triggers (список TriggerCondition),
          включаем check, если хотя бы один из name попадает в applicable_triggers.
        """
        base_checks = self.get_checks_for_doc_type(doc_type)
        if not applicable_triggers:
            # Если триггеров нет, возвращаем только безусловные проверки
            return [check for check in base_checks if not getattr(check, "conditional", None)]

        trigger_set = set(applicable_triggers or [])
        result: list[CheckDefinition] = []

        for check in base_checks:
            cond = getattr(check, "conditional", None)

            # Нет условной конфигурации — всегда включаем
            if not cond:
                result.append(check)
                continue

            # 1) Старое поле trigger (строка)
            if cond.trigger and cond.trigger in trigger_set:
                result.append(check)
                continue

            # 2) Новый список triggers (TriggerCondition)
            if cond.triggers:
                if any(t.name in trigger_set and t.state == "on" for t in cond.triggers):
                    result.append(check)
                    continue

        return result
