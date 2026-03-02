#!/usr/bin/env python
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"

def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""

def check_file(path_rel: str, patterns: list[str]):
    path = SRC / path_rel
    print(f"\n=== {path_rel} ===")
    if not path.exists():
        print("  [MISSING] файл не найден")
        return
    text = read(path)
    for p in patterns:
        if p in text:
            print(f"  [OK]   найдено: {p}")
        else:
            print(f"  [MISS] нет: {p}")

def main():
    print("Проверка наличия ключевых элементов Этапа 10\n")

    # 10.2 config.py
    check_file(
        "core/config.py",
        [
            "API_EXPOSE_YAML_METADATA",
            "API_ALLOW_FORCE_RECLASSIFY",
            "API_RECLASSIFY_BATCH_LIMIT",
        ],
    )

    # 10.3.1 DocumentRepository
    check_file(
        "db/repositories/document_repo.py",
        [
            "async def update_classification",
            "async def get_low_confidence_docs",
        ],
    )

    # 10.3.2 RunRepository
    check_file(
        "db/repositories/run_repo.py",
        [
            "async def get_latest_for_deal",
            "async def get_classification_stats_for_run",
        ],
    )

    # 10.3.3 RunnerRepository
    check_file(
        "db/repositories/runner_repo.py",
        [
            "class RunnerRepository",
            "async def load_documents_for_run",
            "async def load_check_results_for_run",
        ],
    )

    # 10.4.1 documents.py (schemas)
    check_file(
        "api/schemas/documents.py",
        [
            "class ClassificationMetadata",
            "class DocumentResponse",
            "classification_level",
            "classification_confidence",
            "applicable_triggers",
            "class DocumentDetailResponse",
            "classification: ClassificationMetadata",
            "class ReclassifyRequest",
            "class ReclassifyResponse",
            "class ReclassifyBatchRequest",
        ],
    )

    # 10.4.2 runs.py (schemas)
    check_file(
        "api/schemas/runs.py",
        [
            "class RunCreate",
            "force_reclassify",
            "class ClassificationStats",
            "class RunResponse",
            "classification_stats: ClassificationStats",
            "class ClassificationReportResponse",
        ],
    )

    # 10.4.3 results.py (schemas)
    check_file(
        "api/schemas/results.py",
        [
            "class CheckResultResponse",
            "structured_data: dict[str, Any] | None",
            "conditional_check_triggered: bool",
            "trigger_name: str | None",
            "class EvidenceResponse",
            "structured_data: dict[str, Any] | None = None",
            "class StructuredDataResponse",
        ],
    )

    # 10.4.4 requests.py (schemas)
    check_file(
        "api/schemas/requests.py",
        [
            "class DDRequestCreate",
            "addressee",
            "class DDRequestUpdate",
            "class DDRequestResponse",
            "check_id",
            "structured_values",
            "source",
        ],
    )

    # 10.5 DTO deal_review.py
    check_file(
        "api/schemas/deal_review.py",
        [
            "class DocumentSummaryDTO",
            "class CheckItemDTO",
            "class DocumentDetailDTO",
            "class DDRequestDTO",
            "class ConditionalCheckDTO",
            "class ExtractedValueDTO",
            "class DocumentStructuredDataDTO",
        ],
    )

    # 10.6 deal_review_service.py
    check_file(
        "services/deal_review_service.py",
        [
            "async def load_aggregated_results",
            "def build_document_summaries",
            "def build_document_detail",
            "def build_dd_requests",
            "def build_conditional_checks",
            "def build_extracted_values",
        ],
    )

    # 10.7 deal_review endpoints
    check_file(
        "api/endpoints/deal_review.py",
        [
            'APIRouter(prefix="/deals"',
            "async def get_documents_for_run",
            "async def get_document_detail_for_run",
            "async def get_dd_requests",
            "async def get_conditional_checks",
            "async def get_extracted_values",
            "async def get_document_structured_data_for_run",
        ],
    )

    # 10.8.1 documents endpoints
    check_file(
        "api/endpoints/documents.py",
        [
            "async def get_document_detail",
            "async def reclassify_document",
            # Старый structured-data здесь уже по плану удалён
        ],
    )

    # 10.8.3 runs endpoints
    check_file(
        "api/endpoints/runs.py",
        [
            "async def start_run",
            "force_reclassify",
            "async def get_run",
            "classification_stats",
            "async def get_classification_report",
            "ClassificationReportResponse",
        ],
    )

    # 10.8.4 results endpoints
    check_file(
        "api/endpoints/results.py",
        [
            "conditional_only: bool | None =",
            "has_structured_data: bool | None =",
        ],
    )

    # 10.8.5 admin endpoints
    check_file(
        "api/endpoints/admin.py",
        [
            "async def get_yaml_instructions",
            "yaml-instructions",
            "playbooks/document_types",
        ],
    )

    # 10.9 middleware audit
    check_file(
        "api/middleware/audit.py",
        [
            "_AUDITED_PATH_SUFFIXES",
            '"/reclassify"',
            '"/structured-data"',
            "DOCUMENT_RECLASSIFIED",
            "STRUCTURED_DATA_ACCESSED",
        ],
    )

    # 10.10 main.py routers
    check_file(
        "api/main.py",
        [
            "include_router",
            "documents.router",
            "runs.router",
            "results.router",
            "requests.router",
            "admin.router",
            "deal_review.router",
        ],
    )

    # 10.11.1 unit tests for deal_review_service
    test_unit = ROOT / "tests" / "unit" / "test_deal_review_service.py"
    print(f"\n=== tests/unit/test_deal_review_service.py ===")
    if test_unit.exists():
        print("  [OK]   файл существует")
    else:
        print("  [MISS] файл не найден")

    # 10.11.2 api tests (classification endpoints)
    test_api = ROOT / "tests" / "api" / "test_classification_endpoints.py"
    print(f"\n=== tests/api/test_classification_endpoints.py ===")
    if test_api.exists():
        txt = read(test_api)
        if "TestReclassifyEndpoint" in txt:
            print("  [OK]   TestReclassifyEndpoint есть")
        else:
            print("  [MISS] нет TestReclassifyEndpoint")
        if "TestStructuredDataEndpoint" in txt:
            print("  [OK]   TestStructuredDataEndpoint есть")
        else:
            print("  [MISS] нет TestStructuredDataEndpoint")
        if "classification-report" in txt or "ClassificationReport" in txt:
            print("  [OK]   тесты для classification-report есть (по строкам)")
        else:
            print("  [MISS] нет явных тестов для classification-report")
    else:
        print("  [MISS] файл не найден")

if __name__ == "__main__":
    main()
