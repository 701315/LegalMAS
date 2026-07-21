# tests/unit/api/test_instruction_overrides_endpoints.py

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api.deps.auth import CurrentUser, get_current_user
from api.endpoints import instruction_overrides as instruction_overrides_endpoint
from api.endpoints.instruction_overrides import get_override_service
from db.session import get_db
from engine.instructions.override_service import PatchConflictError


def _superadmin_user() -> CurrentUser:
    return CurrentUser(
        id=str(uuid.uuid4()),
        global_role="superadmin",
        tenant_id=uuid.uuid4(),
        email="admin@example.com",
    )


def _tenant_admin_user(tenant_id: uuid.UUID) -> CurrentUser:
    return CurrentUser(
        id=str(uuid.uuid4()),
        global_role="tenant_admin",
        tenant_id=tenant_id,
        email="tenant_admin@example.com",
    )


def _member_user(tenant_id: uuid.UUID) -> CurrentUser:
    return CurrentUser(
        id=str(uuid.uuid4()),
        global_role="member",
        tenant_id=tenant_id,
        email="member@example.com",
    )


def _override(
    *,
    override_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
    deal_id: uuid.UUID | None = None,
    override_scope: str = "tenant",
    status: str = "draft",
    is_stale: bool = False,
):
    return SimpleNamespace(
        id=override_id or uuid.uuid4(),
        instruction_version_id=uuid.uuid4(),
        override_scope=override_scope,
        tenant_id=tenant_id or uuid.uuid4(),
        deal_id=deal_id,
        status=status,
        base_content_hash="sha123",
        patch_ops=[{"op": "replace", "path": "/name", "value": "New Name"}],
        is_stale=is_stale,
        change_summary="summary",
        created_by=uuid.uuid4(),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _build_test_app(
    *,
    db_session: MagicMock,
    override_service: MagicMock,
    user: CurrentUser,
    deal_obj=None,
) -> TestClient:
    app = FastAPI()
    app.include_router(instruction_overrides_endpoint.router, prefix="/api/v1")

    async def override_get_db():
        yield db_session

    async def fake_get_scoped_deal(*args, **kwargs):
        return deal_obj

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_override_service] = lambda: override_service

    # Если нужен deal object — patch напрямую функцию в endpoint module
    if deal_obj is not None:
        instruction_overrides_endpoint.get_scoped_deal = fake_get_scoped_deal

    return TestClient(app)


