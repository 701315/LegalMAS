"""
playbook_converter.py

Назначение файла
----------------
Этот модуль отвечает за преобразование YAML-плейбука в внутренние
питоновские объекты CheckDefinition, с которыми дальше работает движок.

В контексте Stage 8 он решает две задачи:

1. Загрузка секции checks_v8 из YAML
   - читает блок `checks_v8` из playbook-файла (contract_*.yaml);
   - для каждого элемента создаёт объект CheckDefinition.

2. Инициализация вложенных конфигураций
   - разбирает и валидирует вложенные структуры:
     * extraction → ExtractionConfig;
     * conditional → ConditionalConfig (с триггерами и условиями по structured_data);
   - гарантирует, что ошибки в формате YAML ловятся при загрузке,
     а не в момент исполнения проверок.

Где используется
----------------
- Используется загрузчиком плейбуков при старте системы или при обновлении
  инструкций для конкретного типа договора.
- Результат работы — список CheckDefinition из checks_v8 — передаётся
  в Runner/CheckExecutor для выполнения Stage 8 проверок.
"""

from typing import Any, Dict, List

import yaml

from src.engine.playbook.models import (
    CheckDefinition,
    ConditionalConfig,
    ExtractionConfig,
)


class PlaybookConverter:
    """
    Конвертер YAML-плейбука в список CheckDefinition для секции checks_v8.

    Остальные секции playbook'а (старые checks, essential_elements и т.п.)
    могут продолжать обрабатываться по существующей логике в других частях кода.
    """

    def __init__(self) -> None:
        ...

    def load_yaml(self, path: str) -> Dict[str, Any]:
        """
        Прочитать YAML-файл playbook'а с диска и вернуть его как dict.
        """
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def convert_checks_v8(self, raw_playbook: Dict[str, Any]) -> List[CheckDefinition]:
        """
        Читает секцию checks_v8 из сырого YAML-словари и возвращает
        список CheckDefinition, готовых к передаче в Runner.

        Если секция checks_v8 отсутствует или пуста, вернёт пустой список.
        """
        raw_checks = raw_playbook.get("checks_v8") or []
        check_definitions: List[CheckDefinition] = []

        for raw_check in raw_checks:
            check_definitions.append(self._build_check_definition_from_yaml(raw_check))

        return check_definitions

    def _build_check_definition_from_yaml(self, raw_check: Dict[str, Any]) -> CheckDefinition:
        """
        Конвертация одного YAML-узла checks_v8[*] в CheckDefinition.

        Здесь мы:
        - проверяем наличие обязательного поля id;
        - отдельно валидируем nested-конфиги extraction и conditional;
        - подставляем разумные значения по умолчанию для базовых полей.
        """
        if "id" not in raw_check:
            raise ValueError("Каждый checks_v8[*] должен содержать поле 'id'")

        # Отдельно разбираем nested-модели, чтобы дать более понятные ошибки
        extraction_raw = raw_check.get("extraction")
        conditional_raw = raw_check.get("conditional")

        extraction_cfg = None
        if extraction_raw is not None:
            extraction_cfg = ExtractionConfig.model_validate(extraction_raw)

        conditional_cfg = None
        if conditional_raw is not None:
            conditional_cfg = ConditionalConfig.model_validate(conditional_raw)

        return CheckDefinition(
            id=raw_check["id"],
            name=raw_check.get("name", ""),
            description=raw_check.get("description", ""),
            doc_types=raw_check.get("doc_types") or [],
            severity=raw_check.get("severity", "medium"),
            severity_if_fail=raw_check.get("severity_if_fail"),
            severity_if_pass=raw_check.get("severity_if_pass"),
            severity_if_unclear=raw_check.get("severity_if_unclear"),
            # detector_type / rules / llm / evidence / retrieval можно
            # оставить по умолчанию, если в checks_v8 они не задаются:
            detector_type=raw_check.get("detector_type") or None or CheckDefinition.model_fields["detector_type"].default,
            rules=raw_check.get("rules") or CheckDefinition.model_fields["rules"].default_factory(),
            llm=raw_check.get("llm") or CheckDefinition.model_fields["llm"].default_factory(),
            evidence=raw_check.get("evidence") or CheckDefinition.model_fields["evidence"].default_factory(),
            retrieval=raw_check.get("retrieval") or CheckDefinition.model_fields["retrieval"].default_factory(),
            conditional=conditional_cfg,
            extraction=extraction_cfg,
        )
