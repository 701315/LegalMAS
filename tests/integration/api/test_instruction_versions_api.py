# tests/integration/api/test_instruction_versions_api.py

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.deps.auth import CurrentUser, get_current_user
from db.session import get_db


DOC_TYPE_CODE = "nda"
VERSION_ID = uuid.uuid4()


def make_user(role: str) -> CurrentUser:
    return CurrentUser(
        id=str(uuid.uuid4()),
        global_role=role,
        tenant_id=uuid.uuid4(),
        email=f"{role}@example.com",
    )


def make_catalog_item() -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        doc_type_code=DOC_TYPE_CODE,
        name="NDA",
        category="contract",
        risk_level="medium",
        language="en",
        jurisdiction="EN",
        is_registry_available=True,
        total_versions_count=2,
        draft_versions_count=1,
        has_published=True,
        latest_version_id=str(VERSION_ID),
        latest_version_status="draft",
        latest_version_updated_at=now,
        latest_published_version_id=str(uuid.uuid4()),
        latest_published_at=now,
        latest_published_immutable_content_hash="hash-published",
        latest_draft_version_id=str(VERSION_ID),
        latest_draft_is_valid=True,
        latest_draft_updated_at=now,
    )


def make_version(*, updated_at: datetime | None = None, version_id: uuid.UUID | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=version_id or VERSION_ID,
        doc_type_code=DOC_TYPE_CODE,
        name="NDA Draft",
        source_format="yaml",
        source_sha256="sha123",
        version_status="draft",
        immutable_content_hash=None,
        validation_report={"is_valid": True, "checks_count": 2},
        parent_version_id=None,
        published_at=None,
        created_by=uuid.uuid4(),
        change_summary="initial",
        created_at=datetime.now(UTC),
        updated_at=updated_at or datetime.now(UTC),
        source_yaml="checks_v8: []",
        source_path="instructions/nda.yaml",
        git_commit="abcdef",
        semver="0.1.0",
        compiled_payload={"checks_v8": []},
    )


@pytest.fixture(autouse=True)
def _reset_overrides():
    app.dependency_overrides = {}
    yield
    app.dependency_overrides = {}


@pytest.fixture
def client():
    return TestClient(app)


def _override_db(fake_session=None):
    app.dependency_overrides[get_db] = lambda: fake_session or MagicMock()


