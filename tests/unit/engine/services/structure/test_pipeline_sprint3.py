"""
Sprint 3 tests: pipeline quality gates и degraded tree contract.

Проверяем:
- degraded tree проставляет section_chunking_allowed=False
- degraded tree использует effective_uid/raw_uid/scope
- _confidence_and_mode корректно определяет degraded flag
- quality_gates в structure_diagnostics
"""

import pytest
import uuid
from services.structure.pipeline import (
    _degraded_tree,
    _confidence_and_mode,
    STRUCTURE_CONFIDENCE_LOW,
    STRUCTURE_CONFIDENCE_MEDIUM,
    STRUCTURE_CONFIDENCE_HIGH,
    STRUCTURE_CONFIDENCE_FAILED,
)


class TestDegradedTreeContract:
    """Проверка degraded tree metadata contract."""

    def test_degraded_tree_sets_section_chunking_false(self):
        """Degraded tree проставляет section_chunking_allowed=False."""
        doc_id = str(uuid.uuid4())
        elements = [
            {"element_id": "e1", "text": "Text one.", "page": 1},
            {"element_id": "e2", "text": "Text two.", "page": 1},
        ]
        
        tree = _degraded_tree(
            document_id=doc_id,
            elements=elements,
            coverage=0.5,
            structure_confidence=STRUCTURE_CONFIDENCE_LOW,
        )
        
        quality_gates = tree.structure_diagnostics.get("quality_gates", {})
        assert quality_gates["section_chunking_allowed"] is False
        assert quality_gates["technical_fallback_only"] is True

    def test_degraded_tree_uses_canonical_identity(self):
        """Degraded tree chunks имеют effective_uid/raw_uid/scope."""
        doc_id = str(uuid.uuid4())
        elements = [
            {"element_id": "e1", "text": "Text one.", "page": 1},
            {"element_id": "e2", "text": "Text two.", "page": 1},
        ]
        
        tree = _degraded_tree(
            document_id=doc_id,
            elements=elements,
            scope_name="main_contract",
            segment_id="seg_0",
        )
        
        assert len(tree.root) > 0
        
        chunk = tree.root[0]
        assert chunk.effective_uid is not None
        assert chunk.raw_uid is not None
        assert chunk.scope == "main_contract"
        assert chunk.effective_uid.startswith("main_contract::")
        
        # clause_uid НЕ должно быть
        assert not hasattr(chunk, "clause_uid")

    def test_degraded_tree_schema_version_3(self):
        """Degraded tree имеет schema_version = "3.0"."""
        doc_id = str(uuid.uuid4())
        elements = [{"element_id": "e1", "text": "Text.", "page": 1}]
        
        tree = _degraded_tree(document_id=doc_id, elements=elements)
        
        assert tree.schema_version == "3.0"


class TestConfidenceAndMode:
    """Проверка _confidence_and_mode логики."""

    def test_high_coverage_high_numeric_ratio_returns_high_confidence(self):
        """Высокий coverage + numeric_ratio → STRUCTURE_CONFIDENCE_HIGH."""
        confidence, degraded = _confidence_and_mode(
            coverage=0.85,
            headings_count=10,
            numeric_ratio=0.8,
            empty_title_count=0,
        )
        
        assert confidence == STRUCTURE_CONFIDENCE_HIGH
        assert degraded is False

    def test_medium_coverage_returns_medium_confidence(self):
        """Средний coverage → STRUCTURE_CONFIDENCE_MEDIUM."""
        confidence, degraded = _confidence_and_mode(
            coverage=0.75,
            headings_count=10,
            numeric_ratio=0.8,
            empty_title_count=0,
        )
        
        assert confidence == STRUCTURE_CONFIDENCE_MEDIUM
        assert degraded is False

    def test_low_coverage_returns_low_confidence_degraded(self):
        """Низкий coverage → STRUCTURE_CONFIDENCE_LOW + degraded=True."""
        confidence, degraded = _confidence_and_mode(
            coverage=0.3,
            headings_count=10,
            numeric_ratio=0.8,
            empty_title_count=0,
        )
        
        assert confidence == STRUCTURE_CONFIDENCE_LOW
        assert degraded is True

    def test_low_numeric_ratio_returns_degraded(self):
        """Низкий numeric_ratio → degraded=True."""
        confidence, degraded = _confidence_and_mode(
            coverage=0.85,
            headings_count=10,
            numeric_ratio=0.2,
            empty_title_count=0,
        )
        
        assert confidence == STRUCTURE_CONFIDENCE_LOW
        assert degraded is True

    def test_too_many_empty_titles_returns_degraded(self):
        """Много empty title → degraded=True."""
        confidence, degraded = _confidence_and_mode(
            coverage=0.85,
            headings_count=10,
            numeric_ratio=0.8,
            empty_title_count=6,
        )
        
        assert confidence == STRUCTURE_CONFIDENCE_LOW
        assert degraded is True

    def test_no_headings_returns_failed(self):
        """Нет headings → STRUCTURE_CONFIDENCE_FAILED + degraded=True."""
        confidence, degraded = _confidence_and_mode(
            coverage=0.0,
            headings_count=0,
            numeric_ratio=0.0,
            empty_title_count=0,
        )
        
        assert confidence == STRUCTURE_CONFIDENCE_FAILED
        assert degraded is True

    def test_structure_degraded_flag_overrides_confidence(self):
        """Если structure_degraded=True, возвращает LOW даже при высоком coverage."""
        confidence, degraded = _confidence_and_mode(
            coverage=0.95,
            headings_count=10,
            numeric_ratio=0.9,
            empty_title_count=0,
            structure_degraded=True,
        )
        
        assert confidence == STRUCTURE_CONFIDENCE_LOW
        assert degraded is True

        