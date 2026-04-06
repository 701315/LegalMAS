"""
Prometheus Metrics Registry.

Defines all metrics for the MAS DD system, grouped by category:

1. QUALITY metrics — measure accuracy of analysis
2. PERFORMANCE metrics — measure speed of processing
3. RELIABILITY metrics — measure system health
4. MIGRATION SIGNALS — track when Graph DB migration needed
5. CLASSIFICATION metrics — quality of document classification
6. BUILD INFO — build metadata
7. LLM metrics — latency / errors / tokens for LLM calls

Usage in workers/API:

    from ops.metrics import get_metrics, METRICS

    metrics = get_metrics()
    metrics.checks_executed.labels(detector_type="rules", result="fail").inc()
    metrics.check_duration.labels(detector_type="rules").observe(0.45)

    # Старый стиль (совместимость):
    METRICS.checks_executed.labels(detector_type="rules", result="fail").inc()

All metric names use the prefix from settings (default: "mas_dd").

IMPORTANT:
- Metrics are registered in a dedicated CollectorRegistry instance, not the
  global default one, to avoid "Duplicated timeseries in CollectorRegistry"
  in multiprocess / Celery environments.
- MetricsRegistry is a strict singleton per process, created lazily via
  get_metrics().
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from prometheus_client import Counter, Gauge, Histogram, Info, CollectorRegistry

from core.config import settings

_P = settings.METRICS_PREFIX  # e.g. "mas_dd"


# One dedicated registry for the entire process.
# We do NOT touch the global default_registry to avoid duplicates.
_REGISTRY: CollectorRegistry | None = None


def _get_registry() -> CollectorRegistry:
    """
    Return process-wide CollectorRegistry.

    Created lazily on first use. All metrics are registered in this registry,
    preventing accidental double-registration in the default global registry.
    """
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = CollectorRegistry()
    return _REGISTRY


class MetricsRegistry:
    """
    Central registry of all application metrics.

    IMPORTANT:
    - An instance of this class must be created only ONCE per process.
    - Use get_metrics() to retrieve the singleton instance.
    - All metrics are registered in a dedicated CollectorRegistry returned by
      _get_registry(), not in the global default.
    """

    def __init__(self) -> None:
        registry = _get_registry()

        # ==============================================================
        # 1. QUALITY METRICS
        # ==============================================================

        self.evidence_validity_rate = Gauge(
            f"{_P}_evidence_validity_rate",
            "Fraction of FAIL/HIGH/CRITICAL results with valid evidence "
            "(evidence found in raw text). Target: >= 0.95",
            registry=registry,
        )

        self.retrieval_hit_rate_at_5 = Gauge(
            f"{_P}_retrieval_hit_rate_at_5",
            "Fraction of checks where golden evidence appears in top-5 "
            "retrieval candidates. Measured on golden dataset.",
            registry=registry,
        )

        self.check_precision_critical = Gauge(
            f"{_P}_check_precision_critical",
            "Precision = TP / (TP + FP) for critical checks. "
            "Measured on golden dataset. Target: >= 0.90",
            registry=registry,
        )

        self.check_recall_critical = Gauge(
            f"{_P}_check_recall_critical",
            "Recall = TP / (TP + FN) for critical checks. "
            "Measured on golden dataset. Target: >= 0.85",
            registry=registry,
        )

        self.unclear_rate_critical = Gauge(
            f"{_P}_unclear_rate_critical",
            "UNCLEAR / total for critical checks. Target: <= 0.10",
            registry=registry,
        )

        self.regression_f1_current = Gauge(
            f"{_P}_regression_f1_current",
            "F1 score of the current default playbook on golden dataset.",
            registry=registry,
        )

        # ==============================================================
        # 2. PERFORMANCE METRICS
        # ==============================================================

        self.extraction_duration = Histogram(
            f"{_P}_extraction_duration_seconds",
            "Time to extract text from one document.",
            labelnames=["strategy"],  # "pdfplumber", "ocr", "hybrid"
            buckets=[1, 2, 5, 10, 20, 30, 60, 120],
            registry=registry,
        )

        self.extraction_pages = Counter(
            f"{_P}_extraction_pages_total",
            "Total pages extracted.",
            labelnames=["strategy"],
            registry=registry,
        )

        self.check_duration = Histogram(
            f"{_P}_runner_check_duration_seconds",
            "Time to run one check on one document.",
            labelnames=["detector_type"],  # "rules", "llm", "hybrid"
            buckets=[0.1, 0.5, 1, 2, 5, 10, 30],
            registry=registry,
        )

        self.checks_executed = Counter(
            f"{_P}_checks_executed_total",
            "Total checks executed.",
            labelnames=["detector_type", "result"],  # result: fail/pass/unclear
            registry=registry,
        )

        self.checks_per_minute = Gauge(
            f"{_P}_runner_checks_per_minute",
            "Current throughput: checks per minute.",
            registry=registry,
        )

        self.export_duration = Histogram(
            f"{_P}_export_duration_seconds",
            "Time to generate an export file.",
            labelnames=["export_type"],  # "grid_xlsx", "report_docx", etc.
            buckets=[1, 5, 10, 30, 60, 120],
            registry=registry,
        )

        self.relation_traversal_latency = Histogram(
            f"{_P}_relation_traversal_latency_seconds",
            "Time to traverse document relations (e.g., get family).",
            buckets=[0.01, 0.05, 0.1, 0.5, 1, 5],
            registry=registry,
        )

        self.checks_duration = Histogram(
            f"{_P}_deal_checks_duration_seconds",
            "Time to run all checks for one deal/run.",
            labelnames=["stage"],  # e.g.: "deal_checks"
            buckets=[1, 5, 10, 30, 60, 120],
            registry=registry,
        )

        # ==============================================================
        # 3. RELIABILITY METRICS
        # ==============================================================

        self.circuit_breaker_state = Gauge(
            f"{_P}_circuit_breaker_state",
            "Circuit breaker state: 0=CLOSED, 1=OPEN, 2=HALF_OPEN.",
            labelnames=["provider"],  # "openai", "anthropic", "local_llm"
            registry=registry,
        )

        self.circuit_breaker_open_seconds = Counter(
            f"{_P}_circuit_breaker_open_seconds_total",
            "Total seconds a circuit breaker has been OPEN.",
            labelnames=["provider"],
            registry=registry,
        )

        self.dlq_size = Gauge(
            f"{_P}_dlq_size",
            "Current number of records in DLQ.",
            registry=registry,
        )

        self.import_fail = Counter(
            f"{_P}_import_fail_total",
            "Total failed imports (quarantine + errors).",
            labelnames=["reason"],  # "invalid_file", "conversion_error", etc.
            registry=registry,
        )

        self.cloud_fallback = Counter(
            f"{_P}_cloud_fallback_total",
            "Total times cloud LLM was used as fallback.",
            registry=registry,
        )

        self.quarantine = Counter(
            f"{_P}_quarantine_total",
            "Total documents sent to quarantine.",
            labelnames=["reason"],  # "ocr_low", "parse_error", "zero_elements"
            registry=registry,
        )

        self.extraction_ocr_confidence = Histogram(
            f"{_P}_extraction_ocr_confidence",
            "OCR confidence distribution.",
            buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
            registry=registry,
        )

        # ==============================================================
        # 4. MIGRATION SIGNAL METRICS
        # ==============================================================

        self.relation_traversal_depth_p95 = Gauge(
            f"{_P}_relation_traversal_depth_p95",
            "95th percentile of relation traversal depth. "
            "Signal for Graph DB migration if > 3.",
            registry=registry,
        )

        self.relation_edges_per_deal = Gauge(
            f"{_P}_relation_edges_per_deal",
            "Average number of document relation edges per deal. "
            "Signal for Graph DB migration if > 500.",
            registry=registry,
        )

        self.cross_doc_queries_qps = Gauge(
            f"{_P}_cross_doc_queries_qps",
            "Cross-document queries per second. "
            "Signal for Graph DB migration if > 50.",
            registry=registry,
        )

        # ==============================================================
        # 5. CLASSIFICATION METRICS
        # ==============================================================

        self.classification_accuracy = Gauge(
            f"{_P}_classification_accuracy",
            "Fraction of documents correctly classified by HybridClassifier. "
            "Measured on golden dataset. Target: >= 0.90",
            registry=registry,
        )

        self.yaml_coverage_rate = Gauge(
            f"{_P}_yaml_coverage_rate",
            "Fraction of classified doc_types that have a matching YAML "
            "instruction. Target: >= 0.70",
            registry=registry,
        )

        self.low_confidence_rate = Gauge(
            f"{_P}_low_confidence_rate",
            "Fraction of classified documents with confidence < 0.6. "
            "Target: <= 0.15",
            registry=registry,
        )

        self.classification_duration = Histogram(
            f"{_P}_classification_duration_seconds",
            "Time to classify one document via HybridClassifier "
            "by decision source (L2STRONGWINS, HYBRID, L4, fallback, etc.).",
            labelnames=["source"],  # e.g. "MASTERCOPY", "L2STRONGWINS", "HYBRID", "L4", "FALLBACK"
            buckets=[0.05, 0.1, 0.25, 0.5, 1, 2, 5],
            registry=registry,
        )

        self.classification_level_distribution = Counter(
            f"{_P}_classification_level_total",
            "Total documents classified at each level.",
            labelnames=["level", "doc_type"],  # level: L0-L4, doc_type: SPA, NDA...
            registry=registry,
        )

        self.reclassification_total = Counter(
            f"{_P}_reclassification_total",
            "Total manual reclassification operations.",
            labelnames=["previous_doc_type", "new_doc_type"],
            registry=registry,
        )

        # ==============================================================
        # 6. BUILD INFO
        # ==============================================================

        self.build_info = Info(
            f"{_P}_build",
            "Build information.",
            registry=registry,
        )

        # ==============================================================
        # 7. LLM METRICS
        # ==============================================================

        # Время ответа LLM по провайдеру
        self.llm_request_duration_seconds = Histogram(
            f"{_P}_llm_request_duration_seconds",
            "Time to complete one LLM request.",
            labelnames=["provider"],  # "openai", "ollama", "llamacpp", etc.
            buckets=[0.1, 0.5, 1, 2, 5, 10, 20],
            registry=registry,
        )

        # Количество запросов к LLM по провайдеру и типу ошибки
        self.llm_requests_total = Counter(
            f"{_P}_llm_requests_total",
            "Total LLM requests by provider and error type.",
            labelnames=["provider", "error_type"],  # error_type: none/timeout/...
            registry=registry,
        )

        # Общее количество использованных токенов по провайдеру
        self.llm_tokens_total = Counter(
            f"{_P}_llm_tokens_total",
            "Total tokens generated/consumed by LLM.",
            labelnames=["provider"],
            registry=registry,
        )


# ============================================================
# Singleton helper — import get_metrics() from any module
# ============================================================

_METRICS_INSTANCE: MetricsRegistry | None = None


def get_metrics() -> MetricsRegistry:
    """
    Return the singleton MetricsRegistry instance.

    - On first call, creates the object and registers all metrics
      in the dedicated CollectorRegistry.
    - On subsequent calls, returns the already created instance.
    - Safe for dev mode and Celery, as long as import path is consistent.
    """
    global _METRICS_INSTANCE
    if _METRICS_INSTANCE is not None:
        return _METRICS_INSTANCE

    _METRICS_INSTANCE = MetricsRegistry()
    return _METRICS_INSTANCE


# For compatibility with older code:
# from ops.metrics import METRICS
# Now this is a lazy proxy, not an eagerly-created instance.
if TYPE_CHECKING:
    METRICS: MetricsRegistry
else:
    class _MetricsProxy:
        """
        Lazy proxy for MetricsRegistry.

        For non-professional programmers:
        - When you access METRICS.some_metric, this class will
          create the MetricsRegistry singleton (if needed) and
          then return the requested metric.
        - This allows us to keep the old import style
          (from ops.metrics import METRICS) without breaking code.
        """

        def __getattr__(self, item: str):
            # Delegate attribute access to the singleton instance
            return getattr(get_metrics(), item)

    METRICS = _MetricsProxy()
    