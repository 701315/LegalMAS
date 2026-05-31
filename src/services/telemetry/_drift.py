# src/services/telemetry/_drift.py

"""
DriftDetector — per-document processing degradation detector.

Phase 13.2 — Degradation Detection v1.

Назначение:
    Обнаруживает деградацию качества обработки документа
    относительно фиксированных thresholds.

    Это НЕ statistical drift detection — это runtime health check
    поверх уже рассчитанных telemetry метрик.

    Следующий уровень (temporal drift, rolling baseline) строится
    поверх persisted summaries которые начинаем сохранять здесь.

Принципы:
    - Non-blocking: никогда не бросает исключений наружу.
    - Non-mutating: не меняет pipeline state.
    - Configurable thresholds через Settings.
    - Failure-isolated: ошибка detector не ломает pipeline.
    - Audit-friendly: результат сериализуется в dict для AuditLog.

Эволюция:
    Phase 13.2 → per-document fixed thresholds (текущий файл)
    Phase 13.x → temporal drift based on persisted summaries
    Phase 14.x → per-document-type baseline
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from core.logging import get_logger

if TYPE_CHECKING:
    from services.telemetry._events import DocumentProcessedEvent

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Alert severity
# ---------------------------------------------------------------------------

class DriftSeverity(str, Enum):
    """Severity уровень одного drift alert."""

    WARNING = "warning"
    CRITICAL = "critical"


# ---------------------------------------------------------------------------
# Single alert
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DriftAlert:
    """
    Один конкретный сигнал деградации.

    Immutable — создаётся детектором, передаётся в DriftReport.
    """

    metric: str
    """Имя метрики которая нарушила threshold."""

    severity: DriftSeverity
    """WARNING или CRITICAL."""

    observed: float | bool | int
    """Фактическое значение метрики."""

    threshold: float | bool | int
    """Threshold который был нарушен."""

    direction: str
    """'above' если observed > threshold, 'below' если observed < threshold."""

    message: str
    """Human-readable описание."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "severity": self.severity.value,
            "observed": self.observed,
            "threshold": self.threshold,
            "direction": self.direction,
            "message": self.message,
        }


# ---------------------------------------------------------------------------
# Drift report
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DriftReport:
    """
    Результат проверки одного документа.

    Содержит все alerts + итоговый статус.
    Immutable — создаётся DriftDetector.check().
    """

    document_id: str
    alerts: tuple[DriftAlert, ...] = field(default_factory=tuple)
    has_alerts: bool = False
    has_critical: bool = False
    alert_count: int = 0
    critical_count: int = 0
    warning_count: int = 0
    detector_version: str = "v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "has_alerts": self.has_alerts,
            "has_critical": self.has_critical,
            "alert_count": self.alert_count,
            "critical_count": self.critical_count,
            "warning_count": self.warning_count,
            "detector_version": self.detector_version,
            "alerts": [a.to_dict() for a in self.alerts],
        }

    @classmethod
    def clean(cls, document_id: str) -> "DriftReport":
        """Пустой report без alerts."""
        return cls(
            document_id=document_id,
            alerts=(),
            has_alerts=False,
            has_critical=False,
            alert_count=0,
            critical_count=0,
            warning_count=0,
        )


# ---------------------------------------------------------------------------
# Thresholds config
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DriftThresholds:
    """
    Конфигурация thresholds для DriftDetector.

    Создаётся через make_drift_thresholds_from_settings().
    Можно создать вручную для тестов.
    """

    # Structure quality
    orphan_ratio_warning: float = 0.15
    orphan_ratio_critical: float = 0.35

    grammar_violation_ratio_warning: float = 0.15
    grammar_violation_ratio_critical: float = 0.30

    retrieval_safety_score_warning: float = 0.60
    retrieval_safety_score_critical: float = 0.40

    # Enrichment
    enrichment_applied_ratio_warning: float = 0.50
    enrichment_applied_ratio_critical: float = 0.20

    enrichment_failed_warning: int = 1
    enrichment_failed_critical: int = 3

    # Boolean flags (presence = alert)
    alert_on_any_degraded: bool = True
    alert_on_llm_unavailable: bool = True
    alert_on_overall_retrieval_unsafe: bool = True


