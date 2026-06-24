# src/engine/playbook/models.py

"""
Модели данных плейбука (Playbook Data Models).

Задача этого модуля — описать, как выглядят проверки (checks),
которые выполняет движок, в виде Pydantic-моделей:

- A Playbook описывает набор проверок (CheckDefinition), которые нужно
  выполнить для документов в рамках сделки.
- Каждая проверка задаёт:
  - Что искать (ключевые слова, паттерны, LLM‑промпт).
  - Как искать (rules / llm / hybrid).
  - Насколько серьёзна находка (critical / high / medium / low).
  - К каким типам документов она относится (doc_types).

Эти модели используются:

1) Для валидации YAML‑плейбуков (ручная/отладочная загрузка).
2) Для работы с уже скомпилированными плейбуками, которые хранятся
   в PlaybookVersion.compiled_checks и загружаются через
   engine.playbook.loader.load_playbook_from_version.

Поле CheckDefinition.origin заполняется на основании source из
core.playbooks.compiler.GlobalCheckConfig и используется в UI (DD Grid)
для фильтров по происхождению риска.

Изменения (keyword_groups support):
- RulesConfig: добавлено поле keyword_groups и приватный атрибут _group_map.
- model_validator _normalize_keyword_groups: раскладывает паттерны из
  keyword_groups по keywords/regex_patterns и строит _group_map для
  расчёта confidence по уровню в RulesDetector.
- _REGEX_HINT_RE: константа для определения regex-паттернов по наличию
  специальных символов.

Изменения (llm_prompt_extraction support):
- ExtractionConfig: добавлено поле llm_prompt_extraction: str | None.
  Если задано, ExtractionLLMDetector использует его как inline-промпт
  для LLM-извлечения вместо файлового шаблона.

Изменения (retrieval levels/required_kind):
- RetrievalConfig: добавлены поля levels и required_kind.
  levels задаёт, какие уровни чанков использовать для retrieval.
  После P8.8d primary retrieval substrate = legal_unit + section.
  required_kind задаёт предпочитаемый "тип" чанка для evidence.
"""

import re
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, PrivateAttr, field_validator, model_validator

# ────────────────────────── DETECTOR CONFIG ──────────────────────────


class DetectorType(str, Enum):
    """Как именно выполняется проверка."""

    RULES = "rules"  # Только keyword/regex-поиск.
    LLM = "llm"  # Анализ только через LLM.
    HYBRID = "hybrid"  # Сначала rules, потом LLM как fallback.


class KeywordMode(str, Enum):
    """Как объединяются несколько ключевых слов."""

    ANY = "any"  # Достаточно найти хотя бы одно ключевое слово.
    ALL = "all"  # Нужно найти все ключевые слова.


# Признак того, что строка является regex-паттерном, а не plain keyword.
# Наличие любого из этих символов означает regex.
_REGEX_HINT_RE = re.compile(r"[\\()\[\]?+*{}|^$]")


