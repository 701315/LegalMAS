# src/engine/doc_type_checks/loader.py

"""
DocTypeCheckLoader — загружает специфические checks из YAML-инструкции типа документа.

Читает блоки из YAML:
  1. checks_v8        — прямые LLM/hybrid проверки с полной конфигурацией
  2. doc_type_checks  — rules-only проверки (авто-конвертируемые)
  3. compliance_rules — критические compliance-проверки по комбинации триггеров

Не читает: classification_runtime_v1, trigger_definitions (они обрабатываются отдельно).

Возвращает список CheckDefinition, совместимых с CheckExecutor.

Изменения (keyword_groups support):
  - _build_rules_config() — выделен отдельный метод для построения RulesConfig.
    Обрабатывает два формата keywords:
      * Старый: keywords: ["word1", "word2"]  — flat list, без изменений.
      * Новый:  keywords: {high: [...], medium: [...], low: [...]}
                или отдельное поле keyword_groups: {...}
  - _build_check_from_v8, _build_check_from_doc_type, _build_compliance_check
    используют _build_rules_config() вместо прямого RulesConfig(...).

Изменения (CheckContext support, этап 2B):
  - Добавлен метод load_checks_for_context(ctx) — контекстный API.
    Является тонкой надстройкой над load_checks_for_doc().
    Для scope="document" использует document_type как ключ к YAML.
    Для scope="segment" использует segment_doc_type как ключ к YAML.

Изменения (enrichment_hints support):
  - Добавлен метод _parse_enrichment_hints().
  - _build_check_from_v8() теперь читает блок enrichment_hints из YAML
    и передаёт его в CheckDefinition.
  - Позволяет задавать preferred_clause_functions, confidence_bonus_on_match
    и другие enrichment-сигналы прямо в doc-type YAML инструкции.
  - Влияние: executor применяет confidence_bonus_on_match когда
    clause_functions сегмента пересекаются с preferred_clause_functions.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, Dict, Optional

import yaml
from pydantic import ValidationError

from core.config import settings
from core.logging import get_logger
from engine.playbook.models import (
    CheckDefinition,
    ConditionalConfig,
    DetectorType,
    EnrichmentHints,
    EvidenceConfig,
    ExtractionConfig,
    ExtractionFieldConfig,
    ExtractionFieldType,
    ExtractionMode,
    LLMConfig,
    RetrievalConfig,
    RetrievalCorpusScope,
    RulesConfig,
    TriggerCondition,
)

if TYPE_CHECKING:
    from engine.checks.planning.context import CheckContext

logger = get_logger(__name__)


# ─── Fallback-texts parsing ──────────────────────────────────────────────────
#
# Fallback-тексты объявлены авторами полей в `description` в формате:
#     Fallback: "Не установлен" / "Не удалось определить".
#
# Автопарсинг при загрузке playbook → ExtractionFieldConfig.fallback_texts.
# Универсально для всех doc-type файлов, не привязано к check_id/языку.
#
# Нестандартные форматы (продолжение на след. строке, комментарии в скобках,
# bullet-префиксы) — парсер берёт то, что видит на одной строке; недостающее
# фиксируется warning'ом при загрузке. Явный `fallback_texts: [...]` в YAML
# полностью переопределяет автопарсинг.

_FALLBACK_LINE_RE = re.compile(r"Fallback\s*:\s*(.+)", re.IGNORECASE)
_FALLBACK_PHRASE_RE = re.compile(r'"([^"]+)"')


def _extract_fallback_texts_from_description(description: str | None) -> list[str]:
    """
    Извлечь fallback-тексты из description поля.

    Формат источника:
        'Fallback: "Не установлен" / "Не удалось определить".'

    Возвращает список уникальных фраз в порядке появления:
        ["Не установлен", "Не удалось определить"]

    Если `Fallback:` нет или description пуст → [].

    Универсально: не зависит от check_id, doc_type, языка, содержания документа.
    """
    if not description or not isinstance(description, str):
        return []

    m = _FALLBACK_LINE_RE.search(description)
    if not m:
        return []

    line = m.group(1)
    phrases = _FALLBACK_PHRASE_RE.findall(line)

    seen: set[str] = set()
    result: list[str] = []
    for p in phrases:
        normalized = p.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


class InstructionProvider(Protocol):
    """Интерфейс источника инструкций (диск или база данных)."""
    def get_instruction_data(self, doc_type: str) -> Optional[dict]: ...

class FilesystemInstructionProvider:
    """Провайдер для режима разработки/администрирования: читает живые файлы."""

    def __init__(self, registry_dir: Optional[str] = None):
        self._dir = Path(registry_dir or settings.CLASSIFIER_REGISTRY_PATH)
        # In-memory кэш: doc_type → результат чтения YAML (dict или None).
        # None в кэше означает «файл не найден» — повторный disk I/O не нужен.
        # Кэш живёт столько же, сколько экземпляр провайдера.
        # Для получения свежих данных создать новый экземпляр.
        self._cache: dict[str, Optional[dict]] = {}

    def get_instruction_data(self, doc_type: str) -> Optional[dict]:
        if doc_type not in self._cache:
            self._cache[doc_type] = self._load_from_disk(doc_type)
        return self._cache[doc_type]

    def _load_from_disk(self, doc_type: str) -> Optional[dict]:
        """Читает YAML с диска. Вызывается максимум один раз на doc_type."""
        direct = self._dir / f"{doc_type}.yaml"
        if direct.exists():
            try:
                with direct.open(encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception:
                return None

        pattern = f"**/{doc_type}.yaml"
        # ИСПРАВЛЕНО: сортировка по глубине пути (ближайший к корню первый).
        # Лексикографическая сортировка могла выбирать файл из более глубокой
        # подпапки при коллизии имён в разных директориях.
        candidates = sorted(self._dir.glob(pattern), key=lambda p: len(p.parts))
        if candidates:
            try:
                with candidates[0].open(encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception:
                return None
        return None

class DatabaseInstructionProvider:
    """Провайдер для режима Execution/Review: читает зафиксированные snapshot'ы из БД."""
    def __init__(self, instruction_versions: Dict[str, dict]):
        # Карта: doc_type -> compiled_payload (уже распарсенный JSON)
        self._data = instruction_versions

    def get_instruction_data(self, doc_type: str) -> Optional[dict]:
        return self._data.get(doc_type)


