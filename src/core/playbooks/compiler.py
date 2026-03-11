# core/playbooks/compiler.py

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import logging

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)


# Эти пути при необходимости можно будет сделать настраиваемыми через настройки проекта.
GLOBAL_CHECKS_DIR = Path("playbooks/global_checks")
BUNDLES_DIR = Path("playbooks/bundles")


# ===== Pydantic-схемы для compiled_checks =====

class PlaybookConfig(BaseModel):
    """Снимок настроек, которыми пользователь собрал плейбук."""

    bundles: List[str] = Field(
        default_factory=list,
        description="Список ID bundle-файлов, которые были включены."
    )
    include_ids: List[str] = Field(
        default_factory=list,
        description="Чек-ID, которые пользователь явно добавил поверх bundle'ов."
    )
    exclude_ids: List[str] = Field(
        default_factory=list,
        description="Чек-ID, которые пользователь явно выключил."
    )
    profile: Optional[str] = Field(
        default=None,
        description="Профиль глубины проверки: core/full/quick и т.п."
    )


class PlaybookMeta(BaseModel):
    """Служебная информация о том, как собран и интерпретируется плейбук."""

    config: PlaybookConfig = Field(
        default_factory=PlaybookConfig,
        description="Рецепт сборки плейбука (для UI и пересборки).",
    )
    bundle_id: Optional[str] = Field(
        default=None,
        description="Основной bundle, если был выбран один (для удобства).",
    )
    check_ids: List[str] = Field(
        default_factory=list,
        description="Итоговый список чеков после всех include/exclude.",
    )
    version_schema: int = Field(
        default=1,
        description="Версия схемы compiled_checks/meta.",
    )
    source_type: str = Field(
        default="global_checks_v1",
        description="Откуда взялись определения чеков (для трассировки).",
    )


class GlobalCheckConfig(BaseModel):
    """Описание одного глобального чека из YAML."""

    id: str
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    group: Optional[str] = Field(
        default=None,
        description="Крупный блок/секция для UX (например, 'liability').",
    )
    severity: str = Field(
        default="medium",
        description="low | medium | high | critical",
    )
    doc_types: List[str] = Field(
        default_factory=list,
        description="К каким типам документов чек применим.",
    )
    source: str = Field(
        default="global_playbook",
        description="Источник: global_playbook / type_playbook / client_custom и т.п.",
    )

    detector_type: str = Field(
        ...,
        description="'rules' | 'llm' | 'hybrid'",
    )
    rules: Dict[str, Any] = Field(
        default_factory=dict,
        description="Конфиг для rules-базированного детектора (keywords, regex и т.п.).",
    )
    llm: Dict[str, Any] = Field(
        default_factory=dict,
        description="Конфиг для LLM-детектора (prompt, model, параметры).",
    )
    retrieval: Dict[str, Any] = Field(
        default_factory=dict,
        description="Настройки извлечения контекста (scope, k, и т.п.).",
    )
    extraction: Dict[str, Any] = Field(
        default_factory=dict,
        description="Настройки структурированной вытяжки.",
    )
    red_flags: Dict[str, Any] = Field(
        default_factory=dict,
        description="Настройки поиска red flags.",
    )

    profiles_enabled: List[str] = Field(
        default_factory=list,
        description="Какие профили глубины включают этот чек: ['core', 'full'] и т.п.",
    )
    deal_profiles: List[str] = Field(
        default_factory=list,
        description="Типы сделок, для которых чек особенно релевантен.",
    )
    industries: List[str] = Field(
        default_factory=list,
        description="Отрасли, для которых чек особенно релевантен.",
    )
    jurisdictions: List[str] = Field(
        default_factory=list,
        description="Юрисдикции, для которых чек особенно релевантен.",
    )


class BundleConfig(BaseModel):
    """Описание UI-пресета (bundle) из YAML."""

    id: str
    name: str
    description: Optional[str] = None
    check_ids: List[str]


class CompiledPlaybook(BaseModel):
    """Схема JSON, который будет лежать в PlaybookVersion.compiled_checks."""

    checks: List[GlobalCheckConfig]
    meta: PlaybookMeta


# ===== Загрузка global_checks и bundles =====

def load_global_checks() -> Dict[str, GlobalCheckConfig]:
    import yaml

    if not GLOBAL_CHECKS_DIR.exists():
        logger.warning("GLOBAL_CHECKS_DIR does not exist: %s", GLOBAL_CHECKS_DIR)
        return {}

    checks: Dict[str, GlobalCheckConfig] = {}
    # было:
    # for path in sorted(GLOBAL_CHECKS_DIR.glob("*.yaml")):
    # стало (рекурсивно по подпапкам):
    for path in sorted(GLOBAL_CHECKS_DIR.rglob("*.yaml")):
        try:
            with path.open("r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
        except Exception as e:  # noqa: BLE001
            logger.error("Failed to read global check YAML %s: %s", path, e)
            raise RuntimeError(f"Cannot read global check file: {path}") from e

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
    """Загружает YAML bundle по id из playbooks/bundles.

    Если файла нет или формат неверный — выбрасывает FileNotFoundError / RuntimeError.
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
        # защищаемся от рассинхрона имени файла и id внутри
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
    all_checks: Dict[str, GlobalCheckConfig],
    *,
    bundles: Optional[List[str]] = None,
    include_ids: Optional[List[str]] = None,
    exclude_ids: Optional[List[str]] = None,
    profile: Optional[str] = None,
    primary_bundle_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Собирает структуру для PlaybookVersion.compiled_checks.

    На вход:
      - all_checks: все глобальные чек-файлы (из load_global_checks),
      - bundles: список bundle_id, которые выбрал пользователь,
      - include_ids: явные добавления,
      - exclude_ids: явные исключения,
      - profile: профиль глубины проверки (core/full/quick),
      - primary_bundle_id: основной bundle для удобства трассировки.

    На выход: dict, совместимый с CompiledPlaybook.model_dump().
    """
    bundles = bundles or []
    include_ids = include_ids or []
    exclude_ids = exclude_ids or []

    # 1. базовый набор id: все чек-id из выбранных bundles
    base_ids: List[str] = []

    for bundle_id in bundles:
        bundle_cfg = load_bundle(bundle_id)
        base_ids.extend(bundle_cfg.check_ids)

    # 2. добавим явные include_ids
    base_ids.extend(include_ids)

    if not base_ids:
        raise ValueError("No checks selected: bundles and include_ids are both empty")

    # 3. убираем дубликаты, сохраняя порядок
    seen: set[str] = set()
    unique_ids: List[str] = []
    for cid in base_ids:
        if cid in seen:
            continue
        seen.add(cid)
        unique_ids.append(cid)

    # 4. применяем exclude_ids
    excluded_set = set(exclude_ids)
    final_ids: List[str] = [cid for cid in unique_ids if cid not in excluded_set]

    if not final_ids:
        raise ValueError("All checks were excluded; resulting list is empty")

    # 5. проверяем, что все есть в all_checks
    missing: List[str] = [cid for cid in final_ids if cid not in all_checks]
    if missing:
        raise KeyError(f"Unknown check_id(s): {', '.join(missing)}")

    # 6. фильтрация по profile (если нужно)
    if profile:
        filtered_ids: List[str] = []
        for cid in final_ids:
            cfg = all_checks[cid]
            # если profiles_enabled пуст, считаем, что чек доступен во всех профилях
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
            version_schema=1,
            source_type="global_checks_v1",
        ),
    )

    # Возвращаем обычный dict, чтобы его удобно класть в JSONB и через ORM.
    return compiled.model_dump()
