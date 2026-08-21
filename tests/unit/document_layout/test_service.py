"""Unit tests для Document Layout Service (Phase 7)."""

from unittest.mock import MagicMock
import pytest
from services.document_layout.schemas import CanonicalAtom, CanonicalAtomSource, CanonicalPage
from services.document_layout.service import DocumentLayoutService, QualityGateError


class TestDocumentLayoutServiceOrchestration:
    def test_successful_flow_generates_both_refs(self):
        # 1. Сборка моков
        mock_extractor = MagicMock()
        mock_enricher = MagicMock()
        mock_classifier = MagicMock()
        mock_store = MagicMock()

        # Мокаем экстрактор
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
        
        # Передаем реальный объект CanonicalPage вместо MagicMock
        page = CanonicalPage(
            page_number=1,
            width=600.0,
            height=800.0,
            atoms=[atom],
        )

        mock_extractor.extract.return_value = ([atom], [], [page], "abc123sha")

        # Мокаем enricher
        mock_enricher.enrich.return_value = [atom]

        # Мокаем classifier
        classified_atom = atom.model_copy(update={"language": "ru"})
        mock_classifier.classify_atoms.return_value = [classified_atom]

        # Мокаем store
        mock_store.put_json.side_effect = [
            "s3://bucket/canonical.json",  # первый вызов - canonical
            "s3://bucket/primary.json",    # второй вызов - primary
        ]

        # 2. Инициализируем сервис
        service = DocumentLayoutService(
            extractor=mock_extractor,
            enricher=mock_enricher,
            classifier=mock_classifier,
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

        # 3. Проверки
        assert res.canonical_layout_ref == "s3://bucket/canonical.json"
        assert res.layout_primary_ref == "s3://bucket/primary.json"
        assert res.detected_languages == ["ru"]
        assert res.source_pdf_sha256 == "abc123sha"
        assert res.total_atoms == 1

        assert mock_store.put_json.call_count == 2

    def test_gate1_fail_raises_quality_gate_error(self):
        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = ([], [], [], "empty_sha")  # 0 атомов -> Gate 1 упадет

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
