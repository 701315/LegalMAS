from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.deps.auth import CurrentUser, get_current_user
from db.session import get_db


TENANT_ID = uuid.uuid4()


def make_user(role: str) -> CurrentUser:
    return CurrentUser(
        id=str(uuid.uuid4()),
        global_role=role,
        tenant_id=TENANT_ID,
        email="admin@example.com",
    )


class DummySession:
    async def commit(self):
        return None

    async def refresh(self, _obj):
        return None


@pytest.fixture(autouse=True)
def _reset_overrides():
    app.dependency_overrides = {}
    yield
    app.dependency_overrides = {}


@pytest.fixture
def client():
    return TestClient(app)


def override_user():
    app.dependency_overrides[get_current_user] = lambda: make_user("superadmin")


def override_db():
    app.dependency_overrides[get_db] = lambda: DummySession()


def test_create_playbook_version_from_line_uses_instruction_code(client, mocker):
    override_user()
    override_db()

    line_id = uuid.uuid4()
    version_id = uuid.uuid4()
    model_config_id = uuid.uuid4()

    line = type("Playbook", (), {})()
    line.id = line_id

    item1 = type("PlaybookLineItem", (), {})()
    item1.kind = "check"
    item1.instruction_code = "encumbrances_warranty"
    item1.order_index = 10

    item2 = type("PlaybookLineItem", (), {})()
    item2.kind = "check"
    item2.instruction_code = "change_of_control"
    item2.order_index = 20

    fake_version = type("PlaybookVersion", (), {})()
    fake_version.id = version_id
    fake_version.name = "Playbook from template"
    fake_version.semver = "0.1.0"
    fake_version.status = "draft"
    fake_version.playbook_id = line_id

    repo_cls = mocker.patch("api.endpoints.playbooks.PlaybookRepository")
    repo = repo_cls.return_value
    repo.get_line_with_items = mocker.AsyncMock(return_value=(line, [item1, item2]))
    repo.create_version = mocker.AsyncMock(return_value=fake_version)

    build_compiled_checks = mocker.patch("api.endpoints.playbooks.build_compiled_checks")
    build_compiled_checks.return_value = {
        "checks": [],
        "meta": {
            "config": {
                "bundles": [],
                "include_ids": ["encumbrances_warranty", "change_of_control"],
                "exclude_ids": [],
                "profile": None,
            },
            "bundle_id": None,
            "check_ids": ["encumbrances_warranty", "change_of_control"],
            "version_schema": 1,
            "source_type": "global_checks_v1",
        },
    }

    load_global_checks = mocker.patch("api.endpoints.playbooks.load_global_checks")
    load_global_checks.return_value = {
        "encumbrances_warranty": object(),
        "change_of_control": object(),
    }

    payload = {
        "name": None,
        "bundles": [],
        "include_ids": [],
        "exclude_ids": [],
        "profile": None,
        "model_config_id": str(model_config_id),
        "playbook_id": None,
        "from_line_id": str(line_id),
    }

    resp = client.post(
        "/api/v1/playbooks",
        json=payload,
        headers={"Authorization": "Bearer test"},
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["id"] == str(version_id)
    assert body["playbook_id"] == str(line_id)

    build_compiled_checks.assert_called_once()
    kwargs = build_compiled_checks.call_args.kwargs
    assert kwargs["include_ids"] == ["encumbrances_warranty", "change_of_control"]
    assert kwargs["bundles"] == []
    assert kwargs["exclude_ids"] == []


    