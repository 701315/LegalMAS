from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api.deps.auth import CurrentUser, get_current_user
from api.endpoints import instruction_versions as instruction_versions_endpoint
from db.session import get_db
from services.instruction_publishing_service import (
    DraftValidationError,
    DuplicateInstructionContentError,
    ImmutableVersionError,
)


def _superadmin_user() -> CurrentUser:
    return CurrentUser(
        id=str(uuid.uuid4()),
        global_role="superadmin",
        tenant_id=uuid.uuid4(),
        email="admin@example.com",
    )


def _member_user() -> CurrentUser:
    return CurrentUser(
        id=str(uuid.uuid4()),
        global_role="member",
        tenant_id=uuid.uuid4(),
        email="member@example.com",
    )


def _version(
    *,
    version_id: uuid.UUID | None = None,
    doc_type_code: str = "nda",
    version_status: str = "draft",
):
    return SimpleNamespace(
        id=version_id or uuid.uuid4(),
        doc_type_code=doc_type_code,
        name="NDA",
        source_format="yaml",
        source_sha256="sha123",
        version_status=version_status,
        immutable_content_hash=None,
        validation_report={"is_valid": True, "checks_count": 2},
        parent_version_id=None,
        published_at=None,
        created_by=uuid.uuid4(),
        change_summary="summary",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        source_yaml="checks_v8: []",
        source_path="/tmp/nda.yaml",
        git_commit="abcdef",
        semver="1.0.0",
        compiled_payload={"checks_v8": []},
    )


def _compiled(*, is_valid: bool = True, checks_count: int = 2):
    return SimpleNamespace(
        is_valid=is_valid,
        checks_count=checks_count,
        validation_report={
            "is_valid": is_valid,
            "checks_count": checks_count,
            "diagnostics": [],
        },
    )


def _catalog_item(
    *,
    doc_type_code: str = "nda",
    name: str = "NDA",
):
    return SimpleNamespace(
        doc_type_code=doc_type_code,
        name=name,
        category="contract",
        risk_level="medium",
        language="en",
        jurisdiction="EN",
        is_registry_available=True,
        total_versions_count=3,
        draft_versions_count=1,
        has_published=True,
        latest_version_id=str(uuid.uuid4()),
        latest_version_status="draft",
        latest_version_updated_at=datetime.now(UTC),
        latest_published_version_id=str(uuid.uuid4()),
        latest_published_at=datetime.now(UTC),
        latest_published_immutable_content_hash="hash123",
        latest_draft_version_id=str(uuid.uuid4()),
        latest_draft_is_valid=False,
        latest_draft_updated_at=datetime.now(UTC),
    )


def _build_test_app(
    db_session: MagicMock,
    publishing_service: MagicMock,
    catalog_service: MagicMock,
    user: CurrentUser,
) -> TestClient:
    app = FastAPI()
    app.include_router(instruction_versions_endpoint.router, prefix="/api/v1")

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[
        instruction_versions_endpoint.get_instruction_publishing_service
    ] = lambda: publishing_service
    app.dependency_overrides[
        instruction_versions_endpoint.get_instruction_catalog_service
    ] = lambda: catalog_service

    return TestClient(app)