def make_drift_thresholds_from_settings() -> DriftThresholds:
    """
    Создаёт DriftThresholds из application settings.

    Читает DRIFT_* переменные из config если они определены,
    иначе использует safe defaults.
    Failure-isolated: при любой ошибке возвращает defaults.
    """
    try:
        from core.config import settings

        def _get(name: str, default: Any) -> Any:
            return getattr(settings, name, default)

        return DriftThresholds(
            orphan_ratio_warning=float(
                _get("DRIFT_ORPHAN_RATIO_WARNING", 0.15)
            ),
            orphan_ratio_critical=float(
                _get("DRIFT_ORPHAN_RATIO_CRITICAL", 0.35)
            ),
            grammar_violation_ratio_warning=float(
                _get("DRIFT_GRAMMAR_VIOLATION_RATIO_WARNING", 0.15)
            ),
            grammar_violation_ratio_critical=float(
                _get("DRIFT_GRAMMAR_VIOLATION_RATIO_CRITICAL", 0.30)
            ),
            retrieval_safety_score_warning=float(
                _get("DRIFT_RETRIEVAL_SAFETY_SCORE_WARNING", 0.60)
            ),
            retrieval_safety_score_critical=float(
                _get("DRIFT_RETRIEVAL_SAFETY_SCORE_CRITICAL", 0.40)
            ),
            enrichment_applied_ratio_warning=float(
                _get("DRIFT_ENRICHMENT_APPLIED_RATIO_WARNING", 0.50)
            ),
            enrichment_applied_ratio_critical=float(
                _get("DRIFT_ENRICHMENT_APPLIED_RATIO_CRITICAL", 0.20)
            ),
            enrichment_failed_warning=int(
                _get("DRIFT_ENRICHMENT_FAILED_WARNING", 1)
            ),
            enrichment_failed_critical=int(
                _get("DRIFT_ENRICHMENT_FAILED_CRITICAL", 3)
            ),
            alert_on_any_degraded=bool(
                _get("DRIFT_ALERT_ON_ANY_DEGRADED", True)
            ),
            alert_on_llm_unavailable=bool(
                _get("DRIFT_ALERT_ON_LLM_UNAVAILABLE", True)
            ),
            alert_on_overall_retrieval_unsafe=bool(
                _get("DRIFT_ALERT_ON_OVERALL_RETRIEVAL_UNSAFE", True)
            ),
        )
    except Exception as exc:
        logger.warning(
            "DRIFT make_thresholds_from_settings_failed, using defaults",
            error=str(exc),
        )
        return DriftThresholds()


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------

