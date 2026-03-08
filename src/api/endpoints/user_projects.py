from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db
from src.api.deps.auth import get_current_user, CurrentUser
from src.db.repositories.deal_repo import DealRepository

router = APIRouter(prefix="/api/v1/user", tags=["user-projects"])


class UserProject(BaseModel):
    deal_id: str
    deal_name: str
    role: Literal["admin", "editor", "viewer"]
    created_at: str
    contact_person: str | None = None


@router.get("/{user_id}/projects", response_model=list[UserProject])
async def list_user_projects(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    # здесь можно сразу заложить проверку, что user_id == current_user.id
    # чтобы интерфейс был «правильным»:
    if user_id != current_user.id:
        # позже тут будет 403 / проверка прав
        # сейчас можно просто игнорировать, либо вернуть пустой список
        pass

    repo = DealRepository(db)
    # прод‑вариант — сделать нормальную пагинацию + фильтрацию по membership/tenant
    deals_page, _total = await repo.get_page(page=1, per_page=100)

    return [
        UserProject(
            deal_id=str(d.id),
            deal_name=d.name,
                        role="admin",  # временно считаем, что текущий пользователь — админ везде
            created_at=d.created_at.isoformat(),
            contact_person=(
                (d.metadata_ or {}).get("contact_person")
                if getattr(d, "metadata_", None) is not None
                else None
            ),
        )
        for d in deals_page
    ]
