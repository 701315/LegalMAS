from enum import StrEnum


class ExportSuffix(StrEnum):
    CLASSIFICATION_REPORT = "classification-report"
    CHECK_RESULTS = "check-results"
    EVIDENCE = "evidence"
    RISK_SUMMARY = "risk-summary"
    # добавишь остальные по мере надобности


def build_export_filename(run_id: str, suffix: ExportSuffix, ext: str = "json") -> str:
    return f"{run_id}__{suffix.value}.{ext}"
