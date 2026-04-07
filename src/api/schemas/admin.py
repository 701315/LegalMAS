# src/api/schemas/admin.py

"""
   DTO для одной YAML-инструкции (playbook-инструкции для типа документа).

    Используется в админском API `/admin/yaml-instructions` для:
    - отображения списка загруженных YAML-файлов с инструкциями;
    - показа количества чеков, триггеров и шаблонов запросов (DD-requests)
      внутри каждой инструкции;
    - индикации наличия структурированного экстракта и профилей;
    - передачи информации об ошибке парсинга для "битых" файлов.

    Поля:
    - doc_type: логический тип документа, к которому относится инструкция;
    - filename: имя YAML-файла на диске;
    - checks_count: количество чеков в этой инструкции;
    - triggers_count: количество триггеров;
    - dd_request_templates_count: число шаблонов запросов;
    - has_structured_extraction: есть ли блок структурированного извлечения;
    - profiles: список профилей (если инструкция профилируется);
    - error: текст ошибки, если файл не удалось корректно разобрать.
"""

from typing import Any

from pydantic import BaseModel


class YamlInstructionDTO(BaseModel):
    """
    Метаданные YAML-инструкции для типа документа.

    Используется в админском API /admin/yaml-instructions.
    """
    doc_type: str
    filename: str
    checks_count: int
    triggers_count: int
    dd_request_templates_count: int
    has_structured_extraction: bool
    profiles: list[str] | None = None
    # Можно оставить поле error для "битых" файлов
    error: str | None = None
