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

Изменения (keyword_groups support):
   - load_playbook_from_dict теперь корректно обрабатывает два формата keywords:
       * Старый: rules.keywords: ["word1", "word2"]  — flat list, без изменений.
       * Новый:  rules.keywords: {high: [...], medium: [...], low: [...]}
                 или отдельное поле keyword_groups: {...}
     В обоих случаях результирующий RulesConfig получает keyword_groups,
     а model_validator в RulesConfig нормализует паттерны по нужным полям.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from core.logging import get_logger
from core.playbooks.compiler import CheckSource, GlobalCheckConfig
from db.models.playbook import PlaybookVersion

from .models import (
    CheckDefinition,
    DDGridColumnSpec,
    DetectorType,
    EnrichmentHints,
    ExtractionConfig,
    LLMConfig,
    PlaybookDefinition,
    RetrievalConfig,
    RulesConfig,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Вспомогательная функция: строим RulesConfig из сырого dict
# ---------------------------------------------------------------------------


def _build_rules_config(rules_raw: dict, extra_keyword_groups: dict | None = None) -> RulesConfig:
    """
    Собрать RulesConfig из сырого dict блока rules.

    Обрабатывает два формата keywords:

    Старый (flat list):
        rules:
          keywords: ["word1", "word2"]

    Новый (уровни, inline в rules.keywords):
        rules:
          keywords:
            high: ["(?i)governed\\s+by"]
            medium: ["jurisdiction"]
            low: ["court"]

    Также поддерживает отдельное поле keyword_groups на уровне GlobalCheckConfig
    (передаётся через extra_keyword_groups).

    Приоритет источников keyword_groups:
        1) rules.keywords (если это dict — берём его)
        2) rules.keyword_groups (вложенное поле)
        3) extra_keyword_groups (отдельное поле GlobalCheckConfig.keyword_groups)
    """
    raw_keywords = rules_raw.get("keywords")

    if isinstance(raw_keywords, dict):
        # Новый формат: keywords содержит уровни {high: [...], medium: [...], low: [...]}
        keyword_groups = raw_keywords
        flat_keywords: list[str] = []
    else:
        # Старый формат: keywords — плоский список строк
        flat_keywords = raw_keywords or []
        # keyword_groups может быть вложен в rules или передан снаружи
        keyword_groups = rules_raw.get("keyword_groups") or extra_keyword_groups or {}

    return RulesConfig(
        keywords=flat_keywords,
        keyword_mode=rules_raw.get("keyword_mode", "any"),
        regex_patterns=rules_raw.get("regex_patterns") or [],
        clause_patterns=rules_raw.get("clause_patterns") or [],
        negative_keywords=rules_raw.get("negative_keywords") or [],
        keyword_groups=keyword_groups,
    )

def _parse_dd_grid_columns(
    raw: list[dict] | None,
    *,
    check_id: str,
) -> list[DDGridColumnSpec] | None:
    """
    Разобрать raw list[dict] из compiled_checks в list[DDGridColumnSpec].

    Вызывается при загрузке GlobalCheckConfig → CheckDefinition для
    проброса явных DD Grid column specs из compiled playbook в
    ExtractionConfig.dd_grid_columns.

    Args:
        raw:      Значение поля GlobalCheckConfig.dd_grid_columns (или None).
        check_id: ID check'а — используется только для logging.

    Returns:
        list[DDGridColumnSpec] если хотя бы одна колонка валидна.
        None если raw is None, не список, или все элементы невалидны.

    Поведение при ошибках:
        - raw не список → warning, return None
        - элемент не dict → warning, skip
        - невалидный DDGridColumnSpec → warning, skip
        - все элементы невалидны → return None
    """
    if raw is None:
        return None

    if not isinstance(raw, list):
        logger.warning(
            "load_playbook_from_dict: dd_grid_columns is not a list, ignoring",
            check_id=check_id,
            type_got=type(raw).__name__,
        )
        return None

    result: list[DDGridColumnSpec] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            logger.warning(
                "load_playbook_from_dict: dd_grid_columns item is not a dict, skipping",
                check_id=check_id,
                item_index=i,
                type_got=type(item).__name__,
            )
            continue
        try:
            result.append(DDGridColumnSpec(**item))
        except Exception as exc:
            logger.warning(
                "load_playbook_from_dict: invalid DDGridColumnSpec, skipping",
                check_id=check_id,
                item_index=i,
                error=str(exc),
            )

    if not result:
        if raw:
            logger.debug(
                "load_playbook_from_dict: dd_grid_columns had items but none were valid",
                check_id=check_id,
                raw_count=len(raw),
            )
        return None

    return result


# ---------------------------------------------------------------------------
# Публичные функции загрузки
# ---------------------------------------------------------------------------


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
        upper = source.upper()
        if upper in ("GLOBAL_PLAYBOOK", "DOCUMENT_TYPE", "SYSTEM"):
            return upper
        if upper in ("GLOBAL", "GLOBAL_PLAYBOOKS", "GLOBAL_PLAYBOOK_V1"):
            return "GLOBAL_PLAYBOOK"
        if upper in ("DOCUMENT_TYPE_PLAYBOOK", "TYPE_PLAYBOOK"):
            return "DOCUMENT_TYPE"
        if upper in ("SYS", "TECH", "TECHNICAL"):
            return "SYSTEM"
        return "GLOBAL_PLAYBOOK"

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
            * rules  – через _build_rules_config() с поддержкой keyword_groups.
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

        # Строим RulesConfig с поддержкой нового формата keyword_groups.
        # extra_keyword_groups — отдельное поле GlobalCheckConfig (если задано).
        extra_keyword_groups = getattr(cfg, "keyword_groups", None) or {}
        rules = _build_rules_config(cfg.rules or {}, extra_keyword_groups)

        # Parse enrichment_hints if present in compiled check config.
        # getattr with None default: safe for configs that predate enrichment_hints.
        _raw_enrichment_hints = getattr(cfg, "enrichment_hints", None)
        _enrichment_hints: EnrichmentHints | None = None
        if isinstance(_raw_enrichment_hints, dict) and _raw_enrichment_hints:
            try:
                _enrichment_hints = EnrichmentHints(**_raw_enrichment_hints)
            except Exception:
                # Malformed hints: degrade gracefully, do not block check loading.
                _enrichment_hints = None

        # DD Grid V1: parse top-level dd_grid_columns from GlobalCheckConfig.
        # These are stored as raw list[dict] in compiled_checks and need to be
        # injected into ExtractionConfig.dd_grid_columns as list[DDGridColumnSpec].
        _raw_dd_grid_columns = getattr(cfg, "dd_grid_columns", None)
        _parsed_dd_grid_columns = _parse_dd_grid_columns(
            _raw_dd_grid_columns,
            check_id=cfg.id,
        )

        # Build ExtractionConfig, injecting parsed dd_grid_columns.
        # We create a shallow copy of the raw extraction dict to avoid
        # mutating the original compiled_checks data.
        _extraction: ExtractionConfig | None = None
        if cfg.extraction:
            _extraction_payload = dict(cfg.extraction)
            if _parsed_dd_grid_columns is not None:
                # Inject validated DDGridColumnSpec list into extraction payload.
                # Overrides any dd_grid_columns already present in extraction dict.
                _extraction_payload["dd_grid_columns"] = _parsed_dd_grid_columns
            try:
                _extraction = ExtractionConfig(**_extraction_payload)
            except Exception as exc:
                logger.warning(
                    "load_playbook_from_dict: cannot build ExtractionConfig, skipping extraction",
                    check_id=cfg.id,
                    error=str(exc),
                )
                _extraction = None
        elif _parsed_dd_grid_columns is not None:
            # dd_grid_columns present at top level but no extraction block.
            # This is a config inconsistency — log and ignore.
            logger.debug(
                "load_playbook_from_dict: dd_grid_columns declared but extraction is absent, ignoring",
                check_id=cfg.id,
            )

        checks.append(
            CheckDefinition(
                id=cfg.id,
                name=cfg.name,
                description=cfg.description or "",
                doc_types=cfg.doc_types or [],
                origin=origin,
                ui_mode=getattr(cfg, "ui_mode", None),
                # DD Grid V1: group and display_order for hierarchy and sorting.
                group=getattr(cfg, "group", None),
                display_order=getattr(cfg, "display_order", 0),
                severity=cfg.severity,
                # severity_if_* пробрасываем если заданы в GlobalCheckConfig
                severity_if_fail=getattr(cfg, "severity_if_fail", None),
                severity_if_pass=getattr(cfg, "severity_if_pass", None),
                severity_if_unclear=getattr(cfg, "severity_if_unclear", None),
                detector_type=DetectorType(cfg.detector_type),
                rules=rules,
                llm=LLMConfig(**(cfg.llm or {})),
                retrieval=RetrievalConfig(**(cfg.retrieval or {})),
                extraction=_extraction,
                enrichment_hints=_enrichment_hints,
            )
        )

    meta = raw.get("meta") or {}
    name = meta.get("config", {}).get("profile") or meta.get("bundle_id") or "build_compiled_checks"
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
        raise ValueError(f"PlaybookVersion {version.id} has empty or invalid compiled_checks")

    return load_playbook_from_dict(raw)
