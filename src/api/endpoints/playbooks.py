# src/api/endpoints/playbooks.py


"""
Эндпоинты для работы с плейбуками (Playbook / PlaybookVersion).
"""

from __future__ import annotations

from typing import List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.schemas.playbooks import (
    BundleInfo,
    GlobalCheckInfo,
    PlaybookCreateRequest,
    PlaybookCreateResponse,
    PlaybookVersionShort,
    PlaybookLineShort,
    PlaybookVersionDetail,
    PlaybookLineDetail,
    PlaybookLineCreate,
    PlaybookLineItemPayload,
    PlaybookTopicInfo,
)
from core.playbooks.compiler import (
    load_global_checks,
    build_compiled_checks,
    BundleConfig,
    BUNDLES_DIR,
)
from db.session import get_db
from db.repositories.playbook_repo import PlaybookRepository
from services.playbooks.catalog import load_global_checks_catalog
from pydantic import BaseModel  # ← добавили

router = APIRouter(
    prefix="/playbooks",
    tags=["playbooks"],
)


async def require_playbook_admin(
    user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """
    Проверка прав на управление шаблонами playbook.

    Разрешаем только пользователям с глобальной ролью 'superadmin' или 'admin'.
    В dev-режиме get_current_user возвращает global_role='admin', поэтому
    проверки будут проходить.
    """
    if user.global_role not in ("superadmin", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions to manage playbook templates.",
        )
    return user


@router.get(
    "/catalog",
    response_model=list[PlaybookTopicInfo],
    summary="Каталог глобальных чеков (темы и инструкции)",
)
async def get_playbooks_catalog(
    db: AsyncSession = Depends(get_db),  # задел на будущее (кэш/ACL)
):
    return load_global_checks_catalog()


@router.get(
    "/checks",
    response_model=List[GlobalCheckInfo],
    summary="Список всех глобальных проверок (global_checks)",
)
async def list_global_checks(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
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
    import yaml

    items: List[BundleInfo] = []

    if not BUNDLES_DIR.exists():
        return items

    for path in sorted(BUNDLES_DIR.glob("*.yaml")):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            cfg = BundleConfig(**raw)
        except Exception:
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


@router.get(
    "/lines",
    response_model=List[PlaybookLineShort],
    summary="Список логических плейбуков (Playbook-шаблонов)",
)
async def list_playbook_lines(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_playbook_admin),
    deal_type: Optional[str] = Query(
        default=None,
        description="Фильтр по типу сделки: real_estate, mna, nda, corporate и т.п.",
    ),
    jurisdiction: Optional[str] = Query(
        default=None,
        description="Фильтр по юрисдикции: RU, EN, DE и т.п.",
    ),
    language: Optional[str] = Query(
        default=None,
        description="Фильтр по языку документов: 'ru', 'en' и т.п.",
    ),
):
    repo = PlaybookRepository(db)
    playbooks = await repo.list_playbooks(
        deal_type=deal_type,
        jurisdiction=jurisdiction,
        language=language,
    )

    return [
        PlaybookLineShort(
            id=p.id,
            code=p.code,
            title=p.title,
            description=p.description,
            deal_type=p.deal_type,
            jurisdiction=p.jurisdiction,
            language=p.language,
            risk_profile=p.risk_profile,
        )
        for p in playbooks
    ]


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
    Создать новую версию плейбука.

    Источники состава (checks):

    1) bundles + include_ids / exclude_ids — старый режим.
    2) from_line_id — новый режим: берём PlaybookLine и его items,
       маппим topic_code + check_code к глобальным checks и строим include_ids.
    """

    repo = PlaybookRepository(db)

    # Стартовый include_ids из payload (старый контракт сохраняем)
    include_ids: list[str] = list(payload.include_ids or [])

    # Если указан from_line_id — достаём линию и её элементы
    if payload.from_line_id:
        line, items = await repo.get_line_with_items(payload.from_line_id)
        if not line:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Playbook line not found for from_line_id.",
            )

        # Загружаем каталог тем/проверок, чтобы маппить topic_code/check_code -> global_check_id
        topics = load_global_checks_catalog()
        topic_by_code = {t.topic_code: t for t in topics}

        for item in items:
            # Нас интересуют только элементы типа "check"
            if item.kind != "check":
                continue
            if not item.topic_code or not item.check_code:
                continue

            topic = topic_by_code.get(item.topic_code)
            if not topic:
                continue

            # В каталоге PlaybookTopicInfo.checks у нас PlaybookCheckInfo,
            # где сейчас есть code (и, при необходимости, можно добавить global_check_id).
            check = next(
                (c for c in topic.checks if c.code == item.check_code),
                None,
            )
            if not check:
                continue

            # ВАЖНО: если в PlaybookCheckInfo позже появится явный global_check_id,
            # то здесь лучше использовать его. Пока используем code как ID.
            global_check_id = check.code

            if global_check_id not in include_ids:
                include_ids.append(global_check_id)

        # Если playbook_id не задан, логично привязать версию к этой линии
        if not payload.playbook_id:
            payload.playbook_id = line.id

    # Проверка: хотя бы bundles, или include_ids (включая собранные из from_line_id)
    if not payload.bundles and not include_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "At least one bundle, include_ids, or from_line_id "
                "must be provided."
            ),
        )

    # Загружаем все глобальные проверки
    all_checks = load_global_checks()
    if not all_checks:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No global checks loaded; check server configuration.",
        )

    # Компилируем итоговый набор checks через существующий механизм
    try:
        compiled = build_compiled_checks(
            all_checks=all_checks,
            bundles=payload.bundles,
            include_ids=include_ids,
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

    # Имя версии
    if payload.name:
        name = payload.name
    elif payload.bundles:
        name = f"Bundle: {', '.join(payload.bundles)}"
    elif payload.from_line_id:
        name = "Playbook from template"
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
        playbook_id=payload.playbook_id,
    )

    await db.commit()
    await db.refresh(pv)

    return PlaybookCreateResponse(
        id=pv.id,
        name=pv.name,
        semver=pv.semver,
        status=pv.status,
        playbook_id=pv.playbook_id,
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
            playbook_id=row.playbook_id,
        )
        for row in rows
    ]


@router.get(
    "/{version_id}",
    response_model=PlaybookVersionDetail,
    summary="Детальная информация о версии плейбука",
)
async def get_playbook_version_detail(
    version_id: uuid.UUID = Path(..., description="ID версии плейбука"),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Возвращает детальное представление версии плейбука.

    Используется фронтендом для:
    - просмотра состава плейбука;
    - отображения профилей, секций и DD-запросов на UI.
    """
    repo = PlaybookRepository(db)
    pv = await repo.get_by_id(version_id)
    if pv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playbook version not found.",
        )

    return PlaybookVersionDetail(
        id=pv.id,
        name=pv.name,
        semver=pv.semver,
        status=pv.status,
        playbook_id=pv.playbook_id,
        model_config_id=pv.model_config_id,
        compiled_checks=pv.compiled_checks,
        trigger_definitions=pv.trigger_definitions,
        dd_request_templates=pv.dd_request_templates,
        section_markers=pv.section_markers,
        classification_config=pv.classification_config,
    )


