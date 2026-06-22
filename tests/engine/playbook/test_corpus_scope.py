"""
Tests for RetrievalCorpusScope enum and RetrievalConfig.corpus_scope field.
"""

from __future__ import annotations

import pytest

from engine.playbook.models import (
    RetrievalConfig,
    RetrievalCorpusScope,
)


class TestRetrievalCorpusScopeEnum:
    def test_enum_values_exist(self):
        assert RetrievalCorpusScope.PRIMARY_SEGMENT == "primary_segment"
        assert RetrievalCorpusScope.CURRENT_SEGMENT == "current_segment"
        assert RetrievalCorpusScope.DOCUMENT == "document"

    def test_enum_is_str(self):
        assert isinstance(RetrievalCorpusScope.PRIMARY_SEGMENT, str)
        assert isinstance(RetrievalCorpusScope.DOCUMENT, str)

    def test_enum_from_string(self):
        assert RetrievalCorpusScope("primary_segment") == RetrievalCorpusScope.PRIMARY_SEGMENT
        assert RetrievalCorpusScope("document") == RetrievalCorpusScope.DOCUMENT
        assert RetrievalCorpusScope("current_segment") == RetrievalCorpusScope.CURRENT_SEGMENT

    def test_enum_invalid_value_raises(self):
        with pytest.raises(ValueError):
            RetrievalCorpusScope("invalid_scope")


class TestRetrievalConfigCorpusScope:
    def test_default_is_primary_segment(self):
        cfg = RetrievalConfig()
        assert cfg.corpus_scope == RetrievalCorpusScope.PRIMARY_SEGMENT

    def test_explicit_document_scope(self):
        cfg = RetrievalConfig(corpus_scope=RetrievalCorpusScope.DOCUMENT)
        assert cfg.corpus_scope == RetrievalCorpusScope.DOCUMENT

    def test_explicit_current_segment_scope(self):
        cfg = RetrievalConfig(corpus_scope=RetrievalCorpusScope.CURRENT_SEGMENT)
        assert cfg.corpus_scope == RetrievalCorpusScope.CURRENT_SEGMENT

    def test_corpus_scope_from_string(self):
        cfg = RetrievalConfig(corpus_scope="document")
        assert cfg.corpus_scope == RetrievalCorpusScope.DOCUMENT

    def test_corpus_scope_does_not_affect_other_fields(self):
        cfg = RetrievalConfig(
            corpus_scope=RetrievalCorpusScope.DOCUMENT,
            context_k=7,
            rerank=False,
        )
        assert cfg.context_k == 7
        assert cfg.rerank is False
        assert cfg.corpus_scope == RetrievalCorpusScope.DOCUMENT

    def test_retrieval_config_serialization(self):
        cfg = RetrievalConfig(corpus_scope=RetrievalCorpusScope.DOCUMENT)
        dumped = cfg.model_dump()
        assert dumped["corpus_scope"] == "document"


        