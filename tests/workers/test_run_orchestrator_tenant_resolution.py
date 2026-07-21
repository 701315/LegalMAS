import uuid
from types import SimpleNamespace

import pytest

import workers.run_orchestrator as run_orchestrator


@pytest.mark.asyncio
async def test_orchestrator_resolve_tenant_id_ignores_zero_payload(monkeypatch):
    deal_id = uuid.uuid4()
    db_tenant_id = uuid.uuid4()

    class FakeDealRepository:
        def __init__(self, session):
            self.session = session

        async def internal_unsafe_get_by_id(self, requested_deal_id):
            assert requested_deal_id == deal_id
            return SimpleNamespace(id=deal_id, tenant_id=db_tenant_id)

    monkeypatch.setattr(run_orchestrator, "DealRepository", FakeDealRepository)

    resolved = await run_orchestrator._resolve_tenant_id(
        tenant_id=str(uuid.UUID(int=0)),
        deal_uuid=deal_id,
        db=object(),
    )

    assert resolved == str(db_tenant_id)


@pytest.mark.asyncio
async def test_orchestrator_resolve_tenant_id_ignores_invalid_payload(monkeypatch):
    deal_id = uuid.uuid4()
    db_tenant_id = uuid.uuid4()

    class FakeDealRepository:
        def __init__(self, session):
            self.session = session

        async def internal_unsafe_get_by_id(self, requested_deal_id):
            assert requested_deal_id == deal_id
            return SimpleNamespace(id=deal_id, tenant_id=db_tenant_id)

    monkeypatch.setattr(run_orchestrator, "DealRepository", FakeDealRepository)

    resolved = await run_orchestrator._resolve_tenant_id(
        tenant_id="invalid-tenant-id",
        deal_uuid=deal_id,
        db=object(),
    )

    assert resolved == str(db_tenant_id)