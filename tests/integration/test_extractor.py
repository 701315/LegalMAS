"""
Integration tests for Extract Worker — production.

Tests the full extraction pipeline:
  Document in MinIO → _extract_document_async() → textlayoutraw in MinIO + DB updated

Requires Docker services (make up) and seed data (python -m scripts.seed).
"""

import os
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import DocumentStatus
from src.core.exceptions import QuarantineError
from src.db.models.bundle import Bundle
from src.db.repositories import (
    DealRepository,
    DocumentRepository,
    DocumentVersionRepository,
    PlaybookRepository,
)
from src.mas_queue.celery_app import celery_app
from src.storage.artifact_store import ArtifactPath, ArtifactStore
from src.workers.extract_worker import _extract_document_async

pytestmark = pytest.mark.asyncio(scope="module")

FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "fixtures",
)
TENANT_ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(autouse=True)
def celery_eager():
    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)
    yield
    celery_app.conf.update(task_always_eager=False, task_eager_propagates=False)


async def ensure_seed_async(db_session: AsyncSession) -> None:
    repo = PlaybookRepository(db_session)
    has_seed = await repo.get_default() is not None

    if not has_seed:
        pytest.skip("Seed data required. Run python -m scripts.seed")


async def setup_document(
    db_session: AsyncSession,
    pdf_filename: str,
) -> tuple[str, str, str]:
    """
    Create deal / document / version, upload PDF to MinIO, using test db_session.
    """
    pdf_path = os.path.join(FIXTURES_DIR, pdf_filename)
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(
            f"Fixture {pdf_filename} not found. " "Run python -m scripts.create_extraction_fixtures"
        )
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    store = ArtifactStore()

    deal_repo = DealRepository(db_session)
    doc_repo = DocumentRepository(db_session)
    ver_repo = DocumentVersionRepository(db_session)

    deal = await deal_repo.create(
        tenant_id=uuid.UUID(TENANT_ID),
        name=f"Extract Test {uuid.uuid4().hex[:8]}",
    )
    deal_id = str(deal.id)

    bundle = Bundle(
        deal_id=deal.id,
        source_type="local",
        status="done",
        file_count=1,
    )
    db_session.add(bundle)
    await db_session.flush()

    doc = await doc_repo.create(
        deal_id=deal.id,
        bundle_id=bundle.id,
        filename=pdf_filename,
        status=DocumentStatus.PENDING.value,
    )
    doc_id = str(doc.id)

    artifact_path = ArtifactPath.original(TENANT_ID, deal_id, doc_id)
    original_ref = store.put_file(
        artifact_path + ".pdf",
        pdf_bytes,
        content_type="application/pdf",
    )

    version = await ver_repo.create(
        document_id=doc.id,
        version_num=1,
        original_ref=original_ref,
    )
    version_id = str(version.id)

    # Для интеграции логично зафиксировать состояние
    await db_session.commit()

    return deal_id, doc_id, version_id


async def get_doc_info(
    db_session: AsyncSession,
    doc_id: str,
    ver_id: str,
) -> dict:
    doc_repo = DocumentRepository(db_session)
    ver_repo = DocumentVersionRepository(db_session)

    doc = await doc_repo.get_by_id(uuid.UUID(doc_id))
    ver = await ver_repo.get_by_id(uuid.UUID(ver_id))

    return {
        "status": doc.status if doc else None,
        "raw_ref": ver.text_layout_raw_ref if ver else None,
        "strategy": ver.extraction_strategy if ver else None,
    }


class TestExtractWorkerTextPDF:
    @pytest.mark.asyncio
    async def test_text_pdf_extraction(self, db_session: AsyncSession):
        await ensure_seed_async(db_session)
        deal_id, doc_id, ver_id = await setup_document(
            db_session,
            "test_text_clean.pdf",
        )

        result = await _extract_document_async(
            document_version_id=ver_id,
            document_id=doc_id,
            deal_id=deal_id,
            tenant_id=TENANT_ID,
            db=db_session,
        )

        assert result["elements"] > 0
        assert result["strategy"] == "text"
        assert result["pages"] >= 1

    @pytest.mark.asyncio
    async def test_db_updated_after_extraction(self, db_session: AsyncSession):
        await ensure_seed_async(db_session)
        deal_id, doc_id, ver_id = await setup_document(
            db_session,
            "test_text_clean.pdf",
        )

        await _extract_document_async(
            document_version_id=ver_id,
            document_id=doc_id,
            deal_id=deal_id,
            tenant_id=TENANT_ID,
            db=db_session,
        )

        doc_info = await get_doc_info(db_session, doc_id, ver_id)

        assert doc_info["status"] == DocumentStatus.EXTRACTED.value
        assert doc_info["raw_ref"] is not None
        assert doc_info["strategy"] == "text"

    @pytest.mark.asyncio
    async def test_minio_artifact_clause_uid_null(self, db_session: AsyncSession):
        """
        textlayoutraw stored in MinIO must have clause_uid=null in all elements.
        Structure Builder (Stage 6) reads this artifact and populates clause_uid.
        """
        await ensure_seed_async(db_session)
        deal_id, doc_id, ver_id = await setup_document(
            db_session,
            "test_text_clean.pdf",
        )

        await _extract_document_async(
            document_version_id=ver_id,
            document_id=doc_id,
            deal_id=deal_id,
            tenant_id=TENANT_ID,
            db=db_session,
        )

        store = ArtifactStore()
        layout = store.get_json(ArtifactPath.layout_raw(TENANT_ID, deal_id, doc_id))

        for elem in layout["elements"]:
            assert "clause_uid" in elem, "clause_uid key must be present"
            assert elem["clause_uid"] is None, "clause_uid must be null at extraction"


