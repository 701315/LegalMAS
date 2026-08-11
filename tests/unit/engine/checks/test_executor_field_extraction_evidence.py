# tests/unit/engine/checks/test_executor_field_extraction_evidence.py
"""
Tests for the invariant: field_extraction checks must pass joined_text
as detection["evidence"] so that ExtractionExecutor receives the
already-budgeted context, not a raw re-join of all chunks.

This prevents ExtractionExecutor._build_extraction_text() from
bypassing the token budget computed by _build_limited_context().
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from engine.checks.executor import CheckExecutor
from engine.checks.extraction import ExtractionExecutionResult
from engine.playbook.models import (
    CheckDefinition,
    DetectorType,
    ExtractionConfig,
    ExtractionFieldConfig,
    LLMConfig,
    RetrievalConfig,
    RulesConfig,
)


def _make_field_extraction_check() -> CheckDefinition:
    return CheckDefinition(
        id="test_inventory_check",
        name="Test Inventory Check",
        description="Test",
        detector_type=DetectorType.HYBRID,
        rules=RulesConfig(keywords=["объект"]),
        llm=LLMConfig(),
        retrieval=RetrievalConfig(context_k=5, max_chunks=5),
        extraction=ExtractionConfig(
            enabled=True,
            mode="hybrid",  # type: ignore[arg-type]
            llm_max_tokens=1500,
            llm_prompt_extraction=(
                "<role>Тест</role>\n<context>{context}</context>\n<task>Тест</task>"
            ),
            fields=[
                ExtractionFieldConfig(
                    name="details",
                    type="string",  # type: ignore[arg-type]
                    presentation="fact",
                    label="Детали",
                    description="Тестовое поле",
                )
            ],
        ),
    )


def _make_chunks(n: int = 3) -> list[dict]:
    return [
        {
            "id": f"chunk_{i}",
            "text": f"Текст чанка {i} с содержательной информацией об объектах сделки.",
            "score": 0.9 - i * 0.1,
            "metadata": {
                "chunk_kind": "section",
                "clause_uid": f"appendix:{i}",
                "effective_uid": f"appendix:{i}",
                "start_page": i + 1,
                "end_page": i + 1,
                "path_titles": [f"Приложение {i}"],
                "element_ids": [f"elem_{i}"],
                "segment_id": "appendix_1",
                "segment_type": "appendix",
                "segment_title": "Приложение 1",
                "segment_order": 1,
                "is_primary_segment": False,
            },
        }
        for i in range(n)
    ]


class TestFieldExtractionEvidencePassthrough:
    """
    Invariant: for field_extraction checks, detection["evidence"] must equal
    the joined_text produced by _build_limited_context(), not an empty string.
    """

    def test_evidence_is_joined_text_not_empty(self):
        """
        When executor builds detection for field_extraction check,
        detection["evidence"] must be the budgeted joined_text,
        not the empty string "".
        """
        chunks = _make_chunks(3)
        check = _make_field_extraction_check()

        captured_detection: dict[str, Any] = {}

        class CapturingExtractor:
            """Captures detection dict passed to ExtractionExecutor.run_with_telemetry()."""

            def run_with_telemetry(self, doc, check, contexts, detection):
                captured_detection.update(detection)
                return ExtractionExecutionResult(
                    structured_data={
                        "details": {
                            "value": "Объект 1 | кадастр | площадь | адрес",
                            "confidence": 0.9,
                            "source": "llm",
                            "found": True,
                            "unit": None,
                            "location": None,
                            "qc": {
                                "status": "pending",
                                "by": None,
                                "comment": None,
                                "at": None,
                            },
                        }
                    },
                    telemetry=None,
                )

        doc = MagicMock()
        doc.id = "test-doc-id"
        doc.doc_type = "contract_1.6_real_estate"
        doc.classification_confidence = 1.0

        llm_client = MagicMock()
        executor = CheckExecutor(llm_client)
        executor.extractor = CapturingExtractor()  # type: ignore[assignment]

        # Patch HybridDetector so it doesn't run for field_extraction check
        with patch.object(executor, "detector") as mock_detector:
            mock_detector.run.return_value = {
                "found": False,
                "evidence": "",
                "confidence": 0.0,
                "method": "rules",
                "reason": "test",
                "sources": [],
                "location": None,
                "raw": {},
            }

            result = executor.execute(doc=doc, check=check, chunks=chunks)

        # Detector must NOT have been called for field_extraction check
        mock_detector.run.assert_not_called()

        # detection["evidence"] must be non-empty joined_text
        assert "evidence" in captured_detection
        evidence = captured_detection["evidence"]
        assert isinstance(evidence, str)
        assert evidence.strip() != "", (
            "detection['evidence'] must be joined_text, not empty string. "
            "ExtractionExecutor would otherwise re-join all raw chunks without budget."
        )

        # The evidence must contain text from the chunks
        assert any(
            f"Текст чанка {i}" in evidence for i in range(3)
        ), "Evidence must contain text from the provided chunks."

    def test_evidence_contains_all_chunk_texts_when_budget_allows(self):
        """
        When all chunks fit within token budget, joined_text must contain
        text from every chunk.
        """
        chunks = _make_chunks(3)
        check = _make_field_extraction_check()

        captured_detection: dict[str, Any] = {}

        class CapturingExtractor:
            def run_with_telemetry(self, doc, check, contexts, detection):
                captured_detection.update(detection)
                return ExtractionExecutionResult(
                    structured_data=None,
                    telemetry=None,
                )  # empty extraction → unclear result

        doc = MagicMock()
        doc.id = "test-doc-id"
        doc.doc_type = "test_type"
        doc.classification_confidence = 1.0

        llm_client = MagicMock()
        executor = CheckExecutor(llm_client)
        executor.extractor = CapturingExtractor()  # type: ignore[assignment]

        with patch.object(executor, "detector"):
            executor.execute(doc=doc, check=check, chunks=chunks)

        evidence = captured_detection.get("evidence", "")
        for i in range(3):
            assert f"Текст чанка {i}" in evidence, (
                f"Chunk {i} text missing from evidence. "
                "All chunks should be included when budget allows."
            )

    def test_non_field_extraction_check_evidence_from_detector(self):
        """
        For non-field-extraction checks, detection["evidence"] comes from
        HybridDetector, not from joined_text. This behavior must not change.
        """
        from engine.playbook.models import RulesConfig

        check = CheckDefinition(
            id="presence_check",
            name="Presence Check",
            description="Test presence check",
            detector_type=DetectorType.HYBRID,
            ui_mode="clause_presence",
            rules=RulesConfig(keywords=["объект"]),
            llm=LLMConfig(),
            retrieval=RetrievalConfig(context_k=3),
        )

        chunks = _make_chunks(2)
        detector_evidence = "Найдено в пункте 3.1: объект передаётся по акту."

        doc = MagicMock()
        doc.id = "test-doc-id"
        doc.doc_type = "test_type"
        doc.classification_confidence = 1.0

        llm_client = MagicMock()
        executor = CheckExecutor(llm_client)

        with patch.object(executor, "detector") as mock_detector:
            mock_detector.run.return_value = {
                "found": True,
                "evidence": detector_evidence,
                "confidence": 0.9,
                "method": "hybrid",
                "reason": "rules_confident_positive",
                "sources": [],
                "location": None,
                "raw": {},
            }

            result = executor.execute(doc=doc, check=check, chunks=chunks)

        # Detector was called for non-field-extraction check
        mock_detector.run.assert_called_once()

        # Evidence in result comes from detector
        assert result["evidence"] == detector_evidence


        