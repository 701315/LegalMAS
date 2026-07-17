# src/api/endpoints/playbook_runs.py

"""
Эндпоинты для работы с плейбуком сделки и пересчётом результатов.

Основные задачи:
- пересобрать плейбук для конкретной сделки (Deal) на основе новой конфигурации;
- создать новую версию PlaybookVersion и новый Run;
- вернуть фронтенду ID нового плейбука и run;
- дать историю изменений плейбука по сделке;
- отдать текущий состав плейбука для сделки (для инициализации UI).

Важно:

Сейчас поддерживаем два сценария пересборки плейбука для сделки:

1) "Рецептный" (как было раньше):
   - клиент передаёт bundles/include_ids/exclude_ids/profile,
   - пустые поля означают "бери из текущего плейбука",
   - далее вызываем build_compiled_checks(...) с этими параметрами.

2) Новый "после UI-плашек":
   - фронтенд показывает полный список check_id и даёт юристу поставить галочки,
   - после правок отправляет enabled_check_ids (и опционально disabled_check_ids),
   - тогда мы строим include/exclude на их основе.

Логика выбора:

- Если payload.enabled_check_ids НЕ пустой → считаем, что фронт прислал
  явный состав, и игнорируем старые поля bundles/include_ids/exclude_ids.

- Если enabled_check_ids пустой → ведём себя как раньше: берём текущий PlaybookConfig
  из compiled_checks.meta.config и перекрываем его payload.bundles/include/exclude/profile.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import require_project_role
from api.schemas.playbook_runs import (
    DealPlaybookHistoryItem,
    DealPlaybookHistoryResponse,
    DealPlaybookRebuildRequest,
    DealPlaybookRebuildResponse,
)
from api.schemas.playbooks import PlaybookCreateRequest  # для описания "рецепта" в current
from core.constants import PlaybookStatus
from core.playbooks.compiler import (
    PlaybookConfig,
    build_compiled_checks,
    load_global_checks,
)
from core.utils.semver import bump_semver
from db.models.playbook import PlaybookVersion
from db.repositories.deal_repo import DealRepository
from db.repositories.playbook_repo import PlaybookRepository
from db.repositories.run_repo import RunRepository
from db.session import get_db

router = APIRouter(
    prefix="/deals",
    tags=["playbook-runs"],
)


@router.get(
    "/{deal_id}/playbook/current",
    response_model=PlaybookCreateRequest,
    summary="Текущая конфигурация плейбука для сделки (рецепт bundles/include/exclude/profile)",
)
async def get_current_deal_playbook_config(
    deal_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> PlaybookCreateRequest:
    """
    Возвращает текущую конфигурацию плейбука для сделки в виде "рецепта".

    Что именно отдаём:
    - bundles/include_ids/exclude_ids/profile — из compiled_checks.meta.config;
    - model_config_id — тот же, что у текущего PlaybookVersion.

    Для чего это нужно фронту:
    - инициализация UI конструктора плейбука сделки;
    - показ текущего набора тем/проверок, выбранного для этой сделки;
    - возможность на базе этой конфигурации собрать новый плейбук (через rebuild-and-rerun).

    Важно: это НЕ создаёт новую версию и НЕ запускает run, только читает текущую конфигурацию.
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin", "editor", "viewer"),
    )

    deal_repo = DealRepository(db)
    playbook_repo = PlaybookRepository(db)

    deal = await deal_repo.get_by_id(
        deal_id,
        tenant_id=user.tenant_id,
    )
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    playbook = await playbook_repo.get_for_deal(deal_id)
    if not playbook:
        raise HTTPException(
            status_code=400,
            detail="Deal is not configured with a playbook",
        )

    if not playbook.model_config_id:
        raise HTTPException(
            status_code=400,
            detail="Playbook is not configured with model_config",
        )

    compiled = playbook.compiled_checks or {}
    meta = compiled.get("meta") or {}
    config_dict = meta.get("config") or {}

    try:
        current_config = PlaybookConfig(**config_dict) if config_dict else None
    except Exception:
        current_config = None

    return PlaybookCreateRequest(
        name=playbook.name,
        bundles=current_config.bundles if current_config else [],
        include_ids=current_config.include_ids if current_config else [],
        exclude_ids=current_config.exclude_ids if current_config else [],
        profile=current_config.profile if current_config else None,
        model_config_id=playbook.model_config_id,
        semver=None,
        status=None,
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
) -> DealPlaybookRebuildResponse:
    """
    Пересобирает плейбук для сделки и запускает новый Run по всем документам.

    Шаги:
    1) проверка прав (admin/editor);
    2) загрузка Deal и текущего PlaybookVersion;
    3) чтение текущей конфигурации из compiled_checks.meta.config;
    4) определение новой конфигурации:
       - либо через bundles/include/exclude/profile (старый режим),
       - либо через enabled_check_ids/disabled_check_ids (новый режим);
    5) сборка нового compiled_checks через build_compiled_checks;
    6) создание новой PlaybookVersion;
    7) обновление Deal.playbook_version_id;
    8) создание нового Run;
    9) запуск оркестратора start_run_pipeline для этого Run
       (extract → pii → structure → classify → run_deal_checks);
    10) обновление Deal.last_run_id;
    11) возврат ID нового плейбука и run.
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin", "editor"),
    )

    deal_repo = DealRepository(db)
    playbook_repo = PlaybookRepository(db)
    run_repo = RunRepository(db)

    # Определяем checks_mode для нового Run:
    # - если у сделки уже были запуски, берём режим из последнего Run,
    # - иначе используем дефолтный режим.
    last_run = await run_repo.get_latest_for_deal(deal_id)
    if last_run and getattr(last_run, "checks_mode", None):
        checks_mode = last_run.checks_mode
    else:
        checks_mode = "global_and_doc_type"

    deal = await deal_repo.get_by_id(
        deal_id,
        tenant_id=user.tenant_id,
    )
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

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

    compiled = current_playbook.compiled_checks or {}
    meta = compiled.get("meta") or {}
    config_dict = meta.get("config") or {}

    try:
        current_config = PlaybookConfig(**config_dict) if config_dict else PlaybookConfig()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid playbook config for deal: {e}",
        ) from e

    # --- Определяем новую конфигурацию плейбука ---

    if payload.enabled_check_ids:
        bundles = []
        include_ids = payload.enabled_check_ids
        exclude_ids = payload.disabled_check_ids or []
        profile = payload.profile or current_config.profile
    else:
        bundles = payload.bundles or current_config.bundles
        include_ids = payload.include_ids or current_config.include_ids
        exclude_ids = payload.exclude_ids or current_config.exclude_ids
        profile = payload.profile or current_config.profile

    # 5. Собираем новый compiled_checks
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
        ) from e
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to build compiled_checks for new playbook.",
        ) from e

    # 6. Новая PlaybookVersion
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

    # 7. Обновляем Deal.playbook_version_id
    deal.playbook_version_id = new_playbook.id

    # 8. Создаём новый Run
    new_run = await run_repo.create(
        deal_id=deal_id,
        playbook_version_id=new_playbook.id,
        model_config_id=new_playbook.model_config_id,
        bundle_id=None,
        environment_hash=None,
        profile=deal.profile,
        checks_mode=checks_mode,
        checks_scope=payload.checks_scope.model_dump() if payload.checks_scope else None,
    )

    # 9. Запускаем оркестратор пайплайна для этого Run
    from mas_queue.celery_app import celery_app as _celery

    _celery.send_task(
        "workers.start_run_pipeline",
        kwargs={
            "run_id": str(new_run.id),
            "deal_id": str(deal_id),
            "tenant_id": str(deal.tenant_id),
            "force_reclassify": False,
            "checks_mode": checks_mode,
        },
    )

    # 10. Обновляем last_run_id и коммитим
    await deal_repo.set_last_run_id(deal_id=deal_id, run_id=new_run.id)

    await db.commit()
    await db.refresh(new_run)
    await db.refresh(deal)

    # 11. Ответ
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
) -> DealPlaybookHistoryResponse:
    """
    Возвращает историю изменений плейбука по сделке.

    Источник данных:
    - все Run для deal_id (RunRepository.get_by_deal);
    - для каждого Run подтягиваем PlaybookVersion;
    - в UI можно показывать цепочку версий плейбука и запусков.
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin", "editor", "viewer"),
    )

    run_repo = RunRepository(db)
    runs = await run_repo.get_by_deal(deal_id)

    playbook_ids = {r.playbook_version_id for r in runs}
    if not playbook_ids:
        return DealPlaybookHistoryResponse(deal_id=deal_id, items=[])

    result = await db.execute(select(PlaybookVersion).where(PlaybookVersion.id.in_(playbook_ids)))
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

    return DealPlaybookHistoryResponse(deal_id=deal_id, items=items)
