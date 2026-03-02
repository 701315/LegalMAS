import pytest

from src.services.deal_review_service import (
    build_document_summaries,
    build_document_detail,
    build_dd_requests,
    build_conditional_checks,
    build_extracted_values,
)
from src.services.export.models import (
    AggregatedResults,
    ExportRow,
    DDRequest,
    ConditionalCheckRow,
    StructuredValueRow,
)


@pytest.fixture
def sample_documents() -> dict[str, dict]:
    # Минимальная имитация документов, как из RunnerRepository.load_documents_for_run
    return {
        "doc-1": {
            "name": "SPA_main.pdf",
            "folder_path": "01. Corporate",
            "doc_type": "SPA",
            "status": "classified",
            "classification_level": "L3",
            "classification_confidence": 0.88,
            "applicable_triggers": ["coc", "consent"],
        },
        "doc-2": {
            "name": "NDA_side.pdf",
            "folder_path": "02. NDA",
            "doc_type": "NDA",
            "status": "classified",
            "classification_level": "L2",
            "classification_confidence": 0.7,
            "applicable_triggers": [],
        },
    }


@pytest.fixture
def sample_aggregated(sample_documents: dict[str, dict]) -> AggregatedResults:
    # Собираем простой AggregatedResults вручную
    agg = AggregatedResults(
        deal_id="deal-1",
        deal_name="Test Deal",
        run_id="run-1",
        total_documents=len(sample_documents),
        total_checks=3,
    )

    # Строки ExportRow (результаты проверок)
    agg.rows = [
        ExportRow(
            document_name="SPA_main.pdf",
            folder_path="01. Corporate",
            doc_type="SPA",
            check_name="Change of Control",
            check_id="coc_001",
            result="fail",
            severity="critical",
            evidence_snippet="No change of control clause",
            page=5,
            clause_uid="clause-1",
            confidence=0.95,
            detector_used="rules",
            quality_flags="structure_degraded",
            qc_status="pending",
            document_id="doc-1",
            run_id="run-1",
            structured_data_preview="",
            conditional_check_triggered=True,
            trigger_name="TRIG_SPA",
            classification_level="L3",
            classification_confidence=0.88,
        ),
        ExportRow(
            document_name="SPA_main.pdf",
            folder_path="01. Corporate",
            doc_type="SPA",
            check_name="Governing Law",
            check_id="law_001",
            result="pass",
            severity="medium",
            evidence_snippet="Governing law is England & Wales",
            page=10,
            clause_uid="clause-2",
            confidence=0.9,
            detector_used="rules",
            quality_flags="",
            qc_status="pending",
            document_id="doc-1",
            run_id="run-1",
            structured_data_preview="",
            conditional_check_triggered=False,
            trigger_name="",
            classification_level="L3",
            classification_confidence=0.88,
        ),
        ExportRow(
            document_name="NDA_side.pdf",
            folder_path="02. NDA",
            doc_type="NDA",
            check_name="Term",
            check_id="term_001",
            result="unclear",
            severity="medium",
            evidence_snippet="Term clause ambiguous",
            page=3,
            clause_uid="clause-3",
            confidence=0.6,
            detector_used="llm",
            quality_flags="",
            qc_status="pending",
            document_id="doc-2",
            run_id="run-1",
            structured_data_preview="",
            conditional_check_triggered=False,
            trigger_name="",
            classification_level="L2",
            classification_confidence=0.7,
        ),
    ]

    # DDRequests
    agg.dd_requests = [
        DDRequest(
            request_id="req-1",
            check_id="coc_001",
            check_name="Change of Control",
            priority="critical",
            text="Please confirm whether change of control is acceptable",
            addressee="Юридический советник",
            document_ids=["doc-1"],
            document_names=["SPA_main.pdf"],
            doc_types=["SPA"],
            evidence_refs=["No change of control clause"],
            structured_values=[{"field": "amount", "value": "5000000", "doc": "doc-1"}],
            dedup_key="abc123",
        )
    ]

    # Conditional checks
    agg.conditional_rows = [
        ConditionalCheckRow(
            document_name="SPA_main.pdf",
            doc_type="SPA",
            trigger_name="TRIG_SPA",
            check_id="coc_001",
            check_name="Change of Control",
            result="fail",
            severity="critical",
            evidence_snippet="No change of control clause",
            page=5,
            confidence=0.95,
            quality_flags="structure_degraded",
        )
    ]

    # Structured values
    agg.structured_value_rows = [
        StructuredValueRow(
            document_name="SPA_main.pdf",
            doc_type="SPA",
            check_name="Purchase Price",
            field_name="amount",
            field_value="5000000",
            field_format="money",
            page=7,
            clause_uid="clause-4",
            document_id="doc-1",
        )
    ]

    return agg


def test_build_document_summaries(sample_aggregated: AggregatedResults, sample_documents: dict[str, dict]):
    summaries = build_document_summaries(sample_aggregated, sample_documents)

    # Должно быть 2 документа
    assert len(summaries) == 2

    # Ищем SPA_main
    spa = next(s for s in summaries if s.name == "SPA_main.pdf")
    assert spa.critical_count == 1
    assert spa.pass_count == 1
    assert spa.unclear_count == 0
    assert spa.has_degraded_structure is True
    assert spa.classification_level == "L3"
    assert spa.classification_confidence == 0.88


def test_build_document_detail(sample_aggregated: AggregatedResults, sample_documents: dict[str, dict]):
    detail = build_document_detail(sample_aggregated, sample_documents, "doc-1")

    assert detail.document_id == "doc-1"
    assert detail.name == "SPA_main.pdf"
    assert detail.doc_type == "SPA"
    assert len(detail.checks) == 2

    coc_check = next(c for c in detail.checks if c.check_id == "coc_001")
    assert coc_check.result == "fail"
    assert coc_check.severity == "critical"
    assert coc_check.conditional_check_triggered is True
    assert coc_check.trigger_name == "TRIG_SPA"


def test_build_dd_requests(sample_aggregated: AggregatedResults):
    dtos = build_dd_requests(sample_aggregated)
    assert len(dtos) == 1
    dto = dtos[0]
    assert dto.request_id == "req-1"
    assert dto.priority == "critical"
    assert dto.check_id == "coc_001"
    assert "SPA_main.pdf" in dto.document_names


def test_build_conditional_checks(sample_aggregated: AggregatedResults):
    dtos = build_conditional_checks(sample_aggregated)
    assert len(dtos) == 1
    dto = dtos[0]
    assert dto.document_name == "SPA_main.pdf"
    assert dto.trigger_name == "TRIG_SPA"
    assert dto.result == "fail"


def test_build_extracted_values(sample_aggregated: AggregatedResults):
    dtos = build_extracted_values(sample_aggregated)
    assert len(dtos) == 1
    dto = dtos[0]
    assert dto.document_name == "SPA_main.pdf"
    assert dto.field_name == "amount"
    assert dto.field_value == "5000000"
    assert dto.field_format == "money"
