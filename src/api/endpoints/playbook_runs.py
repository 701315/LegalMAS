"""
Эндпоинты для работы с плейбуком сделки и пересчётом результатов.

Основные задачи:
- пересобрать плейбук для конкретной сделки (Deal) на основе новой конфигурации;
- создать новую версию PlaybookVersion и новый Run;
- вернуть фронтенду ID нового плейбука и run;
- дать историю изменений плейбука по сделке.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import require_project_role

from api.schemas.playbook_runs import (
    DealPlaybookRebuildRequest,
    DealPlaybookRebuildResponse,
    DealPlaybookHistoryResponse,
    DealPlaybookHistoryItem,
)
from core.playbooks.compiler import load_global_checks, build_compiled_checks
from db.session import get_db
from db.repositories.deal_repo import DealRepository
from db.repositories.playbook_repo import PlaybookRepository
from db.repositories.run_repo import RunRepository
from db.repositories.document_repo import DocumentRepository
from mas_queue.celery_app import celery_app

from core.constants import PlaybookStatus
from core.utils.semver import bump_semver

router = APIRouter(
    prefix="/deals",
    tags=["playbook-runs"],
)


@router.post(
    "/{deal_id}/playbook/rebuild-and-rerun",
    response_model=DealPlaybookRebuildResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Пересобрать плейбук сделки и пересчитать результаты (новый Run)",
)
async def rebuild_playbook_and_rerun(
    deal_id: UUID,
    payload: DealPlaybookRebuildRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Пересобирает плейбук для сделки и запускает новый run по всем документам.

    Шаги:
    1) проверка прав (admin/editor);
    2) загрузка Deal и текущего PlaybookVersion;
    3) чтение текущей конфигурации из compiled_checks.meta.config;
    4) объединение с payload (если что-то передано);
    5) сборка нового compiled_checks через build_compiled_checks;
    6) создание новой PlaybookVersion;
    7) обновление Deal.playbook_version_id;
    8) создание нового Run;
    9) постановка задач run_checks для всех документов сделки;
    10) обновление Deal.last_run_id;
    11) возврат ID нового плейбука и run.
    """
    # 1. Проверяем права (только admin/editor).
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin", "editor"),
    )

    deal_repo = DealRepository(db)
    playbook_repo = PlaybookRepository(db)
    run_repo = RunRepository(db)
    doc_repo = DocumentRepository(db)

    # 2. Проверяем, что сделка существует
    deal = await deal_repo.get_by_id(deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    # 3. Берём текущий плейбук для сделки (явно привязанный или default)
    current_playbook = await playbook_repo.get_for_deal(deal_id)
    if not current_playbook:
        raise HTTPException(
            status_code=400,
            detail="Deal is not configured with a playbook",
        )

    if not current_playbook.model_config_id:
        raise HTTPException(
            status_code=400,
            detail="Playbook is not configured with model_config",
        )

    # 4. Читаем текущую конфигурацию из compiled_checks.meta.config
    compiled = current_playbook.compiled_checks or {}
    meta = compiled.get("meta") or {}
    config_dict = meta.get("config") or {}

    from core.playbooks.compiler import PlaybookConfig

    # объединяем текущую конфигурацию с новой
    current_config = PlaybookConfig(**config_dict)

    bundles = payload.bundles or current_config.bundles
    include_ids = payload.include_ids or current_config.include_ids
    exclude_ids = payload.exclude_ids or current_config.exclude_ids
    profile = payload.profile or current_config.profile

    # 5. Загружаем все глобальные чек-файлы и собираем новый compiled_checks
    all_checks = load_global_checks()
    if not all_checks:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No global checks loaded; check server configuration.",
        )

    try:
        new_compiled = build_compiled_checks(
            all_checks=all_checks,
            bundles=bundles,
            include_ids=include_ids,
            exclude_ids=exclude_ids,
            profile=profile,
            primary_bundle_id=bundles[0] if bundles else meta.get("bundle_id"),
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
            detail="Failed to build compiled_checks for new playbook.",
        )

    # 6. Создаём новую PlaybookVersion
    # увеличиваем минорную версию плейбука для новой конфигурации
    new_semver = bump_semver(current_playbook.semver, part="minor")
    new_status = PlaybookStatus.STABLE.value

    new_playbook = await playbook_repo.create_version(
        name=current_playbook.name,
        semver=new_semver,
        model_config_id=current_playbook.model_config_id,
        git_commit=current_playbook.git_commit,
        yaml_sha256=current_playbook.yaml_sha256,
        compiled_checks=new_compiled,
        status=new_status,
    )

    # 7. Обновляем Deal.playbook_version_id на новый плейбук
    deal.playbook_version_id = new_playbook.id

    # 8. Создаём новый Run для этой сделки
    new_run = await run_repo.create(
        deal_id=deal_id,
        playbook_version_id=new_playbook.id,
        model_config_id=new_playbook.model_config_id,
        bundle_id=None,
        environment_hash=None,
        profile=deal.profile,  # используем профиль сделки
    )

    # 9. Загружаем все документы сделки и ставим задачи run_checks
    docs = await doc_repo.get_by_deal(deal_id)

    try:
        for d in docs:
            celery_app.send_task(
                "workers.run_checks",
                kwargs={
                    "document_id": str(d.id),
                    "deal_id": str(d.deal_id),
                    "tenant_id": str(user.tenant_id),
                    "run_id": str(new_run.id),
                },
            )
    except Exception:
        # TODO: добавить логирование (sentry/loguru)
        pass

    # 10. Обновляем last_run_id у сделки и коммитим транзакцию
    await deal_repo.set_last_run_id(deal_id=deal_id, run_id=new_run.id)

    await db.commit()
    await db.refresh(new_run)
    await db.refresh(deal)

    # 11. Возвращаем ID нового плейбука и run
    return DealPlaybookRebuildResponse(
        deal_id=deal_id,
        new_playbook_version_id=new_playbook.id,
        new_run_id=new_run.id,
    )


