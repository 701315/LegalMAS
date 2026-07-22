from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.deps.auth import get_current_user
from api.endpoints.instruction_versions import (
    get_db,
    get_instruction_catalog_service,
    get_instruction_editor_service,
    get_instruction_publishing_service,
    router as instruction_versions_router,
)


class FakeAsyncSession:
    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def refresh(self, obj) -> None:
        return None


class FakeVersion:
    def __init__(
        self,
        *,
        id: uuid.UUID,
        doc_type_code: str = "nda",
        name: str | None = "NDA base draft",
        source_yaml: str = "checks_v8: []\n",
        source_path: str | None = "instructions/nda.yaml",
        git_commit: str | None = "manual-test",
        semver: str | None = "0.1.0",
        version_status: str = "draft",
        source_format: str = "yaml",
        source_sha256: str = "8cef80db0b72fc2522862e3915fc1f5eb7c299d1854ce7489017b8435d66231b",
        immutable_content_hash: str | None = None,
        validation_report: dict | None = None,
        parent_version_id: uuid.UUID | None = None,
        published_at: datetime | None = None,
        created_by: uuid.UUID | None = uuid.UUID("22222222-2222-2222-2222-222222222222"),
        change_summary: str | None = "create initial draft",
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        compiled_payload: dict | None = None,
        checks_count: int | None = 0,
    ) -> None:
        now = datetime.now(timezone.utc)
        self.id = id
        self.doc_type_code = doc_type_code
        self.name = name
        self.source_yaml = source_yaml
        self.source_path = source_path
        self.git_commit = git_commit
        self.semver = semver
        self.version_status = version_status
        self.source_format = source_format
        self.source_sha256 = source_sha256
        self.immutable_content_hash = immutable_content_hash
        self.validation_report = validation_report or {
            "is_valid": True,
            "diagnostics": [
                {
                    "path": "checks",
                    "level": "warning",
                    "message": "Instruction compiled successfully but no checks were produced for validation trigger set.",
                }
            ],
            "checks_count": 0,
            "validation_triggers": [],
        }
        self.parent_version_id = parent_version_id
        self.published_at = published_at
        self.created_by = created_by
        self.change_summary = change_summary
        self.created_at = created_at or now
        self.updated_at = updated_at or now
        self.compiled_payload = compiled_payload or {"checks_v8": []}
        self.checks_count = checks_count


class FakeVersionRepo:
    storage: dict[uuid.UUID, FakeVersion] = {}

    def __init__(self, db) -> None:
        self.db = db

    async def get_by_id(self, version_id: uuid.UUID):
        return self.storage.get(version_id)

    async def list_by_doc_type_code(self, doc_type_code: str):
        return [v for v in self.storage.values() if v.doc_type_code == doc_type_code]


class FakeCatalogService:
    async def list_doc_type_catalog(self):
        first_id = next(iter(FakeVersionRepo.storage.keys()))
        first_version = FakeVersionRepo.storage[first_id]
        return [
            SimpleNamespace(
                doc_type_code="nda",
                name="NDA",
                category="contracts",
                risk_level="medium",
                language="en",
                jurisdiction="us",
                is_registry_available=True,
                total_versions_count=1,
                draft_versions_count=1,
                has_published=False,
                latest_version_id=str(first_id),
                latest_version_status="draft",
                latest_version_updated_at=first_version.updated_at,
                latest_published_version_id=None,
                latest_published_at=None,
                latest_published_immutable_content_hash=None,
                latest_draft_version_id=str(first_id),
                latest_draft_is_valid=True,
                latest_draft_updated_at=first_version.updated_at,
            )
        ]


