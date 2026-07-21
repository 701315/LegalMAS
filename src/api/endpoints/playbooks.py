# src/api/endpoints/playbooks.py


"""
Эндпоинты для работы с плейбуками (Playbook / PlaybookVersion).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from pydantic import BaseModel  # ← добавили
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.schemas.playbooks import (
    BundleInfo,
    GlobalCheckInfo,
    PlaybookCreateRequest,
    PlaybookCreateResponse,
    PlaybookLineCreate,
    PlaybookLineDetail,
    PlaybookLineItemPayload,
    PlaybookLineShort,
    PlaybookTopicInfo,
    PlaybookVersionDetail,
    PlaybookVersionShort,
    PlaybookDraftUpdateRequest,
    PlaybookVersionDiffResponse,
)
from services.playbooks.publishing import (
    PlaybookPublishingService,
    PublishedVersionImmutableError,
)
from core.playbooks.compiler import (
    BUNDLES_DIR,
    BundleConfig,
    build_compiled_checks,
    load_global_checks,
)
from db.repositories.playbook_repo import PlaybookRepository
from db.session import get_db
from services.playbooks.catalog import load_global_checks_catalog
from core.constants import PlaybookStatus
from services.playbooks.diff import (
    PlaybookVersionDiffService,
    PlaybookDiffError,
)

router = APIRouter(
    prefix="/playbooks",
    tags=["playbooks"],
)


async def require_playbook_admin(
    user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """
    Проверка прав на управление шаблонами playbook.

    Разрешено: superadmin и tenant_admin.
    superadmin управляет шаблонами всей платформы.
    tenant_admin управляет шаблонами в рамках своего tenant'а.
    """
    if user.global_role not in ("superadmin", "tenant_admin"):
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
    response_model=list[GlobalCheckInfo],
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
    response_model=list[BundleInfo],
    summary="Список всех преднастроенных bundles (presets)",
)
async def list_bundles(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    import yaml

    items: list[BundleInfo] = []

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
    response_model=list[PlaybookLineShort],
    summary="Список логических плейбуков (Playbook-шаблонов)",
)
async def list_playbook_lines(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_playbook_admin),
    deal_type: str | None = Query(
        default=None,
        description="Фильтр по типу сделки: real_estate, mna, nda, corporate и т.п.",
    ),
    jurisdiction: str | None = Query(
        default=None,
        description="Фильтр по юрисдикции: RU, EN, DE и т.п.",
    ),
    language: str | None = Query(
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

    1) bundles + include_ids / exclude_ids — прямой compile contract.
    2) from_line_id — берём PlaybookLine и его items,
       читаем instruction_code и строим include_ids напрямую.
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

        for item in items:
            if item.kind != "check":
                continue
            if not item.instruction_code:
                continue

            if item.instruction_code not in include_ids:
                include_ids.append(item.instruction_code)

        # Если playbook_id не задан, логично привязать версию к этой линии
        if not payload.playbook_id:
            payload.playbook_id = line.id

    # Проверка: хотя бы bundles, или include_ids (включая собранные из from_line_id)
    if not payload.bundles and not include_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=("At least one bundle, include_ids, or from_line_id " "must be provided."),
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

    # Build canonical source_payload (edit lifecycle layer)
    source_payload = {
        "schema_version": 1,
        "bundles": payload.bundles or [],
        "include_ids": payload.include_ids or [],
        "exclude_ids": payload.exclude_ids or [],
        "profile": payload.profile,
        "model_config_id": str(payload.model_config_id),
        "playbook_id": str(payload.playbook_id) if payload.playbook_id else None,
        "from_line_id": str(payload.from_line_id) if payload.from_line_id else None,
    }

    pv = await repo.create_version(
        name=name,
        semver=semver,
        model_config_id=payload.model_config_id,
        git_commit=None,
        yaml_sha256=None,
        compiled_checks=compiled,
        status=status_value,
        playbook_id=payload.playbook_id,
        source_payload=source_payload,
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
    response_model=list[PlaybookVersionShort],
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
        source_payload=pv.source_payload,
        source_payload_sha256=pv.source_payload_sha256,
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
                instruction_code=i.instruction_code,
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
    items_payload = [item.model_dump() for item in payload.items]

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
                instruction_code=i.instruction_code,
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

    items_payload = [item.model_dump() for item in payload.items]
    
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
                instruction_code=i.instruction_code,
                order_index=i.order_index,
            )
            for i in items
        ],
    )


@router.delete(
    "/lines/{line_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить шаблон плейбука (PlaybookLine), если он не используется",
)
async def delete_playbook_line(
    line_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_playbook_admin),
):
    """
    Удаляет логический шаблон плейбука (PlaybookLine), только если он не используется.

    Для непрофессионального программиста:
    - Сначала проверяем, существует ли такой шаблон.
    - Затем проверяем, есть ли у него версии, которые:
      * назначены сделкам (Deal.playbook_version_id),
      * или уже использовались в запуске анализа (Run.playbook_version_id).
    - Если есть использования — возвращаем 409 Conflict с понятным текстом.
    - Если нет — удаляем шаблон и его элементы (line_items), возвращаем 204.
    """
    repo = PlaybookRepository(db)

    usage = await repo.get_line_usage(line_id)

    # 1. Шаблон не найден — 404
    if not usage.line_exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playbook line not found.",
        )

    # 2. Есть версии, которые используются сделками или запусками — 409
    if usage.used_in_deals > 0 or usage.used_in_runs > 0:
        # Формируем человекочитаемое сообщение
        parts: list[str] = []

        if usage.used_in_deals > 0:
            if usage.deal_names:
                deals_str = ", ".join(usage.deal_names)
                parts.append(f"используется в {usage.used_in_deals} сделк(е/ах): {deals_str}")
            else:
                parts.append(f"используется в {usage.used_in_deals} сделк(е/ах)")

        if usage.used_in_runs > 0:
            parts.append(f"использовался в {usage.used_in_runs} запуск(е/ах) анализа (Run)")

        detail = "Шаблон плейбука не может быть удалён: " + "; ".join(parts) + "."

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        )

    # 3. Опциональный консервативный режим:
    #    если не хочешь удалять шаблон, у которого есть версии, но они нигде не используются,
    #    раскомментируй блок ниже.
    #
    # if usage.versions_count > 0:
    #     raise HTTPException(
    #         status_code=status.HTTP_409_CONFLICT,
    #         detail=(
    #             "Шаблон имеет связанные версии плейбука и не может быть удалён. "
    #             "Сначала удалите или заархивируйте связанные PlaybookVersion."
    #         ),
    #     )

    deleted = await repo.delete_line_with_items(line_id)
    if not deleted:
        # Редкий случай гонки:
        # шаблон существовал на этапе проверки usage,
        # но был удалён другим запросом до текущего delete.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playbook line not found.",
        )

    await db.commit()
    return Response()


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

    if pv.status == PlaybookStatus.PUBLISHED.value:
        raise HTTPException(
            status_code=409,
            detail="PUBLISHED_VERSION_IMMUTABLE",
        )

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


@router.post(
    "/{version_id}/publish",
    response_model=PlaybookVersionDetail,
)
async def publish_playbook_version(
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_playbook_admin),
):
    repo = PlaybookRepository(db)
    pv = await repo.get_by_id(version_id)
    if not pv:
        raise HTTPException(status_code=404)

    service = PlaybookPublishingService(db)

    try:
        pv = await service.publish(pv)
    except PublishedVersionImmutableError:
        raise HTTPException(
            status_code=409,
            detail="PUBLISHED_VERSION_IMMUTABLE",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    await db.commit()
    await db.refresh(pv)

    return pv

@router.patch(
    "/{version_id}",
    response_model=PlaybookVersionDetail,
    summary="Обновить draft-версию плейбука",
)
async def update_playbook_draft(
    version_id: uuid.UUID,
    payload: PlaybookDraftUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_playbook_admin),
):
    from core.constants import PlaybookStatus

    repo = PlaybookRepository(db)
    pv = await repo.get_by_id(version_id)
    if not pv:
        raise HTTPException(status_code=404)

    if pv.status != PlaybookStatus.DRAFT.value:
        raise HTTPException(
            status_code=409,
            detail="PUBLISHED_VERSION_IMMUTABLE",
        )

    # Обновляем source_payload
    source = dict(pv.source_payload or {})
    if payload.bundles is not None:
        source["bundles"] = payload.bundles
    source["include_ids"] = payload.include_ids or source.get("include_ids", [])
    source["exclude_ids"] = payload.exclude_ids or source.get("exclude_ids", [])
    source["profile"] = payload.profile or source.get("profile")

    pv.source_payload = source

    # Пересобираем compiled_checks
    all_checks = load_global_checks()

    compiled = build_compiled_checks(
        all_checks=all_checks,
        bundles=source.get("bundles"),
        include_ids=source.get("include_ids"),
        exclude_ids=source.get("exclude_ids"),
        profile=source.get("profile"),
        primary_bundle_id=(
            source.get("bundles")[0]
            if source.get("bundles")
            else None
        ),
    )

    pv.compiled_checks = compiled

    # Пересчитываем source hash
    from db.repositories.playbook_repo import compute_source_payload_hash
    pv.source_payload_sha256 = compute_source_payload_hash(source)

    if payload.name:
        pv.name = payload.name

    await db.commit()
    await db.refresh(pv)

    return pv


@router.get(
    "/{version_id}/diff",
    response_model=PlaybookVersionDiffResponse,
    summary="Diff между двумя версиями плейбука",
)
async def diff_playbook_versions(
    version_id: uuid.UUID,
    against: uuid.UUID = Query(..., description="ID версии для сравнения"),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_playbook_admin),
):
    repo = PlaybookRepository(db)

    base = await repo.get_by_id(version_id)
    other = await repo.get_by_id(against)

    if not base or not other:
        raise HTTPException(status_code=404)

    service = PlaybookVersionDiffService()

    try:
        changes = service.diff(base, other)
    except PlaybookDiffError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return PlaybookVersionDiffResponse(
        base_version_id=base.id,
        compare_version_id=other.id,
        has_changes=len(changes) > 0,
        diff=changes,
    )


@router.post(
    "/{version_id}/archive",
    response_model=PlaybookVersionDetail,
)
async def archive_playbook_version(
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_playbook_admin),
):
    repo = PlaybookRepository(db)
    pv = await repo.get_by_id(version_id)
    if not pv:
        raise HTTPException(status_code=404)

    service = PlaybookPublishingService(db)

    try:
        pv = await service.archive(pv)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    await db.commit()
    await db.refresh(pv)

    return pv

@router.post(
    "/{version_id}/clone",
    response_model=PlaybookVersionDetail,
)
async def clone_playbook_version(
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_playbook_admin),
):
    repo = PlaybookRepository(db)
    pv = await repo.get_by_id(version_id)
    if not pv:
        raise HTTPException(status_code=404)

    service = PlaybookPublishingService(db)

    new_version = await service.clone_to_draft(pv)

    await db.commit()
    await db.refresh(new_version)

    return new_version