class RulesConfig(BaseModel):
    """Конфигурация rules-базированного детектора."""

    keywords: list[str] = Field(default_factory=list)
    keyword_mode: KeywordMode = KeywordMode.ANY
    regex_patterns: list[str] = Field(default_factory=list)
    clause_patterns: list[str] = Field(default_factory=list)  # Сопоставление по clause_uid.
    negative_keywords: list[str] = Field(default_factory=list)

    # Новое: уровневые группы keywords/regex.
    #
    # Формат в YAML:
    #   rules:
    #     keywords:
    #       high:   ["(?i)governed\\s+by\\s+the\\s+laws?\\s+of"]
    #       medium: ["jurisdiction", "governing law"]
    #       low:    ["court", "суд"]
    #
    # Или отдельным полем:
    #   rules:
    #     keyword_groups:
    #       high:   [...]
    #       medium: [...]
    #
    # Паттерны с regex-символами автоматически роутятся в regex_patterns,
    # обычные строки — в keywords. Используется для расчёта confidence
    # в RulesDetector (high→0.85, medium→0.65, low→0.45).
    keyword_groups: dict[str, list[str]] = Field(default_factory=dict)

    # Внутренняя карта: pattern → уровень (заполняется model_validator).
    # PrivateAttr гарантирует отдельный экземпляр для каждого объекта
    # (в отличие от аннотации класса, которая создаёт shared-атрибут).
    # Не сериализуется и не попадает в model_dump().
    _group_map: dict[str, str] = PrivateAttr(default_factory=dict)

    @model_validator(mode="after")
    def _normalize_keyword_groups(self) -> "RulesConfig":
        """
        Нормализует keyword_groups после инициализации объекта:

        1) Строит _group_map: {pattern: level} для всех паттернов из групп.
        2) Regex-паттерны (содержат спецсимволы) добавляет в regex_patterns.
        3) Plain keywords добавляет в keywords.

        Дубли не добавляются: если паттерн уже есть в соответствующем списке,
        пропускается.
        """
        if not self.keyword_groups:
            return self

        group_map: dict[str, str] = {}
        extra_keywords: list[str] = []
        extra_regex: list[str] = []

        for level, patterns in self.keyword_groups.items():
            if not isinstance(patterns, list):
                continue
            for p in patterns:
                if not isinstance(p, str) or not p.strip():
                    continue
                p = p.strip()
                group_map[p] = level
                if _REGEX_HINT_RE.search(p):
                    if p not in self.regex_patterns:
                        extra_regex.append(p)
                else:
                    if p not in self.keywords:
                        extra_keywords.append(p)

        if extra_keywords:
            self.keywords = self.keywords + extra_keywords
        if extra_regex:
            self.regex_patterns = self.regex_patterns + extra_regex

        self._group_map = group_map
        return self


class LLMConfig(BaseModel):
    """Конфигурация LLM‑детектора."""

    prompt_template: str = ""
    prompt_file: str | None = None
    context_k: int = 5
    temperature: float = 0.0
    max_tokens: int = 500


class EvidenceConfig(BaseModel):
    """Настройки требований к evidence (фрагменту текста в подтверждение)."""

    required: bool = True
    min_snippet_length: int = 20
    max_snippet_length: int = 500


class RetrievalPositionBiasConfig(BaseModel):
    """
    Soft position prior for retrieval scoring.

    preferred_range:
        Диапазон нормализованной позиции чанка [min, max] в пределах [0.0, 1.0].

    boost:
        Насколько мягко усиливать чанки, попавшие в preferred_range.

    scope:
        - auto    -> сначала position_ratio_within_segment, потом within_file, потом position_ratio
        - segment -> только position_ratio_within_segment
        - file    -> position_ratio_within_file / position_ratio
    """

    preferred_range: list[float] = Field(default_factory=lambda: [0.0, 1.0])
    boost: float = Field(default=0.0, ge=0.0, le=1.0)
    scope: Literal["auto", "segment", "file"] = "auto"

    @field_validator("preferred_range")
    @classmethod
    def _validate_preferred_range(cls, v: list[float]) -> list[float]:
        if not isinstance(v, list) or len(v) != 2:
            raise ValueError("position_bias.preferred_range must contain exactly 2 numbers")

        try:
            lo = float(v[0])
            hi = float(v[1])
        except (TypeError, ValueError):
            raise ValueError("position_bias.preferred_range must contain numeric values")

        if not (0.0 <= lo <= 1.0 and 0.0 <= hi <= 1.0):
            raise ValueError("position_bias.preferred_range values must be within [0.0, 1.0]")

        if hi < lo:
            raise ValueError("position_bias.preferred_range must satisfy max >= min")

        return [lo, hi]

class RetrievalCorpusScope(str, Enum):
    """
    Определяет, по какому корпусу чанков строится retrieval для данного check.

    PRIMARY_SEGMENT:
        Только primary segment документа (главный договор).
        Default для всех checks если не задано явно.

    CURRENT_SEGMENT:
        Только текущий сегмент в batch segment execution.
        Используется для checks, которые должны работать строго
        в рамках одного логического сегмента.

    DOCUMENT:
        Все сегменты документа (contract + appendices).
        Используется для checks, где evidence может быть распределено
        по основному договору и приложениям.
    """

    PRIMARY_SEGMENT = "primary_segment"
    CURRENT_SEGMENT = "current_segment"
    DOCUMENT = "document"