class FakePublishingService:
    async def create_draft(
        self,
        *,
        doc_type_code: str,
        source: str,
        name: str | None,
        source_path: str | None,
        git_commit: str | None,
        semver: str | None,
        created_by: uuid.UUID,
        change_summary: str | None,
        parent_version_id: uuid.UUID | None,
    ):
        version = FakeVersion(
            id=uuid.uuid4(),
            doc_type_code=doc_type_code,
            source_yaml=source if source.endswith("\n") else f"{source}\n",
            name=name,
            source_path=source_path,
            git_commit=git_commit,
            semver=semver,
            created_by=created_by,
            change_summary=change_summary,
            parent_version_id=parent_version_id,
        )
        FakeVersionRepo.storage[version.id] = version
        return version

    async def update_draft(
        self,
        *,
        version_id: uuid.UUID,
        source: str,
        name: str | None,
        source_path: str | None,
        git_commit: str | None,
        semver: str | None,
        change_summary: str | None,
    ):
        version = FakeVersionRepo.storage[version_id]
        version.source_yaml = source if source.endswith("\n") else f"{source}\n"
        version.name = name
        version.source_path = source_path
        version.git_commit = git_commit
        version.semver = semver
        version.change_summary = change_summary
        version.updated_at = version.updated_at + timedelta(minutes=1)
        return version

    async def validate_draft(self, *, version_id: uuid.UUID):
        return SimpleNamespace(
            is_valid=True,
            checks_count=0,
            validation_report={
                "is_valid": True,
                "diagnostics": [],
                "checks_count": 0,
                "validation_triggers": [],
            },
        )

    async def publish_draft(self, *, version_id: uuid.UUID):
        version = FakeVersionRepo.storage[version_id]
        version.version_status = "published"
        version.published_at = datetime.now(timezone.utc)
        version.updated_at = version.updated_at + timedelta(minutes=1)
        return version

    async def archive_version(self, *, version_id: uuid.UUID):
        version = FakeVersionRepo.storage[version_id]
        version.version_status = "archived"
        version.updated_at = version.updated_at + timedelta(minutes=1)
        return version


class FakeEditorService:
    async def clone_draft(
        self,
        *,
        source_version_id: uuid.UUID,
        change_summary: str | None,
        created_by: uuid.UUID,
    ):
        source = FakeVersionRepo.storage[source_version_id]
        clone = FakeVersion(
            id=uuid.uuid4(),
            doc_type_code=source.doc_type_code,
            source_yaml=source.source_yaml,
            name=source.name,
            source_path=source.source_path,
            git_commit=source.git_commit,
            semver=source.semver,
            created_by=created_by,
            change_summary=change_summary,
            parent_version_id=source.id,
        )
        FakeVersionRepo.storage[clone.id] = clone
        return clone

    async def preview(self, *, doc_type_code: str, source_yaml: str):
        return SimpleNamespace(
            is_valid=True,
            checks_count=0,
            triggers_used=[],
            diagnostics=[],
            validation_report={"is_valid": True, "diagnostics": [], "checks_count": 0},
            compiled_payload={"checks_v8": []},
            source_sha256="preview-sha",
            already_exists=False,
            existing_version_id=None,
        )

    async def diff(self, *, from_version_id: uuid.UUID, to_version_id: uuid.UUID):
        return SimpleNamespace(
            from_version_id=str(from_version_id),
            to_version_id=str(to_version_id),
            from_source_sha256="from-sha",
            to_source_sha256="to-sha",
            are_identical=False,
            unified_diff=["--- a", "+++ b", "@@ -1 +1 @@", "-checks_v8: []", "+checks_v8: [updated]"],
        )


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()
    app.include_router(instruction_versions_router)

    async def override_db():
        yield FakeAsyncSession()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_instruction_catalog_service] = lambda: FakeCatalogService()
    app.dependency_overrides[get_instruction_publishing_service] = lambda: FakePublishingService()
    app.dependency_overrides[get_instruction_editor_service] = lambda: FakeEditorService()
    return app


@pytest.fixture(autouse=True)
def reset_storage():
    FakeVersionRepo.storage = {}
    version = FakeVersion(id=uuid.UUID("584e482c-67e5-4ebb-99f9-616f589db740"))
    other = FakeVersion(
        id=uuid.UUID("4cd4ef2d-cc4d-4108-b9e6-d5dd2a47cbf1"),
        name="NDA published",
        version_status="published",
        semver="0.0.9",
    )
    FakeVersionRepo.storage[version.id] = version
    FakeVersionRepo.storage[other.id] = other
    yield
    FakeVersionRepo.storage = {}


