import uuid
from types import SimpleNamespace

import pytest

import core.tenant_resolver as tenant_resolver
from core.exceptions import PermanentError


@pytest.mark.asyncio
async def test_resolve_artifact_tenant_id_prefers_db_tenant_over_zero_payload(monkeypatch):
    deal_id = uuid.uuid4()
    document_id = uuid.uuid4()
    db_tenant_id = uuid.uuid4()

    class FakeDocumentRepository:
        def __init__(self, session):
            self.session = session

        async def get_by_id(self, requested_document_id):
            assert requested_document_id == document_id
            return SimpleNamespace(id=document_id, deal_id=deal_id)

    class FakeDealRepository:
        def __init__(self, session):
            self.session = session

        async def internal_unsafe_get_by_id(self, requested_deal_id):
            assert requested_deal_id == deal_id
            return SimpleNamespace(id=deal_id, tenant_id=db_tenant_id)

    monkeypatch.setattr(tenant_resolver, "DocumentRepository", FakeDocumentRepository)
    monkeypatch.setattr(tenant_resolver, "DealRepository", FakeDealRepository)

    resolved = await tenant_resolver.resolve_artifact_tenant_id(
        session=object(),
        document_id=document_id,
        payload_tenant_id=str(uuid.UUID(int=0)),
    )

    assert resolved == db_tenant_id


@pytest.mark.asyncio
async def test_resolve_artifact_tenant_id_falls_back_to_payload_when_db_tenant_missing(monkeypatch):
    deal_id = uuid.uuid4()
    payload_tenant_id = uuid.uuid4()

    class FakeDealRepository:
        def __init__(self, session):
            self.session = session

        async def internal_unsafe_get_by_id(self, requested_deal_id):
            assert requested_deal_id == deal_id
            return SimpleNamespace(id=deal_id, tenant_id=None)

    monkeypatch.setattr(tenant_resolver, "DealRepository", FakeDealRepository)

    resolved = await tenant_resolver.resolve_artifact_tenant_id(
        session=object(),
        deal_id=deal_id,
        payload_tenant_id=str(payload_tenant_id),
    )

    assert resolved == payload_tenant_id


@pytest.mark.asyncio
async def test_resolve_artifact_tenant_id_raises_when_db_tenant_missing_and_payload_invalid(
    monkeypatch,
):
    deal_id = uuid.uuid4()

    class FakeDealRepository:
        def __init__(self, session):
            self.session = session

        async def internal_unsafe_get_by_id(self, requested_deal_id):
            assert requested_deal_id == deal_id
            return SimpleNamespace(id=deal_id, tenant_id=uuid.UUID(int=0))

    monkeypatch.setattr(tenant_resolver, "DealRepository", FakeDealRepository)

    with pytest.raises(PermanentError):
        await tenant_resolver.resolve_artifact_tenant_id(
            session=object(),
            deal_id=deal_id,
            payload_tenant_id="not-a-uuid",
        )