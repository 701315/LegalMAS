# src/api/endpoints/deals/settings.py

from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import require_project_role
from api.schemas.deals import DealResponse, _normalize_language_code
from core.constants import DocumentStatus
from core.logging import get_logger
from db.models.playbook import PlaybookVersion
from db.repositories.audit_repo import AuditRepository
from db.repositories.deal_repo import DealRepository
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from db.repositories.playbook_repo import PlaybookRepository
from db.session import get_db
from services.outbox_service import OutboxService  # [+] добавлен импорт

router = APIRouter()
logger = get_logger(__name__)


class DealPlaybookUpdate(BaseModel):
    """
    Тело запроса для обновления playbook сделки.

    Передаём ID версии плейбука, которая должна использоваться
    по умолчанию при запуске анализа для этой сделки.
    """
    playbook_version_id: UUID


class DealModelConfigUpdate(BaseModel):
    """
    Тело запроса для обновления профиля модели (ModelConfig) для сделки.

    Здесь мы храним явный выбор профиля на уровне проекта.
    Если поле model_config_id = null, то специальный профиль
    для сделки сбрасывается, и при запуске анализа будет
    использован профиль, привязанный к PlaybookVersion.
    """
    model_config_id: UUID | None


class DealPrimaryLanguageUpdate(BaseModel):
    """
    Тело запроса для установки основного языка сделки.

    Правила:
    - primary_language должен входить в список languages сделки;
    - если передан null, основной язык сбрасывается.
    """
    primary_language: str | None


