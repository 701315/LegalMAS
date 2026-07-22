"""
Integration tests for read-only Run check-plan API.

Покрывает:
- GET /api/v1/runs/{run_id}/check-plan
- GET /api/v1/runs/{run_id}/check-plan/{plan_item_id}

Контракты:
- endpoint работает только через scoped run access;
- list endpoint передаёт typed enum status в repository;
- invalid status отсекается FastAPI/Pydantic валидацией до ACL/repository;
- summary всегда overall по всему Run, даже если items отфильтрованы;
- detail endpoint scoped по run_id и не допускает cross-run leakage.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.main import app
from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import get_scoped_run
from core.constants import RunCheckPlanItemStatus
from db.session import get_db


RUN_ID = uuid.uuid4()
DEAL_ID = uuid.uuid4()
TENANT_ID = uuid.uuid4()
ITEM_ID = uuid.uuid4()
DOCUMENT_ID = uuid.uuid4()


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


def make_plan_item(
    *,
    item_id: uuid.UUID = ITEM_ID,
    run_id: uuid.UUID = RUN_ID,
    status: str = "succeeded",
) -> MagicMock:
    item = MagicMock()
    item.id = item_id
    item.run_id = run_id
    item.document_id = DOCUMENT_ID
    item.segment_id = None
    item.doc_type = "nda"
    item.check_id = "check_1"
    item.check_name = "Check One"
    item.check_origin = "document_type"
    item.playbook_version_id = None
    item.status = status
    item.attempt_count = 1
    item.dispatch_ref = None
    item.error_details = None
    item.dispatched_at = None
    item.started_at = None
    item.finished_at = None
    return item


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


class TestGetRunCheckPlan:
    def test_success_returns_items_and_summary(self, client):
        app.dependency_overrides[get_current_user] = lambda: make_user("editor")
        app.dependency_overrides[get_scoped_run] = lambda: make_run()
        _override_db()

        items = [
            make_plan_item(status="succeeded"),
            make_plan_item(item_id=uuid.uuid4(), status="failed"),
        ]
        fake_stats = {
            "total_items": 2,
            "terminal_items": 2,
            "active_items": 0,
            "has_errors": True,
        }

        with patch(
            "api.endpoints.runs.require_project_role",
            new=AsyncMock(return_value=None),
        ), patch("api.endpoints.runs.RunCheckPlanItemRepository") as repo_cls:
            fake_repo = MagicMock()
            fake_repo.list_by_run_id = AsyncMock(return_value=items)
            fake_repo.get_run_progress_stats = AsyncMock(return_value=fake_stats)
            repo_cls.return_value = fake_repo

            response = client.get(
                f"/api/v1/runs/{RUN_ID}/check-plan",
                headers={"Authorization": "Bearer test"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["run_id"] == str(RUN_ID)
        assert len(body["items"]) == 2
        assert body["summary"]["total_items"] == 2
        assert body["summary"]["has_errors"] is True
        fake_repo.list_by_run_id.assert_awaited_once_with(RUN_ID, status=None)
        fake_repo.get_run_progress_stats.assert_awaited_once_with(RUN_ID)

    def test_status_filter_passed_to_repository_as_typed_enum(self, client):
        """
        После typed-hardening query-параметра endpoint должен передавать
        в repository именно RunCheckPlanItemStatus.FAILED (enum member),
        а не "сырую" строку "failed".
        """
        app.dependency_overrides[get_current_user] = lambda: make_user("viewer")
        app.dependency_overrides[get_scoped_run] = lambda: make_run()
        _override_db()

        with patch(
            "api.endpoints.runs.require_project_role",
            new=AsyncMock(return_value=None),
        ), patch("api.endpoints.runs.RunCheckPlanItemRepository") as repo_cls:
            fake_repo = MagicMock()
            fake_repo.list_by_run_id = AsyncMock(return_value=[])
            fake_repo.get_run_progress_stats = AsyncMock(
                return_value={
                    "total_items": 0,
                    "terminal_items": 0,
                    "active_items": 0,
                    "has_errors": False,
                }
            )
            repo_cls.return_value = fake_repo

            response = client.get(
                f"/api/v1/runs/{RUN_ID}/check-plan?status=failed",
                headers={"Authorization": "Bearer test"},
            )

        assert response.status_code == 200
        fake_repo.list_by_run_id.assert_awaited_once_with(
            RUN_ID,
            status=RunCheckPlanItemStatus.FAILED,
        )

    def test_invalid_status_value_returns_422_before_reaching_repository(self, client):
        """
        Typed enum query param должен отклонять невалидные значения
        на уровне FastAPI/Pydantic валидации, до вызова require_project_role
        и до обращения к repository.
        """
        app.dependency_overrides[get_current_user] = lambda: make_user("viewer")
        app.dependency_overrides[get_scoped_run] = lambda: make_run()
        _override_db()

        with patch(
            "api.endpoints.runs.require_project_role",
            new=AsyncMock(return_value=None),
        ) as require_role_mock, patch(
            "api.endpoints.runs.RunCheckPlanItemRepository"
        ) as repo_cls:
            fake_repo = MagicMock()
            fake_repo.list_by_run_id = AsyncMock(return_value=[])
            repo_cls.return_value = fake_repo

            response = client.get(
                f"/api/v1/runs/{RUN_ID}/check-plan?status=not_a_real_status",
                headers={"Authorization": "Bearer test"},
            )

        assert response.status_code == 422
        require_role_mock.assert_not_awaited()
        fake_repo.list_by_run_id.assert_not_awaited()

    def test_all_enum_status_values_are_accepted(self, client):
        """
        Каждое значение RunCheckPlanItemStatus должно проходить query
        validation без 422 — это защищает от рассинхронизации между
        enum в constants.py и Query-параметром в endpoint.
        """
        app.dependency_overrides[get_current_user] = lambda: make_user("viewer")
        app.dependency_overrides[get_scoped_run] = lambda: make_run()
        _override_db()

        with patch(
            "api.endpoints.runs.require_project_role",
            new=AsyncMock(return_value=None),
        ), patch("api.endpoints.runs.RunCheckPlanItemRepository") as repo_cls:
            fake_repo = MagicMock()
            fake_repo.list_by_run_id = AsyncMock(return_value=[])
            fake_repo.get_run_progress_stats = AsyncMock(
                return_value={
                    "total_items": 0,
                    "terminal_items": 0,
                    "active_items": 0,
                    "has_errors": False,
                }
            )
            repo_cls.return_value = fake_repo

            for status_value in RunCheckPlanItemStatus:
                response = client.get(
                    f"/api/v1/runs/{RUN_ID}/check-plan?status={status_value.value}",
                    headers={"Authorization": "Bearer test"},
                )
                assert response.status_code == 200, (
                    f"status={status_value.value} unexpectedly rejected"
                )

    def test_summary_reflects_overall_run_regardless_of_status_filter(self, client):
        """
        Закрепляет контракт из RunCheckPlanSummary docstring: summary
        всегда overall по run, даже если items отфильтрованы по status.
        """
        app.dependency_overrides[get_current_user] = lambda: make_user("editor")
        app.dependency_overrides[get_scoped_run] = lambda: make_run()
        _override_db()

        overall_stats = {
            "total_items": 5,
            "terminal_items": 3,
            "active_items": 2,
            "has_errors": True,
        }
        filtered_items = [make_plan_item(status="failed")]

        with patch(
            "api.endpoints.runs.require_project_role",
            new=AsyncMock(return_value=None),
        ), patch("api.endpoints.runs.RunCheckPlanItemRepository") as repo_cls:
            fake_repo = MagicMock()
            fake_repo.list_by_run_id = AsyncMock(return_value=filtered_items)
            fake_repo.get_run_progress_stats = AsyncMock(return_value=overall_stats)
            repo_cls.return_value = fake_repo

            response = client.get(
                f"/api/v1/runs/{RUN_ID}/check-plan?status=failed",
                headers={"Authorization": "Bearer test"},
            )

        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) == 1
        assert body["summary"] == overall_stats
        fake_repo.list_by_run_id.assert_awaited_once_with(
            RUN_ID,
            status=RunCheckPlanItemStatus.FAILED,
        )
        fake_repo.get_run_progress_stats.assert_awaited_once_with(RUN_ID)

    def test_requires_project_membership(self, client):
        app.dependency_overrides[get_current_user] = lambda: make_user("member")
        app.dependency_overrides[get_scoped_run] = lambda: make_run()
        _override_db()

        with patch(
            "api.endpoints.runs.require_project_role",
            new=AsyncMock(side_effect=HTTPException(status_code=403, detail="Forbidden")),
        ):
            response = client.get(
                f"/api/v1/runs/{RUN_ID}/check-plan",
                headers={"Authorization": "Bearer test"},
            )

        assert response.status_code == 403

    def test_requires_auth(self, client):
        response = client.get(f"/api/v1/runs/{RUN_ID}/check-plan")
        assert response.status_code == 401

    def test_unknown_or_cross_tenant_run_returns_404(self, client):
        """
        get_scoped_run сам отвечает 404, если run не найден в tenant
        текущего пользователя. Здесь эмулируем это поведение зависимости.
        """
        app.dependency_overrides[get_current_user] = lambda: make_user("editor")

        def _raise_not_found():
            raise HTTPException(status_code=404, detail="Run not found")

        app.dependency_overrides[get_scoped_run] = _raise_not_found
        _override_db()

        response = client.get(
            f"/api/v1/runs/{RUN_ID}/check-plan",
            headers={"Authorization": "Bearer test"},
        )

        assert response.status_code == 404


class TestGetRunCheckPlanItem:
    def test_success_returns_item(self, client):
        app.dependency_overrides[get_current_user] = lambda: make_user("editor")
        app.dependency_overrides[get_scoped_run] = lambda: make_run()
        _override_db()

        item = make_plan_item()

        with patch(
            "api.endpoints.runs.require_project_role",
            new=AsyncMock(return_value=None),
        ), patch("api.endpoints.runs.RunCheckPlanItemRepository") as repo_cls:
            fake_repo = MagicMock()
            fake_repo.get_by_id_scoped = AsyncMock(return_value=item)
            repo_cls.return_value = fake_repo

            response = client.get(
                f"/api/v1/runs/{RUN_ID}/check-plan/{ITEM_ID}",
                headers={"Authorization": "Bearer test"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == str(ITEM_ID)
        assert body["run_id"] == str(RUN_ID)
        assert body["status"] == "succeeded"
        fake_repo.get_by_id_scoped.assert_awaited_once_with(ITEM_ID, RUN_ID)

    def test_not_found_returns_404(self, client):
        app.dependency_overrides[get_current_user] = lambda: make_user("editor")
        app.dependency_overrides[get_scoped_run] = lambda: make_run()
        _override_db()

        plan_item_id = uuid.uuid4()

        with patch(
            "api.endpoints.runs.require_project_role",
            new=AsyncMock(return_value=None),
        ), patch("api.endpoints.runs.RunCheckPlanItemRepository") as repo_cls:
            fake_repo = MagicMock()
            fake_repo.get_by_id_scoped = AsyncMock(return_value=None)
            repo_cls.return_value = fake_repo

            response = client.get(
                f"/api/v1/runs/{RUN_ID}/check-plan/{plan_item_id}",
                headers={"Authorization": "Bearer test"},
            )

        assert response.status_code == 404
        fake_repo.get_by_id_scoped.assert_awaited_once_with(plan_item_id, RUN_ID)

    def test_item_from_other_run_returns_404(self, client):
        """
        Cross-run leakage protection: даже если item_id валиден, но
        принадлежит другому run_id, get_by_id_scoped возвращает None
        (repository-level filter), и endpoint отдаёт 404.
        """
        app.dependency_overrides[get_current_user] = lambda: make_user("editor")
        app.dependency_overrides[get_scoped_run] = lambda: make_run()
        _override_db()

        with patch(
            "api.endpoints.runs.require_project_role",
            new=AsyncMock(return_value=None),
        ), patch("api.endpoints.runs.RunCheckPlanItemRepository") as repo_cls:
            fake_repo = MagicMock()
            fake_repo.get_by_id_scoped = AsyncMock(return_value=None)
            repo_cls.return_value = fake_repo

            response = client.get(
                f"/api/v1/runs/{RUN_ID}/check-plan/{ITEM_ID}",
                headers={"Authorization": "Bearer test"},
            )

        assert response.status_code == 404
        fake_repo.get_by_id_scoped.assert_awaited_once_with(ITEM_ID, RUN_ID)

    def test_requires_project_membership(self, client):
        app.dependency_overrides[get_current_user] = lambda: make_user("member")
        app.dependency_overrides[get_scoped_run] = lambda: make_run()
        _override_db()

        with patch(
            "api.endpoints.runs.require_project_role",
            new=AsyncMock(side_effect=HTTPException(status_code=403, detail="Forbidden")),
        ):
            response = client.get(
                f"/api/v1/runs/{RUN_ID}/check-plan/{ITEM_ID}",
                headers={"Authorization": "Bearer test"},
            )

        assert response.status_code == 403

    def test_requires_auth(self, client):
        response = client.get(f"/api/v1/runs/{RUN_ID}/check-plan/{ITEM_ID}")
        assert response.status_code == 401


        