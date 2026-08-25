# src/services/document_layout/metrics.py

"""
Aggregated metrics dataclass for SpatialMarkerRecovery pipeline.

Compensating control observability for Docling issue #1345.

Архитектурное решение (2025-06):
- Prometheus-метрики мигрированы в ops/metrics.py (раздел 14).
- Этот файл содержит ТОЛЬКО in-memory dataclass для агрегации
  результатов одного прохода восстановления.
- export_prometheus() делегирует в центральный METRICS singleton,
  гарантируя запись в dedicated CollectorRegistry (видимость на /metrics).
- document_id НЕ используется как Prometheus label (high cardinality).
  Он сохраняется только в structlog через to_log_dict().
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RecoveryMetrics:
    """
    Aggregated metrics for a single document recovery pass.

    Used for:
    - Prometheus metrics export (via ops.metrics.METRICS)
    - Structured logging (via to_log_dict)
    - Downstream quality gates (e.g., block if recovery_rate < 0.5)
    """

    document_id: str

    total_atoms: int = 0
    atoms_without_native_marker: int = 0
    markers_recovered_high_confidence: int = 0   # score >= 0.85
    markers_recovered_medium_confidence: int = 0  # 0.5 <= score < 0.85
    markers_recovered_low_confidence: int = 0     # score < 0.5
    markers_not_recovered: int = 0
    sequence_validation_rejections: int = 0
    spatial_match_attempts: int = 0

    # Computed ratios
    recovery_rate: float = 0.0
    rejection_rate: float = 0.0
    mean_confidence: float = 0.0

    # Per-match scores for histogram export
    confidence_scores: list[float] = field(default_factory=list)
    y_deltas: list[float] = field(default_factory=list)

    def compute_ratios(self) -> None:
        """Compute derived ratios after all counts are populated."""
        if self.atoms_without_native_marker > 0:
            self.recovery_rate = (
                self.markers_recovered_high_confidence
                + self.markers_recovered_medium_confidence
                + self.markers_recovered_low_confidence
            ) / self.atoms_without_native_marker
        else:
            self.recovery_rate = 1.0  # No recovery needed = 100% success

        total_candidates = (
            self.markers_recovered_high_confidence
            + self.markers_recovered_medium_confidence
            + self.markers_recovered_low_confidence
            + self.sequence_validation_rejections
        )
        if total_candidates > 0:
            self.rejection_rate = self.sequence_validation_rejections / total_candidates
        else:
            self.rejection_rate = 0.0

        if self.confidence_scores:
            self.mean_confidence = sum(self.confidence_scores) / len(self.confidence_scores)
        else:
            self.mean_confidence = 1.0

    def export_prometheus(self) -> None:
        """
        Export aggregated metrics to Prometheus via central METRICS registry.

        All metrics are written to the dedicated CollectorRegistry
        (ops/metrics.py), ensuring visibility on the /metrics endpoint.

        document_id is intentionally NOT used as a Prometheus label
        to prevent cardinality explosion. It is available in structlog
        via to_log_dict().
        """
        try:
            from ops.metrics import METRICS
        except ImportError:
            logger.warning(
                "Cannot export Prometheus metrics: ops.metrics unavailable",
                extra={"document_id": self.document_id},
            )
            return

        try:
            # ── Counters ──────────────────────────────────────────────
            METRICS.spatial_recovery_elements_total.labels(
                confidence_level="high",
            ).inc(self.markers_recovered_high_confidence)

            METRICS.spatial_recovery_elements_total.labels(
                confidence_level="medium",
            ).inc(self.markers_recovered_medium_confidence)

            METRICS.spatial_recovery_elements_total.labels(
                confidence_level="low",
            ).inc(self.markers_recovered_low_confidence)

            METRICS.spatial_recovery_elements_total.labels(
                confidence_level="not_recovered",
            ).inc(self.markers_not_recovered)

            METRICS.spatial_recovery_match_attempts_total.inc(
                self.spatial_match_attempts,
            )

            # ── Histograms ────────────────────────────────────────────
            for score in self.confidence_scores:
                METRICS.spatial_recovery_confidence.observe(score)

            for y_delta in self.y_deltas:
                METRICS.spatial_recovery_y_delta.observe(y_delta)

            # ── Gauges (last-document snapshot) ───────────────────────
            METRICS.spatial_recovery_rate.set(self.recovery_rate)
            METRICS.spatial_recovery_rejection_rate.set(self.rejection_rate)
            METRICS.spatial_recovery_mean_confidence.set(self.mean_confidence)
            METRICS.spatial_recovery_atoms_without_marker.set(
                self.atoms_without_native_marker,
            )

        except Exception as e:
            logger.warning(
                "Failed to export spatial recovery metrics to Prometheus",
                extra={"document_id": self.document_id, "error": str(e)},
            )

    def to_log_dict(self) -> dict:
        """Convert to dict for structured logging (includes document_id)."""
        return {
            "document_id": self.document_id,
            "total_atoms": self.total_atoms,
            "atoms_without_native_marker": self.atoms_without_native_marker,
            "markers_recovered_high": self.markers_recovered_high_confidence,
            "markers_recovered_medium": self.markers_recovered_medium_confidence,
            "markers_recovered_low": self.markers_recovered_low_confidence,
            "markers_not_recovered": self.markers_not_recovered,
            "sequence_rejections": self.sequence_validation_rejections,
            "recovery_rate": round(self.recovery_rate, 3),
            "rejection_rate": round(self.rejection_rate, 3),
            "mean_confidence": round(self.mean_confidence, 3),
        }


        