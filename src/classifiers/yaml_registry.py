# src/classifiers/yaml_registry.py

"""
YAML Registry — loads and caches document type configurations.

Reads registry.yaml (list of types) and individual type YAML files.
Thread-safe singleton with lazy loading.

Full version with hot-reload in Stage 6.
"""

import os
import re
import threading
from typing import Optional
import glob

import yaml

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)
_lock = threading.Lock()
_instance: Optional["YAMLRegistry"] = None


class DocumentTypeConfig:
    """
    Parsed configuration for one document type.

    Для непрофессионального программиста:
    - Этот класс отвечает за то, чтобы один YAML-файл типа документа
      превратить в удобный объект для всех уровней классификации (L1–L3)
      и детектора триггеров.

    Источник данных: YAML типа (например, contract_1.6_real_estate.yaml).
    
    НОВОЕ в Sprint 3 (расширенный формат classification_runtime_v1):
    - Поддержка структурированных сигналов с явными weight, distinctiveness, context
    - Поддержка scoring параметров per-type
    - Backwards compatibility с legacy форматом строк
    """

    def __init__(self, raw: dict):
        # Полный сырой YAML-конфиг, сохраняем "как есть" на случай,
        # если где-то ещё нужны нестандартные поля.
        self.raw = raw

        # Базовые поля типа
        self.type_code = str(raw.get("type", ""))
        self.name = str(raw.get("name", ""))

        runtime = raw.get("classification_runtime_v1") or {}
        # Правила классификации: в приоритете блок classification_runtime_v1.rules
        rules = runtime.get("rules") or raw.get("rules", {}) or {}
        validation = raw.get("validation_engine_v3_2") or raw.get("validation_metadata") or {}
        self.triggerdefinitions = dict(
            runtime.get("trigger_definitions") or validation.get("trigger_definitions") or {}
        )

        # === NEW: Scoring parameters ===
        # Опциональные параметры для L2 engine, специфичные для данного типа документа
        self.scoring = runtime.get("scoring") or {}

        # === FIX P2a: filename_patterns / folder_patterns через _compile_regex_list ===
        self.filename_patterns = self._compile_regex_list(
            rules.get("filename_patterns", [])
        )
        self.folder_patterns = self._compile_regex_list(
            rules.get("folder_patterns", [])
        )

        # --- header_patterns: для L2 ---
        # 1) пытаемся взять явные header_patterns из YAML (runtime или корень)
        explicit_header = (
            runtime.get("header_patterns")
            or raw.get("header_patterns")
            or rules.get("header_patterns")
            or []
        )
        if explicit_header:
            header_source = explicit_header
        else:
            # 2) если явных нет — используем keywords.high как паттерны заголовка
            header_source = rules.get("keywords", {}).get("high", []) or []

        self.header_patterns: list = []
        for p in header_source:
            if not isinstance(p, str):
                continue
            try:
                compiled = re.compile(p.lstrip("r").strip('"').strip("'"), re.IGNORECASE)
                self.header_patterns.append(compiled)
            except re.error:
                logger.warning(
                    "Invalid header pattern in YAML",
                    extra={"type_code": self.type_code, "pattern": p},
                )

        # === UPDATED: keywords.* с поддержкой расширенного формата ===
        kw = rules.get("keywords", {}) or {}
        
        # NEW: Парсим расширенный формат для lexical_signals
        self.lexical_signals = {
            "high": self._parse_signal_list(kw.get("high", []), "high"),
            "medium": self._parse_signal_list(kw.get("medium", []), "medium"),
            "low": self._parse_signal_list(kw.get("low", []), "low"),
        }
        
        # LEGACY: сохраняем старые compiled regex для обратной совместимости
        # (на случай если где-то ещё используется keywords_high напрямую)
        self.keywords_high = self._compile_regex_list(kw.get("high", []))
        self.keywords_medium = self._compile_regex_list(kw.get("medium", []))
        self.keywords_low = self._compile_regex_list(kw.get("low", []))
        
        # === UPDATED: exclusions с поддержкой severity ===
        self.negative_signals = self._parse_negative_signals(
            rules.get("exclusions", [])
        )
        
        # LEGACY: сохраняем старые compiled regex для обратной совместимости
        self.exclusions = self._compile_regex_list(rules.get("exclusions", []))

        # НОВОЕ: "сырые" keywords/phrases для семантического уровня (L3).
        # Здесь мы не компилируем ничего в regex, а просто храним строки,
        # чтобы L3 мог собрать текстовый прототип.
        self.rules_keywords: dict[str, list[str]] = {
            "high": [str(x) if isinstance(x, str) else str(x.get("pattern", "")) 
                     for x in kw.get("high", []) or []],
            "medium": [str(x) if isinstance(x, str) else str(x.get("pattern", ""))
                       for x in kw.get("medium", []) or []],
            "low": [str(x) if isinstance(x, str) else str(x.get("pattern", ""))
                    for x in kw.get("low", []) or []],
        }

        phrases = rules.get("phrases", {}) or {}
        self.rules_phrases: dict[str, list[str]] = {
            "high": [str(x) for x in phrases.get("high", []) or []],
            "medium": [str(x) for x in phrases.get("medium", []) or []],
            "low": [str(x) for x in phrases.get("low", []) or []],
        }

        # trigger_definitions → applicable_triggers list
        # Keys of trigger_definitions become trigger IDs (используются в HybridClassifier).
        tdef = raw.get("trigger_definitions", {}) or {}
        self.trigger_ids: list = list(tdef.keys())

        # Полное описание триггеров, которое использует TriggerDetector,
        # чтобы понять, какие триггеры реально нашли подтверждение в тексте.
        self.trigger_definitions: dict = tdef

        metadata = raw.get("metadata", {}) or {}
        self.category: str = metadata.get("category", "contract")
        self.complexity: str = metadata.get("complexity", "medium")
        self.risk_level: str = metadata.get("risk_level", "medium")
        self.language: str = metadata.get("language", "ru")
        self.jurisdiction: str = metadata.get("jurisdiction", "RU")

        # НОВОЕ: семантические маркеры для L3 и checks.
        # aliases / section_markers могут использоваться как дополнительные сигналы.
        self.aliases: list[str] = list(metadata.get("aliases", []) or [])
        self.section_markers: list[str] = list(metadata.get("section_markers", []) or [])

        # essential_elements передаём наверх, чтобы L3 и checks могли
        # строить логику вокруг ключевых элементов договора.
        self.essential_elements: list[dict] = list(raw.get("essential_elements") or [])

        # NEW: party role keywords from essential_elements.parties
        self.party_role_keywords: dict[str, str] = self._build_party_role_keywords(raw)

    @staticmethod
    def _compile_regex_list(items: list) -> list[re.Pattern]:
        """
        Компилирует список строковых regex-паттернов в объекты re.Pattern.

        Для продакшн-уровня:
        - игнорируем нестроковые элементы;
        - обрезаем обрамляющие кавычки и префикс r;
        - логируем, но НЕ падаем при ошибке компиляции, чтобы
          один кривой паттерн не клал весь сервис.
        
        Для непрофессионального программиста:
        - Этот метод принимает список строк из YAML (например, keywords.high).
        - Каждую строку превращает в скомпилированный regex-паттерн.
        - Если паттерн невалидный — логируем warning и пропускаем его (не крашим приложение).
        
        UPDATED: теперь также поддерживает dict-элементы (расширенный формат),
        извлекая из них поле "pattern".
        """
        compiled: list[re.Pattern] = []
        for raw in items or []:
            # NEW: поддержка dict-элементов
            if isinstance(raw, dict):
                pattern_str = raw.get("pattern", "")
            elif isinstance(raw, str):
                pattern_str = raw
            else:
                continue
            
            # убираем возможный префикс r и внешние кавычки из YAML
            pattern_str = pattern_str.lstrip("r").strip('"').strip("'")
            if not pattern_str:
                continue
            try:
                # Внутренний (?i) и другие флаги останутся рабочими.
                compiled.append(re.compile(pattern_str))
            except re.error as e:
                logger.warning(
                    "Invalid regex in YAML keywords/exclusions",
                    extra={"pattern": raw, "error": str(e)},
                )
        return compiled

    # === NEW: Парсинг расширенного формата lexical signals ===
    def _parse_signal_list(self, items: list, group_level: str) -> list[dict]:
        """
        Парсит список сигналов из keywords.high/medium/low с поддержкой
        расширенного формата.

        Входные данные:
        - items: список элементов из YAML (могут быть строками или dict)
        - group_level: "high"/"medium"/"low" для дефолтных весов

        Возвращает:
        - список dict с полями:
          {
            "pattern": compiled re.Pattern,
            "weight": float,
            "distinctiveness": "high"|"medium"|"low",
            "context": "header"|"body"|"any",
            "description": str (optional)
          }

        Для непрофессионального программиста:
        - Если в YAML элемент — простая строка, используем дефолтные значения
        - Если элемент — dict с полями pattern/weight/distinctiveness/context,
          используем явные значения
        - Это позволяет плавно мигрировать: старые YAML работают как раньше,
          новые получают точный контроль
        """
        # Дефолтные веса по уровням (для legacy строк)
        default_weights = {
            "high": 0.5,
            "medium": 0.3,
            "low": 0.15,
        }

        signals = []
        for item in items or []:
            if isinstance(item, str):
                # Legacy формат: простая строка
                pattern_str = item.lstrip("r").strip('"').strip("'")
                if not pattern_str:
                    continue
                
                try:
                    compiled = re.compile(pattern_str, re.IGNORECASE)
                except re.error as e:
                    logger.warning(
                        "Invalid regex pattern in lexical signals",
                        extra={"pattern": item, "error": str(e)},
                    )
                    continue

                signals.append({
                    "pattern": compiled,
                    "weight": default_weights.get(group_level, 0.3),
                    "distinctiveness": "medium",  # консервативный дефолт
                    "context": "any",
                    "description": None,
                })

            elif isinstance(item, dict):
                # NEW: расширенный формат
                pattern_str = item.get("pattern", "")
                if not pattern_str:
                    continue

                pattern_str = pattern_str.lstrip("r").strip('"').strip("'")
                try:
                    compiled = re.compile(pattern_str, re.IGNORECASE)
                except re.error as e:
                    logger.warning(
                        "Invalid regex pattern in lexical signals",
                        extra={"pattern": pattern_str, "error": str(e)},
                    )
                    continue

                # Извлекаем явные значения с fallback на дефолты
                weight = float(item.get("weight", default_weights.get(group_level, 0.3)))
                distinctiveness = item.get("distinctiveness", "medium")
                context = item.get("context", "any")
                description = item.get("description")

                # Валидация enum значений
                if distinctiveness not in ("high", "medium", "low"):
                    logger.warning(
                        "Invalid distinctiveness value, using 'medium'",
                        extra={"value": distinctiveness, "pattern": pattern_str},
                    )
                    distinctiveness = "medium"

                if context not in ("header", "body", "any"):
                    logger.warning(
                        "Invalid context value, using 'any'",
                        extra={"value": context, "pattern": pattern_str},
                    )
                    context = "any"

                signals.append({
                    "pattern": compiled,
                    "weight": weight,
                    "distinctiveness": distinctiveness,
                    "context": context,
                    "description": description,
                })

        return signals

    # === NEW: Парсинг negative signals ===
    def _parse_negative_signals(self, items: list) -> list[dict]:
        """
        Парсит список exclusions с поддержкой расширенного формата.

        Входные данные:
        - items: список элементов из YAML (строки или dict)

        Возвращает:
        - список dict с полями:
          {
            "pattern": compiled re.Pattern,
            "severity": "hard"|"soft",
            "weight": float (negative),
            "description": str (optional)
          }

        Для непрофессионального программиста:
        - severity: "hard" полностью блокирует тип при совпадении
        - severity: "soft" снижает confidence, но не блокирует
        - Legacy строки интерпретируются как soft с весом -0.3
        """
        signals = []
        for item in items or []:
            if isinstance(item, str):
                # Legacy формат: простая строка → soft exclusion
                pattern_str = item.lstrip("r").strip('"').strip("'")
                if not pattern_str:
                    continue

                try:
                    compiled = re.compile(pattern_str, re.IGNORECASE)
                except re.error as e:
                    logger.warning(
                        "Invalid regex pattern in exclusions",
                        extra={"pattern": item, "error": str(e)},
                    )
                    continue

                signals.append({
                    "pattern": compiled,
                    "severity": "soft",
                    "weight": -0.3,
                    "description": None,
                })

            elif isinstance(item, dict):
                # NEW: расширенный формат
                pattern_str = item.get("pattern", "")
                if not pattern_str:
                    continue

                pattern_str = pattern_str.lstrip("r").strip('"').strip("'")
                try:
                    compiled = re.compile(pattern_str, re.IGNORECASE)
                except re.error as e:
                    logger.warning(
                        "Invalid regex pattern in exclusions",
                        extra={"pattern": pattern_str, "error": str(e)},
                    )
                    continue

                severity = item.get("severity", "soft")
                weight = float(item.get("weight", -0.3))
                description = item.get("description")

                # Валидация severity
                if severity not in ("hard", "soft"):
                    logger.warning(
                        "Invalid severity value, using 'soft'",
                        extra={"value": severity, "pattern": pattern_str},
                    )
                    severity = "soft"

                signals.append({
                    "pattern": compiled,
                    "severity": severity,
                    "weight": weight,
                    "description": description,
                })

        return signals

    @staticmethod
    def _build_party_role_keywords(raw: dict) -> dict[str, str]:
        """
        Build {keyword_lower: ROLE_ID} from essential_elements.parties.party_roles.

        Для непрофессионального программиста:
        - В YAML могут быть роли сторон (Покупатель, Продавец и т.п.) с ключевыми словами.
        - Здесь мы строим словарь, чтобы по ключевому слову быстро понять роль.
        """
        mapping: dict[str, str] = {}
        for elem in raw.get("essential_elements") or []:
            if elem.get("element") != "parties":
                continue
            for role in elem.get("party_roles", []) or []:
                role_id = role.get("id")
                if not role_id:
                    continue
                for kw in role.get("keywords", []) or []:
                    mapping[kw.lower()] = role_id
        return mapping


