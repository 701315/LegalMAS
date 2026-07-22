# src/core/playbooks/compiler.py

"""
Playbook compiler.

Этот модуль отвечает за:

1) Загрузку определений глобальных чеков из YAML-файлов
   (каталог playbooks/global_checks, рекурсивно по подпапкам).

2) Загрузку bundle-конфигов (UI-пресетов) из YAML-файлов
   (каталог playbooks/bundles).

3) Сборку "скомпилированного плейбука" (compiled_checks) для сохранения
   в PlaybookVersion.compiled_checks.

Compiled плейбук — это простой JSON-совместимый dict со структурой:

    {
      "checks": [ GlobalCheckConfig, ... ],
      "meta": {
        "config": { ... PlaybookConfig ... },
        "bundle_id": "...",
        "check_ids": ["CHK_001", "CHK_002", ...],
        "version_schema": 1,
        "source_type": "global_checks_v1"
      }
    }

Где:

- GlobalCheckConfig описывает один чек, доступный движку проверок.
- Поле source в GlobalCheckConfig фиксирует происхождение чека и
  используется, в том числе, для фильтров в DD Grid:

    - GLOBAL_PLAYBOOK  – чек пришёл из глобального плейбука
                         (универсальные риски "для любых договоров").
    - DOCUMENT_TYPE    – чек пришёл из инструкций по типу документа.
                         Для текущего генератора global_checks_v1
                         это может не использоваться, но поле зарезервировано.
    - SYSTEM           – системные / технические проверки, созданные кодом.

Текущая реализация build_compiled_checks формирует только GLOBAL_PLAYBOOK
(глобальные чеки, собранные по bundles + include/exclude).
Но структура данных уже готова к тому, чтобы в будущем добавлять
DOCUMENT_TYPE и SYSTEM, не ломая формат.

Изменения (keyword_groups support):
- GlobalCheckConfig получил поле keyword_groups: Dict[str, Any].
  Это позволяет хранить уровневые группы keywords (high/medium/low)
  отдельно от блока rules. Loader затем объединяет:
    * rules.keywords (если dict — inline группы),
    * rules.keyword_groups (вложенное поле),
    * keyword_groups (верхнеуровневое поле GlobalCheckConfig).

Изменения (severity_if_* support):
- GlobalCheckConfig получил поля severity_if_fail / severity_if_pass /
  severity_if_unclear. Они позволяют задавать severity, зависящий от
  результата проверки (fail/pass/unclear), который затем использует
  исполнитель проверок.

Изменения (DD Grid V1 support):
- GlobalCheckConfig получил поля display_order и dd_grid_columns.
  display_order задаёт порядок отображения check в DD Grid.
  dd_grid_columns — явная конфигурация колонок DD Grid (raw dict,
  парсинг в DDGridColumnSpec выполняется loader'ом в V1.2).
"""

from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

# Эти пути при необходимости можно будет сделать настраиваемыми через настройки проекта.
GLOBAL_CHECKS_DIR = Path("playbooks/global_checks")
BUNDLES_DIR = Path("playbooks/bundles")


# ===== Pydantic-схемы для compiled_checks =====


class PlaybookConfig(BaseModel):
    """Снимок настроек, которыми пользователь собрал плейбук.

    Это "рецепт", по которому был сформирован итоговый набор чеков.
    Его можно показать в UI и использовать для пересборки.
    """

    bundles: list[str] = Field(
        default_factory=list,
        description="Список ID bundle-файлов, которые были включены.",
    )
    include_ids: list[str] = Field(
        default_factory=list,
        description="Чек-ID, которые пользователь явно добавил поверх bundle'ов.",
    )
    exclude_ids: list[str] = Field(
        default_factory=list,
        description="Чек-ID, которые пользователь явно выключил.",
    )
    profile: str | None = Field(
        default=None,
        description="Профиль глубины проверки: core/full/quick и т.п.",
    )


class PlaybookMeta(BaseModel):
    """Служебная информация о том, как собран и интерпретируется плейбук."""

    config: PlaybookConfig = Field(
        default_factory=PlaybookConfig,
        description="Рецепт сборки плейбука (для UI и пересборки).",
    )
    bundle_id: str | None = Field(
        default=None,
        description="Основной bundle, если был выбран один (для удобства).",
    )
    check_ids: list[str] = Field(
        default_factory=list,
        description="Итоговый список чеков после всех include/exclude.",
    )
    global_instruction_refs: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Ссылки на published global instruction versions, использованные "
            "при сборке плейбука: {instruction_code: version_id}"
        ),
    )
    version_schema: int = Field(
        default=1,
        description="Версия схемы compiled_checks/meta.",
    )
    source_type: str = Field(
        default="global_checks_v1",
        description="Откуда взялись определения чеков (для трассировки).",
    )