class TestInstructionVersionsEndpoints:
    def test_list_catalog_success(self) -> None:
        db = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        publishing_service = MagicMock()
        catalog_service = MagicMock()
        catalog_service.list_doc_type_catalog = AsyncMock(
            return_value=[_catalog_item()]
        )

        client = _build_test_app(
            db,
            publishing_service,
            catalog_service,
            _superadmin_user(),
        )
        response = client.get("/api/v1/admin/instructions/doc-types")

        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) == 1
        assert body["items"][0]["doc_type_code"] == "nda"
        assert body["items"][0]["total_versions_count"] == 3
        assert body["items"][0]["latest_draft_is_valid"] is False

    def test_list_versions_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        db = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        publishing_service = MagicMock()
        catalog_service = MagicMock()
        version = _version(version_status="published")

        async def fake_list_by_doc_type_code(self, doc_type_code: str):
            return [version]

        monkeypatch.setattr(
            instruction_versions_endpoint.DocumentTypeInstructionVersionRepository,
            "list_by_doc_type_code",
            fake_list_by_doc_type_code,
        )

        client = _build_test_app(
            db,
            publishing_service,
            catalog_service,
            _superadmin_user(),
        )
        response = client.get("/api/v1/admin/instructions/doc-types/nda/versions")

        assert response.status_code == 200
        body = response.json()
        assert body["doc_type_code"] == "nda"
        assert len(body["items"]) == 1
        assert body["items"][0]["version_status"] == "published"

    def test_get_version_detail_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        db = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        publishing_service = MagicMock()
        catalog_service = MagicMock()
        version = _version()

        async def fake_get_by_id(self, version_id):
            return version

        monkeypatch.setattr(
            instruction_versions_endpoint.DocumentTypeInstructionVersionRepository,
            "get_by_id",
            fake_get_by_id,
        )

        client = _build_test_app(
            db,
            publishing_service,
            catalog_service,
            _superadmin_user(),
        )
        response = client.get(f"/api/v1/admin/instruction-versions/{version.id}")

        assert response.status_code == 200
        body = response.json()
        assert body["item"]["id"] == str(version.id)
        assert body["item"]["source_yaml"] == "checks_v8: []"
        assert body["item"]["compiled_payload"] == {"checks_v8": []}
        assert body["item"]["checks_count"] == 2

    def test_get_version_not_found(self, monkeypatch: pytest.MonkeyPatch) -> None:
        db = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        publishing_service = MagicMock()
        catalog_service = MagicMock()

        async def fake_get_by_id(self, version_id):
            return None

        monkeypatch.setattr(
            instruction_versions_endpoint.DocumentTypeInstructionVersionRepository,
            "get_by_id",
            fake_get_by_id,
        )

        client = _build_test_app(
            db,
            publishing_service,
            catalog_service,
            _superadmin_user(),
        )
        response = client.get(f"/api/v1/admin/instruction-versions/{uuid.uuid4()}")

        assert response.status_code == 404

    def test_create_draft_success(self) -> None:
        db = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        publishing_service = MagicMock()
        catalog_service = MagicMock()
        version = _version()
        publishing_service.create_draft = AsyncMock(return_value=version)

        client = _build_test_app(
            db,
            publishing_service,
            catalog_service,
            _superadmin_user(),
        )
        response = client.post(
            "/api/v1/admin/instructions/doc-types/nda/drafts",
            json={
                "source_yaml": "checks_v8: []",
                "name": "NDA draft",
                "change_summary": "initial",
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["item"]["doc_type_code"] == "nda"
        assert body["item"]["version_status"] == "draft"
        db.commit.assert_awaited_once()

    def test_create_draft_duplicate_returns_409(self) -> None:
        db = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        publishing_service = MagicMock()
        catalog_service = MagicMock()
        publishing_service.create_draft = AsyncMock(
            side_effect=DuplicateInstructionContentError("duplicate")
        )

        client = _build_test_app(
            db,
            publishing_service,
            catalog_service,
            _superadmin_user(),
        )
        response = client.post(
            "/api/v1/admin/instructions/doc-types/nda/drafts",
            json={"source_yaml": "checks_v8: []"},
        )

        assert response.status_code == 409
        db.rollback.assert_awaited_once()

    def test_update_draft_immutable_returns_409(self) -> None:
        db = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        publishing_service = MagicMock()
        catalog_service = MagicMock()
        publishing_service.update_draft = AsyncMock(
            side_effect=ImmutableVersionError("immutable")
        )

        client = _build_test_app(
            db,
            publishing_service,
            catalog_service,
            _superadmin_user(),
        )
        response = client.patch(
            f"/api/v1/admin/instruction-versions/{uuid.uuid4()}",
            json={"source_yaml": "checks_v8: []"},
        )

        assert response.status_code == 409
        db.rollback.assert_awaited_once()

    def test_validate_draft_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        db = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        publishing_service = MagicMock()
        catalog_service = MagicMock()
        version = _version()
        compiled = _compiled(is_valid=True, checks_count=3)

        publishing_service.validate_draft = AsyncMock(return_value=compiled)

        async def fake_get_by_id(self, version_id):
            return version

        monkeypatch.setattr(
            instruction_versions_endpoint.DocumentTypeInstructionVersionRepository,
            "get_by_id",
            fake_get_by_id,
        )

        client = _build_test_app(
            db,
            publishing_service,
            catalog_service,
            _superadmin_user(),
        )
        response = client.post(
            f"/api/v1/admin/instruction-versions/{version.id}/validate"
        )

        assert response.status_code == 200
        body = response.json()
        assert body["is_valid"] is True
        assert body["checks_count"] == 3
        assert body["item"]["id"] == str(version.id)
        db.commit.assert_awaited_once()

    def test_publish_draft_validation_error_returns_422(self) -> None:
        db = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        publishing_service = MagicMock()
        catalog_service = MagicMock()
        publishing_service.publish_draft = AsyncMock(
            side_effect=DraftValidationError("validation failed")
        )

        client = _build_test_app(
            db,
            publishing_service,
            catalog_service,
            _superadmin_user(),
        )
        response = client.post(
            f"/api/v1/admin/instruction-versions/{uuid.uuid4()}/publish"
        )

        assert response.status_code == 422
        db.rollback.assert_awaited_once()

    def test_archive_version_success(self) -> None:
        db = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        publishing_service = MagicMock()
        catalog_service = MagicMock()
        version = _version(version_status="archived")
        publishing_service.archive_version = AsyncMock(return_value=version)

        client = _build_test_app(
            db,
            publishing_service,
            catalog_service,
            _superadmin_user(),
        )
        response = client.post(
            f"/api/v1/admin/instruction-versions/{version.id}/archive"
        )

        assert response.status_code == 200
        body = response.json()
        assert body["item"]["version_status"] == "archived"
        db.commit.assert_awaited_once()

    def test_non_admin_forbidden(self) -> None:
        db = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        publishing_service = MagicMock()
        catalog_service = MagicMock()

        client = _build_test_app(
            db,
            publishing_service,
            catalog_service,
            _member_user(),
        )
        response = client.get("/api/v1/admin/instructions/doc-types")

        assert response.status_code == 403


        