@pytest.fixture
def superadmin_user():
    return SimpleNamespace(
        id="22222222-2222-2222-2222-222222222222",
        global_role="superadmin",
        tenant_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        email="superadmin@example.com",
    )


@pytest.fixture
def tenant_admin_user():
    return SimpleNamespace(
        id="33333333-3333-3333-3333-333333333333",
        global_role="tenant_admin",
        tenant_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        email="tenantadmin@example.com",
    )


@pytest.fixture
def superadmin_client(app: FastAPI, superadmin_user):
    app.dependency_overrides[get_current_user] = lambda: superadmin_user
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def tenant_admin_client(app: FastAPI, tenant_admin_user):
    app.dependency_overrides[get_current_user] = lambda: tenant_admin_user
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def version_id() -> str:
    return "584e482c-67e5-4ebb-99f9-616f589db740"


@pytest.fixture
def other_version_id() -> str:
    return "4cd4ef2d-cc4d-4108-b9e6-d5dd2a47cbf1"


@pytest.fixture(autouse=True)
def patch_repo(monkeypatch):
    monkeypatch.setattr(
        "api.endpoints.instruction_versions.DocumentTypeInstructionVersionRepository",
        FakeVersionRepo,
    )


def test_list_instruction_catalog_returns_200(superadmin_client: TestClient):
    response = superadmin_client.get("/admin/instructions/doc-types")

    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert len(body["items"]) == 1
    assert body["items"][0]["doc_type_code"] == "nda"


def test_list_instruction_versions_for_doc_type_returns_items(superadmin_client: TestClient):
    response = superadmin_client.get("/admin/instructions/doc-types/nda/versions")

    assert response.status_code == 200
    body = response.json()
    assert body["doc_type_code"] == "nda"
    assert len(body["items"]) >= 1
    assert body["items"][0]["doc_type_code"] == "nda"


def test_get_instruction_version_sets_etag(superadmin_client: TestClient, version_id: str):
    response = superadmin_client.get(f"/admin/instruction-versions/{version_id}")

    assert response.status_code == 200
    assert "etag" in response.headers
    assert response.headers["etag"].startswith('"')
    assert response.json()["item"]["id"] == version_id


def test_get_instruction_version_returns_404_for_missing(superadmin_client: TestClient):
    missing_id = "11111111-1111-1111-1111-111111111111"

    response = superadmin_client.get(f"/admin/instruction-versions/{missing_id}")

    assert response.status_code == 404
    body = response.json()
    assert body["detail"]["code"] == "INSTRUCTION_VERSION_NOT_FOUND"


