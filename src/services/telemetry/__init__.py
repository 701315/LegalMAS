# src/services/telemetry/__init__.py

"""
Telemetry package — Phase 13.1 + 13.2.

Public API:
    TelemetryCollector  — per-document event collector
    DriftDetector       — per-document degradation detector
    DriftReport         — result of drift check
    DriftAlert          — single degradation signal
    DriftThresholds     — configurable thresholds
    emit_*_event        — typed event builders (convenience)
"""

from services.telemetry._collector import TelemetryCollector
from services.telemetry._drift import (
    DriftAlert,
    DriftDetector,
    DriftReport,
    DriftSeverity,
    DriftThresholds,
    make_drift_thresholds_from_settings,
)
from services.telemetry._events import (
    BaseTelemetryEvent,
    ChunkingCompletedEvent,
    DocumentProcessedEvent,
    EnrichmentCompletedEvent,
    QualityEvaluatedEvent,
    StructureBuiltEvent,
)

__all__ = [
    # Collector
    "TelemetryCollector",
    # Events
    "BaseTelemetryEvent",
    "StructureBuiltEvent",
    "QualityEvaluatedEvent",
    "ChunkingCompletedEvent",
    "EnrichmentCompletedEvent",
    "DocumentProcessedEvent",
    # Drift detection (Phase 13.2)
    "DriftDetector",
    "DriftReport",
    "DriftAlert",
    "DriftSeverity",
    "DriftThresholds",
    "make_drift_thresholds_from_settings",
]

