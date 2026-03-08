"""
Prometheus Metrics Registry.

Defines all metrics for the MAS DD system, grouped by category:

1. QUALITY metrics — measure accuracy of analysis
2. PERFORMANCE metrics — measure speed of processing
3. RELIABILITY metrics — measure system health
4. MIGRATION SIGNALS — track when Graph DB migration needed
5. CLASSIFICATION metrics — quality of document classification
6. BUILD INFO — build metadata

Usage in workers/API:

    from src.ops.metrics import get_metrics

    METRICS = get_metrics()
    METRICS.checks_executed.labels(detector_type="rules", result="fail").inc()
    METRICS.check_duration.labels(detector_type="rules").observe(0.45)

All metric names use the prefix from settings (default: "mas_dd").
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from prometheus_client import Counter, Gauge, Histogram, Info

from src.core.config import settings


_P = settings.METRICS_PREFIX  # "mas_dd"


class MetricsRegistry:
    """
    Central registry of all application metrics.

    ВАЖНО:
    - Экземпляр этого класса должен создаваться ОДИН раз на процесс.
    - При запуске uvicorn с --reload модуль может импортироваться несколько раз,
      поэтому создавать MetricsRegistry на уровне модуля (METRICS = MetricsRegistry())
      приводит к ошибке "Duplicated timeseries in CollectorRegistry".
    - Вместо этого используем ленивую инициализацию через get_metrics().
    """

    def __init__(self) -> None:
        # ==============================================================
        # 1. QUALITY METRICS
        # ==============================================================

        self.evidence_validity_rate = Gauge(
            f"{_P}_evidence_validity_rate",
            "Fraction of FAIL/HIGH/CRITICAL results with valid evidence "
            "(evidence found in raw text). Target: >= 0.95",
        )

        self.retrieval_hit_rate_at_5 = Gauge(
            f"{_P}_retrieval_hit_rate_at_5",
            "Fraction of checks where golden evidence appears in top-5 "
            "retrieval candidates. Measured on golden dataset.",
        )

        self.check_precision_critical = Gauge(
            f"{_P}_check_precision_critical",
            "Precision = TP / (TP + FP) for critical checks. "
            "Measured on golden dataset. Target: >= 0.90",
        )

        self.check_recall_critical = Gauge(
            f"{_P}_check_recall_critical",
            "Recall = TP / (TP + FN) for critical checks. "
            "Measured on golden dataset. Target: >= 0.85",
        )

        self.unclear_rate_critical = Gauge(
            f"{_P}_unclear_rate_critical",
            "UNCLEAR / total for critical checks. Target: <= 0.10",
        )

        self.regression_f1_current = Gauge(
            f"{_P}_regression_f1_current",
            "F1 score of the current default playbook on golden dataset.",
        )

        # ==============================================================
        # 2. PERFORMANCE METRICS
        # ==============================================================

        self.extraction_duration = Histogram(
            f"{_P}_extraction_duration_seconds",
            "Time to extract text from one document.",
            labelnames=["strategy"],  # "pdfplumber", "ocr", "hybrid"
            buckets=[1, 2, 5, 10, 20, 30, 60, 120],
        )

        self.extraction_pages = Counter(
            f"{_P}_extraction_pages_total",
            "Total pages extracted.",
            labelnames=["strategy"],
        )

        self.check_duration = Histogram(
            f"{_P}_runner_check_duration_seconds",
            "Time to run one check on one document.",
            labelnames=["detector_type"],  # "rules", "llm", "hybrid"
            buckets=[0.1, 0.5, 1, 2, 5, 10, 30],
        )

        self.checks_executed = Counter(
            f"{_P}_checks_executed_total",
            "Total checks executed.",
            labelnames=["detector_type", "result"],  # result: fail/pass/unclear
        )

        self.checks_per_minute = Gauge(
            f"{_P}_runner_checks_per_minute",
            "Current throughput: checks per minute.",
        )

        self.export_duration = Histogram(
            f"{_P}_export_duration_seconds",
            "Time to generate an export file.",
            labelnames=["export_type"],  # "grid_xlsx", "report_docx", etc.
            buckets=[1, 5, 10, 30, 60, 120],
        )

        self.relation_traversal_latency = Histogram(
            f"{_P}_relation_traversal_latency_seconds",
            "Time to traverse document relations (e.g., get family).",
            buckets=[0.01, 0.05, 0.1, 0.5, 1, 5],
        )

        # ==============================================================
        # 3. RELIABILITY METRICS
        # ==============================================================

        self.circuit_breaker_state = Gauge(
            f"{_P}_circuit_breaker_state",
            "Circuit breaker state: 0=CLOSED, 1=OPEN, 2=HALF_OPEN.",
            labelnames=["provider"],  # "openai", "anthropic", "local_llm"
        )

        self.circuit_breaker_open_seconds = Counter(
            f"{_P}_circuit_breaker_open_seconds_total",
            "Total seconds a circuit breaker has been OPEN.",
            labelnames=["provider"],
        )

        self.dlq_size = Gauge(
            f"{_P}_dlq_size",
            "Current number of records in DLQ.",
        )

        self.import_fail = Counter(
            f"{_P}_import_fail_total",
            "Total failed imports (quarantine + errors).",
            labelnames=["reason"],  # "invalid_file", "conversion_error", etc.
        )

        self.cloud_fallback = Counter(
            f"{_P}_cloud_fallback_total",
            "Total times cloud LLM was used as fallback.",
        )

        self.quarantine = Counter(
            f"{_P}_quarantine_total",
            "Total documents sent to quarantine.",
            labelnames=["reason"],  # "ocr_low", "parse_error", "zero_elements"
        )

        self.extraction_ocr_confidence = Histogram(
            f"{_P}_extraction_ocr_confidence",
            "OCR confidence distribution.",
            buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
        )

        # ==============================================================
        # 4. MIGRATION SIGNAL METRICS
        # ==============================================================

        self.relation_traversal_depth_p95 = Gauge(
            f"{_P}_relation_traversal_depth_p95",
            "95th percentile of relation traversal depth. "
            "Signal for Graph DB migration if > 3.",
        )

        self.relation_edges_per_deal = Gauge(
            f"{_P}_relation_edges_per_deal",
            "Average number of document relation edges per deal. "
            "Signal for Graph DB migration if > 500.",
        )

        self.cross_doc_queries_qps = Gauge(
            f"{_P}_cross_doc_queries_qps",
            "Cross-document queries per second. "
            "Signal for Graph DB migration if > 50.",
        )

        # ==============================================================
        # 5. CLASSIFICATION METRICS (NEW)
        # ==============================================================

        self.classification_accuracy = Gauge(
            f"{_P}_classification_accuracy",
            "Fraction of documents correctly classified by HybridClassifier. "
            "Measured on golden dataset. Target: >= 0.90",
        )

        self.yaml_coverage_rate = Gauge(
            f"{_P}_yaml_coverage_rate",
            "Fraction of classified doc_types that have a matching YAML "
            "instruction. Target: >= 0.70",
        )

        self.low_confidence_rate = Gauge(
            f"{_P}_low_confidence_rate",
            "Fraction of classified documents with confidence < 0.6. "
            "Target: <= 0.15",
        )

        self.classification_duration = Histogram(
            f"{_P}_classification_duration_seconds",
            "Time to classify one document via HybridClassifier.",
            labelnames=["level"],   # "L0", "L1", "L2", "L3", "L4", "L_manual"
            buckets=[0.05, 0.1, 0.25, 0.5, 1, 2, 5],
        )

        self.classification_level_distribution = Counter(
            f"{_P}_classification_level_total",
            "Total documents classified at each level.",
            labelnames=["level", "doc_type"],   # level: L0-L4, doc_type: SPA, NDA...
        )

        self.reclassification_total = Counter(
            f"{_P}_reclassification_total",
            "Total manual reclassification operations.",
            labelnames=["previous_doc_type", "new_doc_type"],
        )

        # ==============================================================
        # 6. BUILD INFO
        # ==============================================================

        self.build_info = Info(
            f"{_P}_build",
            "Build information.",
        )


# ============================================================
# Singleton helper — импортируйте get_metrics() из любого модуля
# ============================================================

_METRICS_INSTANCE: MetricsRegistry | None = None


def get_metrics() -> MetricsRegistry:
    """
    Возвращает единственный экземпляр MetricsRegistry.

    - При первом вызове создаёт объект и регистрирует все метрики
      в глобальном CollectorRegistry.
    - При последующих вызовах возвращает уже созданный экземпляр.
    - Безопасен для dev-режима с uvicorn --reload.
    """
    global _METRICS_INSTANCE
    if _METRICS_INSTANCE is not None:
        return _METRICS_INSTANCE

    _METRICS_INSTANCE = MetricsRegistry()
    return _METRICS_INSTANCE


# Для совместимости со старым кодом:
# from src.ops.metrics import METRICS
# Но теперь это ленивый синглтон, а не немедленное создание.
if TYPE_CHECKING:
    # только для type checkers
    METRICS: MetricsRegistry
else:
    # рантаймовый alias на get_metrics(), чтобы старый код продолжал работать:
    class _MetricsProxy:
        def __getattr__(self, item):
            return getattr(get_metrics(), item)

    METRICS = _MetricsProxy()
