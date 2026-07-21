import pytest
from fastapi.testclient import TestClient

from src.api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_cannot_update_published(client, published_playbook):
    response = client.patch(
        f"/api/v1/playbooks/{published_playbook.id}",
        json={"name": "new name"},
    )
    assert response.status_code == 409


def test_update_draft_rebuilds_hash(client, draft_playbook):
    old_hash = draft_playbook.source_payload_sha256

    response = client.patch(
        f"/api/v1/playbooks/{draft_playbook.id}",
        json={"profile": "core"},
    )

    assert response.status_code == 200
    assert response.json()["source_payload_sha256"] != old_hash


def test_archive_only_published(client, draft_playbook):
    response = client.post(f"/api/v1/playbooks/{draft_playbook.id}/archive")
    assert response.status_code == 400