class DriftDetector:
    """
    Per-document processing degradation detector.

    Принимает DocumentProcessedEvent (telemetry summary)
    и возвращает DriftReport с alerts.

    Использование:
        detector = DriftDetector()
        report = detector.check(doc_summary)
        if report.has_critical:
            await audit_repo.log(..., action="PROCESSING_DEGRADATION_ALERT", ...)
    """

    def __init__(
        self,
        thresholds: DriftThresholds | None = None,
    ) -> None:
        self._thresholds = thresholds or make_drift_thresholds_from_settings()

    @property
    def thresholds(self) -> DriftThresholds:
        return self._thresholds

    def check(
        self,
        summary: "DocumentProcessedEvent",
    ) -> DriftReport:
        """
        Проверить DocumentProcessedEvent на деградацию.

        Failure-isolated: при любой ошибке возвращает clean report
        и логирует warning.

        Returns:
            DriftReport с alerts если деградация обнаружена,
            иначе DriftReport.clean().
        """
        try:
            return self._check_internal(summary)
        except Exception as exc:
            document_id = _safe_str(getattr(summary, "document_id", "unknown"))
            logger.warning(
                "DRIFT check_failed, returning clean report",
                document_id=document_id,
                error=str(exc),
            )
            return DriftReport.clean(document_id=document_id)

    # ── Internal ─────────────────────────────────────────────────────────

    def _check_internal(
        self,
        summary: "DocumentProcessedEvent",
    ) -> DriftReport:
        document_id = _safe_str(getattr(summary, "document_id", "unknown"))
        t = self._thresholds
        alerts: list[DriftAlert] = []

        total_segments = _safe_int(getattr(summary, "total_segments", 0))
        total_units = _safe_int(getattr(summary, "total_units", 0))

        # ── 1. Structure: avg_orphan_ratio ────────────────────────────────
        orphan_ratio = _safe_float(getattr(summary, "avg_orphan_ratio", 0.0))
        if orphan_ratio >= t.orphan_ratio_critical:
            alerts.append(DriftAlert(
                metric="avg_orphan_ratio",
                severity=DriftSeverity.CRITICAL,
                observed=round(orphan_ratio, 4),
                threshold=t.orphan_ratio_critical,
                direction="above",
                message=(
                    f"avg_orphan_ratio={orphan_ratio:.3f} exceeds critical "
                    f"threshold={t.orphan_ratio_critical:.3f}. "
                    "Structure recovery is failing at critical level."
                ),
            ))
        elif orphan_ratio >= t.orphan_ratio_warning:
            alerts.append(DriftAlert(
                metric="avg_orphan_ratio",
                severity=DriftSeverity.WARNING,
                observed=round(orphan_ratio, 4),
                threshold=t.orphan_ratio_warning,
                direction="above",
                message=(
                    f"avg_orphan_ratio={orphan_ratio:.3f} exceeds warning "
                    f"threshold={t.orphan_ratio_warning:.3f}."
                ),
            ))

        # ── 2. Structure: avg_grammar_violation_ratio ─────────────────────
        grammar_ratio = _safe_float(
            getattr(summary, "avg_grammar_violation_ratio", 0.0)
        )
        if grammar_ratio >= t.grammar_violation_ratio_critical:
            alerts.append(DriftAlert(
                metric="avg_grammar_violation_ratio",
                severity=DriftSeverity.CRITICAL,
                observed=round(grammar_ratio, 4),
                threshold=t.grammar_violation_ratio_critical,
                direction="above",
                message=(
                    f"avg_grammar_violation_ratio={grammar_ratio:.3f} exceeds "
                    f"critical threshold={t.grammar_violation_ratio_critical:.3f}. "
                    "Heading grammar is severely degraded."
                ),
            ))
        elif grammar_ratio >= t.grammar_violation_ratio_warning:
            alerts.append(DriftAlert(
                metric="avg_grammar_violation_ratio",
                severity=DriftSeverity.WARNING,
                observed=round(grammar_ratio, 4),
                threshold=t.grammar_violation_ratio_warning,
                direction="above",
                message=(
                    f"avg_grammar_violation_ratio={grammar_ratio:.3f} exceeds "
                    f"warning threshold={t.grammar_violation_ratio_warning:.3f}."
                ),
            ))

        # ── 3. Quality: avg_retrieval_safety_score ────────────────────────
        # Проверяем только если pipeline реально обработал сегменты.
        # Иначе 0.0 по умолчанию даст ложный CRITICAL.
        safety_score = _safe_float(
            getattr(summary, "avg_retrieval_safety_score", 0.0)
        )
        if total_segments > 0:
            if safety_score < t.retrieval_safety_score_critical:
                alerts.append(DriftAlert(
                    metric="avg_retrieval_safety_score",
                    severity=DriftSeverity.CRITICAL,
                    observed=round(safety_score, 4),
                    threshold=t.retrieval_safety_score_critical,
                    direction="below",
                    message=(
                        f"avg_retrieval_safety_score={safety_score:.3f} below "
                        f"critical threshold={t.retrieval_safety_score_critical:.3f}. "
                        "Retrieval quality is critically degraded."
                    ),
                ))
            elif safety_score < t.retrieval_safety_score_warning:
                alerts.append(DriftAlert(
                    metric="avg_retrieval_safety_score",
                    severity=DriftSeverity.WARNING,
                    observed=round(safety_score, 4),
                    threshold=t.retrieval_safety_score_warning,
                    direction="below",
                    message=(
                        f"avg_retrieval_safety_score={safety_score:.3f} below "
                        f"warning threshold={t.retrieval_safety_score_warning:.3f}."
                    ),
                ))

        # ── 4. Boolean: any_degraded ──────────────────────────────────────
        if t.alert_on_any_degraded and _safe_bool(
            getattr(summary, "any_degraded", False)
        ):
            alerts.append(DriftAlert(
                metric="any_degraded",
                severity=DriftSeverity.WARNING,
                observed=True,
                threshold=False,
                direction="above",
                message=(
                    "One or more segments processed in degraded mode. "
                    "Structure confidence is below acceptable level."
                ),
            ))

        # ── 5. Boolean: overall_retrieval_safe ────────────────────────────
        # Проверяем только если есть сегменты — иначе False по умолчанию
        # даст ложный alert на пустых документах.
        if t.alert_on_overall_retrieval_unsafe and total_segments > 0:
            overall_safe = _safe_bool(
                getattr(summary, "overall_retrieval_safe", False)
            )
            if not overall_safe:
                alerts.append(DriftAlert(
                    metric="overall_retrieval_safe",
                    severity=DriftSeverity.WARNING,
                    observed=False,
                    threshold=True,
                    direction="below",
                    message=(
                        "Document is not fully retrieval-safe. "
                        "Some chunks may produce unreliable retrieval results."
                    ),
                ))

        # ── 6. Enrichment: applied_ratio ──────────────────────────────────
        # Проверяем только если есть units для enrichment.
        if total_units > 0:
            enrichment_applied = _safe_int(
                getattr(summary, "enrichment_applied_count", 0)
            )
            applied_ratio = enrichment_applied / total_units

            if applied_ratio < t.enrichment_applied_ratio_critical:
                alerts.append(DriftAlert(
                    metric="enrichment_applied_ratio",
                    severity=DriftSeverity.CRITICAL,
                    observed=round(applied_ratio, 4),
                    threshold=t.enrichment_applied_ratio_critical,
                    direction="below",
                    message=(
                        f"enrichment_applied_ratio={applied_ratio:.3f} below "
                        f"critical threshold={t.enrichment_applied_ratio_critical:.3f}. "
                        "LLM enrichment is almost completely failing."
                    ),
                ))
            elif applied_ratio < t.enrichment_applied_ratio_warning:
                alerts.append(DriftAlert(
                    metric="enrichment_applied_ratio",
                    severity=DriftSeverity.WARNING,
                    observed=round(applied_ratio, 4),
                    threshold=t.enrichment_applied_ratio_warning,
                    direction="below",
                    message=(
                        f"enrichment_applied_ratio={applied_ratio:.3f} below "
                        f"warning threshold={t.enrichment_applied_ratio_warning:.3f}."
                    ),
                ))

        # ── 7. Enrichment: failed_count ───────────────────────────────────
        enrichment_failed = _safe_int(
            getattr(summary, "enrichment_failed_count", 0)
        )
        if enrichment_failed >= t.enrichment_failed_critical:
            alerts.append(DriftAlert(
                metric="enrichment_failed_count",
                severity=DriftSeverity.CRITICAL,
                observed=enrichment_failed,
                threshold=t.enrichment_failed_critical,
                direction="above",
                message=(
                    f"enrichment_failed_count={enrichment_failed} exceeds "
                    f"critical threshold={t.enrichment_failed_critical}. "
                    "LLM is consistently returning errors."
                ),
            ))
        elif enrichment_failed >= t.enrichment_failed_warning:
            alerts.append(DriftAlert(
                metric="enrichment_failed_count",
                severity=DriftSeverity.WARNING,
                observed=enrichment_failed,
                threshold=t.enrichment_failed_warning,
                direction="above",
                message=(
                    f"enrichment_failed_count={enrichment_failed} exceeds "
                    f"warning threshold={t.enrichment_failed_warning}."
                ),
            ))

        # ── 8. Boolean: llm_unavailable ───────────────────────────────────
        if t.alert_on_llm_unavailable and _safe_bool(
            getattr(summary, "enrichment_llm_unavailable", False)
        ):
            alerts.append(DriftAlert(
                metric="enrichment_llm_unavailable",
                severity=DriftSeverity.WARNING,
                observed=True,
                threshold=False,
                direction="above",
                message=(
                    "LLM was unavailable during enrichment. "
                    "All units processed without semantic enrichment."
                ),
            ))

        # ── Build report ──────────────────────────────────────────────────
        critical_count = sum(
            1 for a in alerts if a.severity == DriftSeverity.CRITICAL
        )
        warning_count = sum(
            1 for a in alerts if a.severity == DriftSeverity.WARNING
        )

        report = DriftReport(
            document_id=document_id,
            alerts=tuple(alerts),
            has_alerts=bool(alerts),
            has_critical=critical_count > 0,
            alert_count=len(alerts),
            critical_count=critical_count,
            warning_count=warning_count,
        )

        if report.has_critical:
            logger.warning(
                "DRIFT critical_degradation_detected",
                document_id=document_id,
                critical_count=critical_count,
                warning_count=warning_count,
                metrics=[
                    a.metric for a in alerts
                    if a.severity == DriftSeverity.CRITICAL
                ],
            )
        elif report.has_alerts:
            logger.info(
                "DRIFT warnings_detected",
                document_id=document_id,
                warning_count=warning_count,
                metrics=[a.metric for a in alerts],
            )
        else:
            logger.debug(
                "DRIFT no_alerts",
                document_id=document_id,
            )

        return report


# ---------------------------------------------------------------------------
# Helpers (module-private)
# ---------------------------------------------------------------------------

def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _safe_bool(value: Any, default: bool = False) -> bool:
    try:
        if value is None:
            return default
        return bool(value)
    except Exception:
        return default


def _safe_str(value: Any, default: str = "") -> str:
    try:
        if value is None:
            return default
        return str(value)
    except Exception:
        return default
    