class TestInstructionVersionsApi:
    def test_requires_auth_for_catalog(self, client: TestClient):
        response = client.get("/api/v1/admin/instructions/doc-types")
        assert response.status_code == 401

    def test_non_superadmin_forbidden_for_catalog(self, client: TestClient):
        app.dependency_overrides[get_current_user] = lambda: make_user("member")
        _override_db()

        response = client.get(
            "/api/v1/admin/instructions/doc-types",
            headers={"Authorization": "Bearer test"},
        )

        assert response.status_code == 403

    def test_superadmin_can_list_catalog(self, client: TestClient):
        app.dependency_overrides[get_current_user] = lambda: make_user("superadmin")
        _override_db()

        with patch(
            "api.endpoints.instruction_versions.InstructionCatalogService"
        ) as service_cls:
            fake_service = MagicMock()
            fake_service.list_doc_type_catalog = AsyncMock(return_value=[make_catalog_item()])
            service_cls.return_value = fake_service

            response = client.get(
                "/api/v1/admin/instructions/doc-types",
                headers={"Authorization": "Bearer test"},
            )

        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) == 1
        assert body["items"][0]["doc_type_code"] == DOC_TYPE_CODE

    def test_superadmin_can_list_versions_for_doc_type(self, client: TestClient):
        app.dependency_overrides[get_current_user] = lambda: make_user("superadmin")
        _override_db()

        version = make_version()

        with patch(
            "api.endpoints.instruction_versions.DocumentTypeInstructionVersionRepository"
        ) as repo_cls:
            fake_repo = MagicMock()
            fake_repo.list_by_doc_type_code = AsyncMock(return_value=[version])
            repo_cls.return_value = fake_repo

            response = client.get(
                f"/api/v1/admin/instructions/doc-types/{DOC_TYPE_CODE}/versions",
                headers={"Authorization": "Bearer test"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["doc_type_code"] == DOC_TYPE_CODE
        assert len(body["items"]) == 1

    def test_detail_sets_etag(self, client: TestClient):
        app.dependency_overrides[get_current_user] = lambda: make_user("superadmin")
        _override_db()

        version = make_version(updated_at=datetime(2026, 7, 22, 10, 0, 0, tzinfo=UTC))

        with patch(
            "api.endpoints.instruction_versions.DocumentTypeInstructionVersionRepository"
        ) as repo_cls:
            fake_repo = MagicMock()
            fake_repo.get_by_id = AsyncMock(return_value=version)
            repo_cls.return_value = fake_repo

            response = client.get(
                f"/api/v1/admin/instruction-versions/{version.id}",
                headers={"Authorization": "Bearer test"},
            )

        assert response.status_code == 200
        assert "etag" in response.headers
        assert response.headers["etag"]

    def test_update_requires_if_match(self, client: TestClient):
        app.dependency_overrides[get_current_user] = lambda: make_user("superadmin")
        _override_db()

        version = make_version()

        with patch(
            "api.endpoints.instruction_versions.DocumentTypeInstructionVersionRepository"
        ) as repo_cls:
            fake_repo = MagicMock()
            fake_repo.get_by_id = AsyncMock(return_value=version)
            repo_cls.return_value = fake_repo

            response = client.patch(
                f"/api/v1/admin/instruction-versions/{version.id}",
                headers={"Authorization": "Bearer test"},
                json={"source_yaml": "checks_v8: [1]"},
            )

        assert response.status_code == 428

    def test_update_rejects_stale_if_match(self, client: TestClient):
        app.dependency_overrides[get_current_user] = lambda: make_user("superadmin")
        _override_db()

        version = make_version(updated_at=datetime(2026, 7, 22, 10, 0, 0, tzinfo=UTC))

        with patch(
            "api.endpoints.instruction_versions.DocumentTypeInstructionVersionRepository"
        ) as repo_cls:
            fake_repo = MagicMock()
            fake_repo.get_by_id = AsyncMock(return_value=version)
            repo_cls.return_value = fake_repo

            response = client.patch(
                f"/api/v1/admin/instruction-versions/{version.id}",
                headers={
                    "Authorization": "Bearer test",
                    "If-Match": '"stale-etag"',
                },
                json={"source_yaml": "checks_v8: [1]"},
            )

        assert response.status_code == 412

    def test_update_accepts_current_if_match_and_returns_etag(self, client: TestClient):
        app.dependency_overrides[get_current_user] = lambda: make_user("superadmin")
        fake_db = MagicMock()
        fake_db.commit = AsyncMock()
        fake_db.rollback = AsyncMock()
        fake_db.refresh = AsyncMock()
        _override_db(fake_db)

        version = make_version(updated_at=datetime(2026, 7, 22, 10, 0, 0, tzinfo=UTC))
        updated_version = make_version(
            version_id=version.id,
            updated_at=datetime(2026, 7, 22, 10, 5, 0, tzinfo=UTC),
        )

        with patch(
            "api.endpoints.instruction_versions.DocumentTypeInstructionVersionRepository"
        ) as repo_cls, patch(
            "api.endpoints.instruction_versions.InstructionPublishingService"
        ) as service_cls:
            fake_repo = MagicMock()
            fake_repo.get_by_id = AsyncMock(side_effect=[version, version])
            repo_cls.return_value = fake_repo

            fake_service = MagicMock()
            fake_service.update_draft = AsyncMock(return_value=updated_version)
            service_cls.return_value = fake_service

            detail_response = client.get(
                f"/api/v1/admin/instruction-versions/{version.id}",
                headers={"Authorization": "Bearer test"},
            )
            assert detail_response.status_code == 200
            etag = detail_response.headers["etag"]

            patch_response = client.patch(
                f"/api/v1/admin/instruction-versions/{version.id}",
                headers={
                    "Authorization": "Bearer test",
                    "If-Match": etag,
                },
                json={"source_yaml": "checks_v8: [1]"},
            )

        assert patch_response.status_code == 200
        assert "etag" in patch_response.headers
        assert patch_response.headers["etag"] != etag


        