@router.get(
    "/{deal_id}/playbook/history",
    response_model=DealPlaybookHistoryResponse,
    summary="История изменений плейбука по сделке (список Run + PlaybookVersion)",
)
async def get_deal_playbook_history(
    deal_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Возвращает историю изменений плейбука по сделке.

    Источник данных:
    - все Run для deal_id (RunRepository.get_by_deal);
    - для каждого Run подтягиваем PlaybookVersion;
    - в UI можно показывать цепочку версий плейбука и запусков.
    """
    # Проверка доступа (любая роль участника проекта)
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin", "editor", "viewer"),
    )

    run_repo = RunRepository(db)
    playbook_repo = PlaybookRepository(db)

    runs = await run_repo.get_by_deal(deal_id)

    # Чтобы не делать N запросов к PlaybookVersion, можно заранее вытянуть все нужные ID.
    from sqlalchemy import select
    from db.models.playbook import PlaybookVersion

    playbook_ids = {r.playbook_version_id for r in runs}
    if not playbook_ids:
        return DealPlaybookHistoryResponse(deal_id=deal_id, items=[])

    result = await db.execute(
        select(PlaybookVersion).where(PlaybookVersion.id.in_(playbook_ids))
    )
    playbooks_by_id = {pb.id: pb for pb in result.scalars().all()}

    items: list[DealPlaybookHistoryItem] = []
    for r in runs:
        pb = playbooks_by_id.get(r.playbook_version_id)
        if not pb:
            continue
        items.append(
            DealPlaybookHistoryItem(
                run_id=r.id,
                playbook_version_id=pb.id,
                playbook_name=pb.name,
                playbook_semver=pb.semver,
                run_status=r.status,
                created_at=r.created_at,
                completed_at=r.completed_at,
                profile=r.profile,
            )
        )

    # runs.get_by_deal уже сортирует по created_at DESC, так что и items будут в нужном порядке.
    return DealPlaybookHistoryResponse(deal_id=deal_id, items=items)
