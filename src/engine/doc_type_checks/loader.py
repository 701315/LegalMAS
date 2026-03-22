# src/engine/doc_type_checks/loader.py

from __future__ import annotations

"""
DocTypeCheckLoader — загружает специфические checks из YAML-инструкции типа документа.

Читает блоки из YAML:
  1. checks_v8        — прямые LLM/hybrid проверки с полной конфигурацией
  2. doc_type_checks  — rules-only проверки (авто-конвертируемые)
  3. compliance_rules — критические compliance-проверки по комбинации триггеров

Не читает: classification_runtime_v1, trigger_definitions (они обрабатываются отдельно).

Возвращает список CheckDefinition, совместимых с CheckExecutor.
"""

import re
from pathlib import Path
from typing import Any

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

logger = get_logger(__name__)


class DocTypeCheckLoader:
    """
    Загружает специфические проверки из YAML-файла типа документа.

    Архитектура:
    - Горячая загрузка: YAML читается при каждом вызове (нет долгосрочного кэша).
      Это позволяет обновлять YAML-файлы без перезапуска сервера.
    - Изоляция ошибок: ошибка в одном check не ломает остальные.
    - Лимит: не более MAX_CHECKS checks на документ.

    Использование в CheckRunner:

        loader = DocTypeCheckLoader()
        doc_type_checks = loader.load_checks_for_doc(
            doc_type="contract_1.6_real_estate",
            applicable_triggers=["land_plot_sale", "individual_party"],
        )
        all_checks = global_checks + doc_type_checks
    """

    # Максимум doc-type checks на документ (защита от взрыва LLM-вызовов)
    MAX_CHECKS = getattr(settings, "DOC_TYPE_MAX_CHECKS_PER_DOC", 30)

    def __init__(self, registry_dir: str | None = None) -> None:
        # Папка, где лежат YAML типов документов (обычно playbooks/document_types)
        self._dir = Path(registry_dir or settings.CLASSIFIER_REGISTRY_PATH)

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

        # Резолвим shared_patterns для подстановки в regex
        shared_patterns = yaml_data.get("shared_patterns") or {}
        trigger_set = set(applicable_triggers)

        result: list[CheckDefinition] = []

        # 1. checks_v8 (LLM/hybrid)
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

        # 2. doc_type_checks (rules-only, авто-конвертируемые)
        for item in yaml_data.get("doc_type_checks") or []:
            if not isinstance(item, dict):
                continue
            if not self._trigger_matches(item, trigger_set):
                continue
            check = self._build_check_from_doc_type(item, doc_type, shared_patterns)
            if check:
                result.append(check)

        # 3. compliance_rules (по комбинации триггеров)
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
        # 1) Прямой путь в корне
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

        # 2) Поиск по подпапкам
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
          triggers: {}                   → всегда запускать (нет ограничений)
          triggers: {any: ["t1","t2"]}   → достаточно одного триггера
          triggers: {all: ["t1","t2"]}   → нужны все перечисленные триггеры
        """
        triggers_cfg = item.get("triggers")

        # Нет секции triggers или пустой dict → запускать всегда
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
        Прямые паттерны (без {{ }}) возвращаются как есть.
        """
        template_re = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")
        resolved: list[str] = []

        for p in patterns:
            p_str = str(p).strip()
            m = template_re.match(p_str)
            if m:
                key_path = m.group(1).split(".")
                # Поддерживаем и "cadastral_number" и "shared_patterns.cadastral_number"
                key = key_path[-1]
                value = shared.get(key, p_str)
                resolved.append(value)
            else:
                resolved.append(p_str)

        return resolved

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

        # Берём первый триггер как primary (для совместимости с ConditionalConfig.trigger)
        if len(any_triggers) == 1:
            return ConditionalConfig(trigger=any_triggers[0])

        # Несколько триггеров → используем список TriggerCondition
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
            # Rules config
            rules_raw = item.get("rules") or {}
            regex_patterns = self._resolve_patterns(
                rules_raw.get("regex_patterns") or [], shared_patterns
            )
            rules = RulesConfig(
                keywords=rules_raw.get("keywords") or [],
                keyword_mode=rules_raw.get("keyword_mode", "any"),
                regex_patterns=regex_patterns,
                negative_keywords=rules_raw.get("negative_keywords") or [],
            )

            # LLM config
            llm_raw = item.get("llm") or {}
            llm = LLMConfig(
                prompt_template=llm_raw.get("prompt_template", ""),
                prompt_file=llm_raw.get("prompt_file"),
                context_k=llm_raw.get("context_k", 5),
                temperature=llm_raw.get("temperature", 0.0),
                max_tokens=llm_raw.get("max_tokens", 512),
            )

            # Retrieval config
            ret_raw = item.get("retrieval") or {}
            retrieval = RetrievalConfig(
                context_k=ret_raw.get("context_k", 5),
                max_chunks=ret_raw.get("max_chunks"),
                boost_keywords=ret_raw.get("boost_keywords") or [],
                rerank=ret_raw.get("rerank", True),
                filters=ret_raw.get("filters") or {},
            )

            # Evidence config
            ev_raw = item.get("evidence") or {}
            evidence = EvidenceConfig(
                required=ev_raw.get("required", True),
                min_snippet_length=ev_raw.get("min_snippet_length", 20),
                max_snippet_length=ev_raw.get("max_snippet_length", 500),
            )

            # Extraction config
            extraction = self._parse_extraction(item.get("extraction"))

            # Conditional (triggers)
            conditional = self._parse_conditional(item.get("triggers"))

            # DetectorType
            dtype_str = item.get("detector_type", "rules")
            try:
                detector_type = DetectorType(dtype_str)
            except ValueError:
                detector_type = DetectorType.RULES

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
            regex_patterns = self._resolve_patterns(
                rules_raw.get("regex_patterns") or [], shared_patterns
            )
            rules = RulesConfig(
                keywords=rules_raw.get("keywords") or [],
                keyword_mode=rules_raw.get("keyword_mode", "any"),
                regex_patterns=regex_patterns,
                negative_keywords=rules_raw.get("negative_keywords") or [],
            )

            # Extraction
            extraction = self._parse_extraction(item.get("extraction"))

            # Conditional (triggers)
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
                llm=LLMConfig(),  # пустой — LLM не используется
                retrieval=RetrievalConfig(
                    boost_keywords=rules_raw.get("keywords", [])[:5],
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
        Compliance-проверки всегда result="fail" если сработали (критические риски).
        """
        rule_id = rule.get("id")
        if not rule_id:
            return None

        try:
            rules_raw = rule.get("rules") or {}
            rules = RulesConfig(
                keywords=rules_raw.get("keywords") or [],
                keyword_mode=rules_raw.get("keyword_mode", "any"),
            )

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
        