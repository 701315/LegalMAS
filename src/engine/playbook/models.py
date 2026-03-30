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
  levels задаёт, какие уровни чанков использовать (section/clause/subclause).
  required_kind задаёт минимальный "тип" чанка для evidence (например, subclause).
"""

import re
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, PrivateAttr, field_validator, model_validator


# ────────────────────────── DETECTOR CONFIG ──────────────────────────


class DetectorType(str, Enum):
    """Как именно выполняется проверка."""

    RULES = "rules"    # Только keyword/regex-поиск.
    LLM = "llm"        # Анализ только через LLM.
    HYBRID = "hybrid"  # Сначала rules, потом LLM как fallback.


class KeywordMode(str, Enum):
    """Как объединяются несколько ключевых слов."""

    ANY = "any"  # Достаточно найти хотя бы одно ключевое слово.
    ALL = "all"  # Нужно найти все ключевые слова.


# Признак того, что строка является regex-паттерном, а не plain keyword.
# Наличие любого из этих символов означает regex.
_REGEX_HINT_RE = re.compile(r'[\\()\[\]?+*{}|^$]')


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


class RetrievalConfig(BaseModel):
    """
    Конфигурация выбора чанков (retrieval) для проверки.

    Для непрофессионального программиста:

    - context_k: сколько чанков реально пойдёт в детектор (rules/LLM).
    - max_chunks: сколько максимум чанков запрашивать из RetrievalEngine.
      (Если None — берём дефолтное top_k движка.)
    - boost_keywords: дополнительные ключевые слова для поиска.
    - rerank: включать ли дополнительный пересортировщик (reranker)
      поверх базового скоринга BM25+dense.
    - filters: будущие фильтры по metadata (page, section_title, clause_uid и т.п.).
    - levels: какие уровни чанков использовать:
        ["subclause", "section"] по умолчанию.
      Например, для узких чеков можно задать ["subclause"],
      для общих — ["section", "clause"].
    - required_kind: минимальный "тип" чанка для evidence.
      Например, "subclause" — значит, мы предпочитаем брать доказательство
      из под‑клаузы, даже если section тоже матчится.
    """

    context_k: int = 5
    max_chunks: int | None = None
    boost_keywords: list[str] = Field(default_factory=list)
    rerank: bool = True
    filters: dict[str, Any] = Field(default_factory=dict)

    # Новое поле: уровни чанков, которые участвуют в retrieval.
    # Возможные значения: "section", "clause", "subclause".
    # По умолчанию: subclause + section, как сейчас в коде.
    levels: list[str] = Field(default_factory=lambda: ["subclause", "section"])

    # Новое поле: "предпочитаемый" тип чанка для evidence.
    # Например:
    #   required_kind = "subclause"
    # означает, что при выборе лучших чанков мы сначала смотрим на subclause,
    # и только если их нет — используем другие уровни.
    required_kind: str | None = None


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
        "==", "!=", ">", ">=", "<", "<=",
        "in", "not_in", "is_null", "not_null",
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

    Примеры:
    - termination_notice_days: NUMBER, unit="days"
    - governing_law: STRING, allowed_values=["RU", "EN", "DE"]
    """

    name: str
    type: ExtractionFieldType = ExtractionFieldType.STRING
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


class ExtractionMode(str, Enum):
    """Режим извлечения значений."""

    RULES = "rules"
    LLM = "llm"
    HYBRID = "hybrid"


class ExtractionConfig(BaseModel):
    """
    Конфигурация структурированного извлечения для проверки.

    Если enabled=False — проверка работает как обычная (pass/fail),
    без попытки вытащить дополнительные поля.
    """

    enabled: bool = False
    mode: ExtractionMode = ExtractionMode.HYBRID
    fields: list[ExtractionFieldConfig] = Field(default_factory=list)

    # Нужно ли сохранять результат извлечения в structured_data в CheckResult.
    store_payload: bool = True

    # NEW: кастомный inline-промпт для LLM-извлечения.
    # Если задан — ExtractionLLMDetector использует его вместо файлового шаблона.
    llm_prompt_extraction: str | None = None

    @field_validator("fields")
    @classmethod
    def _validate_fields_if_enabled(cls, v, info):
        enabled = info.data.get("enabled", False) if hasattr(info, "data") else False
        if enabled and not v:
            raise ValueError("extraction.enabled=true, но fields пустой")
        return v


# ────────────────────────── CHECK & PLAYBOOK ─────────────────────────


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
            return [
                check
                for check in base_checks
                if not getattr(check, "conditional", None)
            ]

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
    