def test_create_instruction_draft_returns_201(superadmin_client: TestClient):
    response = superadmin_client.post(
        "/admin/instructions/doc-types/nda/drafts",
        json={
            "source_yaml": "checks_v8: []",
            "name": "NDA base draft",
            "source_path": "instructions/nda.yaml",
            "git_commit": "manual-test",
            "semver": "0.1.0",
            "change_summary": "create initial draft",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["item"]["doc_type_code"] == "nda"
    assert body["item"]["version_status"] == "draft"


def test_update_instruction_draft_requires_if_match(superadmin_client: TestClient, version_id: str):
    response = superadmin_client.patch(
        f"/admin/instruction-versions/{version_id}",
        json={
            "source_yaml": "checks_v8: []",
            "name": "NDA base draft updated",
            "source_path": "instructions/nda.yaml",
            "git_commit": "manual-test-2",
            "semver": "0.1.1",
            "change_summary": "test missing if-match",
        },
    )

    assert response.status_code == 428
    body = response.json()
    assert body["detail"]["code"] == "PRECONDITION_REQUIRED"


def test_update_instruction_draft_accepts_current_if_match_and_returns_new_etag(
    superadmin_client: TestClient,
    version_id: str,
):
    get_response = superadmin_client.get(f"/admin/instruction-versions/{version_id}")
    assert get_response.status_code == 200
    etag = get_response.headers["etag"]

    patch_response = superadmin_client.patch(
        f"/admin/instruction-versions/{version_id}",
        headers={"If-Match": etag},
        json={
            "source_yaml": "checks_v8: []",
            "name": "NDA base draft updated",
            "source_path": "instructions/nda.yaml",
            "git_commit": "manual-test-2",
            "semver": "0.1.1",
            "change_summary": "test valid if-match",
        },
    )

    assert patch_response.status_code == 200
    assert patch_response.json()["item"]["name"] == "NDA base draft updated"
    assert "etag" in patch_response.headers
    assert patch_response.headers["etag"] != etag


def test_update_instruction_draft_rejects_stale_if_match(
    superadmin_client: TestClient,
    version_id: str,
):
    get_response = superadmin_client.get(f"/admin/instruction-versions/{version_id}")
    assert get_response.status_code == 200
    etag = get_response.headers["etag"]

    ok_response = superadmin_client.patch(
        f"/admin/instruction-versions/{version_id}",
        headers={"If-Match": etag},
        json={
            "source_yaml": "checks_v8: []",
            "name": "NDA base draft updated",
            "source_path": "instructions/nda.yaml",
            "git_commit": "manual-test-2",
            "semver": "0.1.1",
            "change_summary": "test valid if-match",
        },
    )
    assert ok_response.status_code == 200

    stale_response = superadmin_client.patch(
        f"/admin/instruction-versions/{version_id}",
        headers={"If-Match": etag},
        json={
            "source_yaml": "checks_v8: []",
            "name": "NDA base draft updated again",
            "source_path": "instructions/nda.yaml",
            "git_commit": "manual-test-3",
            "semver": "0.1.2",
            "change_summary": "test stale if-match",
        },
    )

    assert stale_response.status_code == 412
    body = stale_response.json()
    assert body["detail"]["code"] == "PRECONDITION_FAILED"
    assert "current_etag" in body["detail"]


def test_validate_instruction_draft_returns_200(superadmin_client: TestClient, version_id: str):
    response = superadmin_client.post(f"/admin/instruction-versions/{version_id}/validate")

    assert response.status_code == 200
    body = response.json()
    assert body["is_valid"] is True
    assert body["item"]["id"] == version_id


def test_publish_instruction_draft_returns_200(superadmin_client: TestClient, version_id: str):
    response = superadmin_client.post(f"/admin/instruction-versions/{version_id}/publish")

    assert response.status_code == 200
    body = response.json()
    assert body["item"]["version_status"] == "published"


def test_archive_instruction_version_returns_200(superadmin_client: TestClient, version_id: str):
    response = superadmin_client.post(f"/admin/instruction-versions/{version_id}/archive")

    assert response.status_code == 200
    body = response.json()
    assert body["item"]["version_status"] == "archived"


def test_clone_instruction_draft_returns_201(superadmin_client: TestClient, version_id: str):
    response = superadmin_client.post(
        f"/admin/instruction-versions/{version_id}/clone-draft",
        json={"change_summary": "edit published"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["item"]["version_status"] == "draft"
    assert body["item"]["parent_version_id"] == version_id


def test_preview_instruction_returns_200(superadmin_client: TestClient):
    response = superadmin_client.post(
        "/admin/instructions/doc-types/nda/preview",
        json={"source_yaml": "checks_v8: []"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["is_valid"] is True
    assert body["source_sha256"] == "preview-sha"


def test_diff_instruction_versions_uses_against_query_param(
    superadmin_client: TestClient,
    version_id: str,
    other_version_id: str,
):
    response = superadmin_client.get(
        f"/admin/instruction-versions/{version_id}/diff",
        params={"against": other_version_id},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["from_version_id"] == version_id
    assert body["to_version_id"] == other_version_id
    assert body["are_identical"] is False
    assert len(body["unified_diff"]) > 0


def test_instruction_admin_requires_superadmin_for_catalog(tenant_admin_client: TestClient):
    response = tenant_admin_client.get("/admin/instructions/doc-types")

    assert response.status_code == 403
    body = response.json()
    assert body["detail"]["code"] == "INSTRUCTION_ACCESS_DENIED"


def test_instruction_admin_requires_superadmin_for_detail(
    tenant_admin_client: TestClient,
    version_id: str,
):
    response = tenant_admin_client.get(f"/admin/instruction-versions/{version_id}")

    assert response.status_code == 403
    body = response.json()
    assert body["detail"]["code"] == "INSTRUCTION_ACCESS_DENIED"


    