class RetrievalConfig(BaseModel):
    """
    Конфигурация retrieval policy для проверки.

    context_k:
        Сколько чанков реально пойдёт в detector / extraction.

    max_chunks:
        Сколько максимум чанков запросить из RetrievalEngine до post-processing.

    retrieval_query:
        Явная поисковая фраза для retrieval на языке документа.
        Если не задана — runtime построит fallback query из check.name + boost_keywords.

    boost_keywords:
        Дополнительные положительные retrieval terms.

    negative_keywords:
        Anti-boost terms. Не удаляют chunk из corpus, но понижают его score,
        если chunk явно попадает в нерелевантную семантику для данного check.

    preferred_unit_types:
        Semantic unit types, которые желательно поднимать в ranking
        (например: warranty, payment_term, liability_provision).

    excluded_unit_types:
        Semantic unit types, которые желательно опускать в ranking
        (например: definition, technical_fragment).

    preferred_clause_functions:
        Functional clause roles, которые желательно поднимать в ranking
        (например: limitations, remedies, obligations).

    position_bias:
        Soft prior по позиции чанка внутри сегмента/файла.

    rerank:
        Включать ли дополнительный lightweight rerank поверх base retrieval.

    filters:
        Reserved for future hard filters by metadata.

    levels:
        Какие retrieval levels читать из corpus.
        По умолчанию: legal_unit + section.

    required_kind:
        Предпочитаемый chunk kind при выборе evidence.
    """

    context_k: int = 5
    max_chunks: int | None = None

    retrieval_query: str | None = None
    boost_keywords: list[str] = Field(default_factory=list)
    negative_keywords: list[str] = Field(default_factory=list)

    preferred_unit_types: list[str] = Field(default_factory=list)
    excluded_unit_types: list[str] = Field(default_factory=list)
    preferred_clause_functions: list[str] = Field(default_factory=list)
    position_bias: RetrievalPositionBiasConfig | None = None

    rerank: bool = True
    filters: dict[str, Any] = Field(default_factory=dict)

    # Уровни чанков, которые участвуют в retrieval.
    # После P8.8d: primary retrieval substrate = legal_unit + section.
    # Legacy "subclause" автоматически алиасится в "legal_unit".
    levels: list[str] = Field(default_factory=lambda: ["legal_unit", "section"])

    # Предпочитаемый тип чанка для evidence.
    required_kind: str | None = None

    # ID retrieval profile из retrieval_profiles.py.
    # Если задан — RetrievalEngine применяет profile-specific boosts
    # по topic_tags/clause_function из enriched chunk metadata.
    # Это universal retrieval intent declaration, не check-specific heuristic.
    # Примеры: "party_identification_check", "governing_law_check".
    retrieval_profile: str | None = None

    # Определяет, по какому корпусу строится retrieval.
    # primary_segment — только основной договор (default).
    # current_segment — только текущий сегмент в batch execution.
    # document — весь документ включая appendices.
    corpus_scope: RetrievalCorpusScope = RetrievalCorpusScope.PRIMARY_SEGMENT

    @field_validator("retrieval_query")
    @classmethod
    def _validate_retrieval_query(cls, v: str | None) -> str | None:
        if v is None:
            return None

        cleaned = " ".join(str(v).strip().split())
        return cleaned or None


# ────────────────────────── NEW CONDITIONAL ──────────────────────────


class TriggerCondition(BaseModel):
    """
    Условие по триггеру (Stage 8).

    Пример YAML:

      - name: "land_plot_sale"
        state: "on"
    """

    name: str
    state: Literal["on", "off"] = "on"


