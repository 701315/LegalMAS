import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.main import app
from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import get_scoped_run
from api.endpoints.runs import get_effective_instruction_service
from services.effective_instruction_service import EffectiveInstructionNotFoundError

DOC_ID = uuid.uuid4()
RUN_ID = uuid.uuid4()
DEAL_ID = uuid.uuid4()
TENANT_ID = uuid.uuid4()


def make_user(role: str) -> CurrentUser:
    return CurrentUser(
        id=str(uuid.uuid4()),
        global_role=role,
        tenant_id=TENANT_ID,
        email="user@example.com",
    )


def make_run() -> MagicMock:
    run = MagicMock()
    run.id = RUN_ID
    run.deal_id = DEAL_ID
    return run


@pytest.fixture(autouse=True)
def _reset_overrides():
    app.dependency_overrides = {}
    yield
    app.dependency_overrides = {}


@pytest.fixture
def client():
    return TestClient(app)


def test_get_effective_instruction_success(client):
    app.dependency_overrides[get_current_user] = lambda: make_user("editor")
    app.dependency_overrides[get_scoped_run] = lambda: make_run()

    fake_service = MagicMock()
    fake_service.get_for_document = AsyncMock(
        return_value={
            "run_id": str(RUN_ID),
            "document_id": str(DOC_ID),
            "playbook_version_id": str(uuid.uuid4()),
            "global_checks": [],
            "doc_type_checks": [],
            "is_frozen_snapshot": True,
        }
    )
    app.dependency_overrides[get_effective_instruction_service] = lambda: fake_service

    with patch(
        "api.endpoints.runs.require_project_role", new=AsyncMock(return_value=None)
    ):
        response = client.get(
            f"/api/v1/runs/{RUN_ID}/documents/{DOC_ID}/effective-instruction",
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == str(RUN_ID)
    assert body["document_id"] == str(DOC_ID)
    assert "playbook_version_id" in body
    assert "global_checks" in body
    assert "doc_type_checks" in body
    assert "is_frozen_snapshot" in body


def test_get_effective_instruction_document_not_found_returns_404(client):
    app.dependency_overrides[get_current_user] = lambda: make_user("editor")
    app.dependency_overrides[get_scoped_run] = lambda: make_run()

    fake_service = MagicMock()
    fake_service.get_for_document = AsyncMock(
        side_effect=EffectiveInstructionNotFoundError(
            "Document not found in this run's deal"
        )
    )
    app.dependency_overrides[get_effective_instruction_service] = lambda: fake_service

    with patch(
        "api.endpoints.runs.require_project_role", new=AsyncMock(return_value=None)
    ):
        response = client.get(
            f"/api/v1/runs/{RUN_ID}/documents/{DOC_ID}/effective-instruction",
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 404


def test_get_effective_instruction_requires_project_membership(client):
    app.dependency_overrides[get_current_user] = lambda: make_user("member")
    app.dependency_overrides[get_scoped_run] = lambda: make_run()

    fake_service = MagicMock()
    app.dependency_overrides[get_effective_instruction_service] = lambda: fake_service

    with patch(
        "api.endpoints.runs.require_project_role",
        new=AsyncMock(side_effect=HTTPException(status_code=403, detail="Forbidden")),
    ):
        response = client.get(
            f"/api/v1/runs/{RUN_ID}/documents/{DOC_ID}/effective-instruction",
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 403


def test_get_effective_instruction_requires_auth(client):
    response = client.get(
        f"/api/v1/runs/{RUN_ID}/documents/{DOC_ID}/effective-instruction",
    )
    assert response.status_code == 401


