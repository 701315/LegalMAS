# src/api/endpoints/admin.py

"""
Админ-эндпоинты.

- GET /admin/yaml-instructions — список YAML-инструкций для типов документов
"""

from pathlib import Path

import yaml
from fastapi import APIRouter

from core.config import settings
from ..schemas.admin import YamlInstructionDTO

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get(
    "/yaml-instructions",
    summary="Список YAML-инструкций по типам документов",
    response_model=list[YamlInstructionDTO],
)
async def list_yaml_instructions() -> list[YamlInstructionDTO]:
    """
    Перечисляет файлы playbooks/document_types/*.yaml
    и собирает по каждому краткие метаданные:

    - doc_type: имя типа (из YAML или из имени файла);
    - checks_count: количество проверок (checks);
    - triggers_count: количество conditional_triggers;
    - dd_request_templates_count: количество dd_request_templates;
    - has_structured_extraction: есть ли правила structured extraction;
    - profiles: список профилей, если указаны в YAML;
    - error: текст ошибки, если файл не удалось прочитать/распарсить.
    """
    base_dir = Path(settings.PLAYBOOK_DOCUMENT_TYPES_DIR)
    if not base_dir.exists():
        return []

    items: list[YamlInstructionDTO] = []

    for path in sorted(base_dir.glob("*.yaml")):
        try:
            with path.open(encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception as e:
            # Если файл битый — возвращаем запись с ошибкой
            items.append(
                YamlInstructionDTO(
                    doc_type=path.stem,
                    filename=path.name,
                    checks_count=0,
                    triggers_count=0,
                    dd_request_templates_count=0,
                    has_structured_extraction=False,
                    profiles=None,
                    error=str(e),
                )
            )
            continue

        doc_type = data.get("doc_type") or path.stem

        checks = data.get("checks") or []
        triggers = data.get("conditional_triggers") or []
        dd_templates = data.get("dd_request_templates") or []
        profiles = data.get("profiles") or []

        # Эвристика: считаем, что есть structured extraction, если
        # в каком-то check есть structured_data / extract / fields.
        has_structured = False
        for ch in checks:
            if not isinstance(ch, dict):
                continue
            if ch.get("structured_data") or ch.get("extract") or ch.get("fields"):
                has_structured = True
                break

        items.append(
            YamlInstructionDTO(
                doc_type=doc_type,
                filename=path.name,
                checks_count=len(checks),
                triggers_count=len(triggers),
                dd_request_templates_count=len(dd_templates),
                has_structured_extraction=has_structured,
                profiles=profiles or None,
                error=None,
            )
        )

    return items
