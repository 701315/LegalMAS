"""
Integration tests for Import Worker — production.

Tests cover:
  - ZIP with mixed valid/invalid files
  - Nested folder hierarchy preservation
  - SHA-256 deduplication
  - Idempotency
  - Quarantine handling
  - Audit logging
  - MinIO storage of originals

Requires Docker services (make up) and seed data (python -m scripts.seed).
"""

import asyncio
import os
import uuid

import pytest

from src.core.constants import DocumentStatus
from src.db.session import get_session
from src.mas_queue.celery_app import celery_app
from src.storage.artifact_store import ArtifactStore
from src.workers.import_worker import _import_bundle_async

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


@pytest.fixture
def fresh_deal_id():
    return asyncio.run(create_deal())


def ensure_fixtures():
    required = ["test_bundle.zip", "test_nested.zip", "test_duplicates.zip"]
    for f in required:
        path = os.path.join(FIXTURES_DIR, f)
        if not os.path.exists(path):
            pytest.skip(
                f"Test fixture not found: {f}. " "Run python -m scripts.create_test_fixtures"
            )


def ensure_seed():
    has_seed = asyncio.run(check_seed())
    if not has_seed:
        pytest.skip("Seed data required. Run python -m scripts.seed")


async def check_seed() -> bool:
    from src.db.repositories import PlaybookRepository

    async with get_session() as session:
        repo = PlaybookRepository(session)
        return await repo.get_default() is not None


async def create_deal() -> str:
    from src.db.repositories import DealRepository

    async with get_session() as session:
        repo = DealRepository(session)
        deal = await repo.create(
            tenant_id=uuid.UUID(TENANT_ID),
            name=f"Import Test {uuid.uuid4().hex[:8]}",
        )
        return str(deal.id)


async def get_all_documents(deal_id: str) -> list:
    from src.db.repositories import DocumentRepository

    async with get_session() as session:
        repo = DocumentRepository(session)
        docs = await repo.get_by_deal(uuid.UUID(deal_id))
        return [
            {
                "id": str(d.id),
                "filename": d.filename,
                "folder_path": d.folder_path,
                "status": d.status,
                "sha256": d.sha256_file,
            }
            for d in docs
        ]


async def get_documents_by_status(deal_id: str, status: str) -> list:
    from src.db.repositories import DocumentRepository

    async with get_session() as session:
        repo = DocumentRepository(session)
        docs = await repo.get_by_deal(uuid.UUID(deal_id), status=status)
        return [str(d.id) for d in docs]


async def get_audit_logs(deal_id: str, action: str | None = None) -> list:
    from src.db.repositories import AuditRepository

    async with get_session() as session:
        repo = AuditRepository(session)
        logs = await repo.get_by_deal(uuid.UUID(deal_id), action=action)
        return [{"action": log.action, "actor": log.actor, "details": log.details} for log in logs]


async def get_document_version(doc_id: str) -> dict | None:
    from src.db.repositories import DocumentVersionRepository

    async with get_session() as session:
        repo = DocumentVersionRepository(session)
        ver = await repo.get_latest(uuid.UUID(doc_id))
        if not ver:
            return None
        return {
            "original_ref": ver.original_ref,
            "text_layout_raw_ref": ver.text_layout_raw_ref,
        }