@router.patch(
    "/{deal_id}/playbook",
    response_model=DealResponse,
    summary="Установить playbook для сделки",
)
async def set_deal_playbook(
    deal_id: UUID,
    payload: DealPlaybookUpdate,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Привязывает конкретную версию playbook (PlaybookVersion) к сделке
    и пишет событие в журнал аудита.
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin", "editor"),
    )

    deal_repo = DealRepository(db)
    audit_repo = AuditRepository(db)

    deal = await deal_repo.get_by_id(deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")

    old_playbook_version_id = deal.playbook_version_id
    new_playbook_version_id = payload.playbook_version_id

    if old_playbook_version_id == new_playbook_version_id:
        return DealResponse.model_validate(deal)

    result = await db.execute(
        sa.select(PlaybookVersion).where(
            PlaybookVersion.id == new_playbook_version_id
        )
    )
    pv = result.scalar_one_or_none()
    if pv is None:
        raise HTTPException(
            status_code=404,
            detail="Playbook version not found",
        )

    deal.playbook_version_id = new_playbook_version_id

    await audit_repo.log(
        tenant_id=deal.tenant_id,
        deal_id=deal.id,
        action="SET_DEAL_PLAYBOOK",
        actor=user.id,
        actor_role=getattr(user, "role", None),
        details={
            "old_playbook_version_id": str(old_playbook_version_id)
            if old_playbook_version_id
            else None,
            "new_playbook_version_id": str(new_playbook_version_id),
            "playbook_id": str(pv.playbook_id)
            if getattr(pv, "playbook_id", None)
            else None,
            "playbook_name": getattr(pv, "name", None),
            "semver": getattr(pv, "semver", None),
        },
    )

    await db.flush()
    await db.commit()
    await db.refresh(deal)

    return DealResponse.model_validate(deal)


@router.patch(
    "/{deal_id}/model-config",
    response_model=DealResponse,
    summary="Установить профиль модели (ModelConfig) для сделки",
)
async def set_deal_model_config(
    deal_id: UUID,
    payload: DealModelConfigUpdate,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Устанавливает или сбрасывает явный профиль модели для сделки.

    Правила:
    - менять профиль модели могут только admin/editor на уровне проекта;
    - если model_config_id не null, такой ModelConfig должен существовать;
    - если model_config_id = null, явный профиль сделки снимается,
      и дальше будет использоваться профиль из PlaybookVersion;
    - если значение не изменилось, просто возвращаем текущую сделку.
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin", "editor"),
    )

    deal_repo = DealRepository(db)
    pb_repo = PlaybookRepository(db)
    audit_repo = AuditRepository(db)

    deal = await deal_repo.get_by_id(deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")

    old_model_config_id = getattr(deal, "model_config_id", None)
    new_model_config_id = payload.model_config_id

    if new_model_config_id is not None:
        mc = await pb_repo.get_model_config(new_model_config_id)
        if mc is None:
            raise HTTPException(status_code=404, detail="ModelConfig not found")
        new_model_config_name = mc.name
    else:
        new_model_config_name = None

    if old_model_config_id == new_model_config_id:
        return DealResponse.model_validate(deal)

    deal.model_config_id = new_model_config_id

    await audit_repo.log(
        tenant_id=deal.tenant_id,
        deal_id=deal.id,
        action="SET_DEAL_MODEL_CONFIG",
        actor=user.id,
        actor_role=getattr(user, "role", None),
        details={
            "old_model_config_id": str(old_model_config_id)
            if old_model_config_id
            else None,
            "new_model_config_id": str(new_model_config_id)
            if new_model_config_id
            else None,
            "new_model_config_name": new_model_config_name,
        },
    )

    await db.flush()
    await db.commit()
    await db.refresh(deal)

    return DealResponse.model_validate(deal)


@router.patch(
    "/{deal_id}/primary-language",
    response_model=DealResponse,
    summary="Установить основной язык сделки",
)
async def set_deal_primary_language(
    deal_id: UUID,
    payload: DealPrimaryLanguageUpdate,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Устанавливает (или сбрасывает) основной язык сделки.

    Правила:
    - менять основной язык могут только роли admin/editor;
    - если primary_language не null, он должен быть в Deal.languages;
    - при нарушении правил возвращаем 400/403/404.

    После смены языка документы в статусе LANGUAGE_SELECTION_REQUIRED
    переводятся в PENDING и через Outbox получают задачу
    workers.build_primary_language_source.
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin", "editor"),
    )

    deal_repo = DealRepository(db)
    doc_repo = DocumentRepository(db)
    dv_repo = DocumentVersionRepository(db)
    audit_repo = AuditRepository(db)   # [+] инстанцируем audit_repo
    outbox = OutboxService(db)         # [+] инстанцируем outbox

    deal = await deal_repo.get_by_id(deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")

    # [-] убран DEBUG_primary_language_patch logger

    raw_lang = payload.primary_language
    new_lang = _normalize_language_code(raw_lang) if raw_lang is not None else None

    deal_languages = list(deal.languages or [])
    normalized_deal_languages = [
        _normalize_language_code(l)
        for l in deal_languages
        if l is not None and str(l).strip()
    ]

    if new_lang is not None:
        if not normalized_deal_languages:
            raise HTTPException(
                status_code=400,
                detail="Cannot set primary_language when deal has no languages",
            )
        if new_lang not in normalized_deal_languages:
            raise HTTPException(
                status_code=400,
                detail="primary_language must be one of deal languages",
            )

    old_lang = deal.primary_language
    deal.primary_language = new_lang

    restart_items: list[tuple[str, str]] = []

    if new_lang is not None and new_lang != old_lang:
        docs_to_restart = await doc_repo.get_by_deal(
            deal_id=deal_id,
            status=DocumentStatus.LANGUAGE_SELECTION_REQUIRED.value,
        )

        for doc in docs_to_restart:
            latest_version = await dv_repo.get_latest(doc.id)
            if latest_version is None:
                continue

            await doc_repo.update_status(
                doc.id,
                DocumentStatus.PENDING.value,
                processing_error_details=None,
            )

            restart_items.append((str(doc.id), str(latest_version.id)))

    # [+] Audit: фиксируем смену primary_language ДО commit
    await audit_repo.log(
        tenant_id=deal.tenant_id,
        deal_id=deal.id,
        action="SET_DEAL_PRIMARY_LANGUAGE",
        actor=user.id,
        actor_role=getattr(user, "role", None),
        details={
            "old_primary_language": old_lang,
            "new_primary_language": new_lang,
            "restarted_documents_count": len(restart_items),
            "restarted_document_ids": [doc_id for doc_id, _ in restart_items],
        },
    )

    # [+] Outbox: enqueue build_primary_language_source для каждого документа
    # в той же транзакции — гарантированная доставка без race condition
    for document_id_str, version_id_str in restart_items:
        await outbox.enqueue_task(
            task_name="workers.build_primary_language_source",
            payload={
                "document_version_id": version_id_str,
                "document_id": document_id_str,
                "deal_id": str(deal.id),
                "tenant_id": str(deal.tenant_id),
                "run_id": None,
                "target_language": new_lang,
            },
            aggregate_type="document",
            aggregate_id=document_id_str,
            dedup_key=f"primary_lang_restart:{document_id_str}:{new_lang}",
            headers={
                "event_type": "PRIMARY_LANGUAGE_SOURCE_REQUESTED",
                "source": "api.set_deal_primary_language",
            },
        )

    # [-] убран прямой celery_app.send_task — заменён на Outbox выше

    await db.flush()
    await db.commit()
    await db.refresh(deal)

    if restart_items:
        logger.info(
            "Primary language set: restarting documents via outbox",
            extra={
                "deal_id": str(deal.id),
                "tenant_id": str(deal.tenant_id),
                "old_primary_language": old_lang,
                "new_primary_language": new_lang,
                "documents_count": len(restart_items),
            },
        )

    return DealResponse.model_validate(deal)
