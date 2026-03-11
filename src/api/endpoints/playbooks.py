"""
Эндпоинты для работы с плейбуками (PlaybookVersion).

Основные задачи:
- отдать фронтенду список всех глобальных проверок (global_checks/*.yaml);
- отдать список преднастроенных наборов (bundles/*.yaml);
- собрать новый плейбук из bundles + ручных чеков и создать PlaybookVersion;
- отдать список существующих PlaybookVersion (для селектора/настроек проекта).

Архитектурные принципы:
- этот слой НЕ лезет в раннер и не читает YAML напрямую;
  он использует компилятор core.playbooks.compiler и PlaybookRepository;
- раннер работает только со snapshot'ом PlaybookVersion.compiled_checks,
  поэтому изменения в global_checks/bundles влияют только на новые версии.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user

from api.schemas.playbooks import (
    BundleInfo,
    GlobalCheckInfo,
    PlaybookCreateRequest,
    PlaybookCreateResponse,
    PlaybookVersionShort,
)
from core.playbooks.compiler import (
    load_global_checks,
    build_compiled_checks,
    BundleConfig,
    BUNDLES_DIR,
)

from db.session import get_db
from db.repositories.playbook_repo import PlaybookRepository


router = APIRouter(
    prefix="/playbooks",
    tags=["playbooks"],
)


@router.get(
    "/checks",
    response_model=List[GlobalCheckInfo],
    summary="Список всех глобальных проверок (global_checks)",
)
async def list_global_checks(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Возвращает список всех глобальных чеков из playbooks/global_checks.

    Используется фронтендом для конструктора плейбука:
    - дерево/таблица "все доступные проверки";
    - фильтрация по category/group/severity/doc_types и т.п.
    """
    all_checks = load_global_checks()
    return [
        GlobalCheckInfo(
            id=cfg.id,
            name=cfg.name,
            description=cfg.description,
            category=cfg.category,
            group=cfg.group,
            severity=cfg.severity,
            doc_types=cfg.doc_types,
        )
        for cfg in all_checks.values()
    ]


@router.get(
    "/bundles",
    response_model=List[BundleInfo],
    summary="Список всех преднастроенных bundles (presets)",
)
async def list_bundles(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Возвращает список всех bundle'ов из playbooks/bundles.

    Используется фронтендом, чтобы показать:
    - "Полный плейбук";
    - "Часто используемые наборы";
    - списки чеков, входящих в каждый preset.
    """
    from pathlib import Path
    import yaml

    items: List[BundleInfo] = []

    if not BUNDLES_DIR.exists():
        return items

    for path in sorted(BUNDLES_DIR.glob("*.yaml")):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            cfg = BundleConfig(**raw)
        except Exception:
            # Битый bundle не ломает весь список — логируем в compiler при использовании.
            continue

        items.append(
            BundleInfo(
                id=cfg.id,
                name=cfg.name,
                description=cfg.description,
                check_ids=cfg.check_ids,
            )
        )

    return items


@router.post(
    "",
    response_model=PlaybookCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать новую версию плейбука (PlaybookVersion)",
)
async def create_playbook_version(
    payload: PlaybookCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Создаёт новую версию плейбука (PlaybookVersion) из bundles и/или явного списка checks.

    Логика:
    - проверяем, что выбраны хотя бы bundles или include_ids;
    - загружаем все глобальные чек-файлы;
    - вызываем build_compiled_checks(...) c bundles/include/exclude/profile;
    - создаём PlaybookVersion через PlaybookRepository.create_version;
    - возвращаем краткую информацию о созданной версии.
    """
    if not payload.bundles and not payload.include_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one bundle or include_ids must be provided.",
        )

    all_checks = load_global_checks()
    if not all_checks:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No global checks loaded; check server configuration.",
        )

    try:
        compiled = build_compiled_checks(
            all_checks=all_checks,
            bundles=payload.bundles,
            include_ids=payload.include_ids,
            exclude_ids=payload.exclude_ids,
            profile=payload.profile,
            primary_bundle_id=payload.bundles[0] if payload.bundles else None,
        )
    except KeyError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to build compiled_checks.",
        )

    repo = PlaybookRepository(db)

    if payload.name:
        name = payload.name
    elif payload.bundles:
        name = f"Bundle: {', '.join(payload.bundles)}"
    else:
        name = "Custom playbook"

    from core.constants import PlaybookStatus

    semver = payload.semver or "0.1.0"
    status_value = payload.status or PlaybookStatus.DRAFT.value

    pv = await repo.create_version(
        name=name,
        semver=semver,
        model_config_id=payload.model_config_id,
        git_commit=None,
        yaml_sha256=None,
        compiled_checks=compiled,
        status=status_value,
    )

    await db.commit()
    await db.refresh(pv)

    return PlaybookCreateResponse(
        id=pv.id,
        name=pv.name,
        semver=pv.semver,
        status=pv.status,
    )


@router.get(
    "",
    response_model=List[PlaybookVersionShort],
    summary="Список версий плейбуков (PlaybookVersion)",
)
async def list_playbook_versions(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Список всех PlaybookVersion.

    Можно использовать на фронте, чтобы:
    - выбрать плейбук по умолчанию для новых сделок;
    - показать историю версий плейбука.
    """
    from sqlalchemy import select
    from db.models.playbook import PlaybookVersion

    result = await db.execute(select(PlaybookVersion))
    rows = result.scalars().all()

    return [
        PlaybookVersionShort(
            id=row.id,
            name=row.name,
            semver=row.semver,
            status=row.status,
        )
        for row in rows
    ]
