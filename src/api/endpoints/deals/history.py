# src/api/endpoints/deals/history.py

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import require_project_role
from api.schemas.deals import DealPlaybookHistoryItem
from db.session import get_db
from db.repositories.audit_repo import AuditRepository

router = APIRouter()


@router.get(
    "/{deal_id}/playbook-history",
    response_model=list[DealPlaybookHistoryItem],
    summary="История смен playbook-версии для сделки",
)
async def get_deal_playbook_history(
    deal_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin", "editor", "reviewer", "viewer"),
    )

    audit_repo = AuditRepository(db)
    logs = await audit_repo.get_by_deal(
        deal_id=deal_id,
        action="SET_DEAL_PLAYBOOK",
        limit=100,
    )

    items: list[DealPlaybookHistoryItem] = []
    for entry in logs:
        details = entry.details or {}
        items.append(
            DealPlaybookHistoryItem(
                created_at=entry.created_at,
                actor=str(entry.actor),
                actor_role=entry.actor_role,
                old_playbook_version_id=details.get("old_playbook_version_id"),
                new_playbook_version_id=details.get("new_playbook_version_id"),
                playbook_id=details.get("playbook_id"),
                playbook_name=details.get("playbook_name"),
                semver=details.get("semver"),
            )
        )

    return items