class DocTypeCheckLoader:
    """
    Загружает специфические проверки через внедренный провайдер.
    """

    MAX_CHECKS = getattr(settings, "DOC_TYPE_MAX_CHECKS_PER_DOC", 1000)

    def __init__(self, provider: Optional[InstructionProvider] = None) -> None:
        # По умолчанию (для API/Admin) используем диск, если провайдер не передан.
        self.provider = provider or FilesystemInstructionProvider()

    def _load_yaml(self, doc_type: str) -> dict | None:
        """Делегирует загрузку провайдеру."""
        return self.provider.get_instruction_data(doc_type)
    
    # ──────────────────────────────────────────────────────────────
    # ПУБЛИЧНЫЕ МЕТОДЫ
    # ──────────────────────────────────────────────────────────────

    def load_checks_for_context(self, ctx: CheckContext) -> list[CheckDefinition]:
        """
        Загрузить checks по контексту (document или segment).
        """
        if ctx.scope == "segment":
            doc_type = ctx.segment_doc_type
        else:
            doc_type = ctx.document_type

        return self.load_checks_for_doc(
            doc_type=doc_type or "",
            applicable_triggers=sorted(ctx.triggers),
        )

    def load_checks_for_doc(
        self,
        doc_type: str,
        applicable_triggers: list[str],
    ) -> list[CheckDefinition]:
        """
        Загрузить все специфические checks для документа данного типа.

        Порядок:
          1. checks_v8        — LLM/hybrid проверки (с фильтрацией по triggers)
          2. doc_type_checks  — rules-only проверки (с фильтрацией по triggers)
          3. compliance_rules — compliance-проверки (если все required_triggers сработали)

        Результат ограничен MAX_CHECKS.
        """
        if not doc_type:
            return []

        yaml_data = self._load_yaml(doc_type)
        if not yaml_data:
            return []

        shared_patterns = yaml_data.get("shared_patterns") or {}
        trigger_set = set(applicable_triggers)

        result: list[CheckDefinition] = []

        # 1. checks_v8 (LLM/hybrid/rules)
        for item in yaml_data.get("checks_v8") or []:
            if not isinstance(item, dict):
                continue
            if not self._trigger_matches(item, trigger_set):
                logger.debug(
                    "DocTypeCheckLoader: skipping checks_v8 item (trigger not matched)",
                    extra={
                        "check_id": item.get("id"),
                        "doc_type": doc_type,
                        "required": item.get("triggers"),
                        "available": list(trigger_set),
                    },
                )
                continue
            check = self._build_check_from_v8(item, doc_type, shared_patterns)
            if check:
                result.append(check)

        # 2. doc_type_checks (rules-only)
        for item in yaml_data.get("doc_type_checks") or []:
            if not isinstance(item, dict):
                continue
            if not self._trigger_matches(item, trigger_set):
                continue
            check = self._build_check_from_doc_type(item, doc_type, shared_patterns)
            if check:
                result.append(check)

        # 3. compliance_rules (rules-only)
        for rule in yaml_data.get("compliance_rules") or []:
            if not isinstance(rule, dict):
                continue
            required = rule.get("required_triggers") or []
            if required and all(t in trigger_set for t in required):
                check = self._build_compliance_check(rule, doc_type)
                if check:
                    result.append(check)
            elif required:
                logger.debug(
                    "DocTypeCheckLoader: compliance rule skipped (not all triggers matched)",
                    extra={
                        "rule_id": rule.get("id"),
                        "required": required,
                        "available": list(trigger_set),
                    },
                )

        if len(result) > self.MAX_CHECKS:
            logger.warning(
                "DocTypeCheckLoader: too many doc-type checks, truncating",
                extra={
                    "doc_type": doc_type,
                    "total": len(result),
                    "max": self.MAX_CHECKS,
                },
            )
            result = result[: self.MAX_CHECKS]

        logger.info(
            "DocTypeCheckLoader: loaded doc-type checks",
            extra={
                "doc_type": doc_type,
                "count": len(result),
                "triggers": list(trigger_set),
            },
        )
        return result

    def load_all_checks_for_doc(
        self,
        doc_type: str,
    ) -> list[CheckDefinition]:
        """
        Загрузить ВСЕ CheckDefinition для doc_type без фильтрации по triggers.

        Отличие от load_checks_for_doc:
          - load_checks_for_doc: возвращает только checks, применимые при
            заданном наборе сработавших triggers (runtime-фильтр).
          - load_all_checks_for_doc: полный список определений для doc_type
            независимо от triggers.

        Использование:
          Когда downstream-код (например build_dd_requests) матчит
          check_results по check_id, ему нужны ПОЛНЫЕ определения. Runtime
          trigger-фильтр уже сработал на этапе executor: check_result
          существует только для triggered checks.

        Контракт:
          - trigger-фильтр НЕ применяется.
          - MAX_CHECKS НЕ применяется (нужны все definitions).
          - Возвращает [] при отсутствии doc_type / yaml_data.
          - Никогда не бросает: _build_* методы сами возвращают None при ошибке.
        """
        if not doc_type:
            return []

        yaml_data = self._load_yaml(doc_type)
        if not yaml_data:
            return []

        shared_patterns = yaml_data.get("shared_patterns") or {}
        result: list[CheckDefinition] = []

        for item in yaml_data.get("checks_v8") or []:
            if not isinstance(item, dict):
                continue
            check = self._build_check_from_v8(item, doc_type, shared_patterns)
            if check:
                result.append(check)

        for item in yaml_data.get("doc_type_checks") or []:
            if not isinstance(item, dict):
                continue
            check = self._build_check_from_doc_type(item, doc_type, shared_patterns)
            if check:
                result.append(check)

        for rule in yaml_data.get("compliance_rules") or []:
            if not isinstance(rule, dict):
                continue
            check = self._build_compliance_check(rule, doc_type)
            if check:
                result.append(check)

        logger.info(
            "DocTypeCheckLoader: loaded all doc-type checks (unfiltered)",
            extra={
                "doc_type": doc_type,
                "count": len(result),
            },
        )
        return result

    # ──────────────────────────────────────────────────────────────
    # ВНУТРЕННИЕ МЕТОДЫ
    # ──────────────────────────────────────────────────────────────



    def _trigger_matches(self, item: dict, trigger_set: set[str]) -> bool:
        """
        Проверить, подходит ли check для данного набора триггеров.
        """
        triggers_cfg = item.get("triggers")
        if not triggers_cfg:
            return True

        any_triggers = triggers_cfg.get("any") or []
        all_triggers = triggers_cfg.get("all") or []

        if any_triggers and not any(t in trigger_set for t in any_triggers):
            return False
        if all_triggers and not all(t in trigger_set for t in all_triggers):
            return False

        return True

    def _resolve_patterns(self, patterns: list[str], shared: dict) -> list[str]:
        """
        Резолвит шаблонные ссылки вида {{ shared_patterns.name }} или {{ name }}.
        """
        template_re = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")
        resolved: list[str] = []

        for p in patterns:
            p_str = str(p).strip()
            m = template_re.match(p_str)
            if m:
                key_path = m.group(1).split(".")
                key = key_path[-1]
                value = shared.get(key, p_str)
                resolved.append(value)
            else:
                resolved.append(p_str)

        return resolved

    def _build_rules_config(
        self,
        rules_raw: dict,
        shared_patterns: dict,
    ) -> RulesConfig:
        """
        Построить RulesConfig из сырого dict блока rules.
        """
        raw_keywords = rules_raw.get("keywords")

        if isinstance(raw_keywords, dict):
            keyword_groups = raw_keywords
            flat_keywords: list[str] = []
        else:
            flat_keywords = raw_keywords or []
            keyword_groups = rules_raw.get("keyword_groups") or {}

        regex_patterns = self._resolve_patterns(
            rules_raw.get("regex_patterns") or [], shared_patterns
        )

        has_flat_keywords = bool(flat_keywords)
        has_grouped_keywords = (
            any(isinstance(v, list) and len(v) > 0 for v in keyword_groups.values())
            if keyword_groups
            else False
        )
        has_regex = bool(regex_patterns)
        has_clause = bool(rules_raw.get("clause_patterns"))

        if not has_flat_keywords and not has_grouped_keywords and not has_regex and not has_clause:
            logger.warning(
                "DocTypeCheckLoader: RulesConfig has no keywords, keyword_groups, "
                "regex_patterns or clause_patterns — rules scoring will be skipped entirely.",
                extra={"rules_id": rules_raw.get("id", "<unknown>")},
            )
        elif isinstance(raw_keywords, dict) and not has_grouped_keywords:
            logger.warning(
                "DocTypeCheckLoader: keyword_groups dict is present but all levels are empty.",
                extra={
                    "rules_id": rules_raw.get("id", "<unknown>"),
                    "keyword_groups_keys": list(keyword_groups.keys()),
                },
            )

        return RulesConfig(
            keywords=flat_keywords,
            keyword_mode=rules_raw.get("keyword_mode", "any"),
            regex_patterns=regex_patterns,
            clause_patterns=rules_raw.get("clause_patterns") or [],
            negative_keywords=rules_raw.get("negative_keywords") or [],
            keyword_groups=keyword_groups,
        )

    def _parse_enrichment_hints(
        self,
        hints_raw: dict | None,
    ) -> EnrichmentHints | None:
        """
        Конвертировать блок enrichment_hints из YAML в EnrichmentHints.

        Поддерживаемые поля:
          preferred_segment_types:               list[str]
          excluded_segment_types:                list[str]
          preferred_clause_functions:            list[str]
          confidence_bonus_on_match:             float 0.0-1.0
          confidence_penalty_on_excluded_segment: float 0.0-1.0

        Пример в YAML check:
          enrichment_hints:
            preferred_clause_functions:
              - "obligations"
              - "procedures"
            confidence_bonus_on_match: 0.10

        Влияние в runtime:
          executor применяет confidence_bonus_on_match когда
          clause_functions сегмента пересекаются с preferred_clause_functions.

        Возвращает None при любой ошибке — не блокирует загрузку check.
        """
        if not hints_raw or not isinstance(hints_raw, dict):
            return None

        try:
            return EnrichmentHints(
                preferred_segment_types=hints_raw.get("preferred_segment_types") or [],
                excluded_segment_types=hints_raw.get("excluded_segment_types") or [],
                preferred_clause_functions=hints_raw.get("preferred_clause_functions") or [],
                confidence_bonus_on_match=float(
                    hints_raw.get("confidence_bonus_on_match", 0.0)
                ),
                confidence_penalty_on_excluded_segment=float(
                    hints_raw.get("confidence_penalty_on_excluded_segment", 0.0)
                ),
            )
        except Exception as e:
            logger.warning(
                "DocTypeCheckLoader: cannot parse enrichment_hints, skipping",
                extra={
                    "error": str(e),
                    "hints_raw": str(hints_raw)[:200],
                },
            )
            return None

    def _parse_extraction(self, extraction_cfg: dict | None) -> ExtractionConfig | None:
        """
        Конвертировать блок extraction из YAML в ExtractionConfig.
        """
        if not extraction_cfg or not extraction_cfg.get("enabled"):
            return None

        mode_str = extraction_cfg.get("mode", "rules")
        try:
            mode = ExtractionMode(mode_str)
        except ValueError:
            mode = ExtractionMode.RULES

        fields: list[ExtractionFieldConfig] = []
        for f in extraction_cfg.get("fields") or []:
            if not isinstance(f, dict):
                continue

            field_name = f.get("name")
            if not field_name:
                continue

            type_str = f.get("type", "string")
            try:
                field_type = ExtractionFieldType(type_str)
            except ValueError:
                field_type = ExtractionFieldType.STRING

            # fallback_texts: явный YAML override > автопарсинг description.
            _explicit_fallbacks = f.get("fallback_texts")
            if _explicit_fallbacks is None:
                _fallback_texts = _extract_fallback_texts_from_description(
                    f.get("description")
                )
            else:
                _fallback_texts = (
                    list(_explicit_fallbacks) if _explicit_fallbacks else []
                )

            fields.append(
                ExtractionFieldConfig(
                    name=field_name,
                    type=field_type,
                    label=f.get("label"),
                    label_en=f.get("label_en"),
                    fallback_texts=_fallback_texts,
                    presentation=f.get("presentation", "fact"),
                    display_in_grid=bool(f.get("display_in_grid", False)),
                    display_priority=f.get("display_priority"),
                    risk_weight=f.get("risk_weight"),
                    description=f.get("description", ""),
                    regex_patterns=f.get("regex_patterns") or [],
                    keyword_hints=f.get("keyword_hints") or [],
                    allowed_values=f.get("allowed_values") or [],
                    unit=f.get("unit"),
                    required=f.get("required", False),
                    max_value_chars=f.get("max_value_chars"),
                    # DD Grid V1: semantic role of the field.
                    # "subgroup_metadata" — поле является метаданными (evidence, reason),
                    # не показывается как отдельная колонка в grid.
                    # None = обычное extraction-поле (default).
                    role=f.get("role"),
                )
            )

        if not fields:
            return None

        # compact_output: читаем как tri-state (None / True / False).
        # Если в YAML поле отсутствует — передаём None (авто-режим).
        # Авто-режим: custom prompt → без footer; fallback → с footer.
        # Явный True/False из YAML имеет приоритет над авто-режимом.
        _raw_compact = extraction_cfg.get("compact_output")
        if _raw_compact is None:
            _compact_output: bool | None = None      # авто-режим
        else:
            _compact_output = bool(_raw_compact)     # явный override из YAML

        return ExtractionConfig(
            enabled=True,
            mode=mode,
            fields=fields,
            store_payload=extraction_cfg.get("store_payload", True),
            llm_prompt_extraction=extraction_cfg.get("llm_prompt_extraction"),
            llm_max_tokens=extraction_cfg.get("llm_max_tokens"),
            compact_output=_compact_output,
            # DD Grid V1: явный маппинг колонок.
            # Raw list[dict] из YAML; Pydantic парсит в list[DDGridColumnSpec].
            # None если не задано — автомаппинг в DDGridColumnBuilder (V1.6).
            dd_grid_columns=extraction_cfg.get("dd_grid_columns"),
            presence_signal=extraction_cfg.get("presence_signal"),
        )

    def _parse_conditional(self, triggers_cfg: dict | None) -> ConditionalConfig | None:
        """
        Конвертировать блок triggers из YAML в ConditionalConfig.
        """
        if not triggers_cfg:
            return None

        any_triggers = triggers_cfg.get("any") or []
        if not any_triggers:
            return None

        if len(any_triggers) == 1:
            return ConditionalConfig(trigger=any_triggers[0])

        return ConditionalConfig(
            triggers=[TriggerCondition(name=t, state="on") for t in any_triggers]
        )


    def _parse_retrieval_config(
        self,
        retrieval_raw: dict | None,
    ) -> RetrievalConfig:
        """
        Parse retrieval block from YAML into RetrievalConfig.

        Maps all RetrievalConfig fields supported by the runtime model.
        This is the single authoritative parser for retrieval config across:
        - checks_v8
        - doc_type_checks
        - compliance_rules

        Failure-isolated:
        - malformed or partial YAML -> log warning -> fall back to defaults
        """
        if not retrieval_raw or not isinstance(retrieval_raw, dict):
            return RetrievalConfig()

        try:
            raw_corpus_scope = retrieval_raw.get("corpus_scope", "primary_segment")
            try:
                corpus_scope = RetrievalCorpusScope(raw_corpus_scope)
            except ValueError:
                logger.warning(
                    "DocTypeCheckLoader: unknown corpus_scope value, using default",
                    extra={
                        "corpus_scope_raw": raw_corpus_scope,
                    },
                )
                corpus_scope = RetrievalCorpusScope.PRIMARY_SEGMENT

            return RetrievalConfig(
                context_k=retrieval_raw.get("context_k", 5),
                max_chunks=retrieval_raw.get("max_chunks"),
                retrieval_query=retrieval_raw.get("retrieval_query"),
                boost_keywords=retrieval_raw.get("boost_keywords") or [],
                negative_keywords=retrieval_raw.get("negative_keywords") or [],
                preferred_unit_types=retrieval_raw.get("preferred_unit_types") or [],
                excluded_unit_types=retrieval_raw.get("excluded_unit_types") or [],
                preferred_clause_functions=(
                    retrieval_raw.get("preferred_clause_functions") or []
                ),
                position_bias=retrieval_raw.get("position_bias"),
                rerank=retrieval_raw.get("rerank", True),
                filters=retrieval_raw.get("filters") or {},
                levels=retrieval_raw.get("levels") or ["legal_unit", "section"],
                required_kind=retrieval_raw.get("required_kind"),
                retrieval_profile=retrieval_raw.get("retrieval_profile"),
                corpus_scope=corpus_scope,
            )
        except Exception as e:
            logger.warning(
                "DocTypeCheckLoader: cannot parse retrieval config, using defaults",
                extra={
                    "error": str(e),
                    "retrieval_raw": str(retrieval_raw)[:500],
                },
            )
            return RetrievalConfig()


    def _build_check_from_v8(
        self,
        item: dict,
        doc_type: str,
        shared_patterns: dict,
    ) -> CheckDefinition | None:
        """
        Конвертировать элемент checks_v8 из YAML в CheckDefinition.
        """
        check_id = item.get("id")
        if not check_id:
            logger.warning(
                "DocTypeCheckLoader: checks_v8 item has no id, skipping",
                extra={"doc_type": doc_type},
            )
            return None

        try:
            rules = self._build_rules_config(
                item.get("rules") or {},
                shared_patterns,
            )

            llm_raw = item.get("llm") or {}
            llm = LLMConfig(
                prompt_template=llm_raw.get("prompt_template", ""),
                prompt_file=llm_raw.get("prompt_file"),
                context_k=llm_raw.get("context_k", 5),
                temperature=llm_raw.get("temperature", 0.0),
                max_tokens=llm_raw.get("max_tokens", 512),
            )

            retrieval = self._parse_retrieval_config(item.get("retrieval"))

            ev_raw = item.get("evidence") or {}
            evidence = EvidenceConfig(
                required=ev_raw.get("required", True),
                min_snippet_length=ev_raw.get("min_snippet_length", 20),
                max_snippet_length=ev_raw.get("max_snippet_length", 500),
            )

            extraction = self._parse_extraction(item.get("extraction"))
            conditional = self._parse_conditional(item.get("triggers"))

            # Читаем enrichment_hints из YAML.
            # Влияет на confidence через executor:
            # если clause_functions сегмента пересекаются с preferred_clause_functions,
            # к confidence добавляется confidence_bonus_on_match.
            enrichment_hints = self._parse_enrichment_hints(
                item.get("enrichment_hints")
            )

            dtype_str = item.get("detector_type", "rules")
            try:
                detector_type = DetectorType(dtype_str)
            except ValueError:
                detector_type = DetectorType.RULES

            if detector_type == DetectorType.RULES:
                if (
                    not rules.keywords
                    and not rules.regex_patterns
                    and not rules.clause_patterns
                    and not rules.keyword_groups
                ):
                    logger.warning(
                        "DocTypeCheckLoader: rules-only checks_v8 item has empty rules "
                        "(no keywords/keyword_groups/regex_patterns/clause_patterns), skipping",
                        extra={
                            "check_id": check_id,
                            "doc_type": doc_type,
                        },
                    )
                    return None

            return CheckDefinition(
                id=check_id,
                name=item.get("name", check_id),
                description=item.get("description", ""),
                doc_types=[doc_type],
                origin=item.get("origin", "DOCUMENT_TYPE"),
                ui_mode=item.get("ui_mode"),
                # DD Grid V1: display_order for stable sorting within type/group.
                display_order=item.get("display_order", 0),
                severity=item.get("severity", "medium"),
                severity_if_fail=item.get("severity_if_fail"),
                severity_if_pass=item.get("severity_if_pass"),
                severity_if_unclear=item.get("severity_if_unclear"),
                detector_type=detector_type,
                rules=rules,
                llm=llm,
                retrieval=retrieval,
                evidence=evidence,
                extraction=extraction,
                conditional=conditional,
                enrichment_hints=enrichment_hints,
            )

        except (ValidationError, Exception) as e:
            logger.warning(
                "DocTypeCheckLoader: cannot build check from checks_v8",
                extra={
                    "check_id": check_id,
                    "doc_type": doc_type,
                    "error": str(e),
                },
            )
            return None

    def _build_check_from_doc_type(
        self,
        item: dict,
        doc_type: str,
        shared_patterns: dict,
    ) -> CheckDefinition | None:
        """
        Конвертировать элемент doc_type_checks из YAML в CheckDefinition.
        Эти проверки — rules-only (без LLM), быстрые.
        """
        check_id = item.get("id")
        if not check_id:
            return None

        try:
            rules_raw = item.get("rules") or {}
            rules = self._build_rules_config(rules_raw, shared_patterns)

            if (
                not rules.keywords
                and not rules.regex_patterns
                and not rules.clause_patterns
                and not rules.keyword_groups
            ):
                logger.warning(
                    "DocTypeCheckLoader: rules-only doc_type_check has empty rules "
                    "(no keywords/keyword_groups/regex_patterns/clause_patterns), skipping",
                    extra={
                        "check_id": check_id,
                        "doc_type": doc_type,
                    },
                )
                return None

            raw_keywords = rules_raw.get("keywords")
            if isinstance(raw_keywords, dict):
                all_kw: list[str] = []
                for lvl_kws in raw_keywords.values():
                    if isinstance(lvl_kws, list):
                        all_kw.extend(lvl_kws)
                boost_kw = all_kw[:5]
            else:
                boost_kw = (raw_keywords or [])[:5]

            extraction = self._parse_extraction(item.get("extraction"))
            conditional = self._parse_conditional(item.get("triggers") or {})

            return CheckDefinition(
                id=check_id,
                name=item.get("name", check_id),
                description=item.get("legal_base", item.get("description", "")),
                doc_types=[doc_type],
                origin=item.get("origin", "DOCUMENT_TYPE"),
                ui_mode=item.get("ui_mode"),
                # DD Grid V1: display_order for stable sorting within type/group.
                display_order=item.get("display_order", 0),
                severity=item.get("severity", "medium"),
                severity_if_fail=item.get("severity_if_fail"),
                severity_if_pass=item.get("severity_if_pass"),
                severity_if_unclear=item.get("severity_if_unclear"),
                detector_type=DetectorType.RULES,
                rules=rules,
                llm=LLMConfig(),
                retrieval=(
                    self._parse_retrieval_config(item.get("retrieval"))
                    if item.get("retrieval")
                    else RetrievalConfig(boost_keywords=boost_kw)
                ),
                evidence=EvidenceConfig(required=True),
                extraction=extraction,
                conditional=conditional,
            )

        except Exception as e:
            logger.warning(
                "DocTypeCheckLoader: cannot build check from doc_type_checks",
                extra={
                    "check_id": check_id,
                    "doc_type": doc_type,
                    "error": str(e),
                },
            )
            return None

    def _build_compliance_check(
        self,
        rule: dict,
        doc_type: str,
    ) -> CheckDefinition | None:
        """
        Конвертировать элемент compliance_rules в CheckDefinition.
        """
        rule_id = rule.get("id")
        if not rule_id:
            return None

        try:
            rules = self._build_rules_config(rule.get("rules") or {}, {})

            if (
                not rules.keywords
                and not rules.regex_patterns
                and not rules.clause_patterns
                and not rules.keyword_groups
            ):
                logger.warning(
                    "DocTypeCheckLoader: compliance rule has empty rules "
                    "(no keywords/keyword_groups/regex_patterns/clause_patterns), skipping",
                    extra={
                        "rule_id": rule_id,
                        "doc_type": doc_type,
                    },
                )
                return None

            retrieval = self._parse_retrieval_config(rule.get("retrieval"))

            return CheckDefinition(
                id=rule_id,
                name=rule.get("name", rule_id),
                description=rule.get("description", rule.get("legal_base", "")),
                doc_types=[doc_type],
                origin="DOCUMENT_TYPE",
                ui_mode=rule.get("ui_mode"),
                severity=rule.get("severity", "critical"),
                severity_if_fail=rule.get("severity_if_fail"),
                severity_if_pass=rule.get("severity_if_pass"),
                severity_if_unclear=rule.get("severity_if_unclear"),
                detector_type=DetectorType.RULES,
                rules=rules,
                llm=LLMConfig(),
                retrieval=retrieval,
                evidence=EvidenceConfig(required=True),
            )

        except Exception as e:
            logger.warning(
                "DocTypeCheckLoader: cannot build compliance check",
                extra={
                    "rule_id": rule_id,
                    "doc_type": doc_type,
                    "error": str(e),
                },
            )
            return None
