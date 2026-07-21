# tests/unit/api/test_instruction_preview_endpoint.py

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.deps.auth import CurrentUser, get_current_user
from api.endpoints import instruction_preview as instruction_preview_endpoint
from db.session import get_db


def _tenant_admin_user(tenant_id: uuid.UUID) -> CurrentUser:
    return CurrentUser(
        id=str(uuid.uuid4()),
        global_role="tenant_admin",
        tenant_id=tenant_id,
        email="tenant_admin@example.com",
    )


def _version(
    *,
    version_id: uuid.UUID | None = None,
    doc_type_code: str = "nda",
    tenant_id: uuid.UUID | None = None,
):
    return SimpleNamespace(
        id=version_id or uuid.uuid4(),
        doc_type_code=doc_type_code,
        tenant_id=tenant_id,
        owner_scope="platform",
        source_sha256="sha123",
        compiled_payload={
            "checks_v8": [
                {
                    "id": "check_1",
                    "name": "Check 1",
                    "detector_type": "rules",
                    "rules": {"keywords": ["nda"]},
                }
            ]
        },
    )


def _override(
    *,
    override_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
    patch_ops: list | None = None,
    is_stale: bool = False,
):
    return SimpleNamespace(
        id=override_id or uuid.uuid4(),
        tenant_id=tenant_id or uuid.uuid4(),
        patch_ops=patch_ops or [],
        is_stale=is_stale,
    )


def _build_test_app(
    *,
    db_session: MagicMock,
    user: CurrentUser,
) -> TestClient:
    app = FastAPI()
    app.include_router(instruction_preview_endpoint.router, prefix="/api/v1")

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


class TestInstructionPreviewEndpoint:
    def test_preview_base_version_success(self, monkeypatch) -> None:
        tenant_id = uuid.uuid4()
        db = MagicMock()

        version = _version()
        repo = MagicMock()
        repo.get_by_id = AsyncMock(return_value=version)

        monkeypatch.setattr(
            instruction_preview_endpoint,
            "DocumentTypeInstructionVersionRepository",
            lambda db: repo,
        )
        monkeypatch.setattr(
            instruction_preview_endpoint,
            "InstructionOverrideRepository",
            lambda db: MagicMock(),
        )

        client = _build_test_app(
            db_session=db,
            user=_tenant_admin_user(tenant_id),
        )

        response = client.post(
            "/api/v1/instruction-preview",
            json={
                "kind": "doc_type",
                "doc_type_code": "nda",
                "base_version_id": str(version.id),
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["valid"] is True
        assert body["base_version_id"] == str(version.id)
        assert body["base_hash"] == "sha123"
        assert body["checks_count"] == 1

    def test_preview_missing_base_version_returns_404(self, monkeypatch) -> None:
        tenant_id = uuid.uuid4()
        db = MagicMock()

        repo = MagicMock()
        repo.get_by_id = AsyncMock(return_value=None)

        monkeypatch.setattr(
            instruction_preview_endpoint,
            "DocumentTypeInstructionVersionRepository",
            lambda db: repo,
        )
        monkeypatch.setattr(
            instruction_preview_endpoint,
            "InstructionOverrideRepository",
            lambda db: MagicMock(),
        )

        client = _build_test_app(
            db_session=db,
            user=_tenant_admin_user(tenant_id),
        )

        response = client.post(
            "/api/v1/instruction-preview",
            json={
                "kind": "doc_type",
                "doc_type_code": "nda",
                "base_version_id": str(uuid.uuid4()),
            },
        )

        assert response.status_code == 404

    def test_preview_patch_conflict_returns_valid_false(self, monkeypatch) -> None:
        tenant_id = uuid.uuid4()
        db = MagicMock()

        version = _version()
        repo = MagicMock()
        repo.get_by_id = AsyncMock(return_value=version)

        monkeypatch.setattr(
            instruction_preview_endpoint,
            "DocumentTypeInstructionVersionRepository",
            lambda db: repo,
        )
        monkeypatch.setattr(
            instruction_preview_endpoint,
            "InstructionOverrideRepository",
            lambda db: MagicMock(),
        )

        client = _build_test_app(
            db_session=db,
            user=_tenant_admin_user(tenant_id),
        )

        response = client.post(
            "/api/v1/instruction-preview",
            json={
                "kind": "doc_type",
                "doc_type_code": "nda",
                "base_version_id": str(version.id),
                "draft_patch_ops": [
                    {"op": "replace", "path": "/does/not/exist", "value": "x"}
                ],
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["valid"] is False
        assert body["errors"]

    def test_preview_tenant_override_access_violation_returns_valid_false(self, monkeypatch) -> None:
        tenant_id = uuid.uuid4()
        other_tenant_id = uuid.uuid4()
        db = MagicMock()

        version = _version()
        version_repo = MagicMock()
        version_repo.get_by_id = AsyncMock(return_value=version)

        override_repo = MagicMock()
        override_repo.get_by_id = AsyncMock(
            return_value=_override(
                tenant_id=other_tenant_id,
                patch_ops=[{"op": "replace", "path": "/name", "value": "x"}],
            )
        )

        monkeypatch.setattr(
            instruction_preview_endpoint,
            "DocumentTypeInstructionVersionRepository",
            lambda db: version_repo,
        )
        monkeypatch.setattr(
            instruction_preview_endpoint,
            "InstructionOverrideRepository",
            lambda db: override_repo,
        )

        client = _build_test_app(
            db_session=db,
            user=_tenant_admin_user(tenant_id),
        )

        response = client.post(
            "/api/v1/instruction-preview",
            json={
                "kind": "doc_type",
                "doc_type_code": "nda",
                "base_version_id": str(version.id),
                "tenant_override_id": str(uuid.uuid4()),
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["valid"] is False
        assert "not accessible" in body["errors"][0]


        