class TestExtractWorkerTablePDF:
    @pytest.mark.asyncio
    async def test_table_extraction(self, db_session: AsyncSession):
        await ensure_seed_async(db_session)
        deal_id, doc_id, ver_id = await setup_document(
            db_session,
            "test_with_table.pdf",
        )

        result = await _extract_document_async(
            document_version_id=ver_id,
            document_id=doc_id,
            deal_id=deal_id,
            tenant_id=TENANT_ID,
            db=db_session,
        )

        assert result["tables"] >= 1

    @pytest.mark.asyncio
    async def test_minio_artifact_has_table(self, db_session: AsyncSession):
        await ensure_seed_async(db_session)
        deal_id, doc_id, ver_id = await setup_document(
            db_session,
            "test_with_table.pdf",
        )

        await _extract_document_async(
            document_version_id=ver_id,
            document_id=doc_id,
            deal_id=deal_id,
            tenant_id=TENANT_ID,
            db=db_session,
        )

        store = ArtifactStore()
        layout = store.get_json(ArtifactPath.layout_raw(TENANT_ID, deal_id, doc_id))

        assert len(layout["tables"]) >= 1
        assert len(layout["tables"][0]["rows"]) >= 2


class TestExtractWorkerEmptyPDF:
    @pytest.mark.asyncio
    async def test_empty_pdf_quarantine(self, db_session: AsyncSession):
        await ensure_seed_async(db_session)
        deal_id, doc_id, ver_id = await setup_document(
            db_session,
            "test_empty.pdf",
        )

        with pytest.raises(QuarantineError):
            await _extract_document_async(
                document_version_id=ver_id,
                document_id=doc_id,
                deal_id=deal_id,
                tenant_id=TENANT_ID,
                db=db_session,
            )


class TestExtractWorkerSPA:
    @pytest.mark.asyncio
    async def test_spa_extraction(self, db_session: AsyncSession):
        """
        test_spa.pdf must extract successfully and contain
        SPA-specific headings required by Structure Builder (Stage 6).
        """
        await ensure_seed_async(db_session)

        spa_path = os.path.join(FIXTURES_DIR, "test_spa.pdf")
        if not os.path.exists(spa_path):
            pytest.skip("test_spa.pdf not found")

        deal_id, doc_id, ver_id = await setup_document(
            db_session,
            "test_spa.pdf",
        )

        result = await _extract_document_async(
            document_version_id=ver_id,
            document_id=doc_id,
            deal_id=deal_id,
            tenant_id=TENANT_ID,
            db=db_session,
        )

        assert result["elements"] >= 5
        assert result["strategy"] == "text"

    @pytest.mark.asyncio
    async def test_spa_minio_headings(self, db_session: AsyncSession):
        """
        Headings in SPA textlayoutraw must be type='heading'.
        Structure Builder uses element.type to detect clause boundaries.
        """
        await ensure_seed_async(db_session)

        spa_path = os.path.join(FIXTURES_DIR, "test_spa.pdf")
        if not os.path.exists(spa_path):
            pytest.skip("test_spa.pdf not found")

        deal_id, doc_id, ver_id = await setup_document(
            db_session,
            "test_spa.pdf",
        )

        await _extract_document_async(
            document_version_id=ver_id,
            document_id=doc_id,
            deal_id=deal_id,
            tenant_id=TENANT_ID,
            db=db_session,
        )

        store = ArtifactStore()
        layout = store.get_json(ArtifactPath.layout_raw(TENANT_ID, deal_id, doc_id))
        headings = [e for e in layout["elements"] if e["type"] == "heading"]

        assert len(headings) >= 3, "SPA fixture must have ≥3 headings for Structure Builder"

    @pytest.mark.asyncio
    async def test_spa_clause_uid_initially_null(self, db_session: AsyncSession):
        """
        All clause_uid must be null in Extractor output.
        Classifier L2 and Structure Builder (Stage 6) receive null and fill it.
        """
        await ensure_seed_async(db_session)

        spa_path = os.path.join(FIXTURES_DIR, "test_spa.pdf")
        if not os.path.exists(spa_path):
            pytest.skip("test_spa.pdf not found")

        deal_id, doc_id, ver_id = await setup_document(
            db_session,
            "test_spa.pdf",
        )

        await _extract_document_async(
            document_version_id=ver_id,
            document_id=doc_id,
            deal_id=deal_id,
            tenant_id=TENANT_ID,
            db=db_session,
        )

        store = ArtifactStore()
        layout = store.get_json(ArtifactPath.layout_raw(TENANT_ID, deal_id, doc_id))

        for elem in layout["elements"]:
            assert elem["clause_uid"] is None
