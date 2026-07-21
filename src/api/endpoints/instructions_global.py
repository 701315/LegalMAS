"""
Facade API for global instruction playbooks.

Это thin adapter над существующим playbook domain:
- logical Playbook -> "global instruction playbook"
- PlaybookVersion -> versions of that global playbook
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser
from api.schemas.playbooks import PlaybookLineShort, PlaybookVersionShort
from db.repositories.playbook_repo import PlaybookRepository
from db.session import get_db
from .playbooks import require_playbook_admin


router = APIRouter(
    prefix="/admin/instructions",
    tags=["admin-instructions"],
)


@router.get(
    "/global",
    response_model=list[PlaybookLineShort],
    summary="Facade: список global playbooks",
)
async def list_global_playbooks(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_playbook_admin),
):
    _ = user

    repo = PlaybookRepository(db)
    playbooks = await repo.list_playbooks()

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


@router.get(
    "/global/{playbook_id}/versions",
    response_model=list[PlaybookVersionShort],
    summary="Facade: версии global playbook",
)
async def list_global_playbook_versions(
    playbook_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_playbook_admin),
):
    _ = user

    repo = PlaybookRepository(db)

    playbook = await repo.get_playbook_by_id(playbook_id)
    if playbook is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playbook not found.",
        )

    versions = await repo.list_versions_for_playbook(playbook_id)

    return [
        PlaybookVersionShort(
            id=row.id,
            name=row.name,
            semver=row.semver,
            status=row.status,
            playbook_id=row.playbook_id,
        )
        for row in versions
    ]



