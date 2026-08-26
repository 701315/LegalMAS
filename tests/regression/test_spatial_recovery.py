"""
Regression test suite for SpatialMarkerRecovery pipeline.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from services.document_layout.schemas import CanonicalAtom
from services.document_layout.spatial_marker_recovery import SpatialMarkerRecovery


def test_spatial_recovery_regression_gates(
    golden_manifest: dict[str, Any],
    regression_fixtures_dir: Any,
):
    """
    Проверяет качество работы SpatialMarkerRecovery на золотом наборе.
    """
    for doc_key, spec in golden_manifest.items():
        json_path = regression_fixtures_dir / f"{doc_key}_atoms.json"
        pdf_path = regression_fixtures_dir / spec["filename"]

        # Защита: если фикстуры еще не подготовлены — пропускаем тест
        if not json_path.exists() or not pdf_path.exists():
            pytest.skip(f"Fixtures for {doc_key} not found, skipping.")

        # 1. Загрузка исходных Docling атомов
        with open(json_path, "r", encoding="utf-8") as f:
            raw_atoms = json.load(f)
            atoms = [CanonicalAtom(**a) for a in raw_atoms]

        pdf_bytes = pdf_path.read_bytes()

        # 2. Выполнение геометрического восстановления
        recovered_atoms, metrics = SpatialMarkerRecovery.recover(
            atoms=atoms,
            pdf_bytes=pdf_bytes,
            document_id=doc_key,
        )

        # 3. Проверка качества по жестким критериям
        assert len(recovered_atoms) == len(atoms), f"Atom mismatch in {doc_key}!"

        recovered_by_us = [
            a for a in recovered_atoms
            if a.metadata and a.metadata.get("marker_source") == "spatial_recovery"
        ]

        # Assurance Gate 1: Объем восстановленной информации
        assert len(recovered_by_us) >= spec["min_recovered_markers"], (
            f"Spatial Recovery Regression in {doc_key}! "
            f"Recovered: {len(recovered_by_us)}, expected at least: {spec['min_recovered_markers']}"
        )

        # Assurance Gate 2: Достоверность восстановления
        if len(recovered_by_us) > 0:
            assert metrics.mean_confidence >= 0.75, (
                f"Validation Failure in {doc_key}! "
                f"Mean confidence is {metrics.mean_confidence:.3f}, target >= 0.75"
            )


            