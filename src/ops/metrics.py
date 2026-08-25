# src/ops/metrics.py

"""
Prometheus metrics registry for the MAS DD system.

Единый реестр всех метрик приложения. Все метрики регистрируются
в одном dedicated CollectorRegistry, экспонируемом через /metrics.

Решение registry mismatch (критический баг предыдущей версии):
- prometheus_fastapi_instrumentator использовал default registry.
- Custom metrics жили в dedicated registry.
- /metrics отдавал только default registry → custom metrics были невидимы.
- Решение: убираем instrumentator. Монтируем ASGI endpoint через
  prometheus_client.make_asgi_app(registry=_REGISTRY).
  HTTP metrics собираем вручную через PrometheusMiddleware в instrument.py.

Группы метрик:
1) HTTP           — request count, latency (замена instrumentator)
2) PIPELINE       — operational pipeline metrics (Этап 2)
3) CELERY         — task lifecycle metrics (Этап 2)
4) DLQ            — dead letter queue size
5) QUALITY        — качество анализа
6) PERFORMANCE    — скорость pipeline
7) RELIABILITY    — здоровье системы (circuit breaker, quarantine)
8) CLASSIFICATION — качество HybridClassifier
9) LLM            — работа LLM-провайдеров
10) PII           — sanitization (перенесены из core/metrics.py)
11) BUILD INFO
12) MIGRATION     — сигналы для Graph DB migration
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    Info,
)

from core.config import settings

_P = settings.METRICS_PREFIX  # e.g. "mas_dd"

_REGISTRY: CollectorRegistry | None = None


def _get_registry() -> CollectorRegistry:
    """
    Вернуть process-wide dedicated CollectorRegistry.
    Создаётся лениво при первом обращении.
    """
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = CollectorRegistry()
    return _REGISTRY


def get_prometheus_registry() -> CollectorRegistry:
    """
    Публичный accessor для dedicated CollectorRegistry.
    Используется в instrument.py для монтирования ASGI /metrics endpoint.
    """
    return _get_registry()


class MetricsRegistry:
    """
    Central registry of all application metrics.

    Один экземпляр на процесс. Используй get_metrics() для доступа.
    Все метрики регистрируются в dedicated registry, не в global default.
    """

    def __init__(self) -> None:
        r = _get_registry()

        # ==============================================================
        # 1. HTTP METRICS
        # Ручные метрики вместо prometheus_fastapi_instrumentator.
        # Instrumentator писал в default registry — несовместимо с нашим
        # dedicated registry. Собираем через PrometheusMiddleware.
        # ==============================================================

        self.http_requests_total = Counter(
            f"{_P}_http_requests_total",
            "Total HTTP requests by method, path template and status code.",
            labelnames=["method", "handler", "status_code"],
            registry=r,
        )

        self.http_request_duration_seconds = Histogram(
            f"{_P}_http_request_duration_seconds",
            "HTTP request duration in seconds by method and path template.",
            labelnames=["method", "handler"],
            buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
            registry=r,
        )

        # ==============================================================
        # 2. PIPELINE OPERATIONAL METRICS
        # ==============================================================

        self.documents_processed_total = Counter(
            f"{_P}_documents_processed_total",
            "Total document stage executions completed, by stage and status.",
            labelnames=["stage", "status"],  # status: succeeded | failed
            registry=r,
        )

        self.document_stage_duration_seconds = Histogram(
            f"{_P}_document_stage_duration_seconds",
            "Duration of one document processing stage in seconds.",
            labelnames=["stage", "status"],  # status: succeeded | failed
            buckets=[0.5, 1, 2, 5, 10, 30, 60, 120, 300, 600, 1200],
            registry=r,
        )

        self.pipeline_run_duration_seconds = Histogram(
            f"{_P}_pipeline_run_duration_seconds",
            "Total pipeline run duration from started_at to completed_at.",
            buckets=[10, 30, 60, 120, 300, 600, 1200, 1800, 3600],
            registry=r,
        )

        self.active_runs = Gauge(
            f"{_P}_active_runs",
            "Number of pipeline runs currently in RUNNING status.",
            registry=r,
        )

        self.stuck_stage_executions_total = Gauge(
            f"{_P}_stuck_stage_executions_total",
            "Stage executions stuck in active status longer than task time limit.",
            registry=r,
        )

        # ==============================================================
        # 3. CELERY TASK METRICS
        # ==============================================================

        self.celery_task_retries_total = Counter(
            f"{_P}_celery_task_retries_total",
            "Total Celery task retry attempts by task name.",
            labelnames=["task_name"],
            registry=r,
        )

        self.celery_task_failures_total = Counter(
            f"{_P}_celery_task_failures_total",
            "Total permanent Celery task failures by task name and failure type.",
            labelnames=["task_name", "failure_type"],
            # failure_type: permanent | transient | timeout | quota
            registry=r,
        )

        self.celery_task_duration_seconds = Histogram(
            f"{_P}_celery_task_duration_seconds",
            "Celery task wall-clock duration from before_start to completion.",
            labelnames=["task_name", "status"],  # status: succeeded | failed
            buckets=[0.5, 1, 5, 10, 30, 60, 120, 300, 600, 1200, 1800, 3600],
            registry=r,
        )

        # ==============================================================
        # 4. DLQ METRICS
        # ==============================================================

        self.dlq_size = Gauge(
            f"{_P}_dlq_size",
            "Current number of records in the Dead Letter Queue (PostgreSQL dlq_records).",
            registry=r,
        )

        # ==============================================================
        # 5. QUALITY METRICS
        # ==============================================================

        self.evidence_validity_rate = Gauge(
            f"{_P}_evidence_validity_rate",
            "Fraction of FAIL/HIGH/CRITICAL results with valid evidence. Target >= 0.95.",
            registry=r,
        )

        self.retrieval_hit_rate_at_5 = Gauge(
            f"{_P}_retrieval_hit_rate_at_5",
            "Fraction of checks where golden evidence appears in top-5 retrieval candidates.",
            registry=r,
        )

        self.check_precision_critical = Gauge(
            f"{_P}_check_precision_critical",
            "Precision for critical checks on golden dataset. Target >= 0.90.",
            registry=r,
        )

        self.check_recall_critical = Gauge(
            f"{_P}_check_recall_critical",
            "Recall for critical checks on golden dataset. Target >= 0.85.",
            registry=r,
        )

        self.unclear_rate_critical = Gauge(
            f"{_P}_unclear_rate_critical",
            "UNCLEAR / total for critical checks. Target <= 0.10.",
            registry=r,
        )

        self.regression_f1_current = Gauge(
            f"{_P}_regression_f1_current",
            "F1 score of the current default playbook on golden dataset.",
            registry=r,
        )

        # ==============================================================
        # 6. PERFORMANCE METRICS
        # ==============================================================

        self.extraction_duration = Histogram(
            f"{_P}_extraction_duration_seconds",
            "Time to extract text from one document.",
            labelnames=["strategy"],  # pdfplumber | ocr | hybrid
            buckets=[1, 2, 5, 10, 20, 30, 60, 120],
            registry=r,
        )

        self.extraction_pages = Counter(
            f"{_P}_extraction_pages_total",
            "Total pages extracted.",
            labelnames=["strategy"],
            registry=r,
        )

        self.check_duration = Histogram(
            f"{_P}_runner_check_duration_seconds",
            "Time to run one check on one document.",
            labelnames=["detector_type"],  # rules | llm | hybrid
            buckets=[0.1, 0.5, 1, 2, 5, 10, 30],
            registry=r,
        )

        self.checks_executed = Counter(
            f"{_P}_checks_executed_total",
            "Total checks executed.",
            labelnames=["detector_type", "result"],  # result: fail | pass | unclear
            registry=r,
        )

        self.checks_per_minute = Gauge(
            f"{_P}_runner_checks_per_minute",
            "Current throughput: checks per minute.",
            registry=r,
        )

        self.export_duration = Histogram(
            f"{_P}_export_duration_seconds",
            "Time to generate an export file.",
            labelnames=["export_type"],  # grid_xlsx | report_docx | etc.
            buckets=[1, 5, 10, 30, 60, 120],
            registry=r,
        )

        self.embedding_text_truncated_total = Counter(
            f"{_P}_embedding_text_truncated_total",
            "Total texts explicitly truncated before embedding encoding to fit model token limit.",
            labelnames=["role"],  # role: query | passage
            registry=r,
        )

        self.relation_traversal_latency = Histogram(
            f"{_P}_relation_traversal_latency_seconds",
            "Time to traverse document relations.",
            buckets=[0.01, 0.05, 0.1, 0.5, 1, 5],
            registry=r,
        )

        self.checks_duration = Histogram(
            f"{_P}_deal_checks_duration_seconds",
            "Time to run all checks for one deal/run.",
            labelnames=["stage"],
            buckets=[1, 5, 10, 30, 60, 120],
            registry=r,
        )

        # ==============================================================
        # 7. RELIABILITY METRICS
        # ==============================================================

        self.circuit_breaker_state = Gauge(
            f"{_P}_circuit_breaker_state",
            "Circuit breaker state: 0=CLOSED, 1=OPEN, 2=HALF_OPEN.",
            labelnames=["provider"],
            registry=r,
        )

        self.circuit_breaker_open_seconds = Counter(
            f"{_P}_circuit_breaker_open_seconds_total",
            "Total seconds a circuit breaker has been OPEN.",
            labelnames=["provider"],
            registry=r,
        )

        self.import_fail = Counter(
            f"{_P}_import_fail_total",
            "Total failed imports.",
            labelnames=["reason"],
            registry=r,
        )

        self.cloud_fallback = Counter(
            f"{_P}_cloud_fallback_total",
            "Total times cloud LLM was used as fallback.",
            registry=r,
        )

        self.quarantine = Counter(
            f"{_P}_quarantine_total",
            "Total documents sent to quarantine.",
            labelnames=["reason"],
            registry=r,
        )

        self.extraction_ocr_confidence = Histogram(
            f"{_P}_extraction_ocr_confidence",
            "OCR confidence distribution.",
            buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
            registry=r,
        )

        # ==============================================================
        # 8. CLASSIFICATION METRICS
        # ==============================================================

        self.classification_accuracy = Gauge(
            f"{_P}_classification_accuracy",
            "Fraction of documents correctly classified. Target >= 0.90.",
            registry=r,
        )

        self.yaml_coverage_rate = Gauge(
            f"{_P}_yaml_coverage_rate",
            "Fraction of classified doc_types with a matching YAML instruction. Target >= 0.70.",
            registry=r,
        )

        self.low_confidence_rate = Gauge(
            f"{_P}_low_confidence_rate",
            "Fraction of classified documents with confidence < 0.6. Target <= 0.15.",
            registry=r,
        )

        self.classification_duration = Histogram(
            f"{_P}_classification_duration_seconds",
            "Time to classify one document by decision source.",
            labelnames=["source"],  # MASTERCOPY | L2STRONGWINS | HYBRID | L4 | FALLBACK
            buckets=[0.05, 0.1, 0.25, 0.5, 1, 2, 5],
            registry=r,
        )

        self.classification_level_distribution = Counter(
            f"{_P}_classification_level_total",
            "Total documents classified at each level.",
            labelnames=["level", "doc_type"],  # level: L0-L4
            registry=r,
        )

        self.reclassification_total = Counter(
            f"{_P}_reclassification_total",
            "Total manual reclassification operations.",
            labelnames=["previous_doc_type", "new_doc_type"],
            registry=r,
        )

        # ==============================================================
        # 9. LLM METRICS
        # ==============================================================

        self.llm_request_duration_seconds = Histogram(
            f"{_P}_llm_request_duration_seconds",
            "Time to complete one LLM request.",
            labelnames=["provider"],  # openai | ollama | llamacpp | etc.
            buckets=[0.1, 0.5, 1, 2, 5, 10, 20, 60],
            registry=r,
        )

        self.llm_requests_total = Counter(
            f"{_P}_llm_requests_total",
            "Total LLM requests by provider and error type.",
            labelnames=["provider", "error_type"],  # error_type: none | timeout | ...
            registry=r,
        )

        self.llm_tokens_total = Counter(
            f"{_P}_llm_tokens_total",
            "Total tokens consumed by LLM.",
            labelnames=["provider"],
            registry=r,
        )

        self.llm_timeout_total = Counter(
            f"{_P}_llm_timeout_total",
            "Total LLM request timeouts by provider.",
            labelnames=["provider"],
            registry=r,
        )

        # ==============================================================
        # 10. PII METRICS
        # Перенесены из src/core/metrics.py.
        # Тот файл удалён — все PII метрики теперь в dedicated registry.
        # ==============================================================

        self.pii_entities_detected_total = Counter(
            f"{_P}_pii_entities_detected_total",
            "Total PII entities detected by entity type.",
            labelnames=["entity_type"],
            registry=r,
        )

        self.pii_entities_tokenized_total = Counter(
            f"{_P}_pii_entities_tokenized_total",
            "Total PII entities replaced with tokens.",
            labelnames=["entity_type"],
            registry=r,
        )

        self.pii_entities_preserved_total = Counter(
            f"{_P}_pii_entities_preserved_total",
            "Total PII entities preserved (INN, OGRN, cadastral).",
            labelnames=["entity_type"],
            registry=r,
        )

        self.pii_role_map_used_total = Counter(
            f"{_P}_pii_role_map_used_total",
            "Times party-role mapping was applied during PII sanitization.",
            registry=r,
        )

        self.pii_sanitization_duration_seconds = Histogram(
            f"{_P}_pii_sanitization_duration_seconds",
            "Duration of PII sanitization per document.",
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
            registry=r,
        )

        self.pii_sanitization_skipped_total = Counter(
            f"{_P}_pii_sanitization_skipped_total",
            "Documents skipped by PII sanitizer (already sanitized).",
            registry=r,
        )

        # ==============================================================
        # 11. BUILD INFO
        # ==============================================================

        self.build_info = Info(
            f"{_P}_build",
            "Build information (version, environment).",
            registry=r,
        )

        # ==============================================================
        # 12. MIGRATION SIGNALS
        # ==============================================================

        self.relation_traversal_depth_p95 = Gauge(
            f"{_P}_relation_traversal_depth_p95",
            "P95 relation traversal depth. Signal for Graph DB migration if > 3.",
            registry=r,
        )

        self.relation_edges_per_deal = Gauge(
            f"{_P}_relation_edges_per_deal",
            "Average document relation edges per deal. Signal for Graph DB migration if > 500.",
            registry=r,
        )

        self.cross_doc_queries_qps = Gauge(
            f"{_P}_cross_doc_queries_qps",
            "Cross-document queries per second. Signal for Graph DB migration if > 50.",
            registry=r,
        )

        # ==============================================================
        # 13. ADMIN METRICS
        # ==============================================================

        self.admin_logs_query_duration_seconds = Histogram(
            f"{_P}_admin_logs_query_duration_seconds",
            "Duration of Loki log queries from tenant admin panel.",
            labelnames=["since_minutes_bucket"],
            buckets=[0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 15.0, 30.0],
            registry=r,
        )

        # ==============================================================
        # 14. SPATIAL MARKER RECOVERY METRICS
        # Compensating control observability for Docling issue #1345.
        # Мигрированы из services/document_layout/metrics.py
        # (исправление registry mismatch + удаление high-cardinality
        #  document_id label).
        # ==============================================================

        self.spatial_recovery_elements_total = Counter(
            f"{_P}_spatial_recovery_elements_total",
            "Total marker recovery results by confidence level.",
            labelnames=["confidence_level"],  # high | medium | low | not_recovered
            registry=r,
        )

        self.spatial_recovery_match_attempts_total = Counter(
            f"{_P}_spatial_recovery_match_attempts_total",
            "Total spatial matching attempts (marker → atom).",
            registry=r,
        )

        self.spatial_recovery_rejections_total = Counter(
            f"{_P}_spatial_recovery_rejections_total",
            "Total markers rejected by sequence validation.",
            labelnames=["reason"],  # duplicate | non_monotonic | invalid_level_close
            registry=r,
        )

        self.spatial_recovery_confidence = Histogram(
            f"{_P}_spatial_recovery_confidence",
            "Distribution of marker recovery confidence scores.",
            buckets=[0.0, 0.25, 0.5, 0.65, 0.75, 0.85, 0.9, 0.95, 0.98, 1.0],
            registry=r,
        )

        self.spatial_recovery_y_delta = Histogram(
            f"{_P}_spatial_recovery_y_delta",
            "Distribution of Y-axis deltas in successful matches (points).",
            buckets=[0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 7.5, 10.0, 15.0, 20.0],
            registry=r,
        )

        self.spatial_recovery_rate = Gauge(
            f"{_P}_spatial_recovery_rate",
            "Fraction of atoms without native marker that got recovered (last document).",
            registry=r,
        )

        self.spatial_recovery_rejection_rate = Gauge(
            f"{_P}_spatial_recovery_rejection_rate",
            "Fraction of candidate matches rejected by sequence validation (last document).",
            registry=r,
        )

        self.spatial_recovery_mean_confidence = Gauge(
            f"{_P}_spatial_recovery_mean_confidence",
            "Mean confidence score of marker recovery (last document).",
            registry=r,
        )

        self.spatial_recovery_atoms_without_marker = Gauge(
            f"{_P}_spatial_recovery_atoms_without_marker",
            "Count of atoms lacking native Docling marker (last document).",
            registry=r,
        )

        # ==============================================================
        # 15. CLAUSE DETECTOR METRICS
        # LLMClauseDetector observability: LLM calls, fallback, timing.
        # ==============================================================

        self.clause_detector_clauses_added_total = Counter(
            f"{_P}_clause_detector_clauses_added_total",
            "Total clauses added to the tree by extraction method.",
            labelnames=["method"],  # llm | fallback
            registry=r,
        )

        self.clause_detector_refine_duration_seconds = Histogram(
            f"{_P}_clause_detector_refine_duration_seconds",
            "Duration of refine_tree() execution.",
            labelnames=["status"],  # success | error | skipped
            buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 30.0, 60.0],
            registry=r,
        )

        self.clause_detector_llm_calls_total = Counter(
            f"{_P}_clause_detector_llm_calls_total",
            "Total LLM calls made by ClauseDetector.",
            labelnames=["status"],  # success | error | empty | unavailable
            registry=r,
        )

        self.clause_detector_fallback_clauses_total = Counter(
            f"{_P}_clause_detector_fallback_clauses_total",
            "Total clauses extracted via regex fallback parser.",
            labelnames=["pattern_type"],  # strict_numeric | table_row | generic
            registry=r,
        )

        self.clause_detector_skipped_total = Counter(
            f"{_P}_clause_detector_skipped_total",
            "Total clause candidates skipped during tree assembly.",
            labelnames=["reason"],  # duplicate | no_match | construction_failed
            registry=r,
        )


# ── Singleton ─────────────────────────────────────────────────────────────────

_METRICS_INSTANCE: MetricsRegistry | None = None


def get_metrics() -> MetricsRegistry:
    """
    Вернуть singleton MetricsRegistry.

    При первом вызове создаёт экземпляр и регистрирует все метрики
    в dedicated CollectorRegistry. Последующие вызовы возвращают
    уже созданный экземпляр. Безопасно для Celery prefork workers.
    """
    global _METRICS_INSTANCE
    if _METRICS_INSTANCE is not None:
        return _METRICS_INSTANCE
    _METRICS_INSTANCE = MetricsRegistry()
    return _METRICS_INSTANCE


# Backward compatibility proxy: from ops.metrics import METRICS
if TYPE_CHECKING:
    METRICS: MetricsRegistry
else:

    class _MetricsProxy:
        """Lazy proxy — создаёт singleton при первом обращении к атрибуту."""

        def __getattr__(self, item: str):
            return getattr(get_metrics(), item)

    METRICS = _MetricsProxy()


    