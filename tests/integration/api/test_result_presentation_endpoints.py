"""
Integration seam tests for locale-specific result-presentation endpoints.

Покрывает:
- POST request creation для admin/editor project access;
- запрет write-action при недостаточной project role;
- transactional outbox payload и commit;
- GET progress для read access;
- public progress response contract;
- обязательный locale query parameter.

Тесты используют FastAPI TestClient и mocks зависимостей endpoint-а.
Реальные Postgres, Redis, Celery и LLM не требуются.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.deps.auth import CurrentUser, get_current_user
from api.main import app
from db.session import get_db
from services.result_presentation_request_service import (
    ResultPresentationProgress,
)


RUN_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
DEAL_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
TENANT_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")

BASE_PATH = (
    f"/api/v1/deals/{DEAL_ID}/runs/{RUN_ID}/result-presentations"
)


def make_user(
    *,
    global_role: str = "member",
) -> CurrentUser:
    return CurrentUser(
        id=str(uuid.uuid4()),
        global_role=global_role,
        tenant_id=TENANT_ID,
        email="reviewer@example.com",
        ui_locale="en",
    )


def make_run() -> SimpleNamespace:
    return SimpleNamespace(
        id=RUN_ID,
        deal_id=DEAL_ID,
        tenant_id=TENANT_ID,
    )


def make_deal() -> SimpleNamespace:
    return SimpleNamespace(
        id=DEAL_ID,
        primary_language="ru",
    )


def make_progress(
    *,
    locale: str = "en",
    total: int = 2,
    missing: int = 0,
    pending: int = 2,
    processing: int = 0,
    ready: int = 0,
    reviewed: int = 0,
    approved: int = 0,
    failed: int = 0,
    stale: int = 0,
    created_pending: int = 2,
    existing: int = 0,
) -> ResultPresentationProgress:
    return ResultPresentationProgress(
        run_id=str(RUN_ID),
        locale=locale,
        content_version="v1",
        total=total,
        missing=missing,
        pending=pending,
        processing=processing,
        ready=ready,
        reviewed=reviewed,
        approved=approved,
        failed=failed,
        stale=stale,
        created_pending=created_pending,
        existing=existing,
    )


def make_db(
    *,
    deal: object | None = None,
) -> MagicMock:
    db = MagicMock()
    db.get = AsyncMock(return_value=deal)
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


@pytest.fixture(autouse=True)
def reset_dependency_overrides():
    app.dependency_overrides = {}
    yield
    app.dependency_overrides = {}


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def override_db(db: MagicMock) -> None:
    app.dependency_overrides[get_db] = lambda: db


def override_user(user: CurrentUser) -> None:
    app.dependency_overrides[get_current_user] = lambda: user


def test_request_requires_authentication(client: TestClient) -> None:
    response = client.post(
        f"{BASE_PATH}/requests",
        json={"locale": "en"},
    )

    assert response.status_code == 401


def test_request_rejects_insufficient_project_role(
    client: TestClient,
) -> None:
    db = make_db(deal=make_deal())
    override_db(db)
    override_user(make_user())

    async def reject_viewer_write(
        *,
        allowed_roles: tuple[str, ...],
        **_: object,
    ) -> None:
        assert allowed_roles == ("admin", "editor")
        raise HTTPException(
            status_code=403,
            detail="Insufficient project role",
        )

    with patch(
        "api.endpoints.deal_review.RunRepository",
    ) as run_repo_cls, patch(
        "api.endpoints.deal_review.require_project_role",
        new=AsyncMock(side_effect=reject_viewer_write),
    ):
        run_repo = MagicMock()
        run_repo.get_by_id = AsyncMock(return_value=make_run())
        run_repo_cls.return_value = run_repo

        response = client.post(
            f"{BASE_PATH}/requests",
            json={"locale": "en"},
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 403
    db.get.assert_not_awaited()
    db.commit.assert_not_awaited()


def test_editor_request_enqueues_outbox_and_returns_queued_progress(
    client: TestClient,
) -> None:
    db = make_db(deal=make_deal())
    override_db(db)
    override_user(make_user())

    progress = make_progress()

    with patch(
        "api.endpoints.deal_review.RunRepository",
    ) as run_repo_cls, patch(
        "api.endpoints.deal_review.require_project_role",
        new=AsyncMock(return_value=None),
    ) as require_role_mock, patch(
        "api.endpoints.deal_review.ResultPresentationRequestService",
    ) as request_service_cls, patch(
        "api.endpoints.deal_review.AuditRepository",
    ) as audit_repo_cls, patch(
        "api.endpoints.deal_review.OutboxService",
    ) as outbox_service_cls:
        run_repo = MagicMock()
        run_repo.get_by_id = AsyncMock(return_value=make_run())
        run_repo_cls.return_value = run_repo

        request_service = MagicMock()
        request_service.request_pending_presentations = AsyncMock(
            return_value=progress,
        )
        request_service_cls.return_value = request_service

        audit_repo = MagicMock()
        audit_repo.log = AsyncMock()
        audit_repo_cls.return_value = audit_repo

        outbox_service = MagicMock()
        outbox_service.enqueue_task = AsyncMock(
            return_value=uuid.uuid4(),
        )
        outbox_service_cls.return_value = outbox_service

        response = client.post(
            f"{BASE_PATH}/requests",
            json={"locale": "en"},
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 201, response.text

    body = response.json()
    assert body == {
        "run_id": str(RUN_ID),
        "locale": "en",
        "content_version": "v1",
        "total": 2,
        "missing": 0,
        "pending": 2,
        "processing": 0,
        "ready": 0,
        "reviewed": 0,
        "approved": 0,
        "failed": 0,
        "stale": 0,
        "created_pending": 2,
        "existing": 0,
        "is_complete": False,
        "dispatch_status": "queued",
    }

    require_role_mock.assert_awaited_once_with(
        db=db,
        user=ANY,
        deal_id=DEAL_ID,
        allowed_roles=("admin", "editor"),
    )

    request_service.request_pending_presentations.assert_awaited_once_with(
        run_id=RUN_ID,
        locale="en",
        source_locale="ru",
    )

    audit_repo.log.assert_awaited_once()

    outbox_service.enqueue_task.assert_awaited_once_with(
        task_name="workers.process_pending_result_presentations",
        payload={
            "run_id": str(RUN_ID),
            "deal_id": str(DEAL_ID),
            "tenant_id": str(TENANT_ID),
            "locale": "en",
            "content_version": "v1",
            "batch_limit": 5,
        },
        aggregate_type="run",
        aggregate_id=str(RUN_ID),
        dedup_key=(
            "result-presentation-batch:"
            f"{RUN_ID}:en:v1"
        ),
        headers={
            "queue": "heavy_llm_checks",
        },
    )

    db.commit.assert_awaited_once()


def test_progress_is_available_to_viewer_project_role(
    client: TestClient,
) -> None:
    db = make_db()
    override_db(db)
    override_user(make_user())

    progress = make_progress(
        pending=0,
        processing=0,
        ready=1,
        approved=1,
        created_pending=0,
        existing=0,
    )

    with patch(
        "api.endpoints.deal_review.RunRepository",
    ) as run_repo_cls, patch(
        "api.endpoints.deal_review.require_project_role",
        new=AsyncMock(return_value=None),
    ) as require_role_mock, patch(
        "api.endpoints.deal_review.ResultPresentationRequestService",
    ) as request_service_cls:
        run_repo = MagicMock()
        run_repo.get_by_id = AsyncMock(return_value=make_run())
        run_repo_cls.return_value = run_repo

        request_service = MagicMock()
        request_service.get_progress = AsyncMock(
            return_value=progress,
        )
        request_service_cls.return_value = request_service

        response = client.get(
            f"{BASE_PATH}/progress?locale=en",
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 200, response.text

    body = response.json()
    assert body["run_id"] == str(RUN_ID)
    assert body["locale"] == "en"
    assert body["ready"] == 1
    assert body["approved"] == 1
    assert body["pending"] == 0
    assert body["processing"] == 0
    assert body["is_complete"] is True
    assert body["dispatch_status"] == "not_dispatched"

    require_role_mock.assert_awaited_once_with(
        db=db,
        user=ANY,
        deal_id=DEAL_ID,
        allowed_roles=("admin", "editor", "viewer"),
    )

    request_service.get_progress.assert_awaited_once_with(
        run_id=RUN_ID,
        locale="en",
    )


def test_progress_requires_locale_query_parameter(
    client: TestClient,
) -> None:
    db = make_db()
    override_db(db)
    override_user(make_user())

    response = client.get(
        f"{BASE_PATH}/progress",
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 422
