"""
Observability Integration Tests: Metric updates and registry checks.
"""

from __future__ import annotations

import pytest

from ops.metrics import get_metrics, get_prometheus_registry


def test_prometheus_metrics_mutation_flow():
    """
    Проверяет, что метрики успешно изменяют свое состояние при работе пайплайна.
    Использует поиск по sample.name для точной эмуляции Prometheus scraper.
    """
    m = get_metrics()
    reg = get_prometheus_registry()

    # Считываем значение счетчиков по имени сэмпла (sample.name)
    def get_val(sample_name: str, **labels) -> float:
        for metric in reg.collect():
            for sample in metric.samples:
                if sample.name == sample_name:
                    # Проверяем соответствие всех переданных лейблов
                    if labels:
                        match = True
                        for k, v in labels.items():
                            if sample.labels.get(k) != str(v):
                                match = False
                                break
                        if not match:
                            continue
                    return sample.value
        return 0.0

    # 1. Проверяем инкремент счетчиков Spatial Recovery
    m.spatial_recovery_elements_total.labels(confidence_level="high").inc(10)
    assert get_val("mas_dd_spatial_recovery_elements_total", confidence_level="high") == 10.0

    # 2. Проверяем инкремент счетчиков Clause Detector
    m.clause_detector_clauses_added_total.labels(method="llm").inc(5)
    assert get_val("mas_dd_clause_detector_clauses_added_total", method="llm") == 5.0

    # 3. Проверяем запись гистограмм времени выполнения
    m.clause_detector_refine_duration_seconds.labels(status="success").observe(1.23)
    val = get_val("mas_dd_clause_detector_refine_duration_seconds_count", status="success")
    assert val >= 1.0


    