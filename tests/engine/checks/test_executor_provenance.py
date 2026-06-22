from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from engine.checks.executor import CheckExecutor
from engine.playbook.models import (
    CheckDefinition,
    DetectorType,
    EvidenceConfig,
    ExtractionConfig,
    ExtractionFieldConfig,
    ExtractionMode,
    ExtractionFieldType,
    LLMConfig,
    RetrievalConfig,
    RetrievalCorpusScope,
    RulesConfig,
)


def _build_check() -> CheckDefinition:
    return CheckDefinition(
        id="real_estate_asset_schedule_cluster",
        name="Перечень объектов сделки",
        description="Inventory extraction check",
        doc_types=["contract_1.6_real_estate"],
        origin="DOCUMENT_TYPE",
        severity="high",
        detector_type=DetectorType.HYBRID,
        rules=RulesConfig(),
        llm=LLMConfig(),
        evidence=EvidenceConfig(required=False),
        retrieval=RetrievalConfig(
            corpus_scope=RetrievalCorpusScope.DOCUMENT,
            levels=["section"],
            context_k=5,
            max_chunks=5,
            rerank=True,
        ),
        extraction=ExtractionConfig(
            enabled=True,
            mode=ExtractionMode.HYBRID,
            fields=[
                ExtractionFieldConfig(
                    name="asset_schedule_details",
                    type=ExtractionFieldType.STRING,
                    label="Перечень объектов сделки",
                    presentation="fact",
                    description="Полный перечень объектов сделки",
                )
            ],
            store_payload=True,
            llm_prompt_extraction=(
                "<role>Extract inventory</role>\n"
                "<context>\n{context}\n</context>\n"
                "<task>Return JSON</task>"
            ),
        ),
    )


def test_execute_preserves_segment_metadata_in_context_trace_and_provenance():
    doc = MagicMock()
    doc.id = uuid.uuid4()
    doc.doc_type = "contract_1.6_real_estate"
    doc.classification_confidence = 0.95

    check = _build_check()

    chunks = [
        {
            "id": "dummy-chunk",
            "text": "dummy",
            "metadata": {},
        }
    ]

    retrieval_contexts = [
        {
            "id": "chunk-appendix-10",
            "text": (
                "10 Наименование объекта: нежилое здание "
                "10.1 Кадастровый номер: 78:36:0005503:3012 "
                "10.2 Площадь объекта: 4 144,6 кв.м. "
                "10.5 Адрес объекта: г. Санкт-Петербург, ADDRESS1"
            ),
            "metadata": {
                "effective_uid": "appendix_a:10",
                "clause_uid": "appendix_a:10",
                "page": 12,
                "start_page": 12,
                "end_page": 12,
                "path_titles": ["Приложение", "Недвижимое имущество"],
                "element_ids": ["e1", "e2"],
                "chunk_id": "chunk-appendix-10",
                "chunk_index": 0,
                "segment_id": "seg-appendix-1",
                "segment_type": "appendix",
                "segment_title": "Приложение №4",
                "segment_order": 1,
                "is_primary_segment": False,
                "score_breakdown": {"combined_score": 0.91},
            },
            "score": 0.91,
            "score_breakdown": {"combined_score": 0.91},
        }
    ]

    executor = CheckExecutor(llm_client=None)
    executor.extractor.run = MagicMock(
        return_value={
            "asset_schedule_details": {
                "value": "Нежилое здание | 78:36:0005503:3012 | 4 144,6 кв.м. | г. Санкт-Петербург, ADDRESS1",
                "confidence": 0.95,
            }
        }
    )

    with patch("engine.checks.executor.RetrievalEngine") as mock_retrieval_cls:
        mock_retriever = MagicMock()
        mock_retriever.search.return_value = retrieval_contexts
        mock_retrieval_cls.return_value = mock_retriever

        result = executor.execute(doc=doc, check=check, chunks=chunks)

    assert result["result"] == "pass"

    # Provenance should come from retrieval context metadata, not be lost.
    assert result["segment_id"] == "seg-appendix-1"
    assert result["segment_type"] == "appendix"
    assert result["segment_title"] == "Приложение №4"
    assert result["is_primary_segment"] is False

    # Context trace must preserve segment-aware metadata too.
    assert result["context_trace"]
    first_trace = result["context_trace"][0]
    assert first_trace["segment_id"] == "seg-appendix-1"
    assert first_trace["segment_type"] == "appendix"
    assert first_trace["clause_uid"] == "appendix_a:10"
    assert first_trace["chunk_id"] == "chunk-appendix-10"


    