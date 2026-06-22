"""
Tests for DocTypeCheckLoader._parse_retrieval_config corpus_scope parsing.
"""

from __future__ import annotations

import pytest

from engine.doc_type_checks.loader import DocTypeCheckLoader
from engine.playbook.models import RetrievalCorpusScope


@pytest.fixture()
def loader() -> DocTypeCheckLoader:
    return DocTypeCheckLoader.__new__(DocTypeCheckLoader)


class TestParseRetrievalConfigCorpusScope:
    def test_default_when_not_specified(self, loader):
        result = loader._parse_retrieval_config({})
        assert result.corpus_scope == RetrievalCorpusScope.PRIMARY_SEGMENT

    def test_document_scope_parsed(self, loader):
        result = loader._parse_retrieval_config({"corpus_scope": "document"})
        assert result.corpus_scope == RetrievalCorpusScope.DOCUMENT

    def test_primary_segment_scope_parsed(self, loader):
        result = loader._parse_retrieval_config({"corpus_scope": "primary_segment"})
        assert result.corpus_scope == RetrievalCorpusScope.PRIMARY_SEGMENT

    def test_current_segment_scope_parsed(self, loader):
        result = loader._parse_retrieval_config({"corpus_scope": "current_segment"})
        assert result.corpus_scope == RetrievalCorpusScope.CURRENT_SEGMENT

    def test_invalid_scope_falls_back_to_primary(self, loader):
        result = loader._parse_retrieval_config({"corpus_scope": "unknown_value"})
        assert result.corpus_scope == RetrievalCorpusScope.PRIMARY_SEGMENT

    def test_none_retrieval_raw_returns_defaults(self, loader):
        result = loader._parse_retrieval_config(None)
        assert result.corpus_scope == RetrievalCorpusScope.PRIMARY_SEGMENT

    def test_corpus_scope_combined_with_other_fields(self, loader):
        result = loader._parse_retrieval_config({
            "corpus_scope": "document",
            "context_k": 8,
            "rerank": False,
            "levels": ["legal_unit"],
        })
        assert result.corpus_scope == RetrievalCorpusScope.DOCUMENT
        assert result.context_k == 8
        assert result.rerank is False
        assert result.levels == ["legal_unit"]


        