@router.get(
    "/lines/{line_id}",
    response_model=PlaybookLineDetail,
    summary="Детали шаблона плейбука (PlaybookLine)",
)
async def get_playbook_line(
    line_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_playbook_admin),
):
    repo = PlaybookRepository(db)
    line, items = await repo.get_line_with_items(line_id)
    if not line:
        raise HTTPException(status_code=404, detail="Playbook line not found")

    return PlaybookLineDetail(
        id=line.id,
        code=line.code,
        title=line.title,
        description=line.description,
        deal_type=line.deal_type,
        jurisdiction=line.jurisdiction,
        language=line.language,
        risk_profile=line.risk_profile,
        items=[
            PlaybookLineItemPayload(
                kind=i.kind,
                topic_code=i.topic_code,
                check_code=i.check_code,
                order_index=i.order_index,
            )
            for i in items
        ],
    )


@router.post(
    "/lines",
    response_model=PlaybookLineDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Создать шаблон плейбука (PlaybookLine)",
)
async def create_playbook_line(
    payload: PlaybookLineCreate,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_playbook_admin),
):
    repo = PlaybookRepository(db)

    # Преобразуем Pydantic-объекты в dict, чтобы репозиторий не зависел от Pydantic
    items_payload = [item.dict() for item in payload.items]

    line, items = await repo.create_line_with_items(
        title=payload.title,
        description=payload.description,
        deal_type=payload.deal_type,
        jurisdiction=payload.jurisdiction,
        language=payload.language,
        items=items_payload,
    )
    await db.commit()
    await db.refresh(line)

    return PlaybookLineDetail(
        id=line.id,
        code=line.code,
        title=line.title,
        description=line.description,
        deal_type=line.deal_type,
        jurisdiction=line.jurisdiction,
        language=line.language,
        risk_profile=line.risk_profile,
        items=[
            PlaybookLineItemPayload(
                kind=i.kind,
                topic_code=i.topic_code,
                check_code=i.check_code,
                order_index=i.order_index,
            )
            for i in items
        ],
    )


