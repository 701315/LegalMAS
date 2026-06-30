# src/api/endpoints/admin.py

"""
Административный API.

Разделён на две группы:

1. Управление tenant'ами и пользователями (только superadmin):
   GET    /admin/tenants
   POST   /admin/tenants
   GET    /admin/tenants/{tenant_id}
   PUT    /admin/tenants/{tenant_id}
   DELETE /admin/tenants/{tenant_id}/deactivate
   GET    /admin/tenants/{tenant_id}/users
   POST   /admin/tenants/{tenant_id}/users
   PUT    /admin/tenants/{tenant_id}/users/{user_id}
   DELETE /admin/tenants/{tenant_id}/users/{user_id}/deactivate

2. YAML инструкции (superadmin + tenant_admin):
   GET    /admin/yaml-instructions
"""

from __future__ import annotations

import uuid
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.schemas.admin import (
    TenantCreate,
    TenantResponse,
    TenantUpdate,
    TenantWithStats,
    UserCreate,
    UserResponse,
    UserUpdate,
    YamlInstructionDTO,
)
from core.config import settings
from core.logging import get_logger
from db.models.deal import Deal
from db.models.tenant import Tenant
from db.models.user import User
from db.repositories.tenant_repo import TenantRepository
from db.repositories.user_repo import UserRepository
from db.session import get_db
from services.auth_service import hash_password

logger = get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


# ── Guards ────────────────────────────────────────────────────────────────


def _require_superadmin(user: CurrentUser) -> None:
    """Проверить что пользователь — superadmin. Иначе 403."""
    if user.global_role != "superadmin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superadmin access required",
        )


