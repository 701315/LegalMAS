import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.deps.auth import get_current_user
from db.session import get_db
from api.endpoints.qc import router as qc_router


class FakeResultRepository:
    def __init__(self, rows_per_call: int = 1):
        self.rows_per_call = rows_per_call

    async def update_review_qc(
        self,
        run_id,
        document_id,
        check_id,
        segment_id,
        qc_status,
        qc_by,
        qc_comment,
    ):
        # CHANGED: теперь возвращаем int (rowcount), а не список Row objects
        return self.rows_per_call


class FakeRunRepository:
    def __init__(self, run):
        self.run = run

    async def get_by_id(self, run_id):
        return self.run


class FakeDealRepository:
    def __init__(self, deal):
        self.deal = deal

    async def get_by_id(self, deal_id):
        return self.deal


class FakeAuditRepository:
    def __init__(self):
        self.logged = []

    async def log(self, **kwargs):
        self.logged.append(kwargs)
        return SimpleNamespace(id=uuid.uuid4())


@pytest.fixture
def ids():
    return {
        "run_id": str(uuid.uuid4()),
        "deal_id": str(uuid.uuid4()),
        "document_id": str(uuid.uuid4()),
        "tenant_id": str(uuid.uuid4()),
    }


@pytest.fixture
def app(ids, monkeypatch):
    app = FastAPI()
    app.include_router(qc_router)

    current_user = SimpleNamespace(
        id=uuid.uuid4(),
        email="qc.user@example.com",
        global_role="admin",
    )

    async def override_get_db():
        class DummySession:
            async def commit(self):
                return None

        yield DummySession()

    async def override_get_current_user():
        return current_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    import services.review_qc_service as service_module
    import api.endpoints.qc as endpoint_module

    fake_run = SimpleNamespace(
        id=uuid.UUID(ids["run_id"]),
        deal_id=uuid.UUID(ids["deal_id"]),
    )
    fake_deal = SimpleNamespace(
        id=uuid.UUID(ids["deal_id"]),
        tenant_id=uuid.UUID(ids["tenant_id"]),
    )
    fake_audit_repo = FakeAuditRepository()

    monkeypatch.setattr(
        service_module,
        "RunRepository",
        lambda db: FakeRunRepository(fake_run),
    )
    monkeypatch.setattr(
        service_module,
        "DealRepository",
        lambda db: FakeDealRepository(fake_deal),
    )
    monkeypatch.setattr(
        service_module,
        "ResultRepository",
        lambda db: FakeResultRepository(rows_per_call=2),
    )
    monkeypatch.setattr(
        service_module,
        "AuditRepository",
        lambda db: fake_audit_repo,
    )
    monkeypatch.setattr(
        endpoint_module,
        "require_project_role",
        _allow_project_role,
    )

    app.state.fake_audit_repo = fake_audit_repo
    return app


async def _allow_project_role(db, user, deal_id, allowed_roles):
    return None


@pytest.mark.anyio
async def test_update_review_qc_success(app, ids):
    payload = {
        "finding": {
            "run_id": ids["run_id"],
            "document_id": ids["document_id"],
            "check_id": "coc_001",
            "segment_id": "seg-1",
        },
        "qc_status": "approved",
        "comment": "Looks correct",
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        response = await ac.post("/qc/review", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == ids["run_id"]
    assert body["document_id"] == ids["document_id"]
    assert body["check_id"] == "coc_001"
    assert body["segment_id"] == "seg-1"
    assert body["qc_status"] == "approved"
    assert body["updated_rows_count"] == 2
    assert len(app.state.fake_audit_repo.logged) == 1


@pytest.mark.anyio
async def test_bulk_update_review_qc_success(app, ids):
    payload = {
        "findings": [
            {
                "run_id": ids["run_id"],
                "document_id": ids["document_id"],
                "check_id": "coc_001",
                "segment_id": "seg-1",
            },
            {
                "run_id": ids["run_id"],
                "document_id": str(uuid.uuid4()),
                "check_id": "nda_002",
                "segment_id": None,
            },
        ],
        "qc_status": "needs_review",
        "comment": "Need second look",
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        response = await ac.post("/qc/review/bulk", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == ids["run_id"]
    assert body["qc_status"] == "needs_review"
    assert body["total_findings"] == 2
    assert body["updated_findings"] == 2
    assert body["changed_findings"] == 2
    assert body["updated_rows_count"] == 4  # 2 findings × 2 rows каждый
    assert len(body["items"]) == 2
    assert len(app.state.fake_audit_repo.logged) == 1


@pytest.mark.anyio
async def test_bulk_update_review_qc_rejects_mixed_run_ids(app, ids):
    payload = {
        "findings": [
            {
                "run_id": ids["run_id"],
                "document_id": ids["document_id"],
                "check_id": "coc_001",
                "segment_id": "seg-1",
            },
            {
                "run_id": str(uuid.uuid4()),
                "document_id": str(uuid.uuid4()),
                "check_id": "nda_002",
                "segment_id": None,
            },
        ],
        "qc_status": "approved",
        "comment": None,
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        response = await ac.post("/qc/review/bulk", json=payload)

    assert response.status_code == 422


@pytest.mark.anyio
async def test_update_review_qc_invalid_run_id(app, ids):
    payload = {
        "finding": {
            "run_id": "not-a-uuid",
            "document_id": ids["document_id"],
            "check_id": "coc_001",
            "segment_id": None,
        },
        "qc_status": "approved",
        "comment": None,
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        response = await ac.post("/qc/review", json=payload)

    assert response.status_code == 422