"""
Tests for SemanticEnrichmentContext.
Covers: factory methods, helpers, prompt block, immutability.
"""
import pytest
from engine.checks.semantic_context import SemanticEnrichmentContext


def test_unavailable_factory_basic():
    ctx = SemanticEnrichmentContext.unavailable(document_id="doc-1")
    assert ctx.enrichment_available is False
    assert ctx.clause_functions == frozenset()
    assert ctx.topic_tags == frozenset()
    assert ctx.document_id == "doc-1"


def test_unavailable_factory_with_segment_info():
    ctx = SemanticEnrichmentContext.unavailable(
        document_id="doc-1",
        segment_id="seg-1",
        segment_type="contract",
        segment_title="Main Agreement",
        is_primary_segment=True,
    )
    assert ctx.enrichment_available is False
    assert ctx.segment_type == "contract"
    assert ctx.segment_title == "Main Agreement"
    assert ctx.is_primary_segment is True


def test_has_clause_function_case_insensitive():
    ctx = SemanticEnrichmentContext(
        document_id="doc-1",
        clause_functions=frozenset({"confidentiality", "assignment"}),
        enrichment_available=True,
    )
    assert ctx.has_clause_function("confidentiality") is True
    assert ctx.has_clause_function("CONFIDENTIALITY") is True
    assert ctx.has_clause_function("  Confidentiality  ") is True
    assert ctx.has_clause_function("governing_law") is False


def test_has_any_clause_function_match():
    ctx = SemanticEnrichmentContext(
        document_id="doc-1",
        clause_functions=frozenset({"confidentiality"}),
        enrichment_available=True,
    )
    assert ctx.has_any_clause_function(["governing_law", "confidentiality"]) is True


def test_has_any_clause_function_no_match():
    ctx = SemanticEnrichmentContext(
        document_id="doc-1",
        clause_functions=frozenset({"confidentiality"}),
        enrichment_available=True,
    )
    assert ctx.has_any_clause_function(["governing_law", "assignment"]) is False


def test_has_any_clause_function_empty_list():
    ctx = SemanticEnrichmentContext(
        document_id="doc-1",
        clause_functions=frozenset({"confidentiality"}),
        enrichment_available=True,
    )
    assert ctx.has_any_clause_function([]) is False


def test_to_prompt_block_full():
    ctx = SemanticEnrichmentContext(
        document_id="doc-1",
        segment_title="Main Contract",
        segment_type="contract",
        is_primary_segment=True,
        clause_functions=frozenset({"confidentiality", "assignment"}),
        enrichment_available=True,
    )
    block = ctx.to_prompt_block()
    assert block is not None
    assert "<document_structure>" in block
    assert "</document_structure>" in block
    assert "contract" in block
    assert "Main Contract" in block
    assert "yes" in block  # is_primary_segment=True


def test_to_prompt_block_without_enrichment_no_segment():
    ctx = SemanticEnrichmentContext.unavailable(document_id="doc-1")
    block = ctx.to_prompt_block()
    assert block is None


def test_to_prompt_block_without_enrichment_but_with_segment():
    ctx = SemanticEnrichmentContext.unavailable(
        document_id="doc-1",
        segment_type="appendix",
        segment_title="Appendix 1",
    )
    block = ctx.to_prompt_block()
    # Even without enrichment, segment info is shown
    assert block is not None
    assert "appendix" in block


def test_frozen_immutable():
    ctx = SemanticEnrichmentContext(document_id="doc-1", enrichment_available=False)
    with pytest.raises(Exception):
        ctx.document_id = "other"  # type: ignore


def test_default_clause_functions_empty():
    ctx = SemanticEnrichmentContext(document_id="doc-1")
    assert ctx.clause_functions == frozenset()
    assert ctx.topic_tags == frozenset()
    assert ctx.enrichment_available is False



    