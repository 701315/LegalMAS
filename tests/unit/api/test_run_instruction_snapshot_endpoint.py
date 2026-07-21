# tests/unit/api/test_run_instruction_snapshot_endpoint.py

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import get_scoped_run
from api.endpoints import runs as runs_endpoint
from db.session import get_db


def _tenant_admin_user(tenant_id: uuid.UUID) -> CurrentUser:
    return CurrentUser(
        id=str(uuid.uuid4()),
        global_role="tenant_admin",
        tenant_id=tenant_id,
        email="tenant_admin@example.com",
    )


def _build_test_app(
    *,
    db_session: MagicMock,
    user: CurrentUser,
    run_obj,
) -> TestClient:
    app = FastAPI()
    app.include_router(runs_endpoint.router, prefix="/api/v1")

    async def override_get_db():
        yield db_session

    # ВАЖНО: dependency override должен иметь явную сигнатуру,
    # а не **kwargs, иначе FastAPI считает kwargs query param.
    async def fake_get_scoped_run(run_id: uuid.UUID):
        return run_obj

    # ВАЖНО: require_project_role вызывается внутри endpoint напрямую,
    # это НЕ Depends, поэтому patch нужен через module attribute.
    async def fake_require_project_role(**kwargs):
        return None

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_scoped_run] = fake_get_scoped_run

    runs_endpoint.require_project_role = fake_require_project_role

    return TestClient(app)


class TestRunInstructionSnapshotEndpoint:
    def test_snapshot_strict_run_is_reproducible(self) -> None:
        tenant_id = uuid.uuid4()
        deal_id = uuid.uuid4()
        run_id = uuid.uuid4()

        run_obj = SimpleNamespace(
            id=run_id,
            deal_id=deal_id,
            snapshot_schema_version=1,
            instruction_versions={"nda": str(uuid.uuid4())},
            instruction_snapshot_manifest={
                "nda": {
                    "version_id": str(uuid.uuid4()),
                    "content_hash": "sha123",
                    "override_id": None,
                }
            },
            instruction_snapshot_payload={"nda": {"checks_v8": []}},
            execution_manifest={"schema_version": 1},
        )

        client = _build_test_app(
            db_session=MagicMock(),
            user=_tenant_admin_user(tenant_id),
            run_obj=run_obj,
        )

        response = client.get(f"/api/v1/runs/{run_id}/instruction-snapshot")

        assert response.status_code == 200
        body = response.json()
        assert body["run_id"] == str(run_id)
        assert body["deal_id"] == str(deal_id)
        assert body["snapshot_schema_version"] == 1
        assert body["is_reproducible"] is True
        assert body["doc_types_count"] == 1

    def test_snapshot_legacy_run_not_reproducible(self) -> None:
        tenant_id = uuid.uuid4()
        deal_id = uuid.uuid4()
        run_id = uuid.uuid4()

        run_obj = SimpleNamespace(
            id=run_id,
            deal_id=deal_id,
            snapshot_schema_version=None,
            instruction_versions={},
            instruction_snapshot_manifest={},
            instruction_snapshot_payload={},
            execution_manifest=None,
        )

        client = _build_test_app(
            db_session=MagicMock(),
            user=_tenant_admin_user(tenant_id),
            run_obj=run_obj,
        )

        response = client.get(f"/api/v1/runs/{run_id}/instruction-snapshot")

        assert response.status_code == 200
        body = response.json()
        assert body["is_reproducible"] is False
        assert body["warning"] is not None


        