"""
Steloom Pipeline Regression Suite — Configuration & Fixtures.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Generator
from unittest.mock import MagicMock, patch

import pytest

from services.document_layout.schemas import CanonicalAtom
from services.structure._models._nodes import MutableHierarchyNode


@pytest.fixture(scope="session")
def regression_fixtures_dir() -> Path:
    """Путь к директории с эталонными JSON-снапшотами."""
    path = Path(__file__).parent / "fixtures"
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture(scope="session")
def golden_manifest() -> dict[str, dict[str, Any]]:
    """
    Манифест золотого датасета (10 типов документов).
    Задает строгие рамки (Assurance Gates) для прохождения регрессии.
    """
    return {
        "doc_01_bilingual": {
            "filename": "contract_ru_en_30p.pdf",
            "min_recovered_markers": 50,
            "min_clause_nodes": 56,  # Наш эталон из Task 1 (56 подразделов)
            "expected_chapters": ["1", "2", "3", "4", "5", "6", "7", "8"],
        },
        "doc_02_monolingual_ru": {
            "filename": "lease_ru_15p.pdf",
            "min_recovered_markers": 10,
            "min_clause_nodes": 20,
            "expected_chapters": ["1", "2", "3", "4"],
        },
        "doc_03_monolingual_en": {
            "filename": "nda_en_15p.pdf",
            "min_recovered_markers": 5,
            "min_clause_nodes": 15,
            "expected_chapters": ["1", "2", "3"],
        },
        "doc_04_ocr_scan": {
            "filename": "ocr_scan_ru_25p.pdf",
            "min_recovered_markers": 25,
            "min_clause_nodes": 30,
            "expected_chapters": ["1", "2", "3", "4", "5"],
        },
        "doc_05_annex_tables": {
            "filename": "annex_with_tables_10p.pdf",
            "min_recovered_markers": 12,
            "min_clause_nodes": 10,
            "expected_chapters": ["1"],
        },
        "doc_0 Roman_num": {
            "filename": "roman_num_en_20p.pdf",
            "min_recovered_markers": 15,
            "min_clause_nodes": 25,
            "expected_chapters": ["I", "II", "III", "IV"],
        },
        "doc_07_alphabetic": {
            "filename": "alpha_ru_15p.pdf",
            "min_recovered_markers": 8,
            "min_clause_nodes": 18,
            "expected_chapters": ["1", "2"],
        },
        "doc_08_deep_hierarchy": {
            "filename": "deep_hierarchy_40p.pdf",
            "min_recovered_markers": 55,
            "min_clause_nodes": 75,
            "expected_chapters": ["1", "2", "3", "4", "5", "6", "7", "8"],
        },
        "doc_09_toc_heavy": {
            "filename": "toc_heavy_ru_50p.pdf",
            "min_recovered_markers": 70,
            "min_clause_nodes": 90,
            "expected_chapters": ["1", "2", "3", "4", "5", "6", "7", "8", "9"],
        },
        "doc_10_minimal": {
            "filename": "minimal_agreement_5p.pdf",
            "min_recovered_markers": 0,
            "min_clause_nodes": 5,
            "expected_chapters": ["1", "2"],
        }
    }


@pytest.fixture
def mock_llm_client() -> Generator[MagicMock, None, None]:
    """
    Детерминированный мок для LLMClient.
    Позволяет гонять регрессионные тесты локально без Ollama.
    """
    with patch("services.structure._clause_detector.detector.LLMClient") as mock_class:
        instance = mock_class.return_value
        instance.is_available.return_value = True
        
        # Эмулируем успешный ответ модели в формате JSON
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "clauses": [
                {"uid": "1.1", "title": "Definitions", "quote_start": "The following terms", "quote_end": "as defined here"},
                {"uid": "1.2", "title": "Interpretation", "quote_start": "In this Agreement", "quote_end": "otherwise required"}
            ]
        })
        instance.call_with_retries.return_value = (mock_response, None)
        yield instance


        