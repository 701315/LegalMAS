"""
Integration tests for all repositories.
Each test uses a database session with automatic rollback.
Requires PostgreSQL to be running (make up).
"""

import uuid

import pytest

from src.core.constants import (
    DealStatus,
    DocumentStatus,
    PlaybookStatus,
    QCStatus,
    Severity,
)
from src.db.repositories import (
    AuditRepository,
    DealRepository,
    DocumentRepository,
    DocumentVersionRepository,
    IdempotencyRepository,
    PlaybookRepository,
    RelationRepository,
    ResultRepository,
    RunRepository,
)


# ============================================================
# Deal Repository
# ============================================================


class TestDealRepository:
    @pytest.mark.asyncio
    async def test_create_and_get(self, db_session, tenant_id):
        repo = DealRepository(db_session)

        deal = await repo.create(
            tenant_id=tenant_id,
            name="Test Deal",
            deal_type="SPA",
            jurisdiction="RU",
        )

        assert deal.id is not None
        assert deal.name == "Test Deal"
        assert deal.status == DealStatus.CREATED.value

        fetched = await repo.get_by_id(deal.id)
        assert fetched is not None
        assert fetched.name == "Test Deal"

    @pytest.mark.asyncio
    async def test_get_by_tenant(self, db_session, tenant_id):
        repo = DealRepository(db_session)

        await repo.create(tenant_id=tenant_id, name="Deal A")
        await repo.create(tenant_id=tenant_id, name="Deal B")
        other_tenant = uuid.uuid4()
        await repo.create(tenant_id=other_tenant, name="Deal C")

        deals = await repo.get_by_tenant(tenant_id)
        assert len(deals) == 2
        names = {d.name for d in deals}
        assert names == {"Deal A", "Deal B"}

    @pytest.mark.asyncio
    async def test_update_status(self, db_session, tenant_id):
        repo = DealRepository(db_session)
        deal = await repo.create(tenant_id=tenant_id, name="Status Test")

        updated = await repo.update_status(deal.id, DealStatus.IMPORTING.value)
        assert updated is not None
        assert updated.status == DealStatus.IMPORTING.value

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, db_session):
        repo = DealRepository(db_session)
        result = await repo.get_by_id(uuid.uuid4())
        assert result is None


# ============================================================
# Document Repository
# ============================================================


class TestDocumentRepository:
    async def _create_deal_and_bundle(self, session, tenant_id):
        """Helper: create a deal and bundle for document tests."""
        deal_repo = DealRepository(session)
        deal = await deal_repo.create(tenant_id=tenant_id, name="Doc Test Deal")

        from src.db.models.bundle import Bundle
        bundle = Bundle(deal_id=deal.id, source_type="local", status="completed", file_count=0)
        session.add(bundle)
        await session.flush()

        return deal, bundle

    @pytest.mark.asyncio
    async def test_create_and_get(self, db_session, tenant_id):
        deal, bundle = await self._create_deal_and_bundle(db_session, tenant_id)
        repo = DocumentRepository(db_session)

        doc = await repo.create(
            deal_id=deal.id,
            bundle_id=bundle.id,
            filename="contract.pdf",
            folder_path="01. Contracts",
            sha256_file="abc123",
        )

        assert doc.id is not None
        assert doc.filename == "contract.pdf"
        assert doc.status == DocumentStatus.PENDING.value

        fetched = await repo.get_by_id(doc.id)
        assert fetched is not None
        assert fetched.folder_path == "01. Contracts"

    @pytest.mark.asyncio
    async def test_get_by_sha256_for_dedup(self, db_session, tenant_id):
        deal, bundle = await self._create_deal_and_bundle(db_session, tenant_id)
        repo = DocumentRepository(db_session)

        await repo.create(
            deal_id=deal.id, bundle_id=bundle.id,
            filename="doc1.pdf", sha256_file="hash_abc",
        )

        found = await repo.get_by_sha256(deal.id, "hash_abc")
        assert found is not None
        assert found.filename == "doc1.pdf"

        not_found = await repo.get_by_sha256(deal.id, "hash_xyz")
        assert not_found is None

    @pytest.mark.asyncio
    async def test_count_by_status(self, db_session, tenant_id):
        deal, bundle = await self._create_deal_and_bundle(db_session, tenant_id)
        repo = DocumentRepository(db_session)

        await repo.create(deal_id=deal.id, bundle_id=bundle.id, filename="a.pdf")
        await repo.create(deal_id=deal.id, bundle_id=bundle.id, filename="b.pdf")
        doc3 = await repo.create(deal_id=deal.id, bundle_id=bundle.id, filename="c.pdf")
        await repo.update_status(doc3.id, DocumentStatus.QUARANTINE.value)

        counts = await repo.count_by_status(deal.id)
        assert counts.get(DocumentStatus.PENDING.value, 0) == 2
        assert counts.get(DocumentStatus.QUARANTINE.value, 0) == 1

    @pytest.mark.asyncio
    async def test_get_quarantined(self, db_session, tenant_id):
        deal, bundle = await self._create_deal_and_bundle(db_session, tenant_id)
        repo = DocumentRepository(db_session)

        await repo.create(deal_id=deal.id, bundle_id=bundle.id, filename="good.pdf")
        bad = await repo.create(deal_id=deal.id, bundle_id=bundle.id, filename="bad.pdf")
        await repo.update_status(bad.id, DocumentStatus.QUARANTINE.value)

        quarantined = await repo.get_quarantined(deal.id)
        assert len(quarantined) == 1
        assert quarantined[0].filename == "bad.pdf"


