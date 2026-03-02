"""Тесты для Aggregator Service (Stage 9)."""

import pytest

from src.services.export.aggregator import aggregate_results
from tests.fixtures.export_test_data import SAMPLE_CHECK_RESULTS_V9, SAMPLE_DOCUMENTS_V9

DEAL_ID = "deal-test-001"
DEAL_NAME = "Тестовая сделка"
RUN_ID = "run-test-001"


@pytest.fixture
def aggregated():
    return aggregate_results(
        deal_id=DEAL_ID,
        deal_name=DEAL_NAME,
        run_id=RUN_ID,
        check_results=SAMPLE_CHECK_RESULTS_V9,
        documents=SAMPLE_DOCUMENTS_V9,
    )


class TestBasicCounts:
    def test_total_documents(self, aggregated):
        assert aggregated.total_documents == len(SAMPLE_DOCUMENTS_V9)

    def test_total_checks(self, aggregated):
        assert aggregated.total_checks == len(SAMPLE_CHECK_RESULTS_V9)

    def test_severity_counts_consistent(self, aggregated):
        sc = aggregated.severity_counts
        assert sc.total == sc.critical + sc.high + sc.medium + sc.pass_count + sc.unclear


class TestConditionalChecks:
    def test_conditional_rows_extracted(self, aggregated):
        # В фикстуре SAMPLE_CHECK_RESULTS_V9 одна запись с conditional_check_triggered=True
        assert aggregated.conditional_checks_total >= 1
        assert len(aggregated.conditional_rows) == aggregated.conditional_checks_total

    def test_conditional_rows_have_trigger_name(self, aggregated):
        for cr in aggregated.conditional_rows:
            assert cr.trigger_name

    def test_conditional_checks_stats(self, aggregated):
        assert aggregated.conditional_checks_triggered <= aggregated.conditional_checks_total


class TestStructuredValues:
    def test_structured_values_extracted(self, aggregated):
        # В SAMPLE_CHECK_RESULTS_V9 есть structured_data у land_subject_extraction
        assert len(aggregated.structured_value_rows) >= 1

    def test_structured_values_have_field_name(self, aggregated):
        for sv in aggregated.structured_value_rows:
            assert sv.field_name
            assert sv.field_value


class TestDDRequestsAddresseeFromYAML:
    def test_requests_generated_for_fail_results(self, aggregated):
        assert len(aggregated.dd_requests) >= 1

    def test_requests_have_addressee(self, aggregated):
        for req in aggregated.dd_requests:
            assert req.addressee
            assert len(req.addressee) > 3

    def test_requests_have_doc_types(self, aggregated):
        for req in aggregated.dd_requests:
            assert len(req.doc_types) >= 1


class TestDocTypeSummaries:
    def test_summaries_generated(self, aggregated):
        assert len(aggregated.doc_type_summaries) >= 1

    def test_summaries_have_classification_confidence(self, aggregated):
        for summary in aggregated.doc_type_summaries:
            assert 0.0 <= summary.avg_classification_confidence <= 1.0

    def test_empty_check_results_does_not_crash(self):
        agg = aggregate_results(
            deal_id=DEAL_ID,
            deal_name=DEAL_NAME,
            run_id=RUN_ID,
            check_results=[],
            documents=SAMPLE_DOCUMENTS_V9,
        )
        assert agg.total_checks == 0
        assert agg.severity_counts.total == 0