class CheckSource(str, Enum):
    """Источник определения проверки (используется и бекендом, и UI).

    Значения:

    - GLOBAL_PLAYBOOK  – чек пришёл из глобального плейбука
                         (универсальные темы для любых договоров).
    - DOCUMENT_TYPE    – чек определён в инструкциях по конкретному типу документа.
    - SYSTEM           – чек сгенерирован системой (тех/диагностические проверки).
    """

    GLOBAL_PLAYBOOK = "GLOBAL_PLAYBOOK"
    DOCUMENT_TYPE = "DOCUMENT_TYPE"
    SYSTEM = "SYSTEM"


class GlobalCheckConfig(BaseModel):
    """Описание одного глобального чека (как он хранится в compiled_checks).

    Это уже "плоская" структура, готовая для использования движком проверок
    и для отображения в UI (через PlaybookDefinition / CheckDefinition).
    """

    id: str
    name: str
    description: str | None = None
    category: str | None = None
    group: str | None = Field(
        default=None,
        description="Крупный блок/секция для UX (например, 'liability').",
    )
    display_order: int = Field(
        default=0,
        description=(
            "Порядок отображения check внутри группы/списка в DD Grid. "
            "Меньше = раньше. Checks с одинаковым display_order "
            "сортируются по name (алфавитно)."
        ),
    )
    severity: str = Field(
        default="medium",
        description="low | medium | high | critical",
    )
    # Outcome‑зависимые severity (опционально, переопределяют базовый severity)
    severity_if_fail: str | None = Field(
        default=None,
        description="Severity, если результат проверки: fail (опционально).",
    )
    severity_if_pass: str | None = Field(
        default=None,
        description="Severity, если результат проверки: pass (опционально).",
    )
    severity_if_unclear: str | None = Field(
        default=None,
        description="Severity, если результат проверки: unclear (опционально).",
    )

    ui_mode: str | None = Field(
        default=None,
        description=(
            "Semantic type of check for business-result mapping and UI display. "
            "Supported values: 'clause_presence', 'risk_detection', 'field_extraction'. "
            "None = legacy fallback behavior."
        ),
    )

    doc_types: list[str] = Field(
        default_factory=list,
        description="К каким типам документов чек применим.",
    )

    # ВАЖНО: это ровно то поле, которое будет транслироваться в origin на уровне CheckDefinition.
    # Для глобального плейбука мы ставим GLOBAL_PLAYBOOK, для будущих инструкций по типу
    # документа можно будет использовать DOCUMENT_TYPE, для тех. чеков – SYSTEM.
    source: CheckSource = Field(
        default=CheckSource.GLOBAL_PLAYBOOK,
        description="Источник: GLOBAL_PLAYBOOK / DOCUMENT_TYPE / SYSTEM.",
    )

    detector_type: str = Field(
        ...,
        description="'rules' | 'llm' | 'hybrid'",
    )

    # Конфиг для rules-базированного детектора (keywords, regex и т.п.).
    # Хранится как сырой dict, loader строит RulesConfig.
    rules: dict[str, Any] = Field(
        default_factory=dict,
        description="Конфиг для rules-базированного детектора (keywords, regex и т.п.).",
    )

    # Новое: уровневые keyword-группы (high/medium/low).
    # Хранятся отдельно от rules для явной передачи в RulesConfig.keyword_groups.
    # Если задано — используется loader'ом как дополнительный источник:
    #   1) rules.keywords (если dict — inline groups),
    #   2) rules.keyword_groups,
    #   3) keyword_groups (это поле).
    keyword_groups: dict[str, Any] = Field(
        default_factory=dict,
        description="Уровневые группы keywords: {'high': [...], 'medium': [...], 'low': [...]}",
    )

    llm: dict[str, Any] = Field(
        default_factory=dict,
        description="Конфиг для LLM-детектора (prompt, model, параметры).",
    )
    retrieval: dict[str, Any] = Field(
        default_factory=dict,
        description="Настройки извлечения контекста (scope, k, и т.п.).",
    )
    extraction: dict[str, Any] = Field(
        default_factory=dict,
        description="Настройки структурированной вытяжки.",
    )
    dd_grid_columns: list[dict[str, Any]] | None = Field(
        default=None,
        description=(
            "Явная конфигурация DD Grid колонок для field_extraction checks. "
            "Raw list[dict] — парсинг в DDGridColumnSpec выполняется loader'ом."
        ),
    )
    red_flags: dict[str, Any] = Field(
        default_factory=dict,
        description="Настройки поиска red flags.",
    )

    profiles_enabled: list[str] = Field(
        default_factory=list,
        description="Какие профили глубины включают этот чек: ['core', 'full'] и т.п.",
    )
    deal_profiles: list[str] = Field(
        default_factory=list,
        description="Типы сделок, для которых чек особенно релевантен.",
    )
    industries: list[str] = Field(
        default_factory=list,
        description="Отрасли, для которых чек особенно релевантен.",
    )
    jurisdictions: list[str] = Field(
        default_factory=list,
        description="Юрисдикции, для которых чек особенно релевантен.",
    )