def _require_admin_or_superadmin(user: CurrentUser) -> None:
    """Проверить что пользователь — superadmin или tenant_admin. Иначе 403."""
    if user.global_role not in ("superadmin", "tenant_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )


# ── Tenant endpoints ─────────────────────────────────────────────────────


@router.get(
    "/tenants",
    response_model=list[TenantWithStats],
    summary="Список всех клиентов (только superadmin)",
)
async def list_tenants(
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> list[TenantWithStats]:
    """
    Вернуть список всех tenant'ов с количеством пользователей и сделок.

    Доступ: только superadmin.
    """
    _require_superadmin(user)

    tenant_repo = TenantRepository(db)
    tenants = await tenant_repo.get_all(include_inactive=include_inactive)

    result: list[TenantWithStats] = []
    for tenant in tenants:
        users_count_result = await db.execute(
            select(func.count(User.id)).where(
                User.tenant_id == tenant.id,
                User.is_active.is_(True),
            )
        )
        users_count = users_count_result.scalar_one() or 0

        deals_count_result = await db.execute(
            select(func.count(Deal.id)).where(Deal.tenant_id == tenant.id)
        )
        deals_count = deals_count_result.scalar_one() or 0

        result.append(
            TenantWithStats(
                id=tenant.id,
                name=tenant.name,
                slug=tenant.slug,
                is_active=tenant.is_active,
                notes=tenant.notes,
                created_at=tenant.created_at,
                updated_at=tenant.updated_at,
                users_count=users_count,
                deals_count=deals_count,
            )
        )

    return result


@router.post(
    "/tenants",
    response_model=TenantResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать нового клиента (только superadmin)",
)
async def create_tenant(
    payload: TenantCreate,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> TenantResponse:
    """
    Создать нового клиента (tenant).

    Доступ: только superadmin.

    Проверяет уникальность slug.
    """
    _require_superadmin(user)

    tenant_repo = TenantRepository(db)

    existing = await tenant_repo.get_by_slug(payload.slug)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tenant with slug '{payload.slug}' already exists",
        )

    tenant = await tenant_repo.create(
        name=payload.name,
        slug=payload.slug,
        notes=payload.notes,
    )
    await db.commit()
    await db.refresh(tenant)

    logger.info(
        "Tenant created",
        tenant_id=str(tenant.id),
        slug=tenant.slug,
        created_by=user.id,
    )

    return TenantResponse.model_validate(tenant)


@router.get(
    "/tenants/{tenant_id}",
    response_model=TenantWithStats,
    summary="Детали клиента (только superadmin)",
)
async def get_tenant(
    tenant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> TenantWithStats:
    """Получить детали tenant'а с количеством пользователей и сделок."""
    _require_superadmin(user)

    tenant_repo = TenantRepository(db)
    tenant = await tenant_repo.get_by_id(tenant_id)

    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    users_count_result = await db.execute(
        select(func.count(User.id)).where(
            User.tenant_id == tenant.id,
            User.is_active.is_(True),
        )
    )
    users_count = users_count_result.scalar_one() or 0

    deals_count_result = await db.execute(
        select(func.count(Deal.id)).where(Deal.tenant_id == tenant.id)
    )
    deals_count = deals_count_result.scalar_one() or 0

    return TenantWithStats(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        is_active=tenant.is_active,
        notes=tenant.notes,
        created_at=tenant.created_at,
        updated_at=tenant.updated_at,
        users_count=users_count,
        deals_count=deals_count,
    )


@router.put(
    "/tenants/{tenant_id}",
    response_model=TenantResponse,
    summary="Обновить клиента (только superadmin)",
)
async def update_tenant(
    tenant_id: uuid.UUID,
    payload: TenantUpdate,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> TenantResponse:
    """Обновить данные tenant'а."""
    _require_superadmin(user)

    tenant_repo = TenantRepository(db)
    tenant = await tenant_repo.update(
        tenant_id,
        name=payload.name,
        notes=payload.notes,
        clear_notes=payload.clear_notes,
    )

    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    await db.commit()
    await db.refresh(tenant)

    return TenantResponse.model_validate(tenant)


@router.patch(
    "/tenants/{tenant_id}/deactivate",
    response_model=TenantResponse,
    summary="Деактивировать клиента (только superadmin)",
)
async def deactivate_tenant(
    tenant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> TenantResponse:
    """
    Деактивировать tenant.

    После деактивации все пользователи этого tenant'а
    не смогут войти в систему.
    Данные не удаляются.
    """
    _require_superadmin(user)

    tenant_repo = TenantRepository(db)
    tenant = await tenant_repo.set_active(tenant_id, is_active=False)

    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    await db.commit()
    await db.refresh(tenant)

    logger.info(
        "Tenant deactivated",
        tenant_id=str(tenant_id),
        deactivated_by=user.id,
    )

    return TenantResponse.model_validate(tenant)


@router.patch(
    "/tenants/{tenant_id}/activate",
    response_model=TenantResponse,
    summary="Активировать клиента (только superadmin)",
)
async def activate_tenant(
    tenant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> TenantResponse:
    """Активировать ранее деактивированный tenant."""
    _require_superadmin(user)

    tenant_repo = TenantRepository(db)
    tenant = await tenant_repo.set_active(tenant_id, is_active=True)

    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    await db.commit()
    await db.refresh(tenant)

    return TenantResponse.model_validate(tenant)


# ── User endpoints ────────────────────────────────────────────────────────


@router.get(
    "/tenants/{tenant_id}/users",
    response_model=list[UserResponse],
    summary="Пользователи клиента (только superadmin)",
)
async def list_tenant_users(
    tenant_id: uuid.UUID,
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> list[UserResponse]:
    """
    Вернуть список пользователей указанного tenant'а.

    Доступ: только superadmin.
    """
    _require_superadmin(user)

    tenant_repo = TenantRepository(db)
    tenant = await tenant_repo.get_by_id(tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    user_repo = UserRepository(db)
    users = await user_repo.get_by_tenant(
        tenant_id,
        include_inactive=include_inactive,
    )

    return [UserResponse.model_validate(u) for u in users]


@router.post(
    "/tenants/{tenant_id}/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать пользователя в клиенте (только superadmin)",
)
async def create_tenant_user(
    tenant_id: uuid.UUID,
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> UserResponse:
    """
    Создать нового пользователя в указанном tenant'е.

    Доступ: только superadmin.

    Проверяет:
    - существование tenant'а;
    - уникальность email в системе.

    Разрешённые system_role: tenant_admin, member.
    """
    _require_superadmin(user)

    tenant_repo = TenantRepository(db)
    tenant = await tenant_repo.get_by_id(tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    if not tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot create user in inactive tenant",
        )

    allowed_roles = {"superadmin", "tenant_admin", "member"}
    if payload.system_role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid system_role. Allowed: {', '.join(sorted(allowed_roles))}",
        )

    user_repo = UserRepository(db)
    existing = await user_repo.get_by_email_any(payload.email)

    if existing is not None:
        # Если пользователь деактивирован и принадлежит тому же tenant'у —
        # реактивируем его с новыми данными вместо создания дубликата.
        if not existing.is_active and existing.tenant_id == tenant_id:
            new_password_hash = hash_password(payload.password)

            reactivated = await user_repo.update(
                existing.id,
                full_name=payload.full_name,
                system_role=payload.system_role,
                password_hash=new_password_hash,
            )
            await user_repo.set_active(existing.id, is_active=True)
            await db.commit()

            refreshed = await user_repo.get_by_id(existing.id)

            logger.info(
                "User reactivated",
                user_id=str(existing.id),
                email=existing.email,
                tenant_id=str(tenant_id),
                system_role=payload.system_role,
                reactivated_by=user.id,
            )

            return UserResponse.model_validate(refreshed)

        # Если пользователь активен или принадлежит другому tenant'у —
        # создание невозможно.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User with email '{payload.email}' already exists",
        )

    password_hash = hash_password(payload.password)

    new_user = await user_repo.create(
        tenant_id=tenant_id,
        email=payload.email,
        password_hash=password_hash,
        full_name=payload.full_name,
        system_role=payload.system_role,
    )
    await db.commit()
    await db.refresh(new_user)

    logger.info(
        "User created",
        user_id=str(new_user.id),
        email=new_user.email,
        tenant_id=str(tenant_id),
        system_role=new_user.system_role,
        created_by=user.id,
    )

    return UserResponse.model_validate(new_user)


@router.put(
    "/tenants/{tenant_id}/users/{target_user_id}",
    response_model=UserResponse,
    summary="Обновить пользователя (только superadmin)",
)
async def update_tenant_user(
    tenant_id: uuid.UUID,
    target_user_id: uuid.UUID,
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> UserResponse:
    """
    Обновить данные пользователя.

    Доступ: только superadmin.

    Можно обновить:
    - full_name;
    - system_role;
    - password;
    - is_active.
    """
    _require_superadmin(user)

    user_repo = UserRepository(db)
    target = await user_repo.get_by_id(target_user_id)

    if target is None or target.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found in this tenant",
        )

    if payload.system_role is not None:
        allowed_roles = {"superadmin", "tenant_admin", "member"}
        if payload.system_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid system_role. Allowed: {', '.join(sorted(allowed_roles))}",
            )

    password_hash: str | None = None
    if payload.password is not None:
        password_hash = hash_password(payload.password)

    if payload.is_active is not None:
        await user_repo.set_active(target_user_id, is_active=payload.is_active)

    updated = await user_repo.update(
        target_user_id,
        full_name=payload.full_name,
        clear_full_name=payload.clear_full_name,
        system_role=payload.system_role,
        password_hash=password_hash,
    )

    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    await db.commit()
    await db.refresh(updated)

    return UserResponse.model_validate(updated)


@router.patch(
    "/tenants/{tenant_id}/users/{target_user_id}/deactivate",
    response_model=UserResponse,
    summary="Деактивировать пользователя (только superadmin)",
)
async def deactivate_tenant_user(
    tenant_id: uuid.UUID,
    target_user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> UserResponse:
    """
    Деактивировать пользователя.

    После деактивации пользователь не сможет войти в систему.
    Данные не удаляются.
    """
    _require_superadmin(user)

    user_repo = UserRepository(db)
    target = await user_repo.get_by_id(target_user_id)

    if target is None or target.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found in this tenant",
        )

    updated = await user_repo.set_active(target_user_id, is_active=False)

    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    await db.commit()
    await db.refresh(updated)

    logger.info(
        "User deactivated",
        user_id=str(target_user_id),
        tenant_id=str(tenant_id),
        deactivated_by=user.id,
    )

    return UserResponse.model_validate(updated)


# ── YAML Instructions ────────────────────────────────────────────────────


@router.get(
    "/yaml-instructions",
    summary="Список YAML-инструкций по типам документов",
    response_model=list[YamlInstructionDTO],
)
async def list_yaml_instructions(
    user: CurrentUser = Depends(get_current_user),
) -> list[YamlInstructionDTO]:
    """
    Перечисляет файлы playbooks/document_types/*.yaml.

    Доступ: superadmin и tenant_admin.
    """
    _require_admin_or_superadmin(user)

    base_dir = Path(settings.PLAYBOOK_DOCUMENT_TYPES_DIR)
    if not base_dir.exists():
        return []

    items: list[YamlInstructionDTO] = []

    for path in sorted(base_dir.glob("*.yaml")):
        try:
            with path.open(encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception as e:
            items.append(
                YamlInstructionDTO(
                    doc_type=path.stem,
                    filename=path.name,
                    checks_count=0,
                    triggers_count=0,
                    dd_request_templates_count=0,
                    has_structured_extraction=False,
                    profiles=None,
                    error=str(e),
                )
            )
            continue

        doc_type = data.get("doc_type") or path.stem
        checks = data.get("checks") or []
        triggers = data.get("conditional_triggers") or []
        dd_templates = data.get("dd_request_templates") or []
        profiles = data.get("profiles") or []

        has_structured = False
        for ch in checks:
            if not isinstance(ch, dict):
                continue
            if ch.get("structured_data") or ch.get("extract") or ch.get("fields"):
                has_structured = True
                break

        items.append(
            YamlInstructionDTO(
                doc_type=doc_type,
                filename=path.name,
                checks_count=len(checks),
                triggers_count=len(triggers),
                dd_request_templates_count=len(dd_templates),
                has_structured_extraction=has_structured,
                profiles=profiles or None,
                error=None,
            )
        )

    return items


