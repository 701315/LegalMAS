# tests/integration/api/test_instructions_global_facade.py

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.deps.auth import CurrentUser, get_current_user
from db.session import get_db


TENANT_ID = uuid.uuid4()
PLAYBOOK_ID = uuid.uuid4()
VERSION_ID = uuid.uuid4()


def make_user(role: str) -> CurrentUser:
    return CurrentUser(
        id=str(uuid.uuid4()),
        global_role=role,
        tenant_id=TENANT_ID,
        email="user@example.com",
    )


def make_playbook() -> MagicMock:
    playbook = MagicMock()
    playbook.id = PLAYBOOK_ID
    playbook.code = "mna_ru_core"
    playbook.title = "M&A RU Core"
    playbook.description = "Core global playbook"
    playbook.deal_type = "mna"
    playbook.jurisdiction = "RU"
    playbook.language = "ru"
    playbook.risk_profile = None
    return playbook


def make_version() -> MagicMock:
    version = MagicMock()
    version.id = VERSION_ID
    version.name = "M&A RU Core v1"
    version.semver = "1.0.0"
    version.status = "published"
    version.playbook_id = PLAYBOOK_ID
    return version


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


class TestListGlobalPlaybooks:
    def test_superadmin_can_list_global_playbooks(self, client):
        app.dependency_overrides[get_current_user] = lambda: make_user("superadmin")
        _override_db()

        playbooks = [make_playbook()]

        with patch(
            "api.endpoints.instructions_global.PlaybookRepository"
        ) as repo_cls:
            fake_repo = MagicMock()
            fake_repo.list_playbooks = AsyncMock(return_value=playbooks)
            repo_cls.return_value = fake_repo

            response = client.get(
                "/api/v1/admin/instructions/global",
                headers={"Authorization": "Bearer test"},
            )

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["id"] == str(PLAYBOOK_ID)
        assert body[0]["code"] == "mna_ru_core"
        assert body[0]["title"] == "M&A RU Core"

    def test_tenant_admin_can_list_global_playbooks(self, client):
        app.dependency_overrides[get_current_user] = lambda: make_user("tenant_admin")
        _override_db()

        playbooks = [make_playbook()]

        with patch(
            "api.endpoints.instructions_global.PlaybookRepository"
        ) as repo_cls:
            fake_repo = MagicMock()
            fake_repo.list_playbooks = AsyncMock(return_value=playbooks)
            repo_cls.return_value = fake_repo

            response = client.get(
                "/api/v1/admin/instructions/global",
                headers={"Authorization": "Bearer test"},
            )

        assert response.status_code == 200

    def test_non_admin_forbidden(self, client):
        app.dependency_overrides[get_current_user] = lambda: make_user("member")
        _override_db()

        response = client.get(
            "/api/v1/admin/instructions/global",
            headers={"Authorization": "Bearer test"},
        )

        assert response.status_code == 403

    def test_requires_auth(self, client):
        response = client.get("/api/v1/admin/instructions/global")
        assert response.status_code == 401


class TestListGlobalPlaybookVersions:
    def test_returns_versions_for_playbook(self, client):
        app.dependency_overrides[get_current_user] = lambda: make_user("superadmin")
        _override_db()

        playbook = make_playbook()
        versions = [make_version()]

        with patch(
            "api.endpoints.instructions_global.PlaybookRepository"
        ) as repo_cls:
            fake_repo = MagicMock()
            fake_repo.get_playbook_by_id = AsyncMock(return_value=playbook)
            fake_repo.list_versions_for_playbook = AsyncMock(return_value=versions)
            repo_cls.return_value = fake_repo

            response = client.get(
                f"/api/v1/admin/instructions/global/{PLAYBOOK_ID}/versions",
                headers={"Authorization": "Bearer test"},
            )

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["id"] == str(VERSION_ID)
        assert body[0]["playbook_id"] == str(PLAYBOOK_ID)
        assert body[0]["status"] == "published"

    def test_calls_repo_with_scoped_playbook_id(self, client):
        app.dependency_overrides[get_current_user] = lambda: make_user("tenant_admin")
        _override_db()

        playbook = make_playbook()

        with patch(
            "api.endpoints.instructions_global.PlaybookRepository"
        ) as repo_cls:
            fake_repo = MagicMock()
            fake_repo.get_playbook_by_id = AsyncMock(return_value=playbook)
            fake_repo.list_versions_for_playbook = AsyncMock(return_value=[])
            repo_cls.return_value = fake_repo

            response = client.get(
                f"/api/v1/admin/instructions/global/{PLAYBOOK_ID}/versions",
                headers={"Authorization": "Bearer test"},
            )

            assert response.status_code == 200
            fake_repo.list_versions_for_playbook.assert_awaited_once_with(PLAYBOOK_ID)

    def test_returns_404_for_unknown_playbook(self, client):
        app.dependency_overrides[get_current_user] = lambda: make_user("superadmin")
        _override_db()

        with patch(
            "api.endpoints.instructions_global.PlaybookRepository"
        ) as repo_cls:
            fake_repo = MagicMock()
            fake_repo.get_playbook_by_id = AsyncMock(return_value=None)
            fake_repo.list_versions_for_playbook = AsyncMock(return_value=[])
            repo_cls.return_value = fake_repo

            response = client.get(
                f"/api/v1/admin/instructions/global/{PLAYBOOK_ID}/versions",
                headers={"Authorization": "Bearer test"},
            )

        assert response.status_code == 404

    def test_non_admin_forbidden(self, client):
        app.dependency_overrides[get_current_user] = lambda: make_user("member")
        _override_db()

        response = client.get(
            f"/api/v1/admin/instructions/global/{PLAYBOOK_ID}/versions",
            headers={"Authorization": "Bearer test"},
        )

        assert response.status_code == 403

    def test_requires_auth(self, client):
        response = client.get(f"/api/v1/admin/instructions/global/{PLAYBOOK_ID}/versions")
        assert response.status_code == 401



        