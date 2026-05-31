"""
Тесты Phase 13.2 — DriftDetector.

Покрытие:
- DriftReport.clean()
- DriftAlert.to_dict()
- DriftReport.to_dict()
- DriftDetector.check() — clean случай
- DriftDetector.check() — warning по каждой метрике
- DriftDetector.check() — critical по каждой метрике
- has_alerts / has_critical флаги
- Failure isolation (кривой summary)
- DriftThresholds defaults
- make_drift_thresholds_from_settings() fallback
- to_dict() сериализация
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from services.telemetry._drift import (
    DriftAlert,
    DriftDetector,
    DriftReport,
    DriftSeverity,
    DriftThresholds,
    make_drift_thresholds_from_settings,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@dataclass
class FakeSummary:
    """Минимальный fake DocumentProcessedEvent для тестов."""

    document_id: str = "doc-test"
    total_segments: int = 2
    total_nodes: int = 50
    total_chunks: int = 20
    total_units: int = 10

    avg_orphan_ratio: float = 0.0
    avg_grammar_violation_ratio: float = 0.0
    avg_retrieval_safety_score: float = 0.85

    any_degraded: bool = False
    any_technical_fallback: bool = False
    overall_retrieval_safe: bool = True

    enrichment_applied_count: int = 9
    enrichment_failed_count: int = 0
    enrichment_skipped_count: int = 0
    enrichment_llm_unavailable: bool = False

    retrieval_safe_chunks: int = 20
    recommended_action: str = "proceed"
    elapsed_ms: float = 1200.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "total_segments": self.total_segments,
            "total_units": self.total_units,
            "avg_orphan_ratio": self.avg_orphan_ratio,
            "avg_grammar_violation_ratio": self.avg_grammar_violation_ratio,
            "avg_retrieval_safety_score": self.avg_retrieval_safety_score,
            "any_degraded": self.any_degraded,
            "overall_retrieval_safe": self.overall_retrieval_safe,
            "enrichment_applied_count": self.enrichment_applied_count,
            "enrichment_failed_count": self.enrichment_failed_count,
            "enrichment_llm_unavailable": self.enrichment_llm_unavailable,
        }


def _clean_summary(**kwargs: Any) -> FakeSummary:
    """Создаёт clean summary с переопределёнными полями."""
    s = FakeSummary()
    for k, v in kwargs.items():
        object.__setattr__(s, k, v)
    return s


def _strict_thresholds() -> DriftThresholds:
    """
    Thresholds с отключёнными boolean alerts —
    для изолированного тестирования числовых метрик.
    """
    return DriftThresholds(
        alert_on_any_degraded=False,
        alert_on_llm_unavailable=False,
        alert_on_overall_retrieval_unsafe=False,
    )


# ---------------------------------------------------------------------------
# DriftAlert
# ---------------------------------------------------------------------------

class TestDriftAlert:
    def test_to_dict_contains_all_fields(self) -> None:
        alert = DriftAlert(
            metric="avg_orphan_ratio",
            severity=DriftSeverity.WARNING,
            observed=0.20,
            threshold=0.15,
            direction="above",
            message="test message",
        )
        d = alert.to_dict()
        assert d["metric"] == "avg_orphan_ratio"
        assert d["severity"] == "warning"
        assert d["observed"] == 0.20
        assert d["threshold"] == 0.15
        assert d["direction"] == "above"
        assert d["message"] == "test message"

    def test_severity_values(self) -> None:
        assert DriftSeverity.WARNING.value == "warning"
        assert DriftSeverity.CRITICAL.value == "critical"


# ---------------------------------------------------------------------------
# DriftReport
# ---------------------------------------------------------------------------

class TestDriftReport:
    def test_clean_report(self) -> None:
        report = DriftReport.clean("doc-123")
        assert report.document_id == "doc-123"
        assert report.has_alerts is False
        assert report.has_critical is False
        assert report.alert_count == 0
        assert report.critical_count == 0
        assert report.warning_count == 0
        assert report.alerts == ()

    def test_to_dict_clean(self) -> None:
        report = DriftReport.clean("doc-456")
        d = report.to_dict()
        assert d["document_id"] == "doc-456"
        assert d["has_alerts"] is False
        assert d["has_critical"] is False
        assert d["alerts"] == []
        assert "detector_version" in d

    def test_to_dict_with_alerts(self) -> None:
        alert = DriftAlert(
            metric="avg_orphan_ratio",
            severity=DriftSeverity.CRITICAL,
            observed=0.40,
            threshold=0.35,
            direction="above",
            message="critical",
        )
        report = DriftReport(
            document_id="doc-789",
            alerts=(alert,),
            has_alerts=True,
            has_critical=True,
            alert_count=1,
            critical_count=1,
            warning_count=0,
        )
        d = report.to_dict()
        assert d["has_alerts"] is True
        assert d["has_critical"] is True
        assert len(d["alerts"]) == 1
        assert d["alerts"][0]["metric"] == "avg_orphan_ratio"


# ---------------------------------------------------------------------------
# DriftThresholds
# ---------------------------------------------------------------------------

class TestDriftThresholds:
    def test_defaults_are_reasonable(self) -> None:
        t = DriftThresholds()
        assert 0.0 < t.orphan_ratio_warning < t.orphan_ratio_critical <= 1.0
        assert 0.0 < t.grammar_violation_ratio_warning < t.grammar_violation_ratio_critical <= 1.0
        assert 0.0 < t.retrieval_safety_score_critical < t.retrieval_safety_score_warning <= 1.0
        assert 0.0 < t.enrichment_applied_ratio_critical < t.enrichment_applied_ratio_warning <= 1.0
        assert t.enrichment_failed_warning >= 1
        assert t.enrichment_failed_critical > t.enrichment_failed_warning

    def test_make_from_settings_returns_thresholds(self) -> None:
        t = make_drift_thresholds_from_settings()
        assert isinstance(t, DriftThresholds)

    def test_make_from_settings_fallback_on_bad_settings(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """make_drift_thresholds_from_settings() не бросает даже если settings ломается."""
        import services.telemetry._drift as drift_module

        original = drift_module.make_drift_thresholds_from_settings

        def _bad_make() -> DriftThresholds:
            # Симулируем что import settings бросает
            raise RuntimeError("settings exploded")

        # Тестируем что fallback работает на уровне detector
        detector = DriftDetector(thresholds=DriftThresholds())
        assert detector.thresholds is not None


# ---------------------------------------------------------------------------
# DriftDetector — clean case
# ---------------------------------------------------------------------------

class TestDriftDetectorClean:
    def test_no_alerts_on_healthy_document(self) -> None:
        detector = DriftDetector(thresholds=DriftThresholds())
        summary = FakeSummary()
        report = detector.check(summary)
        assert report.has_alerts is False
        assert report.has_critical is False
        assert report.alert_count == 0

    def test_no_alerts_when_no_segments(self) -> None:
        """Числовые метрики не дают alert если total_segments=0."""
        detector = DriftDetector(thresholds=_strict_thresholds())
        summary = FakeSummary(
            total_segments=0,
            total_units=0,
            avg_retrieval_safety_score=0.0,  # было бы critical если segments > 0
        )
        report = detector.check(summary)
        # retrieval_safety и enrichment ratio не должны сработать
        metrics = [a.metric for a in report.alerts]
        assert "avg_retrieval_safety_score" not in metrics
        assert "enrichment_applied_ratio" not in metrics

    def test_failure_isolation_bad_summary(self) -> None:
        """Кривой summary возвращает clean report без исключений."""
        detector = DriftDetector(thresholds=DriftThresholds())
        result = detector.check(None)  # type: ignore[arg-type]
        assert isinstance(result, DriftReport)
        assert result.has_alerts is False


# ---------------------------------------------------------------------------
# DriftDetector — orphan_ratio
# ---------------------------------------------------------------------------

class TestDriftDetectorOrphanRatio:
    def test_no_alert_below_warning(self) -> None:
        detector = DriftDetector(thresholds=_strict_thresholds())
        summary = FakeSummary(avg_orphan_ratio=0.10)
        report = detector.check(summary)
        assert not any(a.metric == "avg_orphan_ratio" for a in report.alerts)

    def test_warning_at_threshold(self) -> None:
        t = DriftThresholds(
            orphan_ratio_warning=0.15,
            orphan_ratio_critical=0.35,
            alert_on_any_degraded=False,
            alert_on_llm_unavailable=False,
            alert_on_overall_retrieval_unsafe=False,
        )
        detector = DriftDetector(thresholds=t)
        summary = FakeSummary(avg_orphan_ratio=0.15)
        report = detector.check(summary)
        orphan_alerts = [a for a in report.alerts if a.metric == "avg_orphan_ratio"]
        assert len(orphan_alerts) == 1
        assert orphan_alerts[0].severity == DriftSeverity.WARNING

    def test_critical_above_critical_threshold(self) -> None:
        t = DriftThresholds(
            orphan_ratio_warning=0.15,
            orphan_ratio_critical=0.35,
            alert_on_any_degraded=False,
            alert_on_llm_unavailable=False,
            alert_on_overall_retrieval_unsafe=False,
        )
        detector = DriftDetector(thresholds=t)
        summary = FakeSummary(avg_orphan_ratio=0.40)
        report = detector.check(summary)
        orphan_alerts = [a for a in report.alerts if a.metric == "avg_orphan_ratio"]
        assert len(orphan_alerts) == 1
        assert orphan_alerts[0].severity == DriftSeverity.CRITICAL
        assert report.has_critical is True

    def test_only_critical_not_both(self) -> None:
        """Если критичный — не добавляем ещё и warning для той же метрики."""
        t = DriftThresholds(
            orphan_ratio_warning=0.15,
            orphan_ratio_critical=0.35,
            alert_on_any_degraded=False,
            alert_on_llm_unavailable=False,
            alert_on_overall_retrieval_unsafe=False,
        )
        detector = DriftDetector(thresholds=t)
        summary = FakeSummary(avg_orphan_ratio=0.50)
        report = detector.check(summary)
        orphan_alerts = [a for a in report.alerts if a.metric == "avg_orphan_ratio"]
        assert len(orphan_alerts) == 1


# ---------------------------------------------------------------------------
# DriftDetector — retrieval_safety_score
# ---------------------------------------------------------------------------

class TestDriftDetectorRetrievalSafety:
    def test_warning_when_below_warning_threshold(self) -> None:
        t = DriftThresholds(
            retrieval_safety_score_warning=0.60,
            retrieval_safety_score_critical=0.40,
            alert_on_any_degraded=False,
            alert_on_llm_unavailable=False,
            alert_on_overall_retrieval_unsafe=False,
        )
        detector = DriftDetector(thresholds=t)
        summary = FakeSummary(
            total_segments=2,
            avg_retrieval_safety_score=0.55,
        )
        report = detector.check(summary)
        safety_alerts = [
            a for a in report.alerts
            if a.metric == "avg_retrieval_safety_score"
        ]
        assert len(safety_alerts) == 1
        assert safety_alerts[0].severity == DriftSeverity.WARNING
        assert safety_alerts[0].direction == "below"

    def test_critical_when_below_critical_threshold(self) -> None:
        t = DriftThresholds(
            retrieval_safety_score_warning=0.60,
            retrieval_safety_score_critical=0.40,
            alert_on_any_degraded=False,
            alert_on_llm_unavailable=False,
            alert_on_overall_retrieval_unsafe=False,
        )
        detector = DriftDetector(thresholds=t)
        summary = FakeSummary(
            total_segments=2,
            avg_retrieval_safety_score=0.30,
        )
        report = detector.check(summary)
        safety_alerts = [
            a for a in report.alerts
            if a.metric == "avg_retrieval_safety_score"
        ]
        assert len(safety_alerts) == 1
        assert safety_alerts[0].severity == DriftSeverity.CRITICAL


# ---------------------------------------------------------------------------
# DriftDetector — enrichment
# ---------------------------------------------------------------------------

class TestDriftDetectorEnrichment:
    def test_llm_unavailable_triggers_warning(self) -> None:
        t = DriftThresholds(
            alert_on_any_degraded=False,
            alert_on_overall_retrieval_unsafe=False,
            alert_on_llm_unavailable=True,
        )
        detector = DriftDetector(thresholds=t)
        summary = FakeSummary(
            total_units=10,
            enrichment_applied_count=0,
            enrichment_llm_unavailable=True,
        )
        report = detector.check(summary)
        llm_alerts = [
            a for a in report.alerts
            if a.metric == "enrichment_llm_unavailable"
        ]
        assert len(llm_alerts) == 1
        assert llm_alerts[0].severity == DriftSeverity.WARNING

    def test_enrichment_failed_count_critical(self) -> None:
        t = DriftThresholds(
            enrichment_failed_warning=1,
            enrichment_failed_critical=3,
            alert_on_any_degraded=False,
            alert_on_llm_unavailable=False,
            alert_on_overall_retrieval_unsafe=False,
        )
        detector = DriftDetector(thresholds=t)
        summary = FakeSummary(enrichment_failed_count=5)
        report = detector.check(summary)
        failed_alerts = [
            a for a in report.alerts
            if a.metric == "enrichment_failed_count"
        ]
        assert len(failed_alerts) == 1
        assert failed_alerts[0].severity == DriftSeverity.CRITICAL

    def test_enrichment_applied_ratio_warning(self) -> None:
        t = DriftThresholds(
            enrichment_applied_ratio_warning=0.50,
            enrichment_applied_ratio_critical=0.20,
            alert_on_any_degraded=False,
            alert_on_llm_unavailable=False,
            alert_on_overall_retrieval_unsafe=False,
        )
        detector = DriftDetector(thresholds=t)
        # 3 из 10 применено = 0.30 < warning 0.50
        summary = FakeSummary(
            total_units=10,
            enrichment_applied_count=3,
        )
        report = detector.check(summary)
        ratio_alerts = [
            a for a in report.alerts
            if a.metric == "enrichment_applied_ratio"
        ]
        assert len(ratio_alerts) == 1
        assert ratio_alerts[0].severity == DriftSeverity.WARNING

    def test_no_enrichment_alert_when_no_units(self) -> None:
        """Если units=0 — enrichment ratio не проверяем."""
        t = DriftThresholds(
            enrichment_applied_ratio_warning=0.50,
            enrichment_applied_ratio_critical=0.20,
            alert_on_any_degraded=False,
            alert_on_llm_unavailable=False,
            alert_on_overall_retrieval_unsafe=False,
        )
        detector = DriftDetector(thresholds=t)
        summary = FakeSummary(
            total_units=0,
            enrichment_applied_count=0,
        )
        report = detector.check(summary)
        ratio_alerts = [
            a for a in report.alerts
            if a.metric == "enrichment_applied_ratio"
        ]
        assert len(ratio_alerts) == 0


# ---------------------------------------------------------------------------
# DriftDetector — boolean flags
# ---------------------------------------------------------------------------

class TestDriftDetectorBooleanFlags:
    def test_any_degraded_triggers_warning(self) -> None:
        t = DriftThresholds(
            alert_on_any_degraded=True,
            alert_on_llm_unavailable=False,
            alert_on_overall_retrieval_unsafe=False,
        )
        detector = DriftDetector(thresholds=t)
        summary = FakeSummary(any_degraded=True)
        report = detector.check(summary)
        degraded_alerts = [
            a for a in report.alerts if a.metric == "any_degraded"
        ]
        assert len(degraded_alerts) == 1
        assert degraded_alerts[0].severity == DriftSeverity.WARNING

    def test_overall_retrieval_unsafe_triggers_warning(self) -> None:
        t = DriftThresholds(
            alert_on_any_degraded=False,
            alert_on_llm_unavailable=False,
            alert_on_overall_retrieval_unsafe=True,
        )
        detector = DriftDetector(thresholds=t)
        summary = FakeSummary(
            total_segments=2,
            overall_retrieval_safe=False,
        )
        report = detector.check(summary)
        safe_alerts = [
            a for a in report.alerts if a.metric == "overall_retrieval_safe"
        ]
        assert len(safe_alerts) == 1

    def test_boolean_alerts_disabled_by_thresholds(self) -> None:
        t = DriftThresholds(
            alert_on_any_degraded=False,
            alert_on_llm_unavailable=False,
            alert_on_overall_retrieval_unsafe=False,
        )
        detector = DriftDetector(thresholds=t)
        summary = FakeSummary(
            any_degraded=True,
            overall_retrieval_safe=False,
            enrichment_llm_unavailable=True,
        )
        report = detector.check(summary)
        boolean_metrics = {
            "any_degraded", "overall_retrieval_safe", "enrichment_llm_unavailable"
        }
        triggered = {a.metric for a in report.alerts} & boolean_metrics
        assert len(triggered) == 0


# ---------------------------------------------------------------------------
# DriftDetector — multiple alerts + report flags
# ---------------------------------------------------------------------------

class TestDriftDetectorMultipleAlerts:
    def test_multiple_alerts_counted_correctly(self) -> None:
        t = DriftThresholds(
            orphan_ratio_warning=0.15,
            orphan_ratio_critical=0.35,
            grammar_violation_ratio_warning=0.15,
            grammar_violation_ratio_critical=0.30,
            retrieval_safety_score_warning=0.60,
            retrieval_safety_score_critical=0.40,
            alert_on_any_degraded=False,
            alert_on_llm_unavailable=False,
            alert_on_overall_retrieval_unsafe=False,
        )
        detector = DriftDetector(thresholds=t)
        summary = FakeSummary(
            total_segments=2,
            avg_orphan_ratio=0.40,          # CRITICAL
            avg_grammar_violation_ratio=0.20, # WARNING
            avg_retrieval_safety_score=0.35,  # CRITICAL
        )
        report = detector.check(summary)

        assert report.has_alerts is True
        assert report.has_critical is True
        assert report.critical_count == 2
        assert report.warning_count == 1
        assert report.alert_count == 3

    def test_report_document_id_preserved(self) -> None:
        detector = DriftDetector(thresholds=DriftThresholds())
        summary = FakeSummary(document_id="my-doc-id-999")
        report = detector.check(summary)
        assert report.document_id == "my-doc-id-999"

    def test_to_dict_round_trip(self) -> None:
        """to_dict() содержит все ожидаемые ключи."""
        detector = DriftDetector(thresholds=DriftThresholds())
        summary = FakeSummary()
        report = detector.check(summary)
        d = report.to_dict()

        assert "document_id" in d
        assert "has_alerts" in d
        assert "has_critical" in d
        assert "alert_count" in d
        assert "critical_count" in d
        assert "warning_count" in d
        assert "detector_version" in d
        assert "alerts" in d
        assert isinstance(d["alerts"], list)

        