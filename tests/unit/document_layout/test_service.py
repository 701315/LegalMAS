"""Unit tests для Document Layout Service (Phase 7 / v3)."""

from unittest.mock import MagicMock
import pytest
from services.document_layout.schemas import (
    CanonicalAtom,
    CanonicalAtomSource,
    CanonicalPage,
    PageRegion,
    PageRegionType,
    StructuralNodeCandidate,
)
from services.document_layout.service import DocumentLayoutService, QualityGateError


class TestDocumentLayoutServiceOrchestration:
    def test_successful_flow_generates_both_refs(self):
        mock_extractor = MagicMock()
        mock_enricher = MagicMock()
        mock_segmenter = MagicMock()
        mock_reconstructor = MagicMock()
        mock_classifier = MagicMock()
        mock_node_builder = MagicMock()
        mock_aligner = MagicMock()
        mock_store = MagicMock()

        atom = CanonicalAtom(
            element_id="atom:000001",
            page=1,
            bbox=(50.0, 30.0, 250.0, 50.0),
            source_reading_order=1,
            layout_order=1,
            text="Пункт договора на русском",
            label="paragraph",
            language="ru",
            source=CanonicalAtomSource(docling_collection="texts"),
        )
        
        page = CanonicalPage(
            page_number=1,
            width=600.0,
            height=800.0,
            atoms=[atom],
        )

        region = PageRegion(
            region_id="page_1_col_0",
            region_type=PageRegionType.COLUMN,
            page=1,
            bbox=(50.0, 30.0, 250.0, 50.0),
            atom_ids=["atom:000001"],
        )

        node = StructuralNodeCandidate(
            node_id="node:1:0001",
            marker=None,
            bbox=(50.0, 30.0, 250.0, 50.0),
            page=1,
            region_id="page_1_col_0",
            hierarchy_path=[],
            source_atom_ids=["atom:000001"],
            language="ru",
            text="Пункт договора на русском",
        )

        mock_extractor.extract.return_value = ([atom], [], [page], "abc123sha")
        mock_enricher.enrich.return_value = [atom]
        mock_segmenter.segment_page.return_value = [region]
        mock_reconstructor.reconstruct_page_reading_order.return_value = [atom]

        classified_atom = atom.model_copy(update={"language": "ru"})
        mock_classifier.classify_atoms.return_value = [classified_atom]
        mock_node_builder.build_page_nodes.return_value = [node]

        mock_align_res = MagicMock()
        mock_align_res.aligned_opposite_node_ids = set()
        mock_aligner.align_nodes.return_value = mock_align_res

        mock_store.put_json.side_effect = [
            "s3://bucket/canonical.json",
            "s3://bucket/primary.json",
        ]

        service = DocumentLayoutService(
            extractor=mock_extractor,
            enricher=mock_enricher,
            region_segmenter=mock_segmenter,
            reading_reconstructor=mock_reconstructor,
            classifier=mock_classifier,
            node_builder=mock_node_builder,
            aligner=mock_aligner,
            store=mock_store,
        )

        res = service.prepare_document_layout(
            pdf_bytes=b"%PDF-test",
            target_language="ru",
            document_id="00000000-0000-0000-0000-000000000001",
            document_version_id="00000000-0000-0000-0000-000000000002",
            run_id="00000000-0000-0000-0000-000000000003",
            tenant_id="00000000-0000-0000-0000-000000000004",
            deal_id="00000000-0000-0000-0000-000000000005",
        )

        assert res.canonical_layout_ref == "s3://bucket/canonical.json"
        assert res.layout_primary_ref == "s3://bucket/primary.json"
        assert res.detected_languages == ["ru"]
        assert res.source_pdf_sha256 == "abc123sha"

    def test_gate1_fail_raises_quality_gate_error(self):
        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = ([], [], [], "empty_sha")

        service = DocumentLayoutService(extractor=mock_extractor)

        with pytest.raises(QualityGateError) as exc_info:
            service.prepare_document_layout(
                pdf_bytes=b"%PDF-test",
                target_language="ru",
                document_id="00000000-0000-0000-0000-000000000001",
                document_version_id="00000000-0000-0000-0000-000000000002",
                run_id="00000000-0000-0000-0000-000000000003",
                tenant_id="00000000-0000-0000-0000-000000000004",
                deal_id="00000000-0000-0000-0000-000000000005",
            )

        assert exc_info.value.reason_code == "CANONICAL_EXTRACTION_EMPTY"
