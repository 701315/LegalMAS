"""
Vertical Slice Integration Test.

Tests the entire pipeline end-to-end:
  Import → Extract → Sanitize → Structure → Classify → Run → Export
"""

import os
import sys
import uuid

import pytest

from src.core.constants import DocumentStatus
from src.db.session import get_session
from src.mas_queue.celery_app import celery_app
from src.storage.artifact_store import ArtifactStore

TEST_PDF_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "fixtures",
    "test_spa.pdf",
)
TENANT_ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(autouse=True)
def celery_eager():
    """Run all Celery tasks synchronously."""
    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)
    yield
    celery_app.conf.update(task_always_eager=False, task_eager_propagates=False)


@pytest.fixture(autouse=True)
def reset_classifier_registry():
    """Reset YAML registry singleton between tests."""
    from src.classifiers.yaml_registry import YAMLRegistry

    YAMLRegistry.reset()
    yield
    YAMLRegistry.reset()


async def _create_test_deal() -> str:
    from src.db.repositories import DealRepository

    async with get_session() as session:
        repo = DealRepository(session)
        deal = await repo.create(
            tenant_id=uuid.UUID(TENANT_ID),
            name=f"Vertical Slice Test {uuid.uuid4().hex[:8]}",
            deal_type="SPA",
        )
        return str(deal.id)


async def _verify_results(deal_id: str, run_id: str) -> dict:
    from sqlalchemy import select

    from src.db.models.export import Export
    from src.db.repositories import (
        DocumentRepository,
        DocumentVersionRepository,
        ResultRepository,
        RunRepository,
    )

    async with get_session() as session:
        doc_repo = DocumentRepository(session)
        ver_repo = DocumentVersionRepository(session)
        result_repo = ResultRepository(session)
        run_repo = RunRepository(session)

        docs = await doc_repo.get_by_deal(uuid.UUID(deal_id))

        doc_info = None
        if docs:
            doc = docs[0]
            version = await ver_repo.get_latest(doc.id)
            doc_info = {
                "id": str(doc.id),
                "status": doc.status,
                "doctype": doc.doc_type,
                "language": doc.language,
                "classification_confidence": doc.classification_confidence,
                "classification_level": doc.classification_level,
                "classification_details": doc.classification_details,
                "applicable_triggers": doc.applicable_triggers,
                "text_layout_raw_ref": (version.text_layout_raw_ref if version else None),
                "text_layout_sanitized_ref": (
                    version.text_layout_sanitized_ref if version else None
                ),
                "clause_tree_ref": version.clause_tree_ref if version else None,
            }

        check_results = await result_repo.get_by_run(uuid.UUID(run_id))

        coc_check = None
        for cr in check_results:
            if cr.check_id == "coc001":
                coc_check = {
                    "result": cr.result,
                    "severity": cr.severity,
                    "value_text": cr.value_text,
                    "structured_data": cr.structured_data,
                    "conditional_check_triggered": cr.conditional_check_triggered,
                    "trigger_name": cr.trigger_name,
                }

        export_result = await session.execute(
            select(Export).where(Export.run_id == uuid.UUID(run_id))
        )
        export = export_result.scalar_one_or_none()
        run = await run_repo.get_by_id(uuid.UUID(run_id))

        return {
            "document_count": len(docs),
            "document": doc_info,
            "check_result_count": len(check_results),
            "coc_check": coc_check,
            "export_exists": export is not None,
            "run_status": run.status if run else None,
        }


