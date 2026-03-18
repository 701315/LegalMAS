# src/engine/playbook/loader.py

"""
Playbook Loader.

Задачи:
- Загрузить playbook из YAML-файла или заранее скомпилированного JSON.
- Провалидировать структуру через Pydantic (PlaybookDefinition).
- Предоставить удобные функции:
    - load_playbook_from_yaml(path) -> PlaybookDefinition
    - load_default_playbook() -> PlaybookDefinition (из конфигурации)
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError
from db.models.playbook import PlaybookVersion
from core.config import settings
from core.logging import get_logger
from .models import PlaybookDefinition

logger = get_logger(__name__)


def load_playbook_from_yaml(path: str) -> PlaybookDefinition:
    """
    Загрузить playbook из YAML-файла и провалидировать через Pydantic.

    Args:
        path: путь к YAML-файлу (абсолютный или относительный).

    Returns:
        PlaybookDefinition.

    Raises:
        FileNotFoundError: если файл не найден.
        ValueError: если YAML пустой или некорректный по схеме.
    """
    yaml_path = Path(path)
    if not yaml_path.exists():
        raise FileNotFoundError(f"Playbook file not found: {path}")

    logger.info("Loading playbook from YAML", path=str(yaml_path))

    with yaml_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not raw or not isinstance(raw, dict):
        raise ValueError(f"Empty or invalid playbook YAML at '{path}'")

    try:
        playbook = PlaybookDefinition(**raw)
    except ValidationError as e:
        logger.error("Playbook YAML validation failed", path=str(yaml_path), error=str(e))
        raise ValueError(f"Playbook validation error at '{path}': {e}") from e

    logger.info(
        "Playbook loaded",
        name=playbook.name,
        version=playbook.version,
        checks=len(playbook.checks),
        path=str(yaml_path),
    )
    return playbook


def load_playbook_from_dict(raw: dict) -> PlaybookDefinition:
    """
    Загрузить playbook из уже подготовленного словаря (например, JSON из БД).

    Args:
        raw: dict со структурой, совместимой с PlaybookDefinition.

    Returns:
        PlaybookDefinition.

    Raises:
        ValueError: если структура некорректна.
    """
    if not raw or not isinstance(raw, dict):
        raise ValueError("Empty or invalid playbook dict")

    try:
        playbook = PlaybookDefinition(**raw)
    except ValidationError as e:
        logger.error("Playbook dict validation failed", error=str(e))
        raise ValueError(f"Playbook validation error: {e}") from e

    logger.info(
        "Playbook loaded from dict",
        name=playbook.name,
        version=playbook.version,
        checks=len(playbook.checks),
    )
    return playbook


def load_default_playbook() -> PlaybookDefinition:
    """
    Загрузить playbook по умолчанию.

    Источник берётся из настроек:
    - settings.PLAYBOOK_DEFAULT_PATH — путь к YAML-файлу,
      например: "playbooks/mandaru/v1.0/playbook.yaml".

    Если настройка не задана — используем разумный дефолт:
    - ./playbooks/mandaru/v1.0/playbook.yaml относительно корня проекта.
    """
    default_path = getattr(settings, "PLAYBOOK_DEFAULT_PATH", "") or ""

    if default_path:
        yaml_path = _resolve_relative_to_project_root(default_path)
    else:
        # Fallback: стандартный путь, если конфиг пока не задан
        yaml_path = _resolve_relative_to_project_root("playbooks/mandaru/v1.0/playbook.yaml")

    return load_playbook_from_yaml(str(yaml_path))


def _resolve_relative_to_project_root(relative_path: str) -> Path:
    """
    Разрешить путь относительно корня проекта (родителя src/).

    relative_path = "playbooks/mandaru/v1.0/playbook.yaml"
    -> <project_root>/playbooks/mandaru/v1.0/playbook.yaml
    """
    file_path = Path(__file__).resolve()
    project_root = file_path.parent.parent.parent.parent
    return (project_root / relative_path).resolve()

def load_playbook_from_version(version: PlaybookVersion) -> PlaybookDefinition:
    """
    Собрать PlaybookDefinition из PlaybookVersion.

    Ожидания:
    - в PlaybookVersion.compiled_checks лежит dict,
      совместимый с моделью PlaybookDefinition.

    Если compiled_checks пустой или None — считаем это ошибкой конфигурации.
    """
    raw = version.compiled_checks
    if not raw or not isinstance(raw, dict):
        raise ValueError(
            f"PlaybookVersion {version.id} has empty or invalid compiled_checks"
        )

    return load_playbook_from_dict(raw)