class StructuredDataCondition(BaseModel):
    """Условие на поле из structured_data (Stage 8)."""

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
        op = info.data.get("op") if hasattr(info, "data") else None
        if op in ("is_null", "not_null"):
            return None
        if op in ("in", "not_in") and v is not None and not isinstance(v, list):
            raise ValueError(f"value для op={op} должен быть списком")
        return v


class ConditionalConfig(BaseModel):
    """
    Условия включения проверки (новая модель Stage 8).

    Поддерживает три уровня:

    1) Старое простое поле trigger (один триггер) — для обратной совместимости.
    2) Список trigger‑условий (triggers).
    3) Условия по structured_data (when).

    Группы triggers и when внутри себя объединяются по AND.
    Между группами работает logic: AND/OR.
    """

    trigger: str | None = None
    triggers: list[TriggerCondition] = Field(default_factory=list)
    when: list[StructuredDataCondition] = Field(default_factory=list)

    min_level: str | None = None
    max_level: str | None = None
    logic: Literal["AND", "OR"] = "AND"
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("logic")
    @classmethod
    def _validate_logic(cls, v, values):
        if values.get("trigger"):
            return v

        has_triggers = bool(values.get("triggers"))
        has_when = bool(values.get("when"))
        enabled_new_conditions = has_triggers or has_when

        if enabled_new_conditions and not (has_triggers or has_when):
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
    ...
    """

    name: str
    type: ExtractionFieldType = ExtractionFieldType.STRING
    label: str | None = None
    presentation: Literal["summary", "fact", "signal", "diagnostic"] = "fact"

    # Grid display contract (universal, playbook-driven).
    #
    # display_in_grid:
    #   Opt-in flag for including this factual field into DD Grid compact summary
    #   when no explicit summary / *_display field is provided.
    #
    # display_priority:
    #   Lower value = earlier in compact DD Grid summary.
    #   If omitted, extraction field declaration order remains fallback priority.
    #
    # These fields are ignored for presentation=signal/diagnostic.
    display_in_grid: bool = False
    display_priority: int | None = None

    description: str = ""

    # Подсказки для rules‑based извлечения.
    regex_patterns: list[str] = Field(default_factory=list)
    keyword_hints: list[str] = Field(default_factory=list)

    # Инструкция для LLM по этому полю.
    llm_instructions: str = ""

    # Пост‑условия / валидация.
    required: bool = False
    allowed_values: list[str] = Field(default_factory=list)
    unit: str | None = None

    min_value: float | None = None
    max_value: float | None = None

    # Maximum number of characters allowed for the final normalized string value.
    #
    # Purpose:
    # - protects summary/fact fields from runaway paragraph-sized payloads;
    # - can be raised explicitly for inventory/schedule fields that are
    #   expected to contain long multi-line lists.
    #
    # Semantics:
    # - None  -> use runtime default cap (currently 500 chars)
    # - int>0 -> field-specific override, declared in playbook YAML
    #
    # This is a playbook-driven contract: output size expectations belong
    # to the field definition, not to hardcoded check-specific logic in code.
    max_value_chars: int | None = None


class ExtractionMode(str, Enum):
    """Режим извлечения значений."""

    RULES = "rules"
    LLM = "llm"
    HYBRID = "hybrid"


class ExtractionConfig(BaseModel):
    """
    Конфигурация structured extraction для проверки.

    Архитектурный контракт:
    - semantic prompt задаётся через llm_prompt_extraction;
    - если custom llm_prompt_extraction задан, он обязан содержать
      плейсхолдер {context}, потому что именно extraction prompt
      отвечает за то, где и как встраивается текст договора;
    - технический JSON contract задаётся отдельно во внешнем
      template-файле playbooks/json_format_ru.txt.
    """

    enabled: bool = False
    mode: ExtractionMode = ExtractionMode.HYBRID
    fields: list[ExtractionFieldConfig] = Field(default_factory=list)

    # Нужно ли сохранять результат извлечения в structured_data в CheckResult.
    store_payload: bool = True

    # Кастомный semantic prompt для extraction.
    # ВАЖНО: если задан, обязан содержать {context}.
    llm_prompt_extraction: str | None = None

    # Per-check override для max_tokens в extraction LLM call.
    llm_max_tokens: int | None = None

    # Whether runtime should append the generic "compact 1-2 sentences" footer
    # to the extraction prompt.
    #
    # True  (default):
    #   Good for summary-style checks where each field is expected to be short.
    #
    # False:
    #   Use for inventory / schedule / register-style checks where a field may
    #   legitimately contain a long multi-line list of items.
    #
    # This is playbook-driven: the check declares its output style contract.
    compact_output: bool = True

    @field_validator("fields")
    @classmethod
    def _validate_fields_if_enabled(cls, v, info):
        enabled = info.data.get("enabled", False) if hasattr(info, "data") else False
        if enabled and not v:
            raise ValueError("extraction.enabled=true, но fields пустой")
        return v

    @field_validator("llm_prompt_extraction")
    @classmethod
    def _validate_llm_prompt_extraction(cls, v: str | None) -> str | None:
        """
        Custom extraction prompt обязан содержать {context}.
        Это устраняет скрытую неоднозначность:
        prompt сам управляет placement контекста, а не внешний шаблон.
        """
        if v is None:
            return None

        cleaned = v.strip()
        if not cleaned:
            return None

        if "{context}" not in cleaned:
            raise ValueError(
                "extraction.llm_prompt_extraction must contain '{context}' placeholder"
            )

        return cleaned

    @field_validator("llm_max_tokens")
    @classmethod
    def _validate_llm_max_tokens(cls, v: int | None) -> int | None:
        if v is None:
            return None
        if v <= 0:
            raise ValueError("extraction.llm_max_tokens must be > 0")
        return v


# ────────────────────────── CHECK & PLAYBOOK ─────────────────────────


class EnrichmentHints(BaseModel):
    """
    Optional semantic enrichment hints for a check definition.

    Controls how legal-unit enrichment metadata influences retrieval
    scoring and confidence calibration for this specific check.

    All fields optional. Absence of this block = no change to base behaviour.

    preferred_segment_types:
        Segment types where evidence is most expected.
        Chunks from these segments receive a soft retrieval boost.
        Example: ["contract", "amendment"]

    excluded_segment_types:
        Segment types where evidence is unlikely or misleading.
        Chunks from these segments receive a soft retrieval penalty.
        Example: ["technical_specification", "price_list"]

    preferred_clause_functions:
        Clause functions relevant to this check (from enrichment sidecar).
        When segment has these functions, retrieval boost is applied.
        Example: ["confidentiality", "data_protection"]

    confidence_bonus_on_match:
        Float 0.0-1.0 added to confidence when semantic match occurs.
        Applied when segment clause_functions intersect preferred_clause_functions.
        Result is capped at 1.0.

    confidence_penalty_on_excluded_segment:
        Float 0.0-1.0 subtracted from confidence when evidence comes
        from an excluded_segment_type.
        Result is floored at 0.0.
    """

    preferred_segment_types: list[str] = Field(default_factory=list)
    excluded_segment_types: list[str] = Field(default_factory=list)
    preferred_clause_functions: list[str] = Field(default_factory=list)
    confidence_bonus_on_match: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence_penalty_on_excluded_segment: float = Field(default=0.0, ge=0.0, le=1.0)


class CheckDefinition(BaseModel):
    """
    Описание одной проверки (check), с которой работает движок.

    Источник данных:
    - либо YAML‑плейбук (ручная/отладочная загрузка),
    - либо скомпилированный плейбук из PlaybookVersion.compiled_checks.
    """

    id: str
    name: str
    description: str = ""
    doc_types: list[str] = Field(default_factory=list)

    # "GLOBAL_PLAYBOOK" / "DOCUMENT_TYPE" / "SYSTEM".
    origin: str | None = None

    # Режим пользовательской интерпретации результата в UI.
    # Нужен для построения понятных сообщений для юриста.
    # Примеры:
    # - "clause_presence"   -> проверка наличия обязательной клаузы
    # - "risk_detection"    -> проверка на наличие риска / проблемной формулировки
    # - "field_extraction"  -> преимущественно извлечение структурированных полей
    # - "generic"           -> нейтральный режим по умолчанию
    #
    # Поле optional для обратной совместимости:
    # старые playbooks без ui_mode продолжают работать как раньше.
    ui_mode: str | None = None

    scope: Literal["document", "family", "deal"] = "document"

    severity: str = "medium"
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

    # Optional semantic enrichment hints.
    # When present, influences retrieval scoring and confidence calibration.
    # Absence = no change to base behaviour.
    enrichment_hints: EnrichmentHints | None = None

    @model_validator(mode="after")
    def _validate_field_extraction_display_contract(self) -> "CheckDefinition":
        """
        Enforce deterministic UI contract for factual extraction checks.

        For field_extraction checks (explicit ui_mode or extraction.enabled):
        - either at least one field has presentation='summary'
        - or at least one field has presentation='fact' with explicit label

        This prevents prompt/instruction text leakage into DD Grid cells.
        """
        extraction = self.extraction
        if extraction is None or not extraction.enabled:
            return self

        raw_ui_mode = self.ui_mode
        ui_mode = str(raw_ui_mode).strip().lower() if raw_ui_mode is not None else ""
        is_field_extraction = (ui_mode == "field_extraction") or (not ui_mode)

        if not is_field_extraction:
            return self

        fields = extraction.fields or []
        if not fields:
            return self

        has_summary = any(
            getattr(f, "presentation", "fact") == "summary"
            for f in fields
        )
        if has_summary:
            return self

        reserved = {"reason", "evidence", "explanation", "notes"}
        missing_labels: list[str] = []

        for field in fields:
            presentation = getattr(field, "presentation", "fact")
            if presentation in ("signal", "diagnostic"):
                continue
            if field.name in reserved:
                continue
            label = getattr(field, "label", None)
            if not (label and str(label).strip()):
                missing_labels.append(field.name)

        if missing_labels:
            raise ValueError(
                f"field_extraction check (id={self.id!r}) is missing explicit "
                f"`label` for fact fields: {missing_labels}. "
                "Add `label: '...'` or set `presentation: signal` / `presentation: diagnostic`."
            )

        return self


class PlaybookDefinition(BaseModel):
    """
    Полное описание плейбука (метаданные + список проверок).

    Источники:
    - YAML‑файл (ручная/отладочная загрузка через load_playbook_from_yaml),
    - dict из PlaybookVersion.compiled_checks (боевой путь через
      load_playbook_from_version / load_playbook_from_dict).
    """

    name: str = "Default Playbook"
    version: str = "1.0.0"
    description: str = ""
    jurisdiction: str = "RU"
    languages: list[str] = Field(default_factory=lambda: ["RU", "EN"])
    checks: list[CheckDefinition] = Field(default_factory=list)

    def get_checks_for_doc_type(self, doc_type: str) -> list[CheckDefinition]:
        """Вернуть проверки, применимые к указанному типу документа."""
        result: list[CheckDefinition] = []
        for check in self.checks:
            if not check.doc_types:
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
        Получить список проверок для doc_type с учётом триггеров.

        - Если у проверки нет conditional → включаем всегда.
        - Если указан старый trigger (строка) и он есть в applicable_triggers → включаем.
        - Если используются новые triggers (список TriggerCondition),
          включаем, если хотя бы один name есть в applicable_triggers и state == "on".
        """
        base_checks = self.get_checks_for_doc_type(doc_type)
        if not applicable_triggers:
            return [check for check in base_checks if not getattr(check, "conditional", None)]

        trigger_set = set(applicable_triggers)
        result: list[CheckDefinition] = []

        for check in base_checks:
            cond = getattr(check, "conditional", None)

            if not cond:
                result.append(check)
                continue

            if cond.trigger and cond.trigger in trigger_set:
                result.append(check)
                continue

            if cond.triggers:
                if any(t.name in trigger_set and t.state == "on" for t in cond.triggers):
                    result.append(check)
                    continue

        return result
