# src/api/schemas/admin.py

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