class BundleConfig(BaseModel):
    """Описание UI-пресета (bundle) из YAML.

    Bundle – это просто именованный набор чеков (по id), который можно
    выбрать в интерфейсе для быстрого старта (например, "Core SPA checks").
    """

    id: str
    name: str
    description: str | None = None
    check_ids: list[str]


class CompiledPlaybook(BaseModel):
    """Схема JSON, который будет лежать в PlaybookVersion.compiled_checks.

    - checks: финальный список чеков (GlobalCheckConfig) после всех фильтров.
    - meta: служебная информация о том, как этот список был получен.
    """

    checks: list[GlobalCheckConfig]
    meta: PlaybookMeta


# ===== Загрузка global_checks и bundles =====


def load_global_checks() -> dict[str, GlobalCheckConfig]:
    """Загрузить все определения глобальных чеков из GLOBAL_CHECKS_DIR.

    Ожидается, что каждый YAML-файл описывает один чек в формате,
    совместимом с GlobalCheckConfig (id, name, severity, detector_type и т.д.).

    Поиск идёт рекурсивно по подпапкам (rglob("*.yaml")).

    Возвращает:
        dict: {check_id: GlobalCheckConfig}.

    Исключения:
        RuntimeError – при ошибке чтения файла или невалидной схеме.
    """
    import yaml

    if not GLOBAL_CHECKS_DIR.exists():
        logger.warning("GLOBAL_CHECKS_DIR does not exist: %s", GLOBAL_CHECKS_DIR)
        return {}

    checks: dict[str, GlobalCheckConfig] = {}

    # Рекурсивно по подпапкам: playbooks/global_checks/**.yaml
    for path in sorted(GLOBAL_CHECKS_DIR.rglob("*.yaml")):
        try:
            with path.open("r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
        except Exception as e:  # noqa: BLE001
            logger.error("Failed to read global check YAML %s: %s", path, e)
            raise RuntimeError(f"Cannot read global check file: {path}") from e

        # НОРМАЛИЗАЦИЯ source перед валидацией:
        source_raw = raw.get("source")
        if isinstance(source_raw, str):
            normalized = source_raw.strip().upper()
            if normalized == "GLOBAL_PLAYBOOK":
                raw["source"] = CheckSource.GLOBAL_PLAYBOOK
            elif normalized == "DOCUMENT_TYPE":
                raw["source"] = CheckSource.DOCUMENT_TYPE
            elif normalized == "SYSTEM":
                raw["source"] = CheckSource.SYSTEM
            else:
                logger.error(
                    "Unknown check source '%s' in %s. "
                    "Expected one of: GLOBAL_PLAYBOOK, DOCUMENT_TYPE, SYSTEM",
                    source_raw,
                    path,
                )
                raise RuntimeError(
                    f"Invalid 'source' value '{source_raw}' in {path}. "
                    "Use GLOBAL_PLAYBOOK / DOCUMENT_TYPE / SYSTEM."
                )

        try:
            cfg = GlobalCheckConfig(**raw)
        except ValidationError as e:
            logger.error("Invalid global check config in %s: %s", path, e)
            raise RuntimeError(f"Invalid global check config in {path}: {e}") from e

        if cfg.id in checks:
            logger.error("Duplicate global check id=%s in %s", cfg.id, path)
            raise RuntimeError(f"Duplicate global check id={cfg.id} in {path}")

        checks[cfg.id] = cfg

    return checks


def load_bundle(bundle_id: str) -> BundleConfig:
    """Загрузить YAML bundle по его id из каталога playbooks/bundles.

    bundle_id маппится на файл <bundle_id>.yaml.

    Возвращает:
        BundleConfig.

    Исключения:
        FileNotFoundError – если файл не найден.
        RuntimeError      – если файл не читается или схема невалидна.
    """
    import yaml

    path = BUNDLES_DIR / f"{bundle_id}.yaml"
    if not path.exists():
        logger.warning("Bundle %s not found at %s", bundle_id, path)
        raise FileNotFoundError(f"Bundle {bundle_id} not found")

    try:
        with path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except Exception as e:  # noqa: BLE001
        logger.error("Failed to read bundle YAML %s: %s", path, e)
        raise RuntimeError(f"Cannot read bundle file: {path}") from e

    try:
        cfg = BundleConfig(**raw)
    except ValidationError as e:
        logger.error("Invalid bundle config in %s: %s", path, e)
        raise RuntimeError(f"Invalid bundle config in {path}: {e}") from e

    if cfg.id != bundle_id:
        logger.error(
            "Bundle id mismatch for %s: file name id=%s, YAML id=%s",
            path,
            bundle_id,
            cfg.id,
        )
        raise RuntimeError(f"Bundle id mismatch: file={bundle_id}, yaml={cfg.id}")

    if not cfg.check_ids:
        logger.error("Bundle %s has empty check_ids list", bundle_id)
        raise RuntimeError(f"Bundle {bundle_id} has empty check_ids list")

    return cfg


# ===== Построение compiled_checks =====


def build_compiled_checks(
    all_checks: dict[str, GlobalCheckConfig],
    *,
    bundles: list[str] | None = None,
    include_ids: list[str] | None = None,
    exclude_ids: list[str] | None = None,
    profile: str | None = None,
    primary_bundle_id: str | None = None,
    global_instruction_refs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Собрать структуру для PlaybookVersion.compiled_checks.

    На вход:
        all_checks:
            Все доступные глобальные чеки (результат load_global_checks()).
        bundles:
            Список bundle_id, которые выбрал пользователь.
        include_ids:
            Чек-ID, которые пользователь явно добавил поверх bundle'ов.
        exclude_ids:
            Чек-ID, которые пользователь явно выключил.
        profile:
            Профиль глубины проверки (например, 'core' / 'full' / 'quick').
        primary_bundle_id:
            Основной bundle для удобства трассировки (может быть None).

    Алгоритм:

        1) Собираем базовый список чек-ID из выбранных bundles.
        2) Добавляем include_ids.
        3) Удаляем дубликаты, сохраняя порядок.
        4) Применяем exclude_ids.
        5) Проверяем, что все ID присутствуют в all_checks.
        6) При необходимости фильтруем по profile.
        7) Формируем CompiledPlaybook (checks + meta) и возвращаем как dict.

    Важно:

    - Поле GlobalCheckConfig.source уже заполнено на этапе чтения YAML.
      Для текущего генератора global_checks_v1 это, как правило,
      CheckSource.GLOBAL_PLAYBOOK.
    - Это поле затем транслируется в origin на уровне CheckDefinition
      (см. engine/playbook/loader.py) и используется DD Grid для фильтров
      "Глобальный плэйбук" и "По типу документа".
    """
    bundles = bundles or []
    include_ids = include_ids or []
    exclude_ids = exclude_ids or []
    global_instruction_refs = global_instruction_refs or {}


    # 1. базовый набор id: все чек-id из выбранных bundles
    base_ids: list[str] = []

    for bundle_id in bundles:
        bundle_cfg = load_bundle(bundle_id)
        base_ids.extend(bundle_cfg.check_ids)

    # 2. добавим явные include_ids
    base_ids.extend(include_ids)

    if not base_ids:
        raise ValueError("No checks selected: bundles and include_ids are both empty")

    # 3. убираем дубликаты, сохраняя порядок
    seen: set[str] = set()
    unique_ids: list[str] = []
    for cid in base_ids:
        if cid in seen:
            continue
        seen.add(cid)
        unique_ids.append(cid)

    # 4. применяем exclude_ids
    excluded_set = set(exclude_ids)
    final_ids: list[str] = [cid for cid in unique_ids if cid not in excluded_set]

    if not final_ids:
        raise ValueError("All checks were excluded; resulting list is empty")

    # 5. проверяем, что все есть в all_checks
    missing: list[str] = [cid for cid in final_ids if cid not in all_checks]
    if missing:
        raise KeyError(f"Unknown check_id(s): {', '.join(missing)}")

    # 6. фильтрация по profile (если нужно)
    if profile:
        filtered_ids: list[str] = []
        for cid in final_ids:
            cfg = all_checks[cid]
            if not cfg.profiles_enabled or profile in cfg.profiles_enabled:
                filtered_ids.append(cid)
        if not filtered_ids:
            raise ValueError(f"No checks left after applying profile='{profile}'")
        final_ids = filtered_ids

    # 7. собираем CompiledPlaybook
    compiled = CompiledPlaybook(
        checks=[all_checks[cid] for cid in final_ids],
        meta=PlaybookMeta(
            config=PlaybookConfig(
                bundles=bundles,
                include_ids=include_ids,
                exclude_ids=exclude_ids,
                profile=profile,
            ),
            bundle_id=primary_bundle_id,
            check_ids=final_ids,
            global_instruction_refs={
                cid: global_instruction_refs[cid]
                for cid in final_ids
                if cid in global_instruction_refs
            },
            version_schema=1,
            source_type="global_checks_v1",
        ),
    )

    # Возвращаем обычный dict, чтобы его удобно класть в JSONB и через ORM.
    return compiled.model_dump()
