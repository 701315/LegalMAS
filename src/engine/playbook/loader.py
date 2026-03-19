# src/engine/playbook/loader.py

"""
Playbook Loader.

Этот модуль отвечает за приведение playbook'ов к единому формату,
который использует движок проверок (PlaybookDefinition / CheckDefinition).

Поддерживаются два сценария загрузки:

1) Загрузка плейбука из YAML-файла на диске
   (load_playbook_from_yaml):

   - Используется только вручную: локальная отладка, тесты, скрипты миграций.
   - Читает YAML, валидирует через Pydantic-модели из engine.playbook.models
     (PlaybookDefinition / CheckDefinition).
   - В боевом пайплайне напрямую НЕ вызывается.

2) Загрузка плейбука из уже "скомпилированной" структуры
   (load_playbook_from_dict / load_playbook_from_version):

   - Исходит из того, что в PlaybookVersion.compiled_checks лежит dict,
     совместимый с core.playbooks.compiler.CompiledPlaybook:
        {
          "checks": [GlobalCheckConfig...],
          "meta": { ... PlaybookMeta ... }
        }
   - Преобразует каждый GlobalCheckConfig в CheckDefinition.
   - Поле source из GlobalCheckConfig (CheckSource) транслируется в origin
     CheckDefinition и дальше используется в DD Grid для фильтров:
        - origin == "GLOBAL_PLAYBOOK"   – риски из глобального плейбука,
        - origin == "DOCUMENT_TYPE"     – риски из инструкций по типу документа,
        - origin == "SYSTEM"            – системные / тех. проверки.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from db.models.playbook import PlaybookVersion
from core.config import settings
from core.logging import get_logger
from .models import (
    PlaybookDefinition,
    CheckDefinition,
    DetectorType,
    RulesConfig,
    LLMConfig,
    RetrievalConfig,
    ExtractionConfig,
)
from core.playbooks.compiler import GlobalCheckConfig, CheckSource

logger = get_logger(__name__)


def load_playbook_from_yaml(path: str) -> PlaybookDefinition:
    """
    Загрузить playbook из YAML-файла и провалидировать через Pydantic.

    Важно:
        Этот путь используется только вручную (локальная отладка, тесты,
        миграции). В боевом пайплайне плейбук берётся из PlaybookVersion.

    Args:
        path: Путь к YAML-файлу (абсолютный или относительный).

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
        logger.error(
            "Playbook YAML validation failed",
            path=str(yaml_path),
            error=str(e),
        )
        raise ValueError(f"Playbook validation error at '{path}': {e}") from e

    logger.info(
        "Playbook loaded",
        name=playbook.name,
        version=playbook.version,
        checks=len(playbook.checks),
        path=str(yaml_path),
    )
    return playbook


def _normalize_origin(source: str | CheckSource | None) -> str:
    """
    Нормализовать источник чека в строку для CheckDefinition.origin.

    Поддерживает:
        - Enum CheckSource (новый формат),
        - строковые значения (старые compiled_checks),
        - None (фолбэк).

    Всегда возвращает строку в верхнем регистре:
        "GLOBAL_PLAYBOOK", "DOCUMENT_TYPE" или "SYSTEM".

    Для неизвестных/пустых значений по умолчанию возвращает "GLOBAL_PLAYBOOK".
    """
    if isinstance(source, CheckSource):
        return source.value

    if isinstance(source, str) and source:
        # Поддержка старых значений вроде "global_playbook", "type_playbook"
        upper = source.upper()
        # Мягкий маппинг старых строк к новым, чтобы не ловить мусор в UI.
        if upper in ("GLOBAL_PLAYBOOK", "DOCUMENT_TYPE", "SYSTEM"):
            return upper
        if upper in ("GLOBAL", "GLOBAL_PLAYBOOKS", "GLOBAL_PLAYBOOK_V1"):
            return "GLOBAL_PLAYBOOK"
        if upper in ("DOCUMENT_TYPE_PLAYBOOK", "TYPE_PLAYBOOK"):
            return "DOCUMENT_TYPE"
        if upper in ("SYS", "TECH", "TECHNICAL"):
            return "SYSTEM"
        # Если встретили что-то экзотическое — безопасно считаем глобальным.
        return "GLOBAL_PLAYBOOK"

    # Совсем пустое значение — тоже считаем глобальным плейбуком.
    return "GLOBAL_PLAYBOOK"


def load_playbook_from_dict(raw: dict) -> PlaybookDefinition:
    """
    Загрузить playbook из уже подготовленного словаря (например, JSON из БД).

    Ожидание:
        raw совместим с схемой CompiledPlaybook из core.playbooks.compiler:

            {
              "checks": [GlobalCheckConfig...],
              "meta": { ... PlaybookMeta ... }
            }

    Логика:
        - Каждый элемент из raw["checks"] валидируется как GlobalCheckConfig.
        - Из GlobalCheckConfig собирается CheckDefinition, включая:
            * id / name / description / doc_types / severity и т.д.
            * origin – нормализованный источник (на основе cfg.source).
        - meta используется только для имени/версии плейбука и логов.
    """
    if not raw or not isinstance(raw, dict):
        raise ValueError("Empty or invalid playbook dict")

    # 1) Парсим checks как GlobalCheckConfig, чтобы взять source и прочие поля
    checks_raw = raw.get("checks") or []
    checks_cfg = [GlobalCheckConfig(**item) for item in checks_raw]

    checks: list[CheckDefinition] = []
    for cfg in checks_cfg:
        origin = _normalize_origin(getattr(cfg, "source", None))
        checks.append(
            CheckDefinition(
                id=cfg.id,
                name=cfg.name,
                description=cfg.description or "",
                doc_types=cfg.doc_types or [],
                origin=origin,
                severity=cfg.severity,
                detector_type=DetectorType(cfg.detector_type),
                rules=RulesConfig(**(cfg.rules or {})),
                llm=LLMConfig(**(cfg.llm or {})),
                retrieval=RetrievalConfig(**(cfg.retrieval or {})),
                extraction=ExtractionConfig(**(cfg.extraction or {}))
                if cfg.extraction
                else None,
            )
        )

    meta = raw.get("meta") or {}
    # Для имени плейбука используем:
    #   1) profile из config (если есть) – полезно для Debug/View;
    #   2) bundle_id – чтобы было понятно, откуда ноги растут;
    #   3) дефолт "Compiled Playbook".
    name = (
        meta.get("config", {}).get("profile")
        or meta.get("bundle_id")
        or "build_compiled_checks"
    )
    version = str(meta.get("version_schema", 1))

    playbook = PlaybookDefinition(
        name=name,
        version=version,
        description="",
        checks=checks,
    )

    logger.info(
        "Playbook loaded from dict",
        name=playbook.name,
        version=playbook.version,
        checks=len(playbook.checks),
    )
    return playbook


def load_playbook_from_version(version: PlaybookVersion) -> PlaybookDefinition:
    """
    Собрать PlaybookDefinition из PlaybookVersion.

    Ожидания:
        - В PlaybookVersion.compiled_checks лежит dict,
          совместимый с core.playbooks.compiler.CompiledPlaybook
          (см. build_compiled_checks).

    Использование:
        Это основной боевой путь: все воркеры и API, которым нужен плейбук
        для проверки документов, должны пользоваться именно этим методом.
    """
    raw = version.compiled_checks
    if not raw or not isinstance(raw, dict):
        raise ValueError(
            f"PlaybookVersion {version.id} has empty or invalid compiled_checks"
        )

    return load_playbook_from_dict(raw)
