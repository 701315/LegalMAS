# tests/api/test_run_concurrent_guard.py
"""
R-33 — concurrent run guard tests.

Covers POST /api/v1/deals/{id}/run when a deal already has an active
(PENDING or RUNNING) run. DB-level guard is the partial unique index
uq_runs_one_active_per_deal (migration bf78307e1293); API layer converts
IntegrityError → 409 Conflict with X-Active-Run-Id header.

Endpoint chain:
- deals/runs.py:start_deal_run calls require_project_role (authz)
- deals/runs.py:start_deal_run calls _start_run_core (business logic, in runs.py)
- runs.py:_start_run_core calls run_repo.create (raises IntegrityError)

Patch targets:
- require_project_role → api.endpoints.deals.runs (where it's called)
- repos (RunRepository, DealRepository, PlaybookRepository, AuditRepository) → api.endpoints.runs (where _start_run_core lives)
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

DEAL_ID = uuid.uuid4()
TENANT_ID = uuid.uuid4()
ACTIVE_RUN_ID = uuid.uuid4()


def _make_user():
    from api.deps.auth import CurrentUser
    return CurrentUser(
        id=str(uuid.uuid4()),
        global_role="member",
        tenant_id=TENANT_ID,
        email="editor@example.com",
    )


@pytest.fixture
def app():
    from api.main import app as fastapi_app
    return fastapi_app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides_after(app):
    yield
    app.dependency_overrides.clear()


def _patch_start_run_deps(*, active_run_id: uuid.UUID | None = ACTIVE_RUN_ID):
    """Build mock repos. run_repo.create raises IntegrityError."""
    fake_deal = MagicMock(
        id=DEAL_ID,
        tenant_id=TENANT_ID,
        primary_language="RU",
        language_discovery_status="completed",
    )
    fake_playbook = MagicMock(
        id=uuid.uuid4(),
        model_config_id=uuid.uuid4(),
    )
    fake_active = MagicMock(id=active_run_id) if active_run_id else None

    run_repo = MagicMock()
    run_repo.create = AsyncMock(
        side_effect=IntegrityError(
            "INSERT INTO runs ...",
            params={},
            orig=Exception("duplicate key value violates unique constraint uq_runs_one_active_per_deal"),
        )
    )
    run_repo.get_latest_for_deal = AsyncMock(return_value=None)
    run_repo.get_active_for_deal = AsyncMock(return_value=fake_active)

    deal_repo = MagicMock()
    deal_repo.get_by_id = AsyncMock(return_value=fake_deal)

    playbook_repo = MagicMock()
    playbook_repo.get_for_deal = AsyncMock(return_value=fake_playbook)

    audit_repo = MagicMock()
    audit_repo.log = AsyncMock()

    db = MagicMock()
    db.rollback = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()

    return run_repo, deal_repo, playbook_repo, audit_repo, db


def _do_request(app, client, db, run_repo, deal_repo, playbook_repo, audit_repo):
    from api.deps.auth import get_current_user
    from db.session import get_db

    user = _make_user()
    app.dependency_overrides[get_current_user] = lambda: user

    async def _override_db():
        return db

    app.dependency_overrides[get_db] = _override_db

    # CRITICAL: require_project_role patched where it's CALLED (deals.runs),
    # not where it's defined (api.deps.security)
    with patch("api.endpoints.deals.runs.require_project_role", new=AsyncMock(return_value=None)), \
         patch("api.endpoints.runs.RunRepository", return_value=run_repo), \
         patch("api.endpoints.runs.DealRepository", return_value=deal_repo), \
         patch("api.endpoints.runs.PlaybookRepository", return_value=playbook_repo), \
         patch("api.endpoints.runs.AuditRepository", return_value=audit_repo):

        response = client.post(
            f"/api/v1/deals/{DEAL_ID}/run",
            json={"profile": "full", "checks_mode": "global_and_doc_type"},
            headers={"Authorization": "Bearer test"},
        )

    return response


def test_start_run_active_exists_returns_409_with_header(app, client):
    run_repo, deal_repo, playbook_repo, audit_repo, db = _patch_start_run_deps()
    response = _do_request(app, client, db, run_repo, deal_repo, playbook_repo, audit_repo)

    assert response.status_code == 409
    assert response.headers.get("X-Error-Code") == "DEAL_ALREADY_HAS_ACTIVE_RUN"
    assert response.headers.get("X-Active-Run-Id") == str(ACTIVE_RUN_ID)


def test_start_run_409_triggers_rollback(app, client):
    run_repo, deal_repo, playbook_repo, audit_repo, db = _patch_start_run_deps()
    response = _do_request(app, client, db, run_repo, deal_repo, playbook_repo, audit_repo)

    assert response.status_code == 409
    db.rollback.assert_awaited_once()


def test_start_run_409_message_does_not_leak_internals(app, client):
    run_repo, deal_repo, playbook_repo, audit_repo, db = _patch_start_run_deps()
    response = _do_request(app, client, db, run_repo, deal_repo, playbook_repo, audit_repo)

    assert response.status_code == 409
    body = response.json()
    assert "active" in body["detail"].lower()
    assert "uq_runs_one_active_per_deal" not in body["detail"]
    assert "duplicate key" not in body["detail"].lower()


def test_start_run_409_without_active_run_id_when_race_resolved(app, client):
    run_repo, deal_repo, playbook_repo, audit_repo, db = _patch_start_run_deps(
        active_run_id=None,
    )
    response = _do_request(app, client, db, run_repo, deal_repo, playbook_repo, audit_repo)

    assert response.status_code == 409
    assert "X-Active-Run-Id" not in response.headers
    assert response.headers.get("X-Error-Code") == "DEAL_ALREADY_HAS_ACTIVE_RUN"