class TestImportBundleZip:
    def test_mixed_file_types(self, fresh_deal_id):
        """
        ZIP with mixed valid/invalid files:
          - 5 valid PDFs → imported
          - 1 corrupted PDF → quarantine
          - 1 empty PDF → quarantine
          - 1 DOCX → quarantine (needs_conversion)
          - 1 hidden file → skip
          - 1 .txt → quarantine (unsupported extension)
        """
        ensure_fixtures()
        ensure_seed()
        zip_path = os.path.join(FIXTURES_DIR, "test_bundle.zip")

        result = asyncio.run(
            _import_bundle_async(
                deal_id=fresh_deal_id,
                tenant_id=TENANT_ID,
                source_path=zip_path,
            )
        )
        assert result["imported_count"] == 5
        assert result["quarantine_count"] >= 3
        assert result["bundle_id"] is not None

    def test_quarantined_documents_have_status(self, fresh_deal_id):
        ensure_fixtures()
        ensure_seed()
        zip_path = os.path.join(FIXTURES_DIR, "test_bundle.zip")

        asyncio.run(
            _import_bundle_async(
                deal_id=fresh_deal_id,
                tenant_id=TENANT_ID,
                source_path=zip_path,
            )
        )
        quarantined = asyncio.run(
            get_documents_by_status(fresh_deal_id, DocumentStatus.QUARANTINE.value)
        )
        assert len(quarantined) >= 2


class TestFolderHierarchy:
    def test_nested_folders_preserved(self, fresh_deal_id):
        """
        ZIP with nested folders should preserve folder_path exactly.

        folder_path is used downstream by the L1 Rule-Based Classifier
        (Stage 6) via folder_patterns in playbooks/document_types/registry.yaml.
        Example: "02. Contracts/SPA" → r'(?i)SPA' → boosts contract1.1spa.
        This test verifies the folder_path is stored faithfully.
        """
        ensure_fixtures()
        ensure_seed()
        zip_path = os.path.join(FIXTURES_DIR, "test_nested.zip")

        result = asyncio.run(
            _import_bundle_async(
                deal_id=fresh_deal_id,
                tenant_id=TENANT_ID,
                source_path=zip_path,
            )
        )
        assert result["imported_count"] == 5
        docs = asyncio.run(get_all_documents(fresh_deal_id))
        folder_paths = {d["folder_path"] for d in docs if d["folder_path"]}

        # These exact folder_paths must be stored for L1 Classifier routing
        assert "01. CorporateCharter" in folder_paths
        assert "01. CorporateBoard" in folder_paths
        assert "02. Contracts/SPA" in folder_paths
        assert "02. Contracts/NDA" in folder_paths
        assert "03. Employment" in folder_paths

    def test_folder_paths_match_registry_patterns(self, fresh_deal_id):
        """
        Verify that stored folder_paths would match the folder_patterns
        defined in playbooks/document_types/registry.yaml.

        This test does NOT call the Classifier — it verifies Import Worker
        stores folder_paths in a format compatible with L1 routing (Stage 6).
        """
        import re

        ensure_fixtures()
        ensure_seed()
        zip_path = os.path.join(FIXTURES_DIR, "test_nested.zip")

        asyncio.run(
            _import_bundle_async(
                deal_id=fresh_deal_id,
                tenant_id=TENANT_ID,
                source_path=zip_path,
            )
        )
        docs = asyncio.run(get_all_documents(fresh_deal_id))
        folder_by_filename = {d["filename"]: d["folder_path"] for d in docs}

        spa_pattern = re.compile(r"(?i)SPA")
        nda_pattern = re.compile(r"(?i)NDA")
        emp_pattern = re.compile(r"(?i)employment")

        assert spa_pattern.search(
            folder_by_filename.get("spa_v1.pdf", "")
        ), "SPA file folder_path must match SPA pattern"
        assert nda_pattern.search(
            folder_by_filename.get("nda.pdf", "")
        ), "NDA file folder_path must match NDA pattern"
        assert emp_pattern.search(
            folder_by_filename.get("ceo_contract.pdf", "")
        ), "Employment file folder_path must match employment pattern"


class TestDeduplication:
    def test_duplicate_files_detected(self, fresh_deal_id):
        """
        ZIP with duplicate files: only 2 unique files should be imported,
        1 duplicate detected by SHA-256 comparison.
        """
        ensure_fixtures()
        ensure_seed()
        zip_path = os.path.join(FIXTURES_DIR, "test_duplicates.zip")

        result = asyncio.run(
            _import_bundle_async(
                deal_id=fresh_deal_id,
                tenant_id=TENANT_ID,
                source_path=zip_path,
            )
        )
        assert result["imported_count"] == 2
        assert result["duplicate_count"] == 1
        assert result["bundle_id"] is not None


