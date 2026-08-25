"""Unit-тесты для верификации работы LLMClauseDetector."""

from __future__ import annotations

from services.structure._clause_detector.parser import parse_llm_response
from services.structure._clause_detector.detector import _match_clauses_to_elements, DetectedClause
from services.structure.models import MutableHierarchyNode


def test_parse_llm_response_valid():
    raw_response = """
    Вот подготовленный список:
    {
      "clauses": [
        {
          "uid": "1.1",
          "title": "Определение термина Акт",
          "quote_start": "« Акт » означает",
          "quote_end": "к Договору."
        }
      ]
    }
    """
    clauses = parse_llm_response(raw_response, "1")
    assert len(clauses) == 1
    assert clauses[0].uid == "1.1"
    assert clauses[0].title == "Определение термина Акт"


def test_match_clauses_to_elements():
    clause = DetectedClause(
        uid="1.1",
        title="Определение термина Акт",
        quote_start="« Акт » означает",
        quote_end="к Договору."
    )
    elements = [
        {"element_id": "el-1", "text": "1 ОПРЕДЕЛЕНИЯ"},
        {"element_id": "el-2", "text": "« Акт » означает акт приема-передачи недвижимости к Договору."},
    ]
    chapter_node = MutableHierarchyNode(
        raw_uid="1",
        effective_uid="main_contract:1",
        title="ОПРЕДЕЛЕНИЯ",
        level=1,
        scope="main_contract",
        own_element_ids=["el-1", "el-2"],
        subtree_element_ids=["el-1", "el-2"],
    )

    matched = _match_clauses_to_elements([clause], elements, chapter_node)
    assert len(matched) == 1
    assert matched[0][1] == ["el-2"]


    