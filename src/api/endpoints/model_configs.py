# src/api/endpoints/model_configs.py

"""
Эндпоинты для конфигураций моделей (ModelConfig).

Задачи:
- отдать фронтенду список доступных конфигураций моделей;
- позволить через UI создавать/редактировать/удалять профили моделей;
- показать, где профиль модели используется (версии плейбуков, сделки).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.playbooks import (
    ModelConfigCreateRequest,
    ModelConfigResponse,
    ModelConfigUpdateRequest,
)
from db.models.deal import Deal
from db.models.playbook import PlaybookVersion
from db.repositories.playbook_repo import PlaybookRepository
from db.session import get_db

router = APIRouter(
    prefix="/model-configs",
    tags=["model-configs"],
)


@router.get(
    "",
    response_model=list[ModelConfigResponse],
    summary="Список конфигураций моделей (ModelConfig)",
)
async def list_model_configs(
    db: AsyncSession = Depends(get_db),
):
    """
    Возвращает список доступных конфигураций моделей.

    Используется фронтендом на странице выбора playbook
    и в админке профилей моделей.
    """
    repo = PlaybookRepository(db)
    configs = await repo.list_model_configs()

    return [
        ModelConfigResponse(
            id=c.id,
            name=c.name,
            description=None,  # сейчас в модели нет description в БД
            embeddings_primary=getattr(c, "embeddings_primary", None),
            embeddings_fallback=getattr(c, "embeddings_fallback", None),
        )
        for c in configs
    ]


@router.post(
    "",
    response_model=ModelConfigResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать новый профиль модели (ModelConfig)",
)
async def create_model_config(
    payload: ModelConfigCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Создаёт новый профиль модели.

    Поля формы (candidate_n, llm_context_k, dense_weight и т.п.)
    упаковываются в retrieval_config и scoring_config.
    """
    repo = PlaybookRepository(db)

    retrieval_config = {
        "candidate_n": payload.candidate_n,
        "llm_context_k": payload.llm_context_k,
    }
    scoring_config = {
        "dense_weight": payload.dense_weight,
        "sparse_weight": payload.sparse_weight,
        "metadata_boost": payload.metadata_boost,
    }

    mc = await repo.create_model_config(
        name=payload.name,
        embeddings_primary=payload.embeddings_primary,
        embeddings_fallback=payload.embeddings_fallback,
        retrieval_config=retrieval_config,
        scoring_config=scoring_config,
    )

    await db.commit()
    await db.refresh(mc)

    return ModelConfigResponse(
        id=mc.id,
        name=mc.name,
        description=None,
        embeddings_primary=mc.embeddings_primary,
        embeddings_fallback=mc.embeddings_fallback,
    )


@router.patch(
    "/{config_id}",
    response_model=ModelConfigResponse,
    summary="Обновить профиль модели (ModelConfig)",
)
async def update_model_config(
    config_id: UUID,
    payload: ModelConfigUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Частично обновляет профиль модели.

    Если какие‑то поля не переданы — они остаются без изменений.
    """
    repo = PlaybookRepository(db)

    mc = await repo.get_model_config(config_id)
    if mc is None:
        raise HTTPException(status_code=404, detail="ModelConfig not found")

    # Распаковываем существующие конфиги
    retrieval = dict(mc.retrieval_config or {})
    scoring = dict(mc.scoring_config or {})

    if payload.candidate_n is not None:
        retrieval["candidate_n"] = payload.candidate_n
    if payload.llm_context_k is not None:
        retrieval["llm_context_k"] = payload.llm_context_k

    if payload.dense_weight is not None:
        scoring["dense_weight"] = payload.dense_weight
    if payload.sparse_weight is not None:
        scoring["sparse_weight"] = payload.sparse_weight
    if payload.metadata_boost is not None:
        scoring["metadata_boost"] = payload.metadata_boost

    mc = await repo.update_model_config(
        config_id,
        name=payload.name if payload.name is not None else None,
        embeddings_primary=payload.embeddings_primary,
        embeddings_fallback=payload.embeddings_fallback,
        retrieval_config=retrieval,
        scoring_config=scoring,
    )

    await db.commit()
    await db.refresh(mc)

    return ModelConfigResponse(
        id=mc.id,
        name=mc.name,
        description=None,
        embeddings_primary=mc.embeddings_primary,
        embeddings_fallback=mc.embeddings_fallback,
    )


@router.delete(
    "/{config_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить профиль модели (ModelConfig)",
)
async def delete_model_config(
    config_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Удаляет профиль модели.

    Важно: не стоит удалять конфиг, который уже привязан к существующим плейбукам
    или сделкам. В проде лучше сделать soft-delete/флаг active.
    Пока — простой delete с обработкой ошибки целостности (FK).
    """
    repo = PlaybookRepository(db)
    mc = await repo.get_model_config(config_id)
    if mc is None:
        raise HTTPException(status_code=404, detail="ModelConfig not found")

    await db.delete(mc)

    try:
        await db.commit()
    except IntegrityError:
        # Откатываем транзакцию и возвращаем понятную 409‑ошибку вместо 500
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Нельзя удалить профиль модели: он всё ещё используется "
                "в существующих плейбуках или сделках."
            ),
        )


# ----------------------------------------------------------------------
# Новый эндпоинт: где используется профиль модели (ModelConfig)
# ----------------------------------------------------------------------


class ModelConfigUsagePlaybookItem(BaseModel):
    id: UUID
    name: str
    semver: str
    status: str


class ModelConfigUsageDealItem(BaseModel):
    id: UUID
    name: str
    status: str


class ModelConfigUsageResponse(BaseModel):
    """
    Где используется профиль модели (ModelConfig):
    - в каких версиях плейбуков (PlaybookVersion),
    - в каких сделках (Deal).
    """

    model_config_id: UUID
    playbook_versions: list[ModelConfigUsagePlaybookItem]
    deals: list[ModelConfigUsageDealItem]


@router.get(
    "/{config_id}/usage",
    response_model=ModelConfigUsageResponse,
    summary="Где используется профиль модели (ModelConfig)",
)
async def get_model_config_usage(
    config_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Возвращает список версий плейбуков и сделок, которые ссылаются
    на данный ModelConfig.

    Используется в админке профилей моделей, чтобы юрист видел,
    в каких плейбуках и проектах используется профиль.
    """
    repo = PlaybookRepository(db)
    mc = await repo.get_model_config(config_id)
    if mc is None:
        raise HTTPException(status_code=404, detail="ModelConfig not found")

    # Версии плейбуков, использующие этот профиль
    pv_result = await db.execute(
        select(PlaybookVersion).where(PlaybookVersion.model_config_id == config_id)
    )
    pv_rows = pv_result.scalars().all()

    playbook_versions = [
        ModelConfigUsagePlaybookItem(
            id=row.id,
            name=row.name,
            semver=row.semver,
            status=row.status,
        )
        for row in pv_rows
    ]

    # Сделки, использующие этот профиль
    deal_result = await db.execute(select(Deal).where(Deal.model_config_id == config_id))
    deal_rows = deal_result.scalars().all()

    deals = [
        ModelConfigUsageDealItem(
            id=row.id,
            name=row.name,
            status=row.status,
        )
        for row in deal_rows
    ]

    return ModelConfigUsageResponse(
        model_config_id=config_id,
        playbook_versions=playbook_versions,
        deals=deals,
    )