class TestVerticalSlice:
    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Full vertical slice is flaky on Windows (asyncpg + event loop)",
    )
    def test_pipeline_single_document(self):
        import asyncio

        from src.workers.orchestrator import start_pipeline

        assert os.path.exists(TEST_PDF_PATH), (
            f"Test PDF not found: {TEST_PDF_PATH}. " "Run python -m scripts.create_test_pdf"
        )

        deal_id = asyncio.run(_create_test_deal())
        result = start_pipeline(
            deal_id=deal_id,
            tenant_id=TENANT_ID,
            source_path=TEST_PDF_PATH,
        )
        assert result["status"] == "started"
        pipeline_run_id = result["run_id"]

        verification = asyncio.run(_verify_results(deal_id, pipeline_run_id))

        # Basic pipeline
        assert verification["document_count"] == 1, "No documents imported"
        doc = verification["document"]
        assert doc is not None, "Document not found"
        assert (
            doc["status"] == DocumentStatus.COMPLETED.value
        ), f"Document status: {doc['status']}, expected: completed"

        # Classification
        assert (
            doc["doctype"] == "contract_1.11_shares"
        ), f"Doc type: {doc['doctype']}, expected: contract_1.11_shares"
        assert doc["classification_confidence"] is not None
        assert doc["classification_confidence"] > 0
        assert doc["classification_level"] is not None
        assert (
            doc["classification_level"] == "L1"
        ), f"classification_level: {doc['classification_level']}, expected: L1"
        assert doc["classification_details"] is not None
        assert "levels_tried" in doc["classification_details"]
        assert "L1" in doc["classification_details"]["levels_tried"]

        assert doc["applicable_triggers"] is not None
        assert isinstance(doc["applicable_triggers"], list)

        # MinIO artifacts
        store = ArtifactStore()
        assert doc["text_layout_raw_ref"] is not None
        assert store.exists(doc["text_layout_raw_ref"].replace(f"s3://{store.bucket}/", ""))

        # Check results
        assert verification["check_result_count"] == 1, "No check results"
        coc = verification["coc_check"]
        assert coc is not None
        assert coc["result"] == "fail"
        assert coc["severity"] == "critical"
        assert coc["structured_data"] is None
        assert coc["conditional_check_triggered"] is False
        assert coc["trigger_name"] is None

        # Export and run
        assert verification["export_exists"], "Export not created"
        assert (
            verification["run_status"] == "completed"
        ), f"Run status: {verification['run_status']}, expected: completed"

    def test_pipeline_detects_coc_keywords(self):
        """Verify Runner correctly detects CoC keywords in elements."""
        from src.workers.runner import _check_change_of_control

        elements = [
            {
                "element_id": "e001",
                "type": "text",
                "text": "Настоящий договор не содержит специальных условий.",
                "page": 1,
                "bbox": [0, 0, 100, 20],
            },
            {
                "element_id": "e002",
                "type": "text",
                "text": (
                    "В случае смены контроля над Покупателем "
                    "Продавец вправе расторгнуть договор."
                ),
                "page": 2,
                "bbox": [0, 0, 100, 20],
            },
        ]
        clause_tree = {"root": {"children": []}}
        result = _check_change_of_control(elements, clause_tree, "test-doc")

        assert result["check_result"]["result"] == "fail"
        assert result["check_result"]["severity"] == "critical"
        assert result["evidence"]["keyword_matched"] is not None
        assert result["evidence"]["element_id"] == "e002"
        assert result["check_result"]["structured_data"] is None
        assert result["check_result"]["conditional_check_triggered"] is False

    def test_pipeline_pass_when_no_coc(self):
        """Verify PASS result when no CoC keywords found."""
        from src.workers.runner import _check_change_of_control

        elements = [
            {
                "element_id": "e001",
                "type": "text",
                "text": "Продавец обязуется передать акции Покупателю.",
                "page": 1,
                "bbox": [0, 0, 100, 20],
            },
        ]
        clause_tree = {"root": {"children": []}}
        result = _check_change_of_control(elements, clause_tree, "test-doc")

        assert result["check_result"]["result"] == "pass"
        assert result["check_result"]["structured_data"] is None
        assert result["check_result"]["conditional_check_triggered"] is False

    def test_classifier_uses_yaml_registry(self):
        """Verify that HybridClassifier loads rules from YAML files."""
        from src.classifiers import HybridClassifier

        classifier = HybridClassifier()
        result = classifier.classify(
            text="купли-продажи акций share purchase уставного капитала",
            text_sanitized="",
            filename="SPA_v2.pdf",
            folder_path="Transaction",
        )
        assert result.doctype == "contract_1.11_shares"
        assert result.confidence > 0
        assert result.level.value == "L1"
        assert "L1" in result.details["levels_tried"]
        assert isinstance(result.applicable_triggers, list)

    def test_classifier_generic_fallback(self):
        """Verify Generic fallback for completely unrecognized documents."""
        from src.classifiers import HybridClassifier

        classifier = HybridClassifier()
        result = classifier.classify(
            text="Lorem ipsum dolor sit amet consectetur adipiscing.",
            text_sanitized="",
            filename="random.pdf",
            folder_path="misc",
        )
        assert result.doctype == "Generic"
        assert result.confidence <= 0.5

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Full vertical slice is flaky on Windows (asyncpg + event loop)",
    )
    def test_new_fields_present_in_db(self):
        import asyncio

        from src.workers.orchestrator import start_pipeline

        assert os.path.exists(TEST_PDF_PATH), (
            f"Test PDF not found: {TEST_PDF_PATH}. " "Run python -m scripts.create_test_pdf"
        )

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            deal_id = loop.run_until_complete(_create_test_deal())
            result = start_pipeline(
                deal_id=deal_id,
                tenant_id=TENANT_ID,
                source_path=TEST_PDF_PATH,
            )
            verification = loop.run_until_complete(_verify_results(deal_id, result["run_id"]))
        finally:
            loop.close()
            asyncio.set_event_loop(None)

        doc = verification["document"]
        assert doc is not None
        assert doc["classification_confidence"] is not None
        assert doc["classification_level"] is not None
        assert doc["classification_details"] is not None
        assert doc["applicable_triggers"] is not None
        details = doc["classification_details"]
        assert "levels_tried" in details
        assert "l1_score" in details
        assert "triggers_from_yaml" in details
