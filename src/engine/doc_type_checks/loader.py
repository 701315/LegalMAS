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
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from pydantic import ValidationError

from core.config import settings
from core.logging import get_logger
from engine.playbook.models import (
    CheckDefinition,
    ConditionalConfig,
    DetectorType,
    EvidenceConfig,
    ExtractionConfig,
    ExtractionFieldConfig,
    ExtractionFieldType,
    ExtractionMode,
    LLMConfig,
    RetrievalConfig,
    RulesConfig,
    TriggerCondition,
)

if TYPE_CHECKING:
    # Импортируем только для аннотаций, чтобы не создавать circular import.
    from engine.checks.planning.context import CheckContext

logger = get_logger(__name__)


class DocTypeCheckLoader:
    """
    Загружает специфические проверки из YAML-файла типа документа.

    Архитектура:
    - Горячая загрузка: YAML читается при каждом вызове (нет долгосрочного кэша).
      Это позволяет обновлять YAML-файлы без перезапуска сервера.
    - Изоляция ошибок: ошибка в одном check не ломает остальные.
    - Лимит: не более MAX_CHECKS checks на документ.
    """

    MAX_CHECKS = getattr(settings, "DOC_TYPE_MAX_CHECKS_PER_DOC", 1000)

    def __init__(self, registry_dir: str | None = None) -> None:
        self._dir = Path(registry_dir or settings.CLASSIFIER_REGISTRY_PATH)

    # ──────────────────────────────────────────────────────────────
    # ПУБЛИЧНЫЕ МЕТОДЫ
    # ──────────────────────────────────────────────────────────────

    def load_checks_for_context(self, ctx: "CheckContext") -> list[CheckDefinition]:
        """
        Загрузить checks по контексту (document или segment).

        Для непрофессионального программиста:
        - Если scope="document", ключом к YAML служит document_type документа.
        - Если scope="segment", ключом служит segment_doc_type сегмента.
        - В обоих случаях внутри вызывается тот же load_checks_for_doc.
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

    # ──────────────────────────────────────────────────────────────
    # ВНУТРЕННИЕ МЕТОДЫ
    # ──────────────────────────────────────────────────────────────

    def _load_yaml(self, doc_type: str) -> dict | None:
        """
        Загрузить YAML-файл для типа документа.

        Поддерживаем два варианта размещения:
          1) <registry_dir>/<doc_type>.yaml
          2) <registry_dir>/**/<doc_type>.yaml  (в любых подпапках)
        """
        direct = self._dir / f"{doc_type}.yaml"
        if direct.exists():
            try:
                with direct.open(encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                logger.warning(
                    "DocTypeCheckLoader: cannot read YAML (direct path)",
                    extra={"doc_type": doc_type, "path": str(direct), "error": str(e)},
                )
                return None

        pattern = f"**/{doc_type}.yaml"
        candidates = sorted(self._dir.glob(pattern))

        if not candidates:
            logger.debug(
                "DocTypeCheckLoader: no YAML for doc_type",
                extra={"doc_type": doc_type, "path": str(direct)},
            )
            return None

        yaml_path: Path = candidates[0]
        if len(candidates) > 1:
            logger.warning(
                "DocTypeCheckLoader: multiple YAML files for doc_type, using first",
                extra={
                    "doc_type": doc_type,
                    "selected": str(yaml_path),
                    "candidates": [str(p) for p in candidates],
                },
            )

        try:
            with yaml_path.open(encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(
                "DocTypeCheckLoader: cannot read YAML (recursive search)",
                extra={"doc_type": doc_type, "path": str(yaml_path), "error": str(e)},
            )
            return None

    def _trigger_matches(self, item: dict, trigger_set: set[str]) -> bool:
        """
        Проверить, подходит ли check для данного набора триггеров.

        Форматы triggers в YAML:
          triggers: {}                  → всегда запускать
          triggers: {any: ["t1","t2"]}  → достаточно одного триггера
          triggers: {all: ["t1","t2"]}  → нужны все
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
        Резолвит шаблонные ссылки вида {{ shared_patterns.cadastral_number }}
        или {{ cadastral_number }} в реальные regex-паттерны.
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

        Обрабатывает два формата keywords:

        Старый (flat list):
            rules:
              keywords: ["word1", "word2"]

        Новый (уровни):
            rules:
              keywords:
                high: ["(?i)governed\\s+by"]
                medium: ["jurisdiction"]
                low: ["court"]

        Также поддерживает отдельное поле keyword_groups рядом с keywords:
            rules:
              keyword_groups:
                high: [...]
                low: [...]

        Regex-паттерны из keyword_groups автоматически роутятся в
        regex_patterns через model_validator в RulesConfig.
        """
        raw_keywords = rules_raw.get("keywords")

        if isinstance(raw_keywords, dict):
            # Новый формат: keywords содержит уровни
            keyword_groups = raw_keywords
            flat_keywords: list[str] = []
        else:
            # Старый формат: keywords — плоский список
            flat_keywords = raw_keywords or []
            keyword_groups = rules_raw.get("keyword_groups") or {}

        regex_patterns = self._resolve_patterns(
            rules_raw.get("regex_patterns") or [], shared_patterns
        )

        # Мягкий guard: предупреждаем, если rules-конфиг совсем пустой.
        has_flat_keywords = bool(flat_keywords)
        has_grouped_keywords = (
            any(
                isinstance(v, list) and len(v) > 0
                for v in keyword_groups.values()
            )
            if keyword_groups
            else False
        )
        has_regex = bool(regex_patterns)
        has_clause = bool(rules_raw.get("clause_patterns"))

        if (
            not has_flat_keywords
            and not has_grouped_keywords
            and not has_regex
            and not has_clause
        ):
            logger.warning(
                "DocTypeCheckLoader: RulesConfig has no keywords, keyword_groups, "
                "regex_patterns or clause_patterns — rules scoring will be skipped entirely. "
                "If this check is rules-only, it will never trigger.",
                extra={"rules_id": rules_raw.get("id", "<unknown>")},
            )
        elif isinstance(raw_keywords, dict) and not has_grouped_keywords:
            logger.warning(
                "DocTypeCheckLoader: keyword_groups dict is present but all levels are empty "
                "— scoring will use zero keywords. Check your YAML.",
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

            fields.append(
                ExtractionFieldConfig(
                    name=field_name,
                    type=field_type,
                    description=f.get("description", ""),
                    regex_patterns=f.get("regex_patterns") or [],
                    keyword_hints=f.get("keyword_hints") or [],
                    allowed_values=f.get("allowed_values") or [],
                    unit=f.get("unit"),
                    required=f.get("required", False),
                )
            )

        if not fields:
            return None

        return ExtractionConfig(
            enabled=True,
            mode=mode,
            fields=fields,
            store_payload=extraction_cfg.get("store_payload", True),
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

            ret_raw = item.get("retrieval") or {}
            retrieval = RetrievalConfig(
                context_k=ret_raw.get("context_k", 5),
                max_chunks=ret_raw.get("max_chunks"),
                boost_keywords=ret_raw.get("boost_keywords") or [],
                rerank=ret_raw.get("rerank", True),
                filters=ret_raw.get("filters") or {},
            )

            ev_raw = item.get("evidence") or {}
            evidence = EvidenceConfig(
                required=ev_raw.get("required", True),
                min_snippet_length=ev_raw.get("min_snippet_length", 20),
                max_snippet_length=ev_raw.get("max_snippet_length", 500),
            )

            extraction = self._parse_extraction(item.get("extraction"))
            conditional = self._parse_conditional(item.get("triggers"))

            dtype_str = item.get("detector_type", "rules")
            try:
                detector_type = DetectorType(dtype_str)
            except ValueError:
                detector_type = DetectorType.RULES

            # Fix 8: rules-only checks_v8 с полностью пустым rules-конфигом не загружаем.
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
                severity=item.get("severity", "medium"),
                detector_type=detector_type,
                rules=rules,
                llm=llm,
                retrieval=retrieval,
                evidence=evidence,
                extraction=extraction,
                conditional=conditional,
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

            # Fix 8: жёсткая валидация rules-only doc_type_checks
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
                severity=item.get("severity", "medium"),
                detector_type=DetectorType.RULES,
                rules=rules,
                llm=LLMConfig(),
                retrieval=RetrievalConfig(boost_keywords=boost_kw),
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
        Compliance-проверки всегда result="fail" если сработали (критические риски).
        """
        rule_id = rule.get("id")
        if not rule_id:
            return None

        try:
            rules = self._build_rules_config(rule.get("rules") or {}, {})

            # Fix 8: жёсткая валидация rules-only compliance_rules
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

            ret_raw = rule.get("retrieval") or {}
            retrieval = RetrievalConfig(
                context_k=ret_raw.get("context_k", 5),
                boost_keywords=ret_raw.get("boost_keywords") or [],
                rerank=ret_raw.get("rerank", True),
            )

            return CheckDefinition(
                id=rule_id,
                name=rule.get("name", rule_id),
                description=rule.get("description", rule.get("legal_base", "")),
                doc_types=[doc_type],
                origin="DOCUMENT_TYPE",
                severity=rule.get("severity", "critical"),
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
        
        

        