# ============================================================
# DocumentVersion Repository
# ============================================================


class TestDocumentVersionRepository:
    @pytest.mark.asyncio
    async def test_create_and_update_refs(self, db_session, tenant_id):
        deal_repo = DealRepository(db_session)
        deal = await deal_repo.create(tenant_id=tenant_id, name="V Test")

        from src.db.models.bundle import Bundle
        bundle = Bundle(deal_id=deal.id, source_type="local", status="done", file_count=1)
        db_session.add(bundle)
        await db_session.flush()

        doc_repo = DocumentRepository(db_session)
        doc = await doc_repo.create(deal_id=deal.id, bundle_id=bundle.id, filename="t.pdf")

        ver_repo = DocumentVersionRepository(db_session)
        ver = await ver_repo.create(document_id=doc.id, version_num=1, original_ref="s3://bucket/orig.pdf")

        assert ver.text_layout_raw_ref is None

        updated = await ver_repo.update_refs(
            ver.id,
            raw_ref="s3://bucket/raw.json",
            sanitized_ref="s3://bucket/sanitized.json",
        )

        assert updated is not None
        assert updated.text_layout_raw_ref == "s3://bucket/raw.json"
        assert updated.text_layout_sanitized_ref == "s3://bucket/sanitized.json"

    @pytest.mark.asyncio
    async def test_get_latest(self, db_session, tenant_id):
        deal_repo = DealRepository(db_session)
        deal = await deal_repo.create(tenant_id=tenant_id, name="VL Test")

        from src.db.models.bundle import Bundle
        bundle = Bundle(deal_id=deal.id, source_type="local", status="done", file_count=1)
        db_session.add(bundle)
        await db_session.flush()

        doc_repo = DocumentRepository(db_session)
        doc = await doc_repo.create(deal_id=deal.id, bundle_id=bundle.id, filename="t.pdf")

        ver_repo = DocumentVersionRepository(db_session)
        await ver_repo.create(document_id=doc.id, version_num=1)
        await ver_repo.create(document_id=doc.id, version_num=2)

        latest = await ver_repo.get_latest(doc.id)
        assert latest is not None
        assert latest.version_num == 2


# ============================================================
# Playbook Repository
# ============================================================

import pytest
from sqlalchemy import delete

from src.db.models.playbook import PlaybookVersion, ModelConfig


@pytest.fixture(autouse=True)
async def cleanup_playbooks(db_session):
    """Clean up playbook_versions and model_configs before each test."""
    await db_session.execute(delete(PlaybookVersion))
    await db_session.execute(delete(ModelConfig))
    await db_session.commit()


class TestPlaybookRepository:
    @pytest.mark.asyncio
    async def test_create_and_get_default(self, db_session):
        repo = PlaybookRepository(db_session)

        mc = await repo.create_model_config(name="test-mc")
        pv = await repo.create_version(
            name="Test Playbook",
            semver="1.0.0",
            model_config_id=mc.id,
            status=PlaybookStatus.DEFAULT.value,
            compiled_checks={"checks": []},
        )

        default = await repo.get_default()
        assert default is not None
        assert default.id == pv.id
        assert default.semver == "1.0.0"

    @pytest.mark.asyncio
    async def test_promote_to_default(self, db_session):
        repo = PlaybookRepository(db_session)

        mc = await repo.create_model_config(name="promo-mc")
        v1 = await repo.create_version(
            name="PB", semver="1.0.0", model_config_id=mc.id,
            status=PlaybookStatus.DEFAULT.value,
        )
        v2 = await repo.create_version(
            name="PB", semver="2.0.0", model_config_id=mc.id,
            status=PlaybookStatus.DRAFT.value,
        )

        promoted = await repo.promote_to_default(v2.id)
        assert promoted is not None
        assert promoted.status == PlaybookStatus.DEFAULT.value

        # v1 should now be stable
        old = await repo.get_by_id(v1.id)
        assert old is not None
        assert old.status == PlaybookStatus.STABLE.value


# ============================================================
# Result Repository
# ============================================================