class YAMLRegistry:
    """
    Singleton registry of all document type configurations.

    Usage:
        registry = YAMLRegistry.get_instance()
        configs  = registry.get_all_configs()
        cfg      = registry.get_config("contract1.1spa")
    """

    def __init__(self, registry_path: str):
        self.registry_path = registry_path
        self._configs: dict = {}
        self._load()

    def _load(self):
        registry_file = os.path.join(self.registry_path, "registry.yaml")
        if not os.path.exists(registry_file):
            logger.warning(
                "YAML registry not found",
                path=registry_file,
            )
            return

        with open(registry_file, encoding="utf-8") as f:
            registry = yaml.safe_load(f)

        for entry in registry.get("document_types", []):
            type_code = entry.get("type", "")
            if not type_code:
                continue

            # 1) Прямой путь в корне (на случай, если часть файлов лежит без подпапок)
            direct = os.path.join(self.registry_path, f"{type_code}.yaml")

            yaml_path: str | None = None
            if os.path.exists(direct):
                yaml_path = direct
            else:
                # 2) Рекурсивный поиск по подпапкам, как в DocTypeCheckLoader
                pattern = os.path.join(self.registry_path, "**", f"{type_code}.yaml")
                candidates = sorted(glob.glob(pattern, recursive=True))
                if candidates:
                    yaml_path = candidates[0]

            if yaml_path is None:
                logger.warning(
                    "Type YAML not found — using minimal config from registry",
                    type_code=type_code,
                )
                self._configs[type_code] = DocumentTypeConfig(entry)
                continue

            try:
                with open(yaml_path, encoding="utf-8") as f:
                    type_raw = yaml.safe_load(f) or {}
            except Exception as e:
                logger.warning(
                    "Type YAML cannot be read — using minimal config from registry",
                    extra={"type_code": type_code, "path": yaml_path, "error": str(e)},
                )
                self._configs[type_code] = DocumentTypeConfig(entry)
                continue

            self._configs[type_code] = DocumentTypeConfig(type_raw)

        logger.info(
            "YAML registry loaded",
            total_types=len(self._configs),
        )
        logger.debug(
            "YAML registry types preview",
            sample_types=list(self._configs.keys())[:10],
        )

    # === UPDATED: validate_all_patterns() с поддержкой расширенного формата ===
    def validate_all_patterns(self) -> tuple[bool, list[dict]]:
        """
        Валидация всех regex-паттернов в загруженных конфигах.

        Returns:
            (is_valid, errors_list)
            
        UPDATED: теперь также валидирует:
        - поля weight, distinctiveness, context в lexical signals
        - поля severity, weight в negative signals
        - параметры scoring
        """
        errors = []

        for type_code, cfg in self._configs.items():
            raw = cfg.raw or {}
            runtime = raw.get("classification_runtime_v1") or {}
            rules = runtime.get("rules") or raw.get("rules", {}) or {}

            # Проверяем все поля с паттернами (legacy строки)
            pattern_fields = {
                "filename_patterns": rules.get("filename_patterns", []),
                "folder_patterns": rules.get("folder_patterns", []),
                "header_patterns": (
                    runtime.get("header_patterns")
                    or raw.get("header_patterns")
                    or rules.get("header_patterns")
                    or []
                ),
            }

            for field_name, patterns in pattern_fields.items():
                for pattern_str in patterns or []:
                    if not isinstance(pattern_str, str):
                        continue
                    clean = pattern_str.lstrip("r").strip('"').strip("'")
                    if not clean:
                        continue
                    try:
                        re.compile(clean)
                    except re.error as e:
                        errors.append(
                            {
                                "type_code": type_code,
                                "field": field_name,
                                "pattern": pattern_str,
                                "error": str(e),
                            }
                        )

            # NEW: Валидация keywords с поддержкой расширенного формата
            kw = rules.get("keywords", {}) or {}
            for level in ("high", "medium", "low"):
                for idx, item in enumerate(kw.get(level, []) or []):
                    if isinstance(item, str):
                        # Legacy строка
                        clean = item.lstrip("r").strip('"').strip("'")
                        if clean:
                            try:
                                re.compile(clean)
                            except re.error as e:
                                errors.append({
                                    "type_code": type_code,
                                    "field": f"keywords.{level}[{idx}]",
                                    "pattern": item,
                                    "error": str(e),
                                })
                    elif isinstance(item, dict):
                        # Расширенный формат
                        pattern_str = item.get("pattern", "")
                        if pattern_str:
                            clean = pattern_str.lstrip("r").strip('"').strip("'")
                            try:
                                re.compile(clean)
                            except re.error as e:
                                errors.append({
                                    "type_code": type_code,
                                    "field": f"keywords.{level}[{idx}].pattern",
                                    "pattern": pattern_str,
                                    "error": str(e),
                                })
                        
                        # Валидация enum полей
                        if "distinctiveness" in item and item["distinctiveness"] not in ("high", "medium", "low"):
                            errors.append({
                                "type_code": type_code,
                                "field": f"keywords.{level}[{idx}].distinctiveness",
                                "pattern": pattern_str,
                                "error": f"Invalid value: {item['distinctiveness']}, expected 'high'|'medium'|'low'",
                            })
                        
                        if "context" in item and item["context"] not in ("header", "body", "any"):
                            errors.append({
                                "type_code": type_code,
                                "field": f"keywords.{level}[{idx}].context",
                                "pattern": pattern_str,
                                "error": f"Invalid value: {item['context']}, expected 'header'|'body'|'any'",
                            })

            # NEW: Валидация exclusions с поддержкой severity
            for idx, item in enumerate(rules.get("exclusions", []) or []):
                if isinstance(item, str):
                    # Legacy строка
                    clean = item.lstrip("r").strip('"').strip("'")
                    if clean:
                        try:
                            re.compile(clean)
                        except re.error as e:
                            errors.append({
                                "type_code": type_code,
                                "field": f"exclusions[{idx}]",
                                "pattern": item,
                                "error": str(e),
                            })
                elif isinstance(item, dict):
                    # Расширенный формат
                    pattern_str = item.get("pattern", "")
                    if pattern_str:
                        clean = pattern_str.lstrip("r").strip('"').strip("'")
                        try:
                            re.compile(clean)
                        except re.error as e:
                            errors.append({
                                "type_code": type_code,
                                "field": f"exclusions[{idx}].pattern",
                                "pattern": pattern_str,
                                "error": str(e),
                            })
                    
                    # Валидация severity
                    if "severity" in item and item["severity"] not in ("hard", "soft"):
                        errors.append({
                            "type_code": type_code,
                            "field": f"exclusions[{idx}].severity",
                            "pattern": pattern_str,
                            "error": f"Invalid value: {item['severity']}, expected 'hard'|'soft'",
                        })

            # NEW: Валидация scoring параметров
            scoring = runtime.get("scoring", {})
            if scoring:
                for param, value in scoring.items():
                    if param in ("accept_threshold", "strong_signal_threshold", "max_confidence"):
                        if not isinstance(value, (int, float)) or not (0 < value <= 1):
                            errors.append({
                                "type_code": type_code,
                                "field": f"scoring.{param}",
                                "pattern": str(value),
                                "error": f"Expected float in range (0, 1], got {value}",
                            })
                    elif param == "ambiguity_margin":
                        if not isinstance(value, (int, float)) or not (0 <= value <= 1):
                            errors.append({
                                "type_code": type_code,
                                "field": f"scoring.{param}",
                                "pattern": str(value),
                                "error": f"Expected float in range [0, 1], got {value}",
                            })

        is_valid = len(errors) == 0

        if not is_valid:
            logger.error(
                "YAML Registry validation FAILED",
                extra={"total_errors": len(errors), "errors_sample": errors[:10]},
            )
        else:
            logger.info(
                "YAML Registry validation PASSED", total_types=len(self._configs)
            )

        return is_valid, errors

    def get_all_configs(self) -> list:
        return list(self._configs.values())

    def get_config(self, type_code: str) -> DocumentTypeConfig | None:
        return self._configs.get(type_code)

    @classmethod
    def get_instance(cls, validate: bool = True) -> "YAMLRegistry":
        """
        Получить singleton-экземпляр YAMLRegistry.
        
        Args:
            validate: если True — после загрузки вызываем validate_all_patterns()
                      и падаем с RuntimeError при наличии invalid regex-паттернов.
                      Используйте validate=True при старте приложения (fail-fast).
                      Используйте validate=False в тестах или для hot-reload.
        """
        global _instance
        if _instance is None:
            with _lock:
                if _instance is None:
                    path = getattr(
                        settings,
                        "CLASSIFIER_REGISTRY_PATH",
                        "playbooks/document_types",
                    )
                    _instance = cls(path)

                    # НОВОЕ: startup validation
                    if validate:
                        is_valid, errors = _instance.validate_all_patterns()
                        if not is_valid:
                            # Формируем понятное сообщение об ошибке с примерами
                            error_summary = "\n".join(
                                f"  • {e['type_code']}.{e['field']}: {e['pattern']!r} → {e['error']}"
                                for e in errors[:5]  # показываем первые 5 ошибок
                            )
                            total_errors = len(errors)
                            more_msg = (
                                f"\n  ... and {total_errors - 5} more errors"
                                if total_errors > 5
                                else ""
                            )
                            raise RuntimeError(
                                f"YAML Registry has {total_errors} invalid regex pattern(s):\n"
                                f"{error_summary}{more_msg}\n"
                                f"Fix YAML files before starting the service."
                            )
        return _instance

    def get_master_doc_types(self) -> list[str]:
        """
        Stage 7: Return doc_types suitable as family master documents.

        A doc_type is a master candidate if:
        - Its YAML config exists (already loaded in _configs)
        - classification.level is "L2" or "L3"
        - No "parent_doc_type" key is set (meaning it's not subordinate)
        """
        master_types: list[str] = []

        for type_code, cfg in self._configs.items():
            raw = cfg.raw or {}
            classification = raw.get("classification", {}) or {}
            level = classification.get("level", "L0")

            if level not in ("L2", "L3"):
                continue

            # subordinate if has parent_doc_type
            if raw.get("parent_doc_type"):
                continue

            master_types.append(type_code)

        logger.debug(
            "YAMLRegistry.get_master_doc_types",
            yaml_master_types=master_types,
        )
        return master_types

    def get_classification_rules(self, type_code: str) -> dict:
        """
        Получить правила классификации (ClassificationRulesSpec-подобный dict)
        для HybridClassifier / L1 / L2 / L3.

        Структура возвращаемого словаря:
            {
                "filename_patterns": list[Pattern],  # для L1 (имя файла)
                "folder_patterns":   list[Pattern],  # для L1 (путь к папке)
                "keywords_high":     list[Pattern],  # для L2/L3
                "keywords_medium":   list[Pattern],
                "keywords_low":      list[Pattern],
                "exclusions":        list[Pattern],  # для L2 (и доп. логики)
            }

        Для непрофессионального программиста:
        - это "нарезка" из DocumentTypeConfig, которую удобно подавать
          в L1FilenameClassifier, L2HeaderClassifier и L3SemanticClassifier,
          не вытаскивая весь config.raw.
        """

        config = self.get_config(type_code)
        if not config:
            return {
                "filename_patterns": [],
                "folder_patterns": [],
                "keywords_high": [],
                "keywords_medium": [],
                "keywords_low": [],
                "exclusions": [],
            }

        return {
            "filename_patterns": config.filename_patterns,
            "folder_patterns": config.folder_patterns,
            "keywords_high": config.keywords_high,
            "keywords_medium": config.keywords_medium,
            "keywords_low": config.keywords_low,
            "exclusions": config.exclusions,
        }

    def list_types(self) -> list[str]:
        """
        Вернуть список всех type_code, известных реестру.

        Используется L1/L2/L3/HybridClassifier для обхода всех типов.
        """
        return list(self._configs.keys())

    @classmethod
    def reset(cls):
        """Reset singleton — used in tests to reload registry between runs."""
        global _instance
        with _lock:
            _instance = None

            


