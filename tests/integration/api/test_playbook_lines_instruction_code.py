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


def override_admin():
    app.dependency_overrides[get_current_user] = lambda: make_user("superadmin")


def override_db():
    app.dependency_overrides[get_db] = lambda: DummySession()


def test_create_get_update_playbook_line_with_instruction_code(client, mocker):
    override_admin()
    override_db()

    line_id = uuid.uuid4()

    created_line = type("Playbook", (), {})()
    created_line.id = line_id
    created_line.code = "mna_ru_core"
    created_line.title = "M&A RU Core"
    created_line.description = "Core template"
    created_line.deal_type = "mna"
    created_line.jurisdiction = "RU"
    created_line.language = "ru"
    created_line.risk_profile = None

    item1 = type("PlaybookLineItem", (), {})()
    item1.kind = "check"
    item1.instruction_code = "encumbrances_warranty"
    item1.order_index = 10

    item2 = type("PlaybookLineItem", (), {})()
    item2.kind = "check"
    item2.instruction_code = "change_of_control"
    item2.order_index = 20

    repo_cls = mocker.patch("api.endpoints.playbooks.PlaybookRepository")
    repo = repo_cls.return_value
    repo.create_line_with_items = mocker.AsyncMock(return_value=(created_line, [item1, item2]))
    repo.get_line_with_items = mocker.AsyncMock(return_value=(created_line, [item1, item2]))
    repo.update_line_with_items = mocker.AsyncMock(return_value=(created_line, [item2]))

    create_payload = {
        "title": "M&A RU Core",
        "description": "Core template",
        "deal_type": "mna",
        "jurisdiction": "RU",
        "language": "ru",
        "items": [
            {"kind": "check", "instruction_code": "encumbrances_warranty", "order_index": 10},
            {"kind": "check", "instruction_code": "change_of_control", "order_index": 20},
        ],
    }

    create_resp = client.post(
        "/api/v1/playbooks/lines",
        json=create_payload,
        headers={"Authorization": "Bearer test"},
    )
    assert create_resp.status_code == 201, create_resp.text
    create_body = create_resp.json()
    assert create_body["id"] == str(line_id)
    assert create_body["items"][0]["instruction_code"] == "encumbrances_warranty"
    assert create_body["items"][1]["instruction_code"] == "change_of_control"

    get_resp = client.get(
        f"/api/v1/playbooks/lines/{line_id}",
        headers={"Authorization": "Bearer test"},
    )
    assert get_resp.status_code == 200, get_resp.text
    get_body = get_resp.json()
    assert get_body["items"][0]["instruction_code"] == "encumbrances_warranty"
    assert get_body["items"][1]["instruction_code"] == "change_of_control"

    update_payload = {
        "title": "M&A RU Core",
        "description": "Core template updated",
        "deal_type": "mna",
        "jurisdiction": "RU",
        "language": "ru",
        "items": [
            {"kind": "check", "instruction_code": "change_of_control", "order_index": 20},
        ],
    }

    update_resp = client.put(
        f"/api/v1/playbooks/lines/{line_id}",
        json=update_payload,
        headers={"Authorization": "Bearer test"},
    )
    assert update_resp.status_code == 200, update_resp.text
    update_body = update_resp.json()
    assert len(update_body["items"]) == 1
    assert update_body["items"][0]["instruction_code"] == "change_of_control"


    