class TestInstructionOverridesEndpoints:
    def test_list_tenant_overrides_success_for_tenant_admin(self) -> None:
        tenant_id = uuid.uuid4()
        db = MagicMock()
        override_service = MagicMock()
        override_service.override_repo.list_for_tenant_scope = AsyncMock(
            return_value=[_override(tenant_id=tenant_id)]
        )

        client = _build_test_app(
            db_session=db,
            override_service=override_service,
            user=_tenant_admin_user(tenant_id),
        )

        response = client.get(f"/api/v1/tenants/{tenant_id}/instruction-overrides")
        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) == 1
        assert body["items"][0]["tenant_id"] == str(tenant_id)

    def test_list_tenant_overrides_forbidden_for_member(self) -> None:
        tenant_id = uuid.uuid4()
        db = MagicMock()
        override_service = MagicMock()

        client = _build_test_app(
            db_session=db,
            override_service=override_service,
            user=_member_user(tenant_id),
        )

        response = client.get(f"/api/v1/tenants/{tenant_id}/instruction-overrides")
        assert response.status_code == 403

    def test_create_tenant_override_draft_success(self) -> None:
        tenant_id = uuid.uuid4()
        db = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        created = _override(tenant_id=tenant_id, override_scope="tenant", status="draft")

        override_service = MagicMock()
        override_service.create_tenant_override_draft = AsyncMock(return_value=created)

        client = _build_test_app(
            db_session=db,
            override_service=override_service,
            user=_tenant_admin_user(tenant_id),
        )

        response = client.post(
            f"/api/v1/tenants/{tenant_id}/instruction-overrides/draft",
            json={
                "instruction_version_id": str(uuid.uuid4()),
                "patch_ops": [{"op": "replace", "path": "/name", "value": "X"}],
                "change_summary": "draft override",
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["item"]["override_scope"] == "tenant"
        assert body["item"]["status"] == "draft"
        db.commit.assert_awaited_once()

    def test_create_tenant_override_draft_patch_conflict_returns_422(self) -> None:
        tenant_id = uuid.uuid4()
        db = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        override_service = MagicMock()
        override_service.create_tenant_override_draft = AsyncMock(
            side_effect=PatchConflictError("conflict")
        )

        client = _build_test_app(
            db_session=db,
            override_service=override_service,
            user=_tenant_admin_user(tenant_id),
        )

        response = client.post(
            f"/api/v1/tenants/{tenant_id}/instruction-overrides/draft",
            json={
                "instruction_version_id": str(uuid.uuid4()),
                "patch_ops": [{"op": "replace", "path": "/bad", "value": "X"}],
            },
        )

        assert response.status_code == 422
        db.rollback.assert_awaited_once()

    def test_validate_tenant_override_success(self) -> None:
        tenant_id = uuid.uuid4()
        db = MagicMock()

        override_service = MagicMock()
        override_service.validate_override = AsyncMock(
            return_value={
                "is_valid": True,
                "errors": [],
                "warnings": [],
                "checks_count": 2,
                "effective_payload": {"checks_v8": []},
                "validation_report": {"is_valid": True},
            }
        )

        client = _build_test_app(
            db_session=db,
            override_service=override_service,
            user=_tenant_admin_user(tenant_id),
        )

        override_id = uuid.uuid4()
        response = client.post(
            f"/api/v1/tenants/{tenant_id}/instruction-overrides/{override_id}/validate"
        )

        assert response.status_code == 200
        body = response.json()
        assert body["override_id"] == str(override_id)
        assert body["is_valid"] is True
        assert body["checks_count"] == 2

    def test_activate_tenant_override_success(self) -> None:
        tenant_id = uuid.uuid4()
        db = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        active = _override(
            tenant_id=tenant_id,
            override_scope="tenant",
            status="active",
        )

        override_service = MagicMock()
        override_service.activate_override = AsyncMock(return_value=active)

        client = _build_test_app(
            db_session=db,
            override_service=override_service,
            user=_tenant_admin_user(tenant_id),
        )

        response = client.post(
            f"/api/v1/tenants/{tenant_id}/instruction-overrides/{active.id}/activate"
        )

        assert response.status_code == 200
        body = response.json()
        assert body["item"]["status"] == "active"
        db.commit.assert_awaited_once()

    def test_list_deal_overrides_success(self) -> None:
        tenant_id = uuid.uuid4()
        deal_id = uuid.uuid4()
        db = MagicMock()

        deal_obj = SimpleNamespace(id=deal_id, tenant_id=tenant_id)

        override_service = MagicMock()
        override_service.override_repo.list_for_deal = AsyncMock(
            return_value=[_override(tenant_id=tenant_id, deal_id=deal_id, override_scope="deal")]
        )

        # bypass project role guard
        instruction_overrides_endpoint.require_project_role = AsyncMock(return_value=None)

        client = _build_test_app(
            db_session=db,
            override_service=override_service,
            user=_tenant_admin_user(tenant_id),
            deal_obj=deal_obj,
        )

        response = client.get(f"/api/v1/deals/{deal_id}/instruction-overrides")
        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) == 1
        assert body["items"][0]["override_scope"] == "deal"

    def test_create_deal_override_requires_editor_or_admin(self) -> None:
        tenant_id = uuid.uuid4()
        deal_id = uuid.uuid4()
        db = MagicMock()

        deal_obj = SimpleNamespace(id=deal_id, tenant_id=tenant_id)

        async def forbid_project_role(*args, **kwargs):
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="Insufficient project role")

        instruction_overrides_endpoint.require_project_role = forbid_project_role

        override_service = MagicMock()

        client = _build_test_app(
            db_session=db,
            override_service=override_service,
            user=_member_user(tenant_id),
            deal_obj=deal_obj,
        )

        response = client.post(
            f"/api/v1/deals/{deal_id}/instruction-overrides/draft",
            json={
                "instruction_version_id": str(uuid.uuid4()),
                "patch_ops": [{"op": "replace", "path": "/name", "value": "X"}],
            },
        )
        assert response.status_code == 403

    def test_rebase_deal_override_success(self) -> None:
        tenant_id = uuid.uuid4()
        deal_id = uuid.uuid4()
        db = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        deal_obj = SimpleNamespace(id=deal_id, tenant_id=tenant_id)
        rebased = _override(
            tenant_id=tenant_id,
            deal_id=deal_id,
            override_scope="deal",
            status="draft",
            is_stale=False,
        )

        override_service = MagicMock()
        override_service.rebase_override = AsyncMock(return_value=rebased)

        instruction_overrides_endpoint.require_project_role = AsyncMock(return_value=None)

        client = _build_test_app(
            db_session=db,
            override_service=override_service,
            user=_tenant_admin_user(tenant_id),
            deal_obj=deal_obj,
        )

        response = client.post(
            f"/api/v1/deals/{deal_id}/instruction-overrides/{rebased.id}/rebase",
            json={
                "new_base_version_id": str(uuid.uuid4()),
                "new_patch_ops": [{"op": "replace", "path": "/name", "value": "rebased"}],
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["item"]["override_scope"] == "deal"
        db.commit.assert_awaited_once()



        