@router.put(
    "/lines/{line_id}",
    response_model=PlaybookLineDetail,
    summary="Обновить шаблон плейбука (PlaybookLine)",
)
async def update_playbook_line(
    line_id: uuid.UUID,
    payload: PlaybookLineCreate,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_playbook_admin),
):
    repo = PlaybookRepository(db)

    items_payload = [item.dict() for item in payload.items]

    line, items = await repo.update_line_with_items(
        line_id=line_id,
        title=payload.title,
        description=payload.description,
        deal_type=payload.deal_type,
        jurisdiction=payload.jurisdiction,
        language=payload.language,
        items=items_payload,
    )
    if not line:
        raise HTTPException(status_code=404, detail="Playbook line not found")

    await db.commit()
    await db.refresh(line)

    return PlaybookLineDetail(
        id=line.id,
        code=line.code,
        title=line.title,
        description=line.description,
        deal_type=line.deal_type,
        jurisdiction=line.jurisdiction,
        language=line.language,
        risk_profile=line.risk_profile,
        items=[
            PlaybookLineItemPayload(
                kind=i.kind,
                topic_code=i.topic_code,
                check_code=i.check_code,
                order_index=i.order_index,
            )
            for i in items
        ],
    )


# -------------------------------------------------------------------
# Новый эндпоинт: смена ModelConfig у PlaybookVersion
# -------------------------------------------------------------------


class PlaybookVersionModelConfigUpdate(BaseModel):
    """
    Тело запроса для обновления профиля модели (ModelConfig) у версии плейбука.

    Если model_config_id = null, версия плейбука больше не будет
    указывать конкретный профиль модели.
    """

    model_config_id: uuid.UUID | None


@router.patch(
    "/{version_id}/model-config",
    response_model=PlaybookVersionDetail,
    summary="Обновить профиль модели (ModelConfig) у версии плейбука",
)
async def set_playbook_version_model_config(
    version_id: uuid.UUID,
    payload: PlaybookVersionModelConfigUpdate,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_playbook_admin),
):
    """
    Обновляет поле model_config_id у PlaybookVersion.

    Используется в админке плейбуков, чтобы:
    - привязать версию плейбука к новому профилю модели;
    - очистить старую привязку (model_config_id = null),
      чтобы затем можно было удалить старый профиль модели.
    """
    repo = PlaybookRepository(db)

    pv = await repo.get_by_id(version_id)
    if pv is None:
        raise HTTPException(status_code=404, detail="Playbook version not found.")

    # Если профиль не меняется — просто возвращаем текущее состояние
    if pv.model_config_id == payload.model_config_id:
        return PlaybookVersionDetail(
            id=pv.id,
            name=pv.name,
            semver=pv.semver,
            status=pv.status,
            playbook_id=pv.playbook_id,
            model_config_id=pv.model_config_id,
            compiled_checks=pv.compiled_checks,
            trigger_definitions=pv.trigger_definitions,
            dd_request_templates=pv.dd_request_templates,
            section_markers=pv.section_markers,
            classification_config=pv.classification_config,
        )

    # Если указан новый профиль — проверяем, что он существует
    if payload.model_config_id is not None:
        mc = await repo.get_model_config(payload.model_config_id)
        if mc is None:
            raise HTTPException(
                status_code=404,
                detail="ModelConfig not found",
            )

    pv.model_config_id = payload.model_config_id

    await db.commit()
    await db.refresh(pv)

    return PlaybookVersionDetail(
        id=pv.id,
        name=pv.name,
        semver=pv.semver,
        status=pv.status,
        playbook_id=pv.playbook_id,
        model_config_id=pv.model_config_id,
        compiled_checks=pv.compiled_checks,
        trigger_definitions=pv.trigger_definitions,
        dd_request_templates=pv.dd_request_templates,
        section_markers=pv.section_markers,
        classification_config=pv.classification_config,
    )