class TestIdempotency:
    def test_idempotent_import(self, fresh_deal_id):
        """Same idempotency key must return cached result, not re-import."""
        ensure_fixtures()
        ensure_seed()
        zip_path = os.path.join(FIXTURES_DIR, "test_nested.zip")
        idem_key = f"test-idem-{uuid.uuid4().hex[:8]}"

        result1 = asyncio.run(
            _import_bundle_async(
                deal_id=fresh_deal_id,
                tenant_id=TENANT_ID,
                source_path=zip_path,
                idempotency_key=idem_key,
            )
        )
        assert result1["imported_count"] == 5

        result2 = asyncio.run(
            _import_bundle_async(
                deal_id=fresh_deal_id,
                tenant_id=TENANT_ID,
                source_path=zip_path,
                idempotency_key=idem_key,
            )
        )
        assert result2["bundle_id"] == result1["bundle_id"]
        assert result2["imported_count"] == result1["imported_count"]


class TestAuditLog:
    def test_import_creates_audit_log(self, fresh_deal_id):
        """Every import must create an IMPORT audit log entry."""
        ensure_fixtures()
        ensure_seed()
        zip_path = os.path.join(FIXTURES_DIR, "test_bundle.zip")

        result = asyncio.run(
            _import_bundle_async(
                deal_id=fresh_deal_id,
                tenant_id=TENANT_ID,
                source_path=zip_path,
            )
        )
        logs = asyncio.run(get_audit_logs(fresh_deal_id, action="IMPORT"))
        assert len(logs) == 1
        log = logs[0]
        assert log["action"] == "IMPORT"
        assert log["details"]["bundle_id"] == result["bundle_id"]
        assert log["details"]["imported_count"] == result["imported_count"]


class TestEdgeCases:
    def test_nonexistent_file_raises(self, fresh_deal_id):
        ensure_seed()
        from src.core.exceptions import PermanentError

        with pytest.raises(PermanentError):
            asyncio.run(
                _import_bundle_async(
                    deal_id=fresh_deal_id,
                    tenant_id=TENANT_ID,
                    source_path="/nonexistent/path/file.zip",
                )
            )

    def test_single_pdf_import(self, fresh_deal_id):
        """Single PDF (not ZIP) should be imported directly."""
        ensure_seed()
        fixtures = [
            os.path.join(FIXTURES_DIR, name)
            for name in ["test_text_clean.pdf", "test_spa.pdf"]
            if os.path.exists(os.path.join(FIXTURES_DIR, name))
        ]
        if not fixtures:
            pytest.skip("No single PDF fixture found — run create_extraction_fixtures")

        result = asyncio.run(
            _import_bundle_async(
                deal_id=fresh_deal_id,
                tenant_id=TENANT_ID,
                source_path=fixtures[0],
            )
        )
        assert result["imported_count"] == 1
        assert result["quarantine_count"] == 0


class TestMinIOStorage:
    def test_originals_uploaded_to_minio(self, fresh_deal_id):
        """All imported documents must have their originals in MinIO."""
        ensure_fixtures()
        ensure_seed()
        zip_path = os.path.join(FIXTURES_DIR, "test_bundle.zip")

        result = asyncio.run(
            _import_bundle_async(
                deal_id=fresh_deal_id,
                tenant_id=TENANT_ID,
                source_path=zip_path,
            )
        )
        store = ArtifactStore()
        for doc_id in result["document_ids"]:
            doc_info = asyncio.run(get_document_version(doc_id))
            if doc_info and doc_info["original_ref"]:
                s3_path = doc_info["original_ref"].replace(f"s3://{store.bucket}/", "")
                assert store.exists(s3_path), f"Original not found in MinIO: {s3_path}"
