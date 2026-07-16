import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.deps.auth import CurrentUser, get_current_user


DOC_ID = uuid.uuid4()
VERSION_ID = uuid.uuid4()
TENANT_ID = uuid.uuid4()
DEAL_ID = uuid.uuid4()


def make_user(role: str) -> CurrentUser:
    return CurrentUser(
        id=str(uuid.uuid4()),
        global_role=role,
        tenant_id=TENANT_ID,
        email="user@example.com",
    )


@pytest.fixture(autouse=True)
def _reset_overrides():
    app.dependency_overrides = {}
    yield
    app.dependency_overrides = {}


@pytest.fixture
def client():
    return TestClient(app)


# --- 1. 401 без токена ---

def test_reveal_requires_auth(client):
    response = client.get(f"/api/v1/documents/{DOC_ID}/pii-reveal")
    assert response.status_code == 401


# --- 2. 403 для роли viewer/member ---
# require_project_role вызывается напрямую в теле эндпоинта,
# поэтому патчим её там, где она импортирована в pii_reveal.py

def test_reveal_forbidden_for_viewer(client):
    app.dependency_overrides[get_current_user] = lambda: make_user("member")

    fake_doc = MagicMock(deal_id=DEAL_ID)

    with patch("api.endpoints.documents.pii_reveal.DocumentRepository") as doc_repo_cls, \
         patch("api.endpoints.documents.pii_reveal.require_project_role") as role_check:

        doc_repo = doc_repo_cls.return_value
        doc_repo.get_by_id = AsyncMock(return_value=fake_doc)

        from fastapi import HTTPException
        role_check.side_effect = AsyncMock(
            side_effect=HTTPException(status_code=403, detail="Forbidden")
        )

        response = client.get(
            f"/api/v1/documents/{DOC_ID}/pii-reveal",
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 403


# --- 3. 404 если документ не найден ---
# Здесь require_project_role даже не должна вызываться (или должна пройти),
# так что достаточно замокать её как no-op

def test_reveal_document_not_found(client):
    app.dependency_overrides[get_current_user] = lambda: make_user("editor")

    with patch("api.endpoints.documents.pii_reveal.DocumentRepository") as doc_repo_cls, \
         patch("api.endpoints.documents.pii_reveal.require_project_role", new=AsyncMock(return_value=None)):

        doc_repo = doc_repo_cls.return_value
        doc_repo.get_by_id = AsyncMock(return_value=None)

        response = client.get(
            f"/api/v1/documents/{DOC_ID}/pii-reveal",
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 404


# --- 4. 404 если нет pii_mapping_ref ---

def test_reveal_missing_mapping_ref(client):
    app.dependency_overrides[get_current_user] = lambda: make_user("editor")

    fake_doc = MagicMock(deal_id=DEAL_ID)
    fake_version = MagicMock(
        id=VERSION_ID,
        layout_primary_sanitized_ref="s3://bucket/sanitized.json",
        pii_mapping_ref=None,
    )

    with patch("api.endpoints.documents.pii_reveal.DocumentRepository") as doc_repo_cls, \
         patch("api.endpoints.documents.pii_reveal.DocumentVersionRepository") as ver_repo_cls, \
         patch("api.endpoints.documents.pii_reveal.require_project_role", new=AsyncMock(return_value=None)):

        doc_repo = doc_repo_cls.return_value
        doc_repo.get_by_id = AsyncMock(return_value=fake_doc)

        ver_repo = ver_repo_cls.return_value
        ver_repo.get_latest = AsyncMock(return_value=fake_version)

        response = client.get(
            f"/api/v1/documents/{DOC_ID}/pii-reveal",
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 404


# --- 5. 200 успешный сценарий ---

def test_reveal_success(client):
    app.dependency_overrides[get_current_user] = lambda: make_user("editor")

    fake_doc = MagicMock(deal_id=DEAL_ID)
    fake_version = MagicMock(
        id=VERSION_ID,
        layout_primary_sanitized_ref="s3://bucket/sanitized.json",
        pii_mapping_ref="s3://bucket/mapping.enc",
    )
    restored_layout = {"elements": [{"text": "Иванов И.И."}]}

    with patch("api.endpoints.documents.pii_reveal.DocumentRepository") as doc_repo_cls, \
         patch("api.endpoints.documents.pii_reveal.DocumentVersionRepository") as ver_repo_cls, \
         patch("api.endpoints.documents.pii_reveal.reveal_document_pii") as reveal_mock, \
         patch("api.endpoints.documents.pii_reveal.AuditRepository") as audit_repo_cls, \
         patch("api.endpoints.documents.pii_reveal.require_project_role", new=AsyncMock(return_value=None)):

        doc_repo = doc_repo_cls.return_value
        doc_repo.get_by_id = AsyncMock(return_value=fake_doc)

        ver_repo = ver_repo_cls.return_value
        ver_repo.get_latest = AsyncMock(return_value=fake_version)

        reveal_mock.return_value = restored_layout

        audit_repo = audit_repo_cls.return_value
        audit_repo.log = AsyncMock()

        response = client.get(
            f"/api/v1/documents/{DOC_ID}/pii-reveal",
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == str(DOC_ID)
    assert data["document_version_id"] == str(VERSION_ID)
    assert data["elements_count"] == 1


# --- 6. 503 при ошибке pre-audit (fail-closed) ---

def test_reveal_pre_audit_failure_returns_503(client):
    app.dependency_overrides[get_current_user] = lambda: make_user("editor")

    fake_doc = MagicMock(deal_id=DEAL_ID)
    fake_version = MagicMock(
        id=VERSION_ID,
        layout_primary_sanitized_ref="s3://bucket/sanitized.json",
        pii_mapping_ref="s3://bucket/mapping.enc",
    )

    with patch("api.endpoints.documents.pii_reveal.DocumentRepository") as doc_repo_cls, \
         patch("api.endpoints.documents.pii_reveal.DocumentVersionRepository") as ver_repo_cls, \
         patch("api.endpoints.documents.pii_reveal.AuditRepository") as audit_repo_cls, \
         patch("api.endpoints.documents.pii_reveal.require_project_role", new=AsyncMock(return_value=None)):

        doc_repo = doc_repo_cls.return_value
        doc_repo.get_by_id = AsyncMock(return_value=fake_doc)

        ver_repo = ver_repo_cls.return_value
        ver_repo.get_latest = AsyncMock(return_value=fake_version)

        audit_repo = audit_repo_cls.return_value
        audit_repo.log = AsyncMock(side_effect=Exception("audit fail"))

        response = client.get(
            f"/api/v1/documents/{DOC_ID}/pii-reveal",
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 503


    