class TestResultRepository:
    async def _setup(self, session, tenant_id):
        """Helper: create deal, bundle, doc, playbook, run."""
        deal_repo = DealRepository(session)
        deal = await deal_repo.create(tenant_id=tenant_id, name="Result Test")

        from src.db.models.bundle import Bundle
        bundle = Bundle(deal_id=deal.id, source_type="local", status="done", file_count=1)
        session.add(bundle)
        await session.flush()

        doc_repo = DocumentRepository(session)
        doc = await doc_repo.create(deal_id=deal.id, bundle_id=bundle.id, filename="t.pdf")

        pb_repo = PlaybookRepository(session)
        mc = await pb_repo.create_model_config(name="r-mc")
        pv = await pb_repo.create_version(
            name="R", semver="1.0.0", model_config_id=mc.id,
            status=PlaybookStatus.DEFAULT.value,
        )

        run_repo = RunRepository(session)
        run = await run_repo.create(
            deal_id=deal.id, playbook_version_id=pv.id, model_config_id=mc.id,
        )

        return deal, doc, run

    @pytest.mark.asyncio
    async def test_create_and_count(self, db_session, tenant_id):
        deal, doc, run = await self._setup(db_session, tenant_id)
        repo = ResultRepository(db_session)

        await repo.create(
            run_id=run.id, document_id=doc.id, check_id="coc_001",
            check_name="Change of Control", result="fail", severity="critical",
        )
        await repo.create(
            run_id=run.id, document_id=doc.id, check_id="gov_001",
            check_name="Governing Law", result="pass", severity="pass",
        )

        counts = await repo.count_by_severity(run.id)
        assert counts.get("critical") == 1
        assert counts.get("pass") == 1

    @pytest.mark.asyncio
    async def test_qc_update(self, db_session, tenant_id):
        deal, doc, run = await self._setup(db_session, tenant_id)
        repo = ResultRepository(db_session)

        cr = await repo.create(
            run_id=run.id, document_id=doc.id, check_id="test_001",
            check_name="Test", result="fail", severity="high",
        )

        assert cr.qc_status == QCStatus.PENDING.value

        updated = await repo.update_qc(
            cr.id, qc_status=QCStatus.CONFIRMED.value,
            qc_by="reviewer@firm.com", qc_comment="Looks correct",
        )

        assert updated is not None
        assert updated.qc_status == QCStatus.CONFIRMED.value
        assert updated.qc_by == "reviewer@firm.com"
        assert updated.qc_at is not None

    @pytest.mark.asyncio
    async def test_bulk_qc(self, db_session, tenant_id):
        deal, doc, run = await self._setup(db_session, tenant_id)
        repo = ResultRepository(db_session)

        cr1 = await repo.create(
            run_id=run.id, document_id=doc.id, check_id="a",
            check_name="A", result="pass", severity="pass",
        )
        cr2 = await repo.create(
            run_id=run.id, document_id=doc.id, check_id="b",
            check_name="B", result="pass", severity="pass",
        )

        count = await repo.bulk_update_qc(
            [cr1.id, cr2.id],
            qc_status=QCStatus.CONFIRMED.value,
            qc_by="admin@firm.com",
        )
        assert count == 2


# ============================================================
# Idempotency Repository
# ============================================================


class TestIdempotencyRepository:
    @pytest.mark.asyncio
    async def test_get_or_create_new(self, db_session, tenant_id):
        repo = IdempotencyRepository(db_session)

        record, is_new = await repo.get_or_create(
            tenant_id=tenant_id, endpoint="import", key="key-001",
        )

        assert is_new is True
        assert record.status == "processing"

    @pytest.mark.asyncio
    async def test_get_or_create_existing(self, db_session, tenant_id):
        repo = IdempotencyRepository(db_session)

        r1, new1 = await repo.get_or_create(tenant_id, "import", "key-002")
        r2, new2 = await repo.get_or_create(tenant_id, "import", "key-002")

        assert new1 is True
        assert new2 is False
        assert r1.id == r2.id

    @pytest.mark.asyncio
    async def test_mark_completed(self, db_session, tenant_id):
        repo = IdempotencyRepository(db_session)

        record, _ = await repo.get_or_create(tenant_id, "import", "key-003")
        await repo.mark_completed(record.id, response_hash="abc", result={"bundle_id": "123"})

        # Fetch again
        record2, is_new = await repo.get_or_create(tenant_id, "import", "key-003")
        assert is_new is False
        assert record2.status == "completed"
        assert record2.result == {"bundle_id": "123"}


# ============================================================
# Audit Repository
# ============================================================


class TestAuditRepository:
    @pytest.mark.asyncio
    async def test_log_and_retrieve(self, db_session, tenant_id):
        # Need a deal for deal_id
        deal_repo = DealRepository(db_session)
        deal = await deal_repo.create(tenant_id=tenant_id, name="Audit Test")

        repo = AuditRepository(db_session)

        await repo.log(
            tenant_id=tenant_id, deal_id=deal.id,
            action="IMPORT", actor="user@firm.com",
            actor_role="deal_owner",
            details={"doc_count": 10},
        )
        await repo.log(
            tenant_id=tenant_id, deal_id=deal.id,
            action="EXPORT", actor="user@firm.com",
        )

        logs = await repo.get_by_deal(deal.id)
        assert len(logs) == 2

        import_logs = await repo.get_by_deal(deal.id, action="IMPORT")
        assert len(import_logs) == 1
        assert import_logs[0].details == {"doc_count": 10}
