"""Unit tests для Quality Gates (Phase 6)."""

import pytest
from services.document_layout.monolingual_projector import ProjectionResult
from services.document_layout.quality import (
    validate_canonical_layout,
    validate_compatibility,
    validate_projection,
)
from services.document_layout.schemas import (
    CanonicalAtom,
    CanonicalAtomSource,
    CanonicalLayout,
    CanonicalPage,
    ProjectedElement,
)


def _make_canonical_layout(atoms: list[CanonicalAtom]) -> CanonicalLayout:
    return CanonicalLayout(
        document_id="00000000-0000-0000-0000-000000000001",
        document_version_id="00000000-0000-0000-0000-000000000002",
        source_pdf_sha256="abc123sha",
        page_count=1,
        detected_languages=["ru"],
        pages=[
            CanonicalPage(page_number=1, width=600.0, height=800.0, atoms=atoms)
        ],
    )


class TestCanonicalQualityGate:
    def test_empty_atoms_quarantines(self):
        canonical = _make_canonical_layout([])
        res = validate_canonical_layout(canonical)
        assert res.passed is False
        assert res.quarantine is True
        assert res.reason_code == "CANONICAL_EXTRACTION_EMPTY"

    def test_duplicate_element_id_quarantines(self):
        atom1 = CanonicalAtom(
            element_id="atom:001",
            page=1,
            source_reading_order=1,
            layout_order=1,
            text="Текст 1",
            label="paragraph",
            source=CanonicalAtomSource(docling_collection="texts"),
        )
        atom2 = CanonicalAtom(
            element_id="atom:001",  # Дубликат
            page=1,
            source_reading_order=2,
            layout_order=2,
            text="Текст 2",
            label="paragraph",
            source=CanonicalAtomSource(docling_collection="texts"),
        )
        canonical = _make_canonical_layout([atom1, atom2])
        res = validate_canonical_layout(canonical)
        assert res.passed is False
        assert res.reason_code == "DUPLICATE_CANONICAL_ELEMENT_ID"


class TestProjectionQualityGate:
    def test_opposite_language_leakage_quarantines(self):
        el_leaked = ProjectedElement(
            element_id="ru:atom:002",
            source_element_ids=["atom:002"],
            text="English leaked text",
            page=1,
            reading_order=2,
            type="text",
            label="paragraph",
            language="en",  # Утечка! Не target ('ru') и не shared/mixed
            projection_method="native_language_atom",
        )
        proj = ProjectionResult(
            elements=[el_leaked],
            source_atom_count=10,
            projected_atom_count=1,
        )
        canonical = _make_canonical_layout([])
        res = validate_projection(canonical, proj, target_language="ru")
        assert res.passed is False
        assert res.reason_code == "OPPOSITE_LANGUAGE_LEAKAGE"

    def test_target_language_ratio_too_low(self):
        el_ru = ProjectedElement(
            element_id="ru:atom:001",
            source_element_ids=["atom:001"],
            text="Да",
            page=1,
            reading_order=1,
            type="text",
            label="paragraph",
            language="ru",
            projection_method="native_language_atom",
        )
        proj = ProjectionResult(
            elements=[el_ru],
            source_atom_count=100,  # Огромный документ, доля целевого языка < 5%
            projected_atom_count=1,
        )
        canonical = _make_canonical_layout([])
        res = validate_projection(canonical, proj, target_language="ru")
        assert res.passed is False
        assert res.reason_code == "TARGET_LANGUAGE_RATIO_TOO_LOW"


class TestCompatibilityQualityGate:
    def test_valid_compatibility_payload_passes(self):
        payload = {
            "schema_version": "layout_primary_compat_v1",
            "document_id": "00000000-0000-0000-0000-000000000001",
            "document_version_id": "00000000-0000-0000-0000-000000000002",
            "run_id": "00000000-0000-0000-0000-000000000003",
            "language": "ru",
            "source_canonical_layout_ref": "s3://bucket/canonical.json",
            "metadata": {},
            "elements": [
                {
                    "element_id": "ru:atom:001",
                    "source_element_ids": ["atom:001"],
                    "text": "Текст",
                    "page": 1,
                    "reading_order": 1,
                    "reading_order_source": "docling_texts",
                    "type": "text",
                    "label": "paragraph",
                    "language": "ru",
                    "projection_method": "native_language_atom",
                }
            ],
        }
        res = validate_compatibility(payload)
        assert res.passed is True
