import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.deps.auth import CurrentUser, get_current_user
from api.main import app

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




# --- 7. 429 при превышении rate limit (R-03) ---
# Patch _limiter.hit globally so it returns False → _check_limit raises 429
# before any DB/repo access. No repo patches needed.

def test_reveal_rate_limit_exceeded_returns_429(client):
    app.dependency_overrides[get_current_user] = lambda: make_user("editor")

    with patch("api.deps.rate_limit._limiter") as limiter_mock:
        limiter_mock.hit.return_value = False

        response = client.get(
            f"/api/v1/documents/{DOC_ID}/pii-reveal",
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 429
    assert "Retry-After" in response.headers
    assert response.headers["Retry-After"] == "60"


# --- 8. Rate limit — правильные scope и identity (R-03) ---
# Verify _limiter.hit called with (limit, "pii_reveal", user.id) — per-user,
# not per-IP. This is critical: behind Caddy all clients look like 127.0.0.1.

def test_reveal_rate_limit_scope_and_identity(client):
    user = make_user("editor")
    app.dependency_overrides[get_current_user] = lambda: user

    fake_doc = MagicMock(deal_id=DEAL_ID)
    fake_version = MagicMock(
        id=VERSION_ID,
        layout_primary_sanitized_ref="s3://bucket/sanitized.json",
        pii_mapping_ref="s3://bucket/mapping.enc",
    )

    with patch("api.deps.rate_limit._limiter") as limiter_mock, \
         patch("api.endpoints.documents.pii_reveal.DocumentRepository") as doc_repo_cls, \
         patch("api.endpoints.documents.pii_reveal.DocumentVersionRepository") as ver_repo_cls, \
         patch("api.endpoints.documents.pii_reveal.reveal_document_pii") as reveal_mock, \
         patch("api.endpoints.documents.pii_reveal.AuditRepository") as audit_repo_cls, \
         patch("api.endpoints.documents.pii_reveal.require_project_role", new=AsyncMock(return_value=None)):

        limiter_mock.hit.return_value = True

        doc_repo = doc_repo_cls.return_value
        doc_repo.get_by_id = AsyncMock(return_value=fake_doc)

        ver_repo = ver_repo_cls.return_value
        ver_repo.get_latest = AsyncMock(return_value=fake_version)

        reveal_mock.return_value = {"elements": [{"text": "X"}]}

        audit_repo = audit_repo_cls.return_value
        audit_repo.log = AsyncMock()

        response = client.get(
            f"/api/v1/documents/{DOC_ID}/pii-reveal",
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 200

    # Verify _limiter.hit called with correct scope and identity
    assert limiter_mock.hit.called
    call_args = limiter_mock.hit.call_args
    # _limiter.hit(limit, scope, identity)
    # positional: (limit, "pii_reveal", user.id)
    assert call_args.args[1] == "pii_reveal", f"expected scope=pii_reveal, got {call_args.args[1]}"
    assert call_args.args[2] == user.id, f"expected identity={user.id}, got